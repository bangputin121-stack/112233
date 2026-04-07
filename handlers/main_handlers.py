# handlers/main_handlers.py - Core handlers for Harvest Kingdom

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

# Safe edit/send helpers
async def safe_edit(query, text: str, keyboard=None, parse_mode=ParseMode.MARKDOWN):
    try:
        await query.edit_message_text(
            text, reply_markup=keyboard, parse_mode=parse_mode,
            disable_web_page_preview=True
        )
    except Exception:
        try:
            await query.message.reply_text(
                text, reply_markup=keyboard, parse_mode=parse_mode,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"safe_edit failed: {e}")

async def safe_send(update: Update, text: str, keyboard=None):
    try:
        await update.message.reply_text(
            text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"safe_send failed: {e}")

async def get_item_photo(item_key: str) -> str | None:
    """Get photo file_id for an item from game_settings."""
    photo_id = await get_setting(f"photo_{item_key}")
    return photo_id if photo_id else None

async def safe_send_photo(target, text: str, keyboard=None, photo_id: str = None):
    """Send photo with caption, fallback to text if no photo or error."""
    if not photo_id:
        # No photo, send as text
        if hasattr(target, "edit_message_text"):
            await safe_edit(target, text, keyboard)
        elif hasattr(target, "message") and target.message:
            await safe_send(target, text, keyboard)
        return

    try:
        if hasattr(target, "message") and target.message:
            # From callback query — delete old message, send new photo
            chat_id = target.message.chat_id
            try:
                await target.message.delete()
            except Exception:
                pass
            await target.message.get_bot().send_photo(
                chat_id=chat_id,
                photo=photo_id,
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # From update.message
            await target.message.reply_photo(
                photo=photo_id,
                caption=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        logger.error(f"safe_send_photo failed: {e}, falling back to text")
        if hasattr(target, "edit_message_text"):
            await safe_edit(target, text, keyboard)
        elif hasattr(target, "message") and target.message:
            try:
                await target.message.reply_text(
                    text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass


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
    welcome = await get_setting("welcome_message", "Selamat datang di Harvest Kingdom! 🌾👑")

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

async def farm_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    plots = await get_plots(user.id)
    text = fmt_farm(db_user, plots)
    await safe_edit(query, text, farm_keyboard(plots, db_user["level"]))

async def farm_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    plots = await get_plots(user.id)
    text = fmt_farm(db_user, plots)
    await safe_send(update, text, farm_keyboard(plots, db_user["level"]))

async def plot_plant_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot = int(query.data.split("_")[2])
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    await safe_edit(query, f"🌱 **Pilih tanaman untuk Lahan {slot+1}:**\n\n(Harga yang ditampilkan adalah biaya benih)", plant_keyboard(db_user["level"], slot))

async def plant_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    slot = int(parts[1])
    crop_key = "_".join(parts[2:])
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    ok, msg = await plant_crop(user.id, slot, crop_key)
    if ok:
        plots = await get_plots(user.id)
        db_user = await get_user_full(user.id)
        full_text = msg + "\n\n" + fmt_farm(db_user, plots)
        photo_id = await get_item_photo(crop_key)
        if photo_id:
            await safe_send_photo(query, full_text, farm_keyboard(plots, db_user["level"]), photo_id)
        else:
            await safe_edit(query, full_text, farm_keyboard(plots, db_user["level"]))
    else:
        await query.answer(msg, show_alert=True)

async def plot_harvest_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot = int(query.data.split("_")[2])
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)
    ok, msg = await harvest_crop(user.id, slot)
    if ok:
        db_user = await get_user_full(user.id)
        plots = await get_plots(user.id)
        await safe_edit(query, msg + "\n\n" + fmt_farm(db_user, plots), farm_keyboard(plots, db_user["level"]))
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
    await safe_edit(query, msg + "\n\n" + fmt_farm(db_user, plots), farm_keyboard(plots, db_user["level"]))

async def expand_farm_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    ok, msg = await expand_farm(user.id)
    await query.answer(msg, show_alert=True)
    if ok:
        db_user = await get_user_full(user.id)
        plots = await get_plots(user.id)
        await safe_edit(query, fmt_farm(db_user, plots), farm_keyboard(plots, db_user["level"]))


# ─── PEST & FERTILIZER ──────────────────────────────────────────────────────

async def plot_spray_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot = int(query.data.split("_")[2])
    user = query.from_user
    ok, msg = await spray_pesticide(user.id, slot)
    if ok:
        db_user = await get_user_full(user.id)
        plots = await get_plots(user.id)
        await safe_edit(query, msg + "\n\n" + fmt_farm(db_user, plots), farm_keyboard(plots, db_user["level"]))
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
    await safe_edit(query, msg + "\n\n" + fmt_farm(db_user, plots), farm_keyboard(plots, db_user["level"]))

async def fertilize_menu_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
    await query.answer()
    parts = query.data.split("_")
    slot = int(parts[1])
    fert_type = "_".join(parts[2:])
    user = query.from_user
    ok, msg = await use_fertilizer(user.id, slot, fert_type)
    if ok:
        db_user = await get_user_full(user.id)
        plots = await get_plots(user.id)
        await safe_edit(query, msg + "\n\n" + fmt_farm(db_user, plots), farm_keyboard(plots, db_user["level"]))
    else:
        await query.answer(msg, show_alert=True)


# ─── ANIMALS ──────────────────────────────────────────────────────────────────

async def animals_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    pens = await get_animal_pens(user.id)
    text = fmt_animals(db_user, pens)
    await safe_edit(query, text, animals_keyboard(pens, db_user["level"]))

async def pen_buy_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot = int(query.data.split("_")[2])
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    await safe_edit(query, f"🐾 **Pilih hewan untuk Kandang {slot+1}:**", buy_animal_keyboard(db_user["level"], slot))

async def buyanimal_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    slot = int(parts[1])
    animal_key = "_".join(parts[2:])
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)
    ok, msg = await buy_animal(user.id, slot, animal_key)
    if ok:
        db_user = await get_user_full(user.id)
        pens = await get_animal_pens(user.id)
        await safe_edit(query, msg + "\n\n" + fmt_animals(db_user, pens), animals_keyboard(pens, db_user["level"]))
    else:
        await query.answer(msg, show_alert=True)

async def pen_collect_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot = int(query.data.split("_")[2])
    user = query.from_user
    ok, msg = await collect_animal(user.id, slot)
    if ok:
        db_user = await get_user_full(user.id)
        pens = await get_animal_pens(user.id)
        await safe_edit(query, msg + "\n\n" + fmt_animals(db_user, pens), animals_keyboard(pens, db_user["level"]))
    else:
        await query.answer(msg, show_alert=True)

async def expand_pens_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    ok, msg = await expand_animal_pens(user.id)
    await query.answer(msg, show_alert=True)
    if ok:
        db_user = await get_user_full(user.id)
        pens = await get_animal_pens(user.id)
        await safe_edit(query, fmt_animals(db_user, pens), animals_keyboard(pens, db_user["level"]))

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
    await safe_edit(query, msg + "\n\n" + fmt_animals(db_user, pens), animals_keyboard(pens, db_user["level"]))


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
    await query.answer()
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
    bld = BUILDINGS.get(building_key, {})
    text = f"{bld.get('emoji','🏭')} **{bld.get('name','Factory')}**\n\nPilih resep untuk diproduksi:"
    await safe_edit(query, text, factory_detail_keyboard(building_key, slots))

async def produce_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    building_key = parts[1]
    recipe_key = "_".join(parts[2:])
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
    await query.answer()
    parts = query.data.split("_")
    building_key = parts[1]
    slot = int(parts[2])
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
    await query.answer()
    item_key = "_".join(query.data.split("_")[2:])
    user = query.from_user
    qty = await get_item_count(user.id, item_key)
    if qty == 0:
        await query.answer("Kamu tidak punya item ini!", show_alert=True)
        return
    from game.data import get_item_emoji, get_item_name, CROPS, BUILDINGS
    emoji = get_item_emoji(item_key)
    name = get_item_name(item_key)

    sell_price = 0
    if item_key in CROPS:
        sell_price = CROPS[item_key]["sell_price"]
    else:
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
    await query.answer()
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
    await query.answer()
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
    await query.answer()
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
    text = fmt_orders(orders)
    await safe_edit(query, text, orders_keyboard(orders))

async def orders_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    await ensure_orders(user.id, db_user["level"])
    orders = await get_orders(user.id)
    text = fmt_orders(orders)
    await safe_send(update, text, orders_keyboard(orders))

async def fulfill_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[1])
    user = query.from_user
    ok, msg = await fulfill_order(user.id, order_id)
    if ok:
        db_user = await get_user_full(user.id)
        await ensure_orders(user.id, db_user["level"])
        orders = await get_orders(user.id)
        await safe_edit(query, msg + "\n\n" + fmt_orders(orders), orders_keyboard(orders))
    else:
        await query.answer(msg, show_alert=True)

async def refresh_orders_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    ok, msg = await refresh_orders(user.id, db_user["level"])
    if ok:
        orders = await get_orders(user.id)
        await safe_edit(query, msg + "\n\n" + fmt_orders(orders), orders_keyboard(orders))
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
    await query.answer()
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
    await query.answer()
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
    await query.answer()
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
    await query.answer()
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)
    ok, msg = await claim_daily(user.id)
    await query.answer(msg, show_alert=True)
    if ok:
        db_user = await get_user_full(user.id)
        await safe_edit(query, fmt_profile(db_user), profile_keyboard())

async def daily_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await get_or_create_user(user.id, user.username, user.first_name)
    ok, msg = await claim_daily(user.id)
    await safe_send(update, msg, back_to_menu())

async def help_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await safe_edit(query, fmt_help(), back_to_menu())

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await safe_send(update, fmt_help(), back_to_menu())

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
    await query.answer()
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
    text = fmt_all_items(category)
    # Telegram message max 4096 chars
    if len(text) > 4000:
        text = text[:3990] + "\n\n_(dipotong)_"
    from utils.keyboards import items_keyboard
    await safe_edit(query, text, items_keyboard())

async def items_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from utils.keyboards import items_keyboard
    text = "📚 **Ensiklopedia Item**\n\nPilih kategori item yang mau dilihat:"
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
    await query.answer()
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
    await query.answer()
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
