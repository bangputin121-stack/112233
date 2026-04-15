# handlers/main_handlers.py - Core handlers for Greena Farm

import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database.db import get_or_create_user, get_setting, fetchone, fetchall, get_display_name, set_display_name, get_leaderboard, set_avatar, get_avatar
from game.engine import (
    get_plots, get_animal_pens, get_user_buildings, get_orders,
    plant_crop, harvest_crop, harvest_all,
    buy_animal, collect_animal, collect_all_animals,
    buy_building, start_production, collect_production,
    ensure_orders, fulfill_order, refresh_orders,
    get_market_listings, buy_from_market, list_item_on_market, remove_market_listing,
    get_obstacles, clear_obstacle,
    upgrade_silo, upgrade_barn, expand_farm, expand_animal_pens,
    sell_item, claim_daily, get_user_full, get_item_count,
    buy_tool, spray_pesticide, use_fertilizer
)
from utils.keyboards import (
    main_menu_keyboard, farm_keyboard, plant_keyboard, animals_keyboard,
    buy_animal_keyboard, factories_keyboard, factory_detail_keyboard,
    storage_keyboard, storage_items_keyboard, sell_keyboard,
    orders_keyboard, market_keyboard, land_keyboard, back_to_menu,
    profile_keyboard, leaderboard_keyboard, shop_keyboard, items_keyboard
)
from utils.formatters import (
    fmt_farm, fmt_animals, fmt_storage, fmt_factories,
    fmt_orders, fmt_market, fmt_profile, fmt_help, fmt_leaderboard,
    fmt_tutorial, fmt_all_items
)
from database.db import parse_json_field

logger = logging.getLogger(__name__)

# Safe edit/send helpers — anti-spam, ALWAYS edit, never spam reply
async def safe_edit(query, text: str, keyboard=None, parse_mode=ParseMode.MARKDOWN):
    """Edit pesan dari callback. Pinter handle media vs text:
    - Pesan teks → edit_message_text
    - Pesan punya media + text ≤ 1024 → edit_message_caption
    - Pesan punya media + text > 1024 → delete media + send new text (transisi)
    JANGAN pernah spam reply_text — kalau gagal, tuliskan log doang.
    """
    msg = query.message if hasattr(query, "message") else None
    has_media = bool(msg and (msg.photo or msg.animation or msg.video or msg.document))

    # Telegram caption max = 1024, text msg max = 4096
    CAPTION_MAX = 1020

    # Kalau pesan punya media TAPI text baru kepanjangan buat caption,
    # delete pesan media + kirim text baru. Setelah ini pesan jadi text.
    if has_media and len(text) > CAPTION_MAX:
        try:
            bot = msg.get_bot()
            chat_id = msg.chat_id
            try:
                await msg.delete()
            except Exception:
                pass
            await bot.send_message(
                chat_id=chat_id, text=text, reply_markup=keyboard,
                parse_mode=parse_mode, disable_web_page_preview=True
            )
            return
        except Exception as e:
            logger.error(f"safe_edit media-to-text conversion failed: {e}")
            # Jangan throw, coba fallback edit_caption dengan text ke-potong
            try:
                truncated = text[:CAPTION_MAX - 30] + "\n\n_(terlalu panjang)_"
                await query.edit_message_caption(
                    caption=truncated, reply_markup=keyboard, parse_mode=parse_mode
                )
            except Exception:
                pass
            return

    try:
        if has_media:
            # Pesan punya media, text muat di caption (≤ 1020)
            await query.edit_message_caption(
                caption=text, reply_markup=keyboard, parse_mode=parse_mode
            )
        else:
            # Pesan teks biasa
            await query.edit_message_text(
                text, reply_markup=keyboard, parse_mode=parse_mode,
                disable_web_page_preview=True
            )
        return
    except Exception as e:
        err_str = str(e).lower()
        # Telegram lemparan "Message is not modified" itu normal — abaikan
        if "not modified" in err_str:
            return
        # Kalau error caption too long (rare setelah guard di atas), coba truncate
        if "caption is too long" in err_str and has_media:
            try:
                truncated = text[:CAPTION_MAX - 30] + "\n\n_(dipotong)_"
                await query.edit_message_caption(
                    caption=truncated, reply_markup=keyboard, parse_mode=parse_mode
                )
                return
            except Exception:
                pass
        logger.error(f"safe_edit failed: {e}")

async def safe_send(update: Update, text: str, keyboard=None):
    try:
        await update.message.reply_text(
            text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"safe_send failed: {e}")

async def get_item_photo(item_key: str):
    """Get media (GIF priority, then photo) for an item.
    Returns dict {kind, file_id} or None."""
    gif_id = await get_setting(f"gif_{item_key}")
    if gif_id:
        return {"kind": "animation", "file_id": gif_id}
    photo_id = await get_setting(f"photo_{item_key}")
    if photo_id:
        return {"kind": "photo", "file_id": photo_id}
    return None

async def safe_send_photo(target, text: str, keyboard=None, photo_id=None):
    """Send/edit photo or animation with caption. Anti-spam.

    Strategi:
    - Pesan asal udah ada media → edit_media (replace foto in-place, no new msg)
    - Pesan asal teks → delete + send media (sekali aja, transition text→media)
    - Caption max 1024 chars (Telegram limit) — kalau lebih, truncate atau split.

    photo_id bisa string (legacy = photo) atau dict {kind, file_id} (support GIF).
    """
    if not photo_id:
        # No media, edit teks aja
        await safe_edit(target, text, keyboard)
        return

    # Normalize media format
    if isinstance(photo_id, str):
        media = {"kind": "photo", "file_id": photo_id}
    else:
        media = photo_id
    kind = media["kind"]
    file_id = media["file_id"]

    msg_obj = target.message if hasattr(target, "message") else None
    if not msg_obj:
        return

    # === HANDLE CAPTION LIMIT ===
    # Telegram caption max = 1024 chars (beda dari text msg = 4096)
    # Kalau text kepanjangan, truncate caption + kirim sisanya sebagai text msg
    CAPTION_MAX = 1020  # buffer 4 chars
    overflow_text = None
    caption = text
    if len(text) > CAPTION_MAX:
        # Cari titik potong yang bagus (newline atau spasi)
        cut = text.rfind("\n", 0, CAPTION_MAX)
        if cut < CAPTION_MAX // 2:  # kalau nggak nemu newline yang bagus
            cut = text.rfind(" ", 0, CAPTION_MAX)
        if cut < CAPTION_MAX // 2:
            cut = CAPTION_MAX
        caption = text[:cut].rstrip() + "\n\n_(lanjut di bawah ⬇️)_"
        overflow_text = text[cut:].strip()

    from telegram import InputMediaPhoto, InputMediaAnimation
    has_media = bool(msg_obj.photo or msg_obj.animation or msg_obj.video)
    bot = msg_obj.get_bot()
    chat_id = msg_obj.chat_id

    # Case 1: Pesan asal udah ada media → edit_media (NO SPAM)
    if has_media:
        try:
            if kind == "animation":
                new_media = InputMediaAnimation(
                    media=file_id, caption=caption, parse_mode=ParseMode.MARKDOWN
                )
            else:
                new_media = InputMediaPhoto(
                    media=file_id, caption=caption, parse_mode=ParseMode.MARKDOWN
                )
            await msg_obj.edit_media(media=new_media, reply_markup=keyboard)
            # Kirim overflow kalau ada
            if overflow_text:
                try:
                    await bot.send_message(
                        chat_id=chat_id, text=overflow_text,
                        parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True
                    )
                except Exception:
                    pass
            return
        except Exception as e:
            err_str = str(e).lower()
            if "not modified" in err_str:
                try:
                    await msg_obj.edit_caption(
                        caption=caption, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
                    )
                    if overflow_text:
                        await bot.send_message(
                            chat_id=chat_id, text=overflow_text,
                            parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True
                        )
                except Exception:
                    pass
                return
            logger.error(f"edit_media failed: {e}")
            try:
                await msg_obj.edit_caption(
                    caption=caption, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
                )
                if overflow_text:
                    await bot.send_message(
                        chat_id=chat_id, text=overflow_text,
                        parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True
                    )
            except Exception:
                pass
            return

    # Case 2: Pesan asal teks → delete + send media (sekali, transition)
    try:
        await msg_obj.delete()
    except Exception:
        pass
    try:
        if kind == "animation":
            await bot.send_animation(
                chat_id=chat_id, animation=file_id, caption=caption,
                reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
            )
        else:
            await bot.send_photo(
                chat_id=chat_id, photo=file_id, caption=caption,
                reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
            )
        # Kirim overflow kalau ada
        if overflow_text:
            try:
                await bot.send_message(
                    chat_id=chat_id, text=overflow_text,
                    parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f"send media after delete failed: {e}")
        # Last resort: kirim teks lengkap aja biar player nggak liat chat kosong
        try:
            await bot.send_message(
                chat_id=chat_id, text=text, reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True
            )
        except Exception as e2:
            logger.error(f"final fallback also failed: {e2}")


# ─── START / MENU ─────────────────────────────────────────────────────────────

async def start_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    maintenance = await get_setting("maintenance_mode", "0")
    
    # Check maintenance (skip for admin)
    import os
    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
    if maintenance == "1" and user.id not in admin_ids:
        await update.message.reply_text("🔧 Game sedang maintenance. Coba lagi nanti!")
        return

    db_user = await get_or_create_user(user.id, user.username, user.first_name)

    # Handle deep link: /start buy_<listing_id>
    if ctx.args and ctx.args[0].startswith("buy_"):
        try:
            listing_id = int(ctx.args[0].replace("buy_", ""))
            await handle_deep_link_buy(update, ctx, user, db_user, listing_id)
            return
        except (ValueError, IndexError):
            pass

    name = get_display_name(db_user)
    welcome = await get_setting("welcome_message", "Selamat datang di Greena Farm! 🌾👑")

    text = (
        f"{welcome}\n\n"
        f"👋 Halo, **{name}**!\n"
        f"👑 Level {db_user['level']}  💵 Rp{db_user['coins']:,}\n\n"
        f"Mau ngapain hari ini?"
    )
    await safe_send(update, text, main_menu_keyboard())


async def handle_deep_link_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE, user, db_user, listing_id: int):
    """Handle buy from channel deep link."""
    from database.db import get_db, fetchone
    async with get_db() as db:
        listing = await fetchone(db, "SELECT * FROM market_listings WHERE id = ?", (listing_id,))

    if not listing:
        await safe_send(update, "❌ Listing ini sudah tidak tersedia atau sudah terjual.", back_to_menu())
        return

    listing = dict(listing)
    if listing["seller_id"] == user.id:
        await safe_send(update, "❌ Kamu tidak bisa membeli listing sendiri!", back_to_menu())
        return

    from game.data import get_item_emoji, get_item_name
    emoji = get_item_emoji(listing["item"])
    name = get_item_name(listing["item"])
    total = listing["price"] * listing["qty"]

    text = (
        f"🛒 **Konfirmasi Pembelian**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{emoji} **{name}** x{listing['qty']}\n"
        f"💵 Rp{listing['price']:,}/satuan\n"
        f"💰 Total: **Rp{total:,}**\n"
        f"👤 Penjual: **{listing['seller_name']}**\n\n"
        f"💵 Saldo kamu: Rp{db_user['coins']:,}\n\n"
        f"Mau beli?"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Beli!", callback_data=f"confirm_buy_{listing_id}"),
            InlineKeyboardButton("❌ Batal", callback_data="menu"),
        ]
    ])
    await safe_send(update, text, keyboard)

async def menu_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    name = get_display_name(db_user)

    text = (
        f"🏠 **Menu Utama**\n"
        f"👑 Level {db_user['level']}  💵 Rp{db_user['coins']:,}  💎 {db_user['gems']}\n\n"
        f"Mau ngapain hari ini, **{name}**?"
    )
    await safe_edit(query, text, main_menu_keyboard())


# ─── FARM ─────────────────────────────────────────────────────────────────────

def _get_farm_page(ctx) -> int:
    """Ambil halaman farm yang lagi aktif dari user_data."""
    try:
        return int(ctx.user_data.get("farm_page", 0))
    except Exception:
        return 0


async def farm_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    plots = await get_plots(user.id)
    page = _get_farm_page(ctx)
    text = fmt_farm(db_user, plots, page)
    await safe_edit(query, text, farm_keyboard(plots, db_user["level"], page))


async def farm_page_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handler buat pagination farm: farm_page_<n>"""
    query = update.callback_query
    await query.answer()
    try:
        page = int(query.data.split("_")[2])
    except Exception:
        page = 0
    ctx.user_data["farm_page"] = page
    user = query.from_user
    db_user = await get_user_full(user.id)
    plots = await get_plots(user.id)
    text = fmt_farm(db_user, plots, page)
    await safe_edit(query, text, farm_keyboard(plots, db_user["level"], page))


async def farm_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    plots = await get_plots(user.id)
    page = _get_farm_page(ctx)
    text = fmt_farm(db_user, plots, page)
    await safe_send(update, text, farm_keyboard(plots, db_user["level"], page))

async def plot_plant_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot = int(query.data.split("_")[2])
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    await safe_edit(query, f"🌱 **Pilih tanaman untuk Lahan {slot+1}:**\n\n(Harga yang ditampilkan adalah biaya benih)", plant_keyboard(db_user["level"], slot))

async def plant_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split("_")
    slot = int(parts[1])
    crop_key = "_".join(parts[2:])
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    ok, msg = await plant_crop(user.id, slot, crop_key)
    if ok:
        plots = await get_plots(user.id)
        db_user = await get_user_full(user.id)
        full_text = msg + "\n\n" + fmt_farm(db_user, plots, _get_farm_page(ctx))
        photo_id = await get_item_photo(crop_key)
        if photo_id:
            await safe_send_photo(query, full_text, farm_keyboard(plots, db_user["level"], _get_farm_page(ctx)), photo_id)
        else:
            await safe_edit(query, full_text, farm_keyboard(plots, db_user["level"], _get_farm_page(ctx)))
    else:
        await query.answer(msg, show_alert=True)

async def plot_harvest_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    slot = int(query.data.split("_")[2])
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)
    ok, msg = await harvest_crop(user.id, slot)
    if ok:
        db_user = await get_user_full(user.id)
        plots = await get_plots(user.id)
        await safe_edit(query, msg + "\n\n" + fmt_farm(db_user, plots, _get_farm_page(ctx)), farm_keyboard(plots, db_user["level"], _get_farm_page(ctx)))
    else:
        await query.answer(msg, show_alert=True)

async def harvest_all_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)
    count, failed, _ = await harvest_all(user.id)
    db_user = await get_user_full(user.id)
    plots = await get_plots(user.id)
    if count > 0:
        msg = f"✅ Dipanen {count} tanaman!"
        if failed:
            msg += f" ({failed} gagal, penyimpanan mungkin penuh)"
    else:
        msg = "⏳ Belum ada tanaman yang siap panen."
    await safe_edit(query, msg + "\n\n" + fmt_farm(db_user, plots, _get_farm_page(ctx)), farm_keyboard(plots, db_user["level"], _get_farm_page(ctx)))

async def expand_farm_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    ok, msg = await expand_farm(user.id)
    await query.answer(msg, show_alert=True)
    if ok:
        db_user = await get_user_full(user.id)
        plots = await get_plots(user.id)
        await safe_edit(query, fmt_farm(db_user, plots, _get_farm_page(ctx)), farm_keyboard(plots, db_user["level"], _get_farm_page(ctx)))


# ─── PEST & FERTILIZER ──────────────────────────────────────────────────────

async def plot_spray_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    slot = int(query.data.split("_")[2])
    user = query.from_user
    ok, msg = await spray_pesticide(user.id, slot)
    if ok:
        db_user = await get_user_full(user.id)
        plots = await get_plots(user.id)
        await safe_edit(query, msg + "\n\n" + fmt_farm(db_user, plots, _get_farm_page(ctx)), farm_keyboard(plots, db_user["level"], _get_farm_page(ctx)))
    else:
        await query.answer(msg, show_alert=True)

async def spray_all_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    plots = await get_plots(user.id)
    sprayed = 0
    for p in plots:
        if p["status"] == "infected":
            ok, _ = await spray_pesticide(user.id, p["slot"])
            if ok:
                sprayed += 1
    db_user = await get_user_full(user.id)
    plots = await get_plots(user.id)
    if sprayed > 0:
        msg = f"✅ 🧴 Disemprot {sprayed} tanaman!"
    else:
        msg = "❌ Tidak ada tanaman yang kena hama, atau pestisida habis."
    await safe_edit(query, msg + "\n\n" + fmt_farm(db_user, plots, _get_farm_page(ctx)), farm_keyboard(plots, db_user["level"], _get_farm_page(ctx)))

async def fertilize_menu_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    from game.engine import get_item_count
    fert_count = await get_item_count(user.id, "fertilizer")
    super_count = await get_item_count(user.id, "super_fertilizer")

    plots = await get_plots(user.id)
    growing = [p for p in plots if p["status"] == "growing"]

    if not growing:
        await query.answer("❌ Tidak ada tanaman yang sedang tumbuh.", show_alert=True)
        return

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for p in growing:
        from datetime import datetime, timezone
        ready_at = datetime.fromisoformat(p["ready_at"])
        if ready_at.tzinfo is None:
            ready_at = ready_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if now >= ready_at:
            continue  # already ready
        from game.data import CROPS
        crop = CROPS.get(p["crop"], {})
        from game.engine import fmt_time
        remaining = int((ready_at - now).total_seconds())
        buttons.append([
            InlineKeyboardButton(
                f"🧪 {crop.get('emoji','🌱')} Lahan {p['slot']+1} ({fmt_time(remaining)})",
                callback_data=f"fert_{p['slot']}_fertilizer"
            ),
            InlineKeyboardButton(
                f"⚗️ Super",
                callback_data=f"fert_{p['slot']}_super_fertilizer"
            ),
        ])

    if not buttons:
        await query.answer("✅ Semua tanaman sudah siap panen!", show_alert=True)
        return

    text = (
        f"🧪 **Pilih Tanaman untuk Dipupuk**\n\n"
        f"🧪 Pupuk Biasa (30% cepat): {fert_count} punya\n"
        f"⚗️ Pupuk Super (50% cepat): {super_count} punya\n\n"
        f"Ketuk tanaman di bawah:"
    )
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="farm")])
    await safe_edit(query, text, InlineKeyboardMarkup(buttons))

async def fertilize_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split("_")
    slot = int(parts[1])
    fert_type = "_".join(parts[2:])
    user = query.from_user
    ok, msg = await use_fertilizer(user.id, slot, fert_type)
    if ok:
        db_user = await get_user_full(user.id)
        plots = await get_plots(user.id)
        await safe_edit(query, msg + "\n\n" + fmt_farm(db_user, plots, _get_farm_page(ctx)), farm_keyboard(plots, db_user["level"], _get_farm_page(ctx)))
    else:
        await query.answer(msg, show_alert=True)


# ─── ANIMALS ──────────────────────────────────────────────────────────────────

def _get_pens_page(ctx) -> int:
    """Ambil halaman kandang yang lagi aktif dari user_data."""
    try:
        return int(ctx.user_data.get("pens_page", 0))
    except Exception:
        return 0


async def animals_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    pens = await get_animal_pens(user.id)
    page = _get_pens_page(ctx)
    text = fmt_animals(db_user, pens, page)
    await safe_edit(query, text, animals_keyboard(pens, db_user["level"], page))


async def pens_page_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Pagination kandang: pens_page_<n>"""
    query = update.callback_query
    await query.answer()
    try:
        page = int(query.data.split("_")[2])
    except Exception:
        page = 0
    ctx.user_data["pens_page"] = page
    user = query.from_user
    db_user = await get_user_full(user.id)
    pens = await get_animal_pens(user.id)
    text = fmt_animals(db_user, pens, page)
    await safe_edit(query, text, animals_keyboard(pens, db_user["level"], page))

async def pen_buy_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot = int(query.data.split("_")[2])
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    await safe_edit(query, f"🐾 **Pilih hewan untuk Kandang {slot+1}:**", buy_animal_keyboard(db_user["level"], slot))

async def buyanimal_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split("_")
    slot = int(parts[1])
    animal_key = "_".join(parts[2:])
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)
    ok, msg = await buy_animal(user.id, slot, animal_key)
    if ok:
        db_user = await get_user_full(user.id)
        pens = await get_animal_pens(user.id)
        await safe_edit(query, msg + "\n\n" + fmt_animals(db_user, pens, _get_pens_page(ctx)), animals_keyboard(pens, db_user["level"], _get_pens_page(ctx)))
    else:
        await query.answer(msg, show_alert=True)

async def pen_collect_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    slot = int(query.data.split("_")[2])
    user = query.from_user
    ok, msg = await collect_animal(user.id, slot)
    if ok:
        db_user = await get_user_full(user.id)
        pens = await get_animal_pens(user.id)
        await safe_edit(query, msg + "\n\n" + fmt_animals(db_user, pens, _get_pens_page(ctx)), animals_keyboard(pens, db_user["level"], _get_pens_page(ctx)))
    else:
        await query.answer(msg, show_alert=True)


async def pen_detail_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tampilin detail hewan + opsi doping/hapus."""
    query = update.callback_query
    slot = int(query.data.split("_")[2])
    user = query.from_user
    pens = await get_animal_pens(user.id)
    pen = next((p for p in pens if p["slot"] == slot), None)
    if not pen or pen["status"] != "producing":
        await query.answer("❌ Kandang ini kosong.", show_alert=True)
        return
    await query.answer()

    from game.data import ANIMALS
    animal_key = pen["animal"]
    animal = ANIMALS.get(animal_key, {})

    # Hitung sisa waktu
    from datetime import datetime, timezone
    ready_at = datetime.fromisoformat(pen["ready_at"])
    if ready_at.tzinfo is None:
        ready_at = ready_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    remaining = max(0, int((ready_at - now).total_seconds()))

    db_user = await get_user_full(user.id)
    barn = parse_json_field(db_user["barn_items"])
    has_doping = barn.get("animal_doping", 0) > 0

    from game.engine import fmt_time
    text = (
        f"🐾 **Detail Kandang {slot+1}**\n\n"
        f"{animal.get('emoji', '🐾')} **{animal.get('name', 'Hewan')}**\n"
        f"⏰ Sisa waktu: {fmt_time(remaining) if remaining > 0 else '✅ SIAP PANEN'}\n"
        f"📦 Produk: {animal.get('prod_emoji', '')} {animal.get('product', '?').replace('_', ' ').title()}\n"
        f"💵 Harga jual produk: Rp{animal.get('sell_price', 0):,}\n\n"
        f"💊 Doping kamu: {barn.get('animal_doping', 0)}\n\n"
        f"**Aksi yang tersedia:**\n"
        f"• 💊 Doping → kurangin waktu 30%\n"
        f"• 🗑️ Hapus → refund 50% harga beli"
    )
    from utils.keyboards import pen_detail_keyboard
    await safe_edit(query, text, pen_detail_keyboard(slot, animal_key, has_doping))


async def pen_remove_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Hapus hewan dari kandang dengan refund 50%."""
    query = update.callback_query
    slot = int(query.data.split("_")[2])
    user = query.from_user
    from game.engine import remove_animal
    ok, msg = await remove_animal(user.id, slot)
    if ok:
        db_user = await get_user_full(user.id)
        pens = await get_animal_pens(user.id)
        await safe_edit(query, msg + "\n\n" + fmt_animals(db_user, pens, _get_pens_page(ctx)), animals_keyboard(pens, db_user["level"], _get_pens_page(ctx)))
    else:
        await query.answer(msg, show_alert=True)


async def pen_dope_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Pake doping ke hewan."""
    query = update.callback_query
    slot = int(query.data.split("_")[2])
    user = query.from_user
    from game.engine import apply_animal_doping
    ok, msg = await apply_animal_doping(user.id, slot)
    if ok:
        # Refresh detail page biar player liat efek doping
        db_user = await get_user_full(user.id)
        pens = await get_animal_pens(user.id)
        pen = next((p for p in pens if p["slot"] == slot), None)
        if pen and pen["status"] == "producing":
            from game.data import ANIMALS
            from datetime import datetime, timezone
            from game.engine import fmt_time
            from utils.keyboards import pen_detail_keyboard
            animal = ANIMALS.get(pen["animal"], {})
            ready_at = datetime.fromisoformat(pen["ready_at"])
            if ready_at.tzinfo is None:
                ready_at = ready_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            remaining = max(0, int((ready_at - now).total_seconds()))
            barn = parse_json_field(db_user["barn_items"])
            has_doping = barn.get("animal_doping", 0) > 0
            text = (
                f"🐾 **Detail Kandang {slot+1}**\n\n"
                f"{msg}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{animal.get('emoji', '🐾')} **{animal.get('name', 'Hewan')}**\n"
                f"⏰ Sisa waktu: {fmt_time(remaining) if remaining > 0 else '✅ SIAP PANEN'}\n"
                f"💊 Doping kamu: {barn.get('animal_doping', 0)}"
            )
            await safe_edit(query, text, pen_detail_keyboard(slot, pen["animal"], has_doping))
        else:
            await query.answer(msg, show_alert=True)
    else:
        await query.answer(msg, show_alert=True)

async def expand_pens_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    ok, msg = await expand_animal_pens(user.id)
    await query.answer(msg, show_alert=True)
    if ok:
        db_user = await get_user_full(user.id)
        pens = await get_animal_pens(user.id)
        await safe_edit(query, fmt_animals(db_user, pens, _get_pens_page(ctx)), animals_keyboard(pens, db_user["level"], _get_pens_page(ctx)))

async def collect_all_animals_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)
    collected, failed, _ = await collect_all_animals(user.id)
    db_user = await get_user_full(user.id)
    pens = await get_animal_pens(user.id)
    if collected > 0:
        msg = f"✅ Diambil {collected} produk hewan!"
        if failed:
            msg += f" ({failed} gagal, gudang mungkin penuh)"
    else:
        msg = "⏳ Belum ada produk hewan yang siap diambil."
    await safe_edit(query, msg + "\n\n" + fmt_animals(db_user, pens, _get_pens_page(ctx)), animals_keyboard(pens, db_user["level"], _get_pens_page(ctx)))


# ─── FACTORIES ────────────────────────────────────────────────────────────────

async def factories_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    buildings = await get_user_buildings(user.id)
    text = fmt_factories(db_user, buildings)
    await safe_edit(query, text, factories_keyboard(buildings, db_user["level"]))

async def buy_building_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    building_key = "_".join(query.data.split("_")[2:])
    user = query.from_user
    ok, msg = await buy_building(user.id, building_key)
    if ok:
        db_user = await get_user_full(user.id)
        buildings = await get_user_buildings(user.id)
        await safe_edit(query, msg + "\n\n" + fmt_factories(db_user, buildings), factories_keyboard(buildings, db_user["level"]))
    else:
        await query.answer(msg, show_alert=True)

async def factory_detail_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    building_key = "_".join(query.data.split("_")[1:])
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    buildings = await get_user_buildings(user.id)
    slots = [b for b in buildings if b["building"] == building_key]

    from game.data import BUILDINGS
    from game.engine import get_building_level
    bld = BUILDINGS.get(building_key, {})
    bld_level = await get_building_level(user.id, building_key)
    reduction = (bld_level - 1) * 15
    level_info = ""
    if bld_level > 1:
        level_info = f"\n📈 Level: **{bld_level}** (-{reduction}% waktu produksi)"
    else:
        level_info = "\n📈 Level: **1** (belum di-upgrade)"

    text = (
        f"{bld.get('emoji','🏭')} **{bld.get('name','Factory')}**"
        f"{level_info}\n\n"
        f"Pilih resep untuk diproduksi:"
    )
    await safe_edit(query, text, factory_detail_keyboard(building_key, slots))


async def upgrade_building_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show upgrade confirmation with cost breakdown. Format: upgrade_bld_<building_key>"""
    query = update.callback_query
    payload = query.data[len("upgrade_bld_"):]
    from game.data import BUILDINGS
    if payload not in BUILDINGS:
        await query.answer("❌ Bangunan tidak dikenali", show_alert=True)
        return
    user = query.from_user
    from game.engine import get_building_level
    bld = BUILDINGS[payload]
    current_level = await get_building_level(user.id, payload)
    MAX_LEVEL = 10

    if current_level >= MAX_LEVEL:
        await query.answer(
            f"🎖️ {bld['name']} udah level maksimum ({MAX_LEVEL}).",
            show_alert=True
        )
        return

    await query.answer()

    # Hitung biaya & efek
    base_cost = bld["buy_cost"]
    upgrade_cost = int(base_cost * current_level * 1.5)
    new_level = current_level + 1
    current_reduction = (current_level - 1) * 15
    new_reduction = (new_level - 1) * 15

    db_user = await get_user_full(user.id)
    saldo = db_user["coins"]
    cukup = "✅" if saldo >= upgrade_cost else "❌"

    text = (
        f"⬆️ **KONFIRMASI UPGRADE PABRIK**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{bld['emoji']} **{bld['name']}**\n\n"
        f"📈 Level: **{current_level}** → **{new_level}**\n"
        f"⚡ Waktu produksi: -{current_reduction}% → **-{new_reduction}%**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 **Biaya Upgrade:** Rp{upgrade_cost:,}\n"
        f"💰 Saldo kamu: Rp{saldo:,} {cukup}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Yakin mau upgrade?"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Ya, Upgrade", callback_data=f"upgrade_bldok_{payload}"),
            InlineKeyboardButton("❌ Batal", callback_data=f"factory_{payload}"),
        ]
    ])
    await safe_edit(query, text, keyboard)


async def upgrade_building_confirm_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Eksekusi upgrade setelah konfirmasi. Format: upgrade_bldok_<building_key>"""
    query = update.callback_query
    payload = query.data[len("upgrade_bldok_"):]
    from game.data import BUILDINGS
    if payload not in BUILDINGS:
        await query.answer("❌ Bangunan tidak dikenali", show_alert=True)
        return
    user = query.from_user
    from game.engine import upgrade_building, get_building_level
    ok, msg = await upgrade_building(user.id, payload)
    await query.answer(msg, show_alert=True)
    if ok:
        # Refresh factory detail
        buildings = await get_user_buildings(user.id)
        slots = [b for b in buildings if b["building"] == payload]
        bld = BUILDINGS[payload]
        bld_level = await get_building_level(user.id, payload)
        reduction = (bld_level - 1) * 15
        text = (
            f"{bld.get('emoji','🏭')} **{bld.get('name','Factory')}**\n"
            f"📈 Level: **{bld_level}** (-{reduction}% waktu produksi)\n\n"
            f"Pilih resep untuk diproduksi:"
        )
        await safe_edit(query, text, factory_detail_keyboard(payload, slots))


async def produce_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Format: produce_<building_key>_<recipe_key>
    # Building key bisa multi-word (feed_mill, textile_mill), jadi nggak bisa split simple
    payload = query.data[len("produce_"):]
    from game.data import BUILDINGS
    building_key = None
    recipe_key = None
    for bk in BUILDINGS.keys():
        if payload.startswith(bk + "_"):
            building_key = bk
            recipe_key = payload[len(bk) + 1:]
            break
    if not building_key:
        await query.answer("❌ Bangunan tidak dikenali", show_alert=True)
        return
    user = query.from_user
    ok, msg = await start_production(user.id, building_key, recipe_key)
    if ok:
        buildings = await get_user_buildings(user.id)
        slots = [b for b in buildings if b["building"] == building_key]
        await safe_edit(query, msg, factory_detail_keyboard(building_key, slots))
    else:
        await query.answer(msg, show_alert=True)

async def collect_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Format: collect_<building_key>_<slot>
    # Building key bisa multi-word, jadi parsing dari belakang: slot pasti angka di akhir
    payload = query.data[len("collect_"):]
    from game.data import BUILDINGS
    building_key = None
    slot = None
    for bk in BUILDINGS.keys():
        if payload.startswith(bk + "_"):
            try:
                slot = int(payload[len(bk) + 1:])
                building_key = bk
                break
            except ValueError:
                continue
    if building_key is None or slot is None:
        await query.answer("❌ Bangunan tidak dikenali", show_alert=True)
        return
    user = query.from_user
    ok, msg = await collect_production(user.id, building_key, slot)
    if ok:
        buildings = await get_user_buildings(user.id)
        bld_slots = [b for b in buildings if b["building"] == building_key]
        await safe_edit(query, msg, factory_detail_keyboard(building_key, bld_slots))
    else:
        await query.answer(msg, show_alert=True)


# ─── STORAGE ──────────────────────────────────────────────────────────────────

async def storage_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    silo = parse_json_field(db_user["silo_items"])
    barn = parse_json_field(db_user["barn_items"])
    text = (
        f"📦 **Ringkasan Penyimpanan**\n\n"
        f"🌾 Gudang (Lv{db_user['silo_level']}): {sum(silo.values())}/{db_user['silo_cap']}\n"
        f"🏚 Lumbung (Lv{db_user['barn_level']}): {sum(barn.values())}/{db_user['barn_cap']}\n\n"
        f"Pilih penyimpanan untuk lihat item:"
    )
    await safe_edit(query, text, storage_keyboard())

async def storage_silo_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_user_full(user.id)
    text = fmt_storage(db_user, "silo")
    items = parse_json_field(db_user["silo_items"])
    await safe_edit(query, text, storage_items_keyboard(items, "silo"))

async def storage_barn_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_user_full(user.id)
    text = fmt_storage(db_user, "barn")
    items = parse_json_field(db_user["barn_items"])
    await safe_edit(query, text, storage_items_keyboard(items, "barn"))

async def storage_page_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    storage_type = parts[1]
    page = int(parts[3])
    user = query.from_user
    db_user = await get_user_full(user.id)
    if storage_type == "silo":
        items = parse_json_field(db_user["silo_items"])
        text = fmt_storage(db_user, "silo")
    else:
        items = parse_json_field(db_user["barn_items"])
        text = fmt_storage(db_user, "barn")
    await safe_edit(query, text, storage_items_keyboard(items, storage_type, page))

async def sell_menu_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    item_key = "_".join(query.data.split("_")[2:])
    user = query.from_user
    qty = await get_item_count(user.id, item_key)
    if qty == 0:
        await query.answer("Kamu tidak punya item ini!", show_alert=True)
        return
    from game.data import get_item_emoji, get_item_name, CROPS, BUILDINGS, ANIMALS
    emoji = get_item_emoji(item_key)
    name = get_item_name(item_key)

    sell_price = 0
    if item_key in CROPS:
        sell_price = CROPS[item_key]["sell_price"]
    else:
        # Cek produk hewan default (egg, milk, bacon, wool, dll)
        for a_val in ANIMALS.values():
            if a_val.get("product") == item_key:
                sell_price = a_val.get("sell_price", 0)
                break
        # Cek produk hewan custom
        if sell_price == 0:
            from game.data import CUSTOM_ANIMAL_PRODUCTS
            if item_key in CUSTOM_ANIMAL_PRODUCTS:
                sell_price = CUSTOM_ANIMAL_PRODUCTS[item_key].get("sell_price", 0)
        # Cek produk olahan pabrik
        if sell_price == 0:
            for bld in BUILDINGS.values():
                if item_key in bld["recipes"]:
                    sell_price = bld["recipes"][item_key]["sell_price"]
                    break

    price_line = f"💵 Harga jual: Rp{sell_price:,}/satuan" if sell_price else "⚠️ Tidak bisa dijual langsung (pasang di pasar saja)"
    text = f"{emoji} **{name}** (kamu punya: {qty})\n{price_line}"

    photo_id = await get_item_photo(item_key)
    if photo_id:
        await safe_send_photo(query, text, sell_keyboard(item_key, qty), photo_id)
    else:
        await safe_edit(query, text, sell_keyboard(item_key, qty))

async def sell_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split("_")
    item_key = "_".join(parts[1:-1])
    qty = int(parts[-1])
    user = query.from_user
    ok, msg = await sell_item(user.id, item_key, qty)
    await query.answer(msg, show_alert=True)
    if ok:
        db_user = await get_user_full(user.id)
        silo = parse_json_field(db_user["silo_items"])
        barn = parse_json_field(db_user["barn_items"])
        text = (
            f"📦 **Ringkasan Penyimpanan**\n\n"
            f"🌾 Gudang (Lv{db_user['silo_level']}): {sum(silo.values())}/{db_user['silo_cap']}\n"
            f"🏚 Lumbung (Lv{db_user['barn_level']}): {sum(barn.values())}/{db_user['barn_cap']}\n\n"
            f"Pilih penyimpanan untuk lihat item:"
        )
        await safe_edit(query, text, storage_keyboard())

async def upgrade_silo_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    ok, msg = await upgrade_silo(user.id)
    await query.answer(msg, show_alert=True)
    if ok:
        db_user = await get_user_full(user.id)
        silo = parse_json_field(db_user["silo_items"])
        barn = parse_json_field(db_user["barn_items"])
        await safe_edit(query,
            f"📦 **Penyimpanan**\n🌾 Gudang: {sum(silo.values())}/{db_user['silo_cap']}\n🏚 Lumbung: {sum(barn.values())}/{db_user['barn_cap']}",
            storage_keyboard()
        )

async def upgrade_barn_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    ok, msg = await upgrade_barn(user.id)
    await query.answer(msg, show_alert=True)
    if ok:
        db_user = await get_user_full(user.id)
        silo = parse_json_field(db_user["silo_items"])
        barn = parse_json_field(db_user["barn_items"])
        await safe_edit(query,
            f"📦 **Penyimpanan**\n🌾 Gudang: {sum(silo.values())}/{db_user['silo_cap']}\n🏚 Lumbung: {sum(barn.values())}/{db_user['barn_cap']}",
            storage_keyboard()
        )


# ─── ORDERS ───────────────────────────────────────────────────────────────────

async def orders_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    await ensure_orders(user.id, db_user["level"])
    orders = await get_orders(user.id)
    silo = parse_json_field(db_user["silo_items"])
    barn = parse_json_field(db_user["barn_items"])
    text = fmt_orders(orders, silo, barn)
    await safe_edit(query, text, orders_keyboard(orders))

async def orders_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    await ensure_orders(user.id, db_user["level"])
    orders = await get_orders(user.id)
    silo = parse_json_field(db_user["silo_items"])
    barn = parse_json_field(db_user["barn_items"])
    text = fmt_orders(orders, silo, barn)
    await safe_send(update, text, orders_keyboard(orders))

async def fulfill_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    order_id = int(query.data.split("_")[1])
    user = query.from_user
    ok, msg = await fulfill_order(user.id, order_id)
    if ok:
        db_user = await get_user_full(user.id)
        await ensure_orders(user.id, db_user["level"])
        orders = await get_orders(user.id)
        silo = parse_json_field(db_user["silo_items"])
        barn = parse_json_field(db_user["barn_items"])
        await safe_edit(query, msg + "\n\n" + fmt_orders(orders, silo, barn), orders_keyboard(orders))
    else:
        await query.answer(msg, show_alert=True)

async def refresh_orders_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    ok, msg = await refresh_orders(user.id, db_user["level"])
    if ok:
        orders = await get_orders(user.id)
        db_user2 = await get_user_full(user.id)
        silo = parse_json_field(db_user2["silo_items"])
        barn = parse_json_field(db_user2["barn_items"])
        await safe_edit(query, msg + "\n\n" + fmt_orders(orders, silo, barn), orders_keyboard(orders))
    else:
        await query.answer(msg, show_alert=True)


# ─── MARKET ───────────────────────────────────────────────────────────────────

async def market_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE, page: int = 0):
    if hasattr(update, "callback_query") and update.callback_query:
        query = update.callback_query
        await query.answer()
        send_fn = lambda t, k: safe_edit(query, t, k)
    else:
        send_fn = lambda t, k: safe_send(update, t, k)

    per_page = 9
    listings = await get_market_listings(page, per_page)
    from database.db import get_db, fetchone, fetchall
    async with get_db() as db:
        row = await fetchone(db, "SELECT COUNT(*) as c FROM market_listings")
        total = row["c"]

    text = fmt_market(listings, page, total)
    await send_fn(text, market_keyboard(listings, page, total, per_page))

async def market_page_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split("_")[2])
    per_page = 9
    listings = await get_market_listings(page, per_page)
    from database.db import get_db, fetchone, fetchall
    async with get_db() as db:
        row = await fetchone(db, "SELECT COUNT(*) as c FROM market_listings")
        total = row["c"]
    text = fmt_market(listings, page, total)
    await safe_edit(query, text, market_keyboard(listings, page, total, per_page))

async def market_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await get_or_create_user(user.id, user.username, user.first_name)
    per_page = 9
    listings = await get_market_listings(0, per_page)
    from database.db import get_db, fetchone, fetchall
    async with get_db() as db:
        row = await fetchone(db, "SELECT COUNT(*) as c FROM market_listings")
        total = row["c"]
    text = fmt_market(listings, 0, total)
    await safe_send(update, text, market_keyboard(listings, 0, total, per_page))

async def mkt_buy_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    listing_id = int(query.data.split("_")[2])
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)

    # Get listing info BEFORE buying (including channel_msg_id)
    from database.db import get_db, fetchone, fetchall
    async with get_db() as db:
        listing = await fetchone(db, "SELECT * FROM market_listings WHERE id = ?", (listing_id,))
    listing_info = dict(listing) if listing else None

    ok, msg = await buy_from_market(user.id, listing_id)
    await query.answer(msg, show_alert=True)
    if ok and listing_info:
        buyer_name = user.first_name or user.username or "Farmer"
        await update_channel_listing_sold(
            ctx.bot, listing_info.get("channel_msg_id"),
            buyer_name, listing_info["item"], listing_info["qty"],
            listing_info["price"], listing_info["seller_name"]
        )
        listings = await get_market_listings(0, 9)
        async with get_db() as db:
            row = await fetchone(db, "SELECT COUNT(*) as c FROM market_listings")
            total = row["c"]
        await safe_edit(query, fmt_market(listings, 0, total), market_keyboard(listings, 0, total))

async def confirm_buy_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle buy confirmation from channel deep link."""
    query = update.callback_query
    await query.answer()
    listing_id = int(query.data.split("_")[2])
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)

    # Get listing info BEFORE buying (including channel_msg_id)
    from database.db import get_db, fetchone
    async with get_db() as db:
        listing = await fetchone(db, "SELECT * FROM market_listings WHERE id = ?", (listing_id,))
    listing_info = dict(listing) if listing else None

    ok, msg = await buy_from_market(user.id, listing_id)
    if ok and listing_info:
        buyer_name = user.first_name or user.username or "Farmer"
        await update_channel_listing_sold(
            ctx.bot, listing_info.get("channel_msg_id"),
            buyer_name, listing_info["item"], listing_info["qty"],
            listing_info["price"], listing_info["seller_name"]
        )
        await safe_edit(query, f"{msg}\n\nKembali ke menu utama:", main_menu_keyboard())
    else:
        await safe_edit(query, f"{msg}", back_to_menu())

async def my_listings_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    from database.db import get_db, fetchone, fetchall
    async with get_db() as db:
        rows = await fetchall(db, 
            "SELECT * FROM market_listings WHERE seller_id = ?", (user.id,)
        )
        listings = [dict(r) for r in rows]

    if not listings:
        await safe_edit(query, "📭 Kamu tidak punya listing aktif.", back_to_menu())
        return

    from game.data import get_item_emoji, get_item_name
    buttons = []
    for l in listings:
        emoji = get_item_emoji(l["item"])
        name = get_item_name(l["item"])
        buttons.append([InlineKeyboardButton(
            f"❌ Hapus: {emoji}{name} x{l['qty']} @ Rp{l['price']:,}",
            callback_data=f"rmlist_{l['id']}"
        )])
    buttons.append([InlineKeyboardButton("⬅️ Kembali to Market", callback_data="market")])
    await safe_edit(query, "📋 **Listing Pasar Kamu** (ketuk untuk hapus):", InlineKeyboardMarkup(buttons))

async def listing_sold_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Dipanggil kalau user nge-tap tombol TERJUAL di channel."""
    query = update.callback_query
    await query.answer("✅ Listing ini sudah terjual, nggak tersedia lagi.", show_alert=True)


async def rmlist_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    listing_id = int(query.data.split("_")[1])
    user = query.from_user
    ok, msg = await remove_market_listing(user.id, listing_id)
    await query.answer(msg, show_alert=True)

async def market_list_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item_key = "_".join(query.data.split("_")[2:])
    ctx.user_data["listing_item"] = item_key

    from game.data import get_item_emoji, get_item_name, CROPS, BUILDINGS, ANIMALS
    emoji = get_item_emoji(item_key)
    name = get_item_name(item_key)
    user = query.from_user
    qty = await get_item_count(user.id, item_key)

    # Cari harga jual NPC sebagai referensi
    npc_price = 0
    kategori = "📦 Item"
    if item_key in CROPS:
        npc_price = CROPS[item_key]["sell_price"]
        kategori = "🌾 Hasil Tani"
    else:
        for bld in BUILDINGS.values():
            if item_key in bld["recipes"]:
                npc_price = bld["recipes"][item_key]["sell_price"]
                kategori = f"🏭 Hasil Olahan ({bld['name']})"
                break
        else:
            # Cek produk hewan
            animal_products = {
                "egg": 400, "milk": 800, "bacon": 1000, "wool": 1300,
                "goat_milk": 1100, "honey": 1600, "feather": 700,
                "fish": 900, "lobster": 2500, "mozzarella": 3200,
            }
            if item_key in animal_products:
                npc_price = animal_products[item_key]
                kategori = "🐄 Produk Hewan"

    # Saran harga P2P (markup dari harga NPC)
    saran_murah  = int(npc_price * 1.3) if npc_price else 0
    saran_normal = int(npc_price * 1.8) if npc_price else 0
    saran_mahal  = int(npc_price * 2.5) if npc_price else 0

    # Info listing user
    max_listings = int(await get_setting("max_market_listings", "5"))
    max_price = int(await get_setting("max_market_price", "9999999"))
    from database.db import get_db
    async with get_db() as db:
        row = await fetchone(db,
            "SELECT COUNT(*) as c FROM market_listings WHERE seller_id = ?", (user.id,))
        active_listings = row["c"] if row else 0
    slot_tersisa = max_listings - active_listings

    # Kuantitas contoh yang masuk akal
    qty_contoh = min(qty, 10) if qty >= 10 else qty
    harga_contoh = saran_normal if saran_normal else 1000

    # Bangun teks detail
    lines = [
        f"📢 **PASAR P2P — Pasang Listing**",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"{emoji} **{name}**",
        f"📂 Kategori: {kategori}",
        f"📦 Stok kamu: **{qty}** unit",
        "",
    ]

    if npc_price > 0:
        lines += [
            f"💰 **Harga Referensi**",
            f"  • Jual ke NPC: Rp{npc_price:,}/unit",
            f"",
            f"💡 **Saran Harga P2P** (harga/unit)",
            f"  🟢 Murah   : Rp{saran_murah:,}  _(cepat laku, +30%)_",
            f"  🟡 Normal  : Rp{saran_normal:,}  _(pasar wajar, +80%)_",
            f"  🔴 Mahal   : Rp{saran_mahal:,}  _(untung besar, +150%)_",
            "",
        ]
    else:
        lines += [
            f"⚠️ Item ini tidak punya harga NPC — tentukan sendiri.",
            "",
        ]

    lines += [
        f"📋 **Aturan Pasar**",
        f"  • Harga maks: Rp{max_price:,}/unit",
        f"  • Slot listing: {active_listings}/{max_listings} _(sisa {slot_tersisa})_",
        "",
    ]

    if slot_tersisa <= 0:
        lines += [
            f"❌ **Slot listing kamu penuh!**",
            f"Hapus salah satu listing lama dulu lewat 📢 Listing Saya.",
        ]
    elif qty <= 0:
        lines += [f"❌ Kamu tidak punya stok item ini."]
    else:
        lines += [
            f"✍️ **Format Command**",
            f"`/listitem <item> <qty> <harga/unit>`",
            "",
            f"📝 **Contoh siap pakai** (tap untuk copy):",
            f"`/listitem {item_key} {qty_contoh} {harga_contoh}`",
        ]
        if qty >= 5 and saran_murah:
            lines.append(f"`/listitem {item_key} 5 {saran_murah}`")
        if qty > qty_contoh and saran_mahal:
            lines.append(f"`/listitem {item_key} {qty} {saran_mahal}`")
        lines += [
            "",
            f"ℹ️ Harga yang kamu tulis = **harga per unit**. "
            f"Total = harga × qty. Uang masuk otomatis saat item terbeli.",
        ]

    buttons = [
        [InlineKeyboardButton("📢 Listing Saya", callback_data="my_listings")],
        [InlineKeyboardButton("🏪 Ke Pasar", callback_data="market")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="storage")],
    ]
    await safe_edit(query, "\n".join(lines), InlineKeyboardMarkup(buttons))

async def listitem_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    args = ctx.args
    if len(args) < 3:
        await safe_send(update, "Cara pakai: `/listitem <item> <qty> <price>`\nExample: `/listitem wheat 10 5`")
        return
    item_key = args[0].lower()
    try:
        qty = int(args[1])
        price = int(args[2])
    except ValueError:
        await safe_send(update, "❌ Jumlah dan harga harus angka.")
        return

    seller_name = db_user.get("display_name") or user.first_name or user.username or "Farmer"
    ok, msg, listing_id = await list_item_on_market(user.id, seller_name, item_key, qty, price)
    await safe_send(update, msg)
    if ok:
        await post_to_market_channel(ctx.bot, seller_name, item_key, qty, price, listing_id)


async def post_to_market_channel(bot, seller_name: str, item_key: str, qty: int, price: int, listing_id: int):
    """Post a new market listing to the market channel with Buy button."""
    channel = await get_setting("market_channel")
    if not channel:
        return
    try:
        from game.data import get_item_emoji, get_item_name
        emoji = get_item_emoji(item_key)
        name = get_item_name(item_key)
        total = price * qty
        bot_info = await bot.get_me()
        bot_username = bot_info.username

        text = (
            f"🏪 **Listing Baru di Pasar!**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{emoji} **{name}** x{qty}\n"
            f"💵 Rp{price:,}/satuan (Total: Rp{total:,})\n"
            f"👤 Penjual: **{seller_name}**\n\n"
            f"🛒 Ketuk tombol di bawah untuk beli!"
        )
        # Deep link: when user clicks, bot receives /start buy_<listing_id>
        buy_url = f"https://t.me/{bot_username}?start=buy_{listing_id}"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Beli Sekarang!", url=buy_url)]
        ])
        msg = await bot.send_message(chat_id=channel, text=text, reply_markup=keyboard, parse_mode="Markdown")

        # Save channel message_id for later update
        from database.db import get_db
        async with get_db() as db:
            await db.execute("UPDATE market_listings SET channel_msg_id = ? WHERE id = ?", (msg.message_id, listing_id))
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to post to market channel: {e}")


async def update_channel_listing_sold(bot, channel_msg_id: int, buyer_name: str, item_key: str, qty: int, price: int, seller_name: str):
    """Update the channel message to show listing is sold."""
    channel = await get_setting("market_channel")
    if not channel or not channel_msg_id:
        return
    try:
        from game.data import get_item_emoji, get_item_name
        emoji = get_item_emoji(item_key)
        name = get_item_name(item_key)
        total = price * qty

        text = (
            f"✅ **TERJUAL!**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{emoji} **{name}** x{qty}\n"
            f"💵 Rp{price:,}/satuan (Total: Rp{total:,})\n\n"
            f"👤 Penjual: **{seller_name}**\n"
            f"🛒 Pembeli: **{buyer_name}**\n\n"
            f"_Listing ini sudah terjual_"
        )
        # Ganti tombol "Beli Sekarang" jadi tombol status "TERJUAL"
        sold_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ ITEM INI SUDAH TERJUAL", callback_data="listing_sold")]
        ])
        await bot.edit_message_text(
            chat_id=channel, message_id=channel_msg_id,
            text=text, parse_mode="Markdown", reply_markup=sold_keyboard
        )
    except Exception as e:
        logger.error(f"Failed to update channel listing: {e}")


# ─── LAND ─────────────────────────────────────────────────────────────────────

async def land_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    obstacles = await get_obstacles(user.id)
    plots = await get_plots(user.id)

    if obstacles:
        text = (
            f"🗺️ **Lahan Kamu**\n\n"
            f"🌱 Kebun: {db_user['plots']} lahan\n"
            f"🐾 Kandang: {db_user['animal_pens']} kandang\n\n"
            f"⚠️ Ada **{len(obstacles)} rintangan** yang harus dibersihin!\n"
            f"Ketuk rintangan di bawah buat bersihin.\n"
            f"Butuh alat? Beli di 🛒 **Toko Alat**."
        )
    else:
        text = (
            f"🗺️ **Lahan Kamu**\n\n"
            f"🌱 Kebun: {db_user['plots']} lahan\n"
            f"🐾 Kandang: {db_user['animal_pens']} kandang\n\n"
            f"✅ Semua lahan bersih! Perluas kalau mau nambah."
        )
    await safe_edit(query, text, land_keyboard(obstacles, plots))

async def clear_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    slot = int(query.data.split("_")[1])
    user = query.from_user
    ok, msg = await clear_obstacle(user.id, slot)
    await query.answer(msg, show_alert=True)
    if ok:
        obstacles = await get_obstacles(user.id)
        plots = await get_plots(user.id)
        db_user = await get_user_full(user.id)
        if obstacles:
            text = (
                f"🗺️ **Lahan Kamu**\n\n"
                f"🌱 Kebun: {db_user['plots']} lahan\n\n"
                f"⚠️ Sisa **{len(obstacles)} rintangan** lagi."
            )
        else:
            text = (
                f"🗺️ **Lahan Kamu**\n\n"
                f"🌱 Kebun: {db_user['plots']} lahan\n\n"
                f"✅ Semua lahan bersih!"
            )
        await safe_edit(query, text, land_keyboard(obstacles, plots))


# ─── PROFILE / DAILY / HELP / LEADERBOARD / SETNAME ──────────────────────────

async def profile_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    # Get rank
    lb = await get_leaderboard(50)
    for i, u in enumerate(lb):
        if u["user_id"] == user.id:
            db_user["rank"] = i + 1
            break
    # Get equipped title
    from game.titles import get_equipped_title_display
    db_user["_title_display"] = await get_equipped_title_display(user.id)
    text = fmt_profile(db_user)
    avatar = await get_avatar(user.id)
    if avatar:
        await safe_send_photo(query, text, profile_keyboard(), avatar)
    else:
        await safe_edit(query, text, profile_keyboard())

async def profile_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    lb = await get_leaderboard(50)
    for i, u in enumerate(lb):
        if u["user_id"] == user.id:
            db_user["rank"] = i + 1
            break
    from game.titles import get_equipped_title_display
    db_user["_title_display"] = await get_equipped_title_display(user.id)
    text = fmt_profile(db_user)
    avatar = await get_avatar(user.id)
    if avatar:
        try:
            await update.message.reply_photo(
                photo=avatar, caption=text,
                reply_markup=profile_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            await safe_send(update, text, profile_keyboard())
    else:
        await safe_send(update, text, profile_keyboard())

async def leaderboard_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)
    users = await get_leaderboard(10)
    text = fmt_leaderboard(users, user.id)
    await safe_edit(query, text, leaderboard_keyboard())

async def leaderboard_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await get_or_create_user(user.id, user.username, user.first_name)
    users = await get_leaderboard(10)
    text = fmt_leaderboard(users, user.id)
    await safe_send(update, text, leaderboard_keyboard())

async def setname_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    name = get_display_name(db_user)
    await safe_edit(
        query,
        f"✏️ **Ganti Nama Tampilan**\n\n"
        f"Nama saat ini: **{name}**\n\n"
        f"Kirim nama baru kamu di chat (maks 20 karakter).\n"
        f"Atau ketik /setname <nama baru>\n\n"
        f"Contoh: `/setname PetaniHebat`",
        back_to_menu()
    )
    ctx.user_data["pending_action"] = "setname"


# ─── SET AVATAR ──────────────────────────────────────────────────────────────

async def setavatar_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    avatar = await get_avatar(user.id)
    status = "✅ Sudah di-set" if avatar else "❌ Belum ada"
    await safe_edit(
        query,
        f"🖼️ **Set Avatar Profil**\n\n"
        f"Status avatar: {status}\n\n"
        f"📸 **Kirim foto** ke chat ini untuk set sebagai avatar profilmu.\n\n"
        f"Atau ketik `/setavatar` lalu kirim foto.",
        back_to_menu()
    )
    ctx.user_data["pending_action"] = "setavatar"

async def setavatar_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Check if reply to photo
    if update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]
        await set_avatar(user.id, photo.file_id)
        await safe_send(update, "✅ Avatar profil berhasil di-set! Cek di /profile", back_to_menu())
        return
    # Check if message itself has photo
    if update.message.photo:
        photo = update.message.photo[-1]
        await set_avatar(user.id, photo.file_id)
        await safe_send(update, "✅ Avatar profil berhasil di-set! Cek di /profile", back_to_menu())
        return

    avatar = await get_avatar(user.id)
    status = "✅ Sudah di-set" if avatar else "❌ Belum ada"
    ctx.user_data["pending_action"] = "setavatar"
    await safe_send(
        update,
        f"🖼️ **Set Avatar Profil**\n\n"
        f"Status avatar: {status}\n\n"
        f"📸 Kirim foto ke chat ini untuk set sebagai avatar.",
    )

async def user_photo_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle photo input from users for setavatar."""
    action = ctx.user_data.get("pending_action")
    if action != "setavatar":
        return
    if not update.message.photo:
        return
    ctx.user_data.pop("pending_action", None)
    photo = update.message.photo[-1]
    user = update.effective_user
    await set_avatar(user.id, photo.file_id)
    await safe_send(update, "✅ Avatar profil berhasil di-set! Cek di /profile 🎉", back_to_menu())

async def setname_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    args = ctx.args
    if not args:
        name = get_display_name(db_user)
        await safe_send(
            update,
            f"✏️ **Ganti Nama Tampilan**\n\n"
            f"Nama saat ini: **{name}**\n\n"
            f"Kirim: `/setname <nama baru>`\n"
            f"Contoh: `/setname PetaniHebat`",
            back_to_menu()
        )
        return
    new_name = " ".join(args).strip()
    if len(new_name) > 20:
        await safe_send(update, "❌ Nama terlalu panjang! Maksimal 20 karakter.")
        return
    if len(new_name) < 2:
        await safe_send(update, "❌ Nama terlalu pendek! Minimal 2 karakter.")
        return
    await set_display_name(user.id, new_name)
    await safe_send(update, f"✅ Nama berhasil diganti menjadi **{new_name}**!", back_to_menu())

async def user_text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle text input for setname from regular users."""
    action = ctx.user_data.get("pending_action")
    if not action:
        return
    text = update.message.text.strip()

    if action == "setname":
        ctx.user_data.pop("pending_action", None)
        if len(text) > 20:
            await safe_send(update, "❌ Nama terlalu panjang! Maksimal 20 karakter.")
            return
        if len(text) < 2:
            await safe_send(update, "❌ Nama terlalu pendek! Minimal 2 karakter.")
            return
        user = update.effective_user
        await set_display_name(user.id, text)
        await safe_send(update, f"✅ Nama berhasil diganti menjadi **{text}**!", back_to_menu())

async def daily_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)
    ok, msg = await claim_daily(user.id)
    # Satu kali answer — show popup alert dengan hasil (bukan 2x kayak dulu)
    await query.answer(msg, show_alert=True)
    # Refresh menu utama biar saldo baru keliatan
    if ok:
        db_user = await get_or_create_user(user.id, user.username, user.first_name)
        name = get_display_name(db_user)
        text = (
            f"🏠 **Menu Utama**\n"
            f"👑 Level {db_user['level']}  💵 Rp{db_user['coins']:,}  💎 {db_user['gems']}\n\n"
            f"🎁 +Rp{(10000 + db_user['level']*1000):,} bonus harian masuk!\n"
            f"Mau ngapain lagi, **{name}**?"
        )
        try:
            await safe_edit(query, text, main_menu_keyboard())
        except Exception:
            pass

async def daily_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await get_or_create_user(user.id, user.username, user.first_name)
    ok, msg = await claim_daily(user.id)
    await safe_send(update, msg, back_to_menu())

async def help_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from utils.formatters import help_total_pages
    from utils.keyboards import help_slide_keyboard
    await safe_edit(query, fmt_help(0), help_slide_keyboard(0, help_total_pages()))

async def help_page_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from utils.formatters import help_total_pages
    from utils.keyboards import help_slide_keyboard
    try:
        page = int(query.data.split("_")[2])
    except Exception:
        page = 0
    total = help_total_pages()
    page = max(0, min(page, total - 1))
    await safe_edit(query, fmt_help(page), help_slide_keyboard(page, total))

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from utils.formatters import help_total_pages
    from utils.keyboards import help_slide_keyboard
    await safe_send(update, fmt_help(0), help_slide_keyboard(0, help_total_pages()))


async def transfer_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Transfer item ke player lain. Format: /transfer <user_id> <item_key> <qty>"""
    args = ctx.args
    user = update.effective_user
    await get_or_create_user(user.id, user.username, user.first_name)

    if len(args) < 3:
        await safe_send(update, (
            "📤 **TRANSFER ITEM**\n\n"
            "Kirim item ke player lain.\n\n"
            "**Format:**\n"
            "`/transfer <user_id> <item_key> <qty>`\n\n"
            "**Contoh:**\n"
            "`/transfer 123456789 wheat 20`\n"
            "`/transfer 123456789 egg 5`\n"
            "`/transfer 123456789 bread 3`\n\n"
            "**Aturan:**\n"
            "• Maks 5 transfer/hari (reset jam 07:00 WIB)\n"
            "• Tidak bisa kirim ke diri sendiri\n"
            "• Receiver harus terdaftar di bot\n"
            "• Item bakal dipotong dari Gudang/Lumbung kamu\n"
            "• Cek user_id lewat /profile (yang mau ditransfer harus kasih ID-nya)"
        ), back_to_menu())
        return

    try:
        receiver_id = int(args[0])
    except ValueError:
        await safe_send(update, "❌ user_id harus angka.", back_to_menu())
        return

    item_key = args[1].lower()

    try:
        qty = int(args[2])
    except ValueError:
        await safe_send(update, "❌ qty harus angka.", back_to_menu())
        return

    from game.engine import transfer_item_to_player
    ok, msg = await transfer_item_to_player(user.id, receiver_id, item_key, qty)
    await safe_send(update, msg, back_to_menu())

    # Notif ke receiver
    if ok:
        try:
            from game.data import get_item_emoji, get_item_name
            emoji = get_item_emoji(item_key)
            name = get_item_name(item_key)
            sender_name = user.first_name or "Petani"
            await ctx.bot.send_message(
                receiver_id,
                f"📦 **Kamu dapet kiriman item!**\n\n"
                f"Dari: **{sender_name}** (`{user.id}`)\n"
                f"Item: {qty}x {emoji} {name}\n\n"
                f"Cek di 📦 Penyimpanan!",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass

# ─── TOKO ALAT ────────────────────────────────────────────────────────────────

async def shop_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "🛒 **Toko Alat**\n\n"
        "Beli alat yang kamu butuhkan untuk upgrade & perluasan!\n"
        "Alat juga bisa didapat gratis dari bonus panen (5%).\n\n"
        "Ketuk alat untuk membeli:"
    )
    await safe_edit(query, text, shop_keyboard())

async def shop_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "🛒 **Toko Alat**\n\n"
        "Beli alat yang kamu butuhkan untuk upgrade & perluasan!\n"
        "Alat juga bisa didapat gratis dari bonus panen (5%).\n\n"
        "Ketuk alat untuk membeli:"
    )
    await safe_send(update, text, shop_keyboard())

async def shopbuy_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tool_key = query.data.split("_", 1)[1]
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)
    ok, msg = await buy_tool(user.id, tool_key, 1)
    await query.answer(msg, show_alert=True)
    if ok:
        text = (
            f"{msg}\n\n"
            "🛒 **Toko Alat** — mau beli lagi?"
        )
        await safe_edit(query, text, shop_keyboard())


# ─── TUTORIAL ─────────────────────────────────────────────────────────────────

async def tutorial_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await safe_edit(query, fmt_tutorial(), back_to_menu())

async def tutorial_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await safe_send(update, fmt_tutorial(), back_to_menu())


# ─── ITEMS CATALOG ────────────────────────────────────────────────────────────

async def items_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("items_", "")
    if category not in ("crops", "animals", "products", "tools", "all"):
        category = "all"

    from utils.keyboards import items_keyboard
    # "all" = landing page → tampilin menu pilihan kategori dulu, jangan dump semua
    if category == "all":
        text = (
            "📚 *KATALOG ITEM — Greena Farm*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Pilih kategori item yang mau dilihat:\n\n"
            "🌾 *Tanaman* — semua bibit & hasil panen\n"
            "🐾 *Hewan* — ternak & produk hewan\n"
            "🏭 *Barang Olahan* — resep pabrik\n"
            "🛒 *Alat* — item dari toko alat\n"
        )
        await safe_edit(query, text, items_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    # Kategori spesifik — generate dengan plain text (no markdown) biar nggak parse error
    text = fmt_all_items(category)
    # Strip markdown chars yang bisa bikin parser confused
    text = text.replace("**", "").replace("`", "")
    # Hard limit 4096 (telegram max), kasih buffer
    if len(text) > 4000:
        text = text[:3950] + "\n\n... (terlalu panjang, dipotong)"
    # Send tanpa parse_mode = no markdown error
    try:
        await query.edit_message_text(
            text, reply_markup=items_keyboard(),
            parse_mode=None, disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"items_callback edit failed: {e}")
        # Note: query udah di-answer di atas, jangan di-answer lagi


async def items_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from utils.keyboards import items_keyboard
    text = (
        "📚 *KATALOG ITEM — Greena Farm*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Pilih kategori item yang mau dilihat:\n\n"
        "🌾 *Tanaman* — semua bibit & hasil panen\n"
        "🐾 *Hewan* — ternak & produk hewan\n"
        "🏭 *Barang Olahan* — resep pabrik\n"
        "🛒 *Alat* — item dari toko alat\n"
    )
    await safe_send(update, text, items_keyboard())


async def noop_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Tidak ada yang bisa dilakukan di sini!", show_alert=False)

async def locked_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("🔒 Naik level untuk membuka ini!", show_alert=True)


# ─── TOKO PERMATA (Player Side) ──────────────────────────────────────────────

async def _render_gem_shop(user_id: int, msg_text_extra: str = "") -> tuple[str, InlineKeyboardMarkup]:
    from game.gems import list_gem_items
    from database.db import get_user
    db_user = await get_user(user_id)
    items = await list_gem_items(active_only=True)

    text = (
        f"💎 **TOKO PERMATA**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 Permata kamu: **{db_user['gems']}**\n\n"
    )
    if msg_text_extra:
        text += msg_text_extra + "\n\n"

    if not items:
        text += "📭 Toko sedang kosong.\nTunggu admin tambahin item baru!\n\n"
    else:
        text += "Pilih item buat dibeli 👇\n\n"
        for it in items:
            stock_info = "" if it["stock"] < 0 else f"  _(stok: {it['stock']})_"
            text += f"{it['emoji']} **{it['name']}** — {it['price_gems']}💎{stock_info}\n"
            if it["description"]:
                text += f"   _{it['description']}_\n"
            text += "\n"

    text += (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Permata cuma bisa didapat dari **event spesial** yang dibuat admin.\n"
        "Punya code event? Tap **🎟 Tukar Code** di bawah!"
    )

    buttons = []
    for it in items:
        label = f"{it['emoji']} {it['name']} — {it['price_gems']}💎"
        buttons.append([InlineKeyboardButton(label[:55], callback_data=f"gembuy_{it['id']}")])
    buttons.append([InlineKeyboardButton("🎟 Tukar Code Event", callback_data="redeem_prompt")])
    buttons.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu")])
    return text, InlineKeyboardMarkup(buttons)


async def gemshop_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)
    text, kb = await _render_gem_shop(user.id)
    await safe_edit(query, text, kb)


async def gemshop_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await get_or_create_user(user.id, user.username, user.first_name)
    text, kb = await _render_gem_shop(user.id)
    await safe_send(update, text, kb)


async def gembuy_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    item_id = int(query.data.split("_")[1])
    user = query.from_user
    from game.gems import get_gem_item
    from database.db import get_user
    item = await get_gem_item(item_id)
    if not item:
        await query.answer("❌ Item tidak ditemukan", show_alert=True)
        return
    db_user = await get_user(user.id)
    stock_info = "Tak terbatas" if item["stock"] < 0 else f"{item['stock']} tersisa"
    text = (
        f"💎 **Konfirmasi Pembelian**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{item['emoji']} **{item['name']}**\n"
        f"_{item['description'] or 'Tidak ada deskripsi'}_\n\n"
        f"💰 Harga: **{item['price_gems']} 💎**\n"
        f"📦 Stok: {stock_info}\n"
        f"💎 Permata kamu: {db_user['gems']}\n\n"
        f"Yakin mau beli?"
    )
    buttons = [
        [InlineKeyboardButton("✅ Konfirmasi Beli", callback_data=f"gemconfirm_{item_id}")],
        [InlineKeyboardButton("❌ Batal", callback_data="gemshop")],
    ]
    await safe_edit(query, text, InlineKeyboardMarkup(buttons))


async def gemconfirm_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    item_id = int(query.data.split("_")[1])
    user = query.from_user
    from game.gems import buy_gem_item

    ok, msg, info = await buy_gem_item(user.id, item_id)
    await query.answer(msg[:200], show_alert=True)

    # Notif ke admin kalau perlu manual
    if ok and info and info.get("needs_admin"):
        from handlers.admin_handlers import get_admin_ids
        admin_text = (
            f"🛒 **Pembelian Toko Permata**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 User: {user.first_name} (`{user.id}`)\n"
            f"🎁 Item: {info['item']['emoji']} {info['item']['name']}\n"
            f"💎 Harga: {info['item']['price_gems']} permata\n"
            f"📝 Tipe: `{info['item']['reward_type']}`\n"
            f"📝 Detail: `{info['item']['reward_value']}`\n\n"
            f"_Mohon proses item ini secara manual untuk user._"
        )
        try:
            for aid in get_admin_ids():
                await ctx.bot.send_message(aid, admin_text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Gagal notif admin: {e}")

    # Refresh tampilan toko
    text, kb = await _render_gem_shop(user.id, msg_text_extra=msg if ok else "")
    await safe_edit(query, text, kb)


async def redeem_prompt_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "🎟 **Tukar Code Event**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Punya code dari event yang dibagikan admin?\n\n"
        "Ketik command:\n"
        "`/redeem KODE_KAMU`\n\n"
        "**Contoh:**\n"
        "`/redeem EVENT2026`\n\n"
        "Code biasanya dibagikan admin lewat:\n"
        "📢 Channel pasar\n"
        "👥 Grup official"
    )
    buttons = [[InlineKeyboardButton("⬅️ Kembali", callback_data="gemshop")]]
    await safe_edit(query, text, InlineKeyboardMarkup(buttons))


async def redeem_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await get_or_create_user(user.id, user.username, user.first_name)
    args = ctx.args
    if not args:
        await safe_send(update,
            "🎟 **Tukar Code Event**\n\n"
            "Cara pakai: `/redeem KODE_KAMU`\n"
            "Contoh: `/redeem EVENT2026`")
        return
    from game.gems import redeem_code as redeem_event_code
    ok, msg = await redeem_event_code(user.id, args[0])
    await safe_send(update, msg)


# ─── TITLE / GELAR (Player Side) ─────────────────────────────────────────────

async def _render_mytitles(user_id: int, extra_msg: str = "") -> tuple[str, InlineKeyboardMarkup]:
    from game.titles import get_user_titles, get_equipped_title_display
    owned = await get_user_titles(user_id)
    equipped = await get_equipped_title_display(user_id)

    text = (
        f"🎭 **GELAR KAMU**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )
    if equipped:
        text += f"👤 Sedang dipakai: **{equipped}**\n\n"
    else:
        text += f"👤 Sedang dipakai: _tidak ada_\n\n"

    if extra_msg:
        text += extra_msg + "\n\n"

    if not owned:
        text += (
            "📭 Kamu belum punya gelar.\n\n"
            "Cara dapetin:\n"
            "• Beli di 💎 Toko Permata\n"
            "• Reward event spesial dari admin\n"
            "• Achievement khusus"
        )
    else:
        text += f"**Koleksi kamu** ({len(owned)}):\n\n"
        for t in owned:
            text += f"• {t['display']}\n"
            if t['description']:
                text += f"  _{t['description']}_\n"
            text += "\n"
        text += "Tap tombol di bawah buat pasang / lepas gelar:"

    buttons = []
    for t in owned:
        label = f"✨ Pakai: {t['display']}"
        buttons.append([InlineKeyboardButton(label[:55], callback_data=f"title_eq_{t['title_key']}")])
    if owned and equipped:
        buttons.append([InlineKeyboardButton("❌ Lepas Gelar", callback_data="title_unequip")])
    buttons.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu")])
    return text, InlineKeyboardMarkup(buttons)


async def mytitles_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await get_or_create_user(user.id, user.username, user.first_name)
    text, kb = await _render_mytitles(user.id)
    await safe_send(update, text, kb)


async def mytitles_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)
    text, kb = await _render_mytitles(user.id)
    await safe_edit(query, text, kb)


async def title_equip_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    title_key = "_".join(query.data.split("_")[2:])
    user = query.from_user
    from game.titles import equip_title
    ok, msg = await equip_title(user.id, title_key)
    await query.answer(msg, show_alert=True)
    text, kb = await _render_mytitles(user.id, extra_msg=msg if ok else "")
    await safe_edit(query, text, kb)


async def title_unequip_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    from game.titles import equip_title
    ok, msg = await equip_title(user.id, "")
    await query.answer(msg, show_alert=True)
    text, kb = await _render_mytitles(user.id, extra_msg=msg if ok else "")
    await safe_edit(query, text, kb)
