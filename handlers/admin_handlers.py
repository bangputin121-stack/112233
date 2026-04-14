# handlers/admin_handlers.py - Admin panel for Greena Farm

import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database.db import (
    get_db, fetchone, fetchall, get_user, update_user, parse_json_field,
    dump_json_field, log_admin_action, get_setting, set_setting
)
from game.engine import (
    add_to_inventory, remove_from_inventory, get_user_full,
    get_item_count
)
from game.data import (
    CROPS, ANIMALS, BUILDINGS, UPGRADE_TOOLS, EXPANSION_TOOLS,
    CLEARING_TOOLS, get_item_emoji, get_item_name
)

logger = logging.getLogger(__name__)

def get_admin_ids() -> list[int]:
    raw = os.getenv("ADMIN_IDS", "")
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]

def is_admin(user_id: int) -> bool:
    return user_id in get_admin_ids()

def admin_only(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not is_admin(user.id):
            if update.message:
                await update.message.reply_text("🚫 Khusus admin.")
            elif update.callback_query:
                await update.callback_query.answer("🚫 Khusus admin.", show_alert=True)
            return
        return await func(update, ctx)
    wrapper.__name__ = func.__name__
    return wrapper


def admin_main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 Kelola Pengguna", callback_data="adm_users"),
            InlineKeyboardButton("💵 Beri Item", callback_data="adm_give"),
        ],
        [
            InlineKeyboardButton("⚙️ Pengaturan Game", callback_data="adm_settings"),
            InlineKeyboardButton("📊 Statistik", callback_data="adm_stats"),
        ],
        [
            InlineKeyboardButton("📢 Siaran", callback_data="adm_broadcast"),
            InlineKeyboardButton("🗃️ Log Admin", callback_data="adm_logs"),
        ],
        [
            InlineKeyboardButton("🌾 Kelola Database Item", callback_data="adm_items"),
            InlineKeyboardButton("🏠 Tutup", callback_data="menu"),
        ],
    ])

def admin_settings_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔧 Aktif/Nonaktif Maintenance", callback_data="adm_set_maintenance")],
        [InlineKeyboardButton("Event 2x XP", callback_data="adm_set_double_xp")],
        [InlineKeyboardButton("Event 2x Koin", callback_data="adm_set_double_coins")],
        [InlineKeyboardButton("✏️ Atur Pesan Sambutan", callback_data="adm_set_welcome")],
        [InlineKeyboardButton("📈 Atur Drop Rate", callback_data="adm_set_droprate")],
        [InlineKeyboardButton("🏪 Atur Harga Pasar Maks", callback_data="adm_set_maxprice")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="adm_panel")],
    ])


@admin_only
async def admin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👑 **Panel Admin — Greena Farm**\n\nPilih menu:",
        reply_markup=admin_main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@admin_only
async def adm_panel_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "👑 **Panel Admin — Greena Farm**\n\nPilih menu:",
        reply_markup=admin_main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )


# ─── STATS ───────────────────────────────────────────────────────────────────

@admin_only
async def adm_stats_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    async with get_db() as db:
        total_users = (await fetchone(db, "SELECT COUNT(*) as c FROM users"))["c"]
        total_harvests_sum = (await fetchone(db, "SELECT SUM(total_harvests) as s FROM users"))["s"] or 0
        total_sales_sum = (await fetchone(db, "SELECT SUM(total_sales) as s FROM users"))["s"] or 0
        total_market = (await fetchone(db, "SELECT COUNT(*) as c FROM market_listings"))["c"]
        max_level_user = await fetchone(db, "SELECT first_name, level, xp FROM users ORDER BY level DESC, xp DESC LIMIT 1")
        total_coins = (await fetchone(db, "SELECT SUM(coins) as s FROM users"))["s"] or 0
        active_orders = (await fetchone(db, "SELECT COUNT(*) as c FROM orders WHERE status='active'"))["c"]

    top = f"{max_level_user['first_name']} (Lv {max_level_user['level']})" if max_level_user else "N/A"
    maintenance = await get_setting("maintenance_mode", "0")
    double_xp = await get_setting("double_xp", "0")
    double_koin = await get_setting("double_coins", "0")
    drop_rate = await get_setting("bonus_drop_rate", "0.05")

    text = (
        f"📊 **Statistik Game**\n\n"
        f"👥 Total pemain: **{total_users}**\n"
        f"🌾 Total panen: **{total_harvests_sum:,}**\n"
        f"🚚 Total penjualan: **{total_sales_sum:,}**\n"
        f"🏪 Listing pasar: **{total_market}**\n"
        f"📋 Pesanan aktif: **{active_orders}**\n"
        f"💵 Total uang dalam game: **Rp{total_coins:,}**\n"
        f"🏆 Pemain teratas: **{top}**\n\n"
        f"**Event Aktif:**\n"
        f"🔧 Maintenance: {'ON' if maintenance=='1' else 'OFF'}\n"
        f"⭐ Double XP: {'ON' if double_xp=='1' else 'OFF'}\n"
        f"💵 Double Rp: {'ON' if double_koin=='1' else 'OFF'}\n"
        f"🎁 Drop Rate: {float(drop_rate)*100:.1f}%"
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ Kembali", callback_data="adm_panel")
    ]]), parse_mode=ParseMode.MARKDOWN)


# ─── SETTINGS ────────────────────────────────────────────────────────────────

@admin_only
async def adm_settings_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    maintenance = await get_setting("maintenance_mode", "0")
    double_xp = await get_setting("double_xp", "0")
    double_koin = await get_setting("double_coins", "0")
    drop_rate = await get_setting("bonus_drop_rate", "0.05")

    text = (
        f"⚙️ **Pengaturan Game**\n\n"
        f"🔧 Maintenance: {'🟢 ON' if maintenance=='1' else '🔴 OFF'}\n"
        f"⭐ Double XP: {'🟢 ON' if double_xp=='1' else '🔴 OFF'}\n"
        f"💵 Double Rp: {'🟢 ON' if double_koin=='1' else '🔴 OFF'}\n"
        f"🎁 Drop Rate: {float(drop_rate)*100:.1f}%\n"
    )
    await query.edit_message_text(text, reply_markup=admin_settings_keyboard(), parse_mode=ParseMode.MARKDOWN)

@admin_only
async def adm_toggle_setting(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "adm_set_maintenance":
        cur = await get_setting("maintenance_mode", "0")
        new = "0" if cur == "1" else "1"
        await set_setting("maintenance_mode", new)
        status = "diaktifkan" if new == "1" else "dinonaktifkan"
        await query.answer(f"Maintenance {status}!", show_alert=True)

    elif action == "adm_set_double_xp":
        cur = await get_setting("double_xp", "0")
        new = "0" if cur == "1" else "1"
        await set_setting("double_xp", new)
        await query.answer(f"2x XP {'ON' if new=='1' else 'OFF'}!", show_alert=True)

    elif action == "adm_set_double_coins":
        cur = await get_setting("double_coins", "0")
        new = "0" if cur == "1" else "1"
        await set_setting("double_coins", new)
        await query.answer(f"2x Coins {'ON' if new=='1' else 'OFF'}!", show_alert=True)

    elif action == "adm_set_welcome":
        ctx.user_data["adm_action"] = "set_welcome"
        await query.edit_message_text(
            "✏️ Kirim teks pesan sambutan baru:\n(Kirim /cancel untuk batal)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Batal", callback_data="adm_settings")]]),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    elif action == "adm_set_droprate":
        ctx.user_data["adm_action"] = "set_droprate"
        cur = await get_setting("bonus_drop_rate", "0.05")
        await query.edit_message_text(
            f"📈 Drop rate saat ini: {float(cur)*100:.1f}%\n\nKirim rate baru dalam desimal (e.g. 0.05 = 5%):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Batal", callback_data="adm_settings")]]),
        )
        return

    elif action == "adm_set_maxprice":
        ctx.user_data["adm_action"] = "set_maxprice"
        cur = await get_setting("max_market_price", "9999999")
        await query.edit_message_text(
            f"🏪 Harga maks saat ini: Rp{cur}\n\nKirim harga maks baru:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Batal", callback_data="adm_settings")]]),
        )
        return

    # Refresh settings page
    await adm_settings_callback(update, ctx)

@admin_only
async def adm_text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    action = ctx.user_data.get("adm_action")
    if not action:
        return
    text = update.message.text.strip()

    if action == "set_welcome":
        await set_setting("welcome_message", text)
        await update.message.reply_text(f"✅ Pesan sambutan diperbarui!")
        ctx.user_data.pop("adm_action", None)

    elif action == "set_droprate":
        try:
            rate = float(text)
            if not 0 <= rate <= 1:
                raise ValueError
            await set_setting("bonus_drop_rate", str(rate))
            await update.message.reply_text(f"✅ Drop rate set ke {rate*100:.1f}%")
        except ValueError:
            await update.message.reply_text("❌ Invalid. Send a decimal 0.0 ke 1.0")
        ctx.user_data.pop("adm_action", None)

    elif action == "set_maxprice":
        try:
            price = int(text)
            await set_setting("max_market_price", str(price))
            await update.message.reply_text(f"✅ Max market price set ke Rp{price:,}")
        except ValueError:
            await update.message.reply_text("❌ Angka tidak valid.")
        ctx.user_data.pop("adm_action", None)

    elif action == "give_item_qty":
        try:
            parts = text.split()
            target_id = int(ctx.user_data.get("adm_target_id"))
            item_key = ctx.user_data.get("adm_give_item")
            qty = int(parts[0])
            ok, msg = await add_to_inventory(target_id, item_key, qty)
            if ok:
                await log_admin_action(update.effective_user.id, "give_item", target_id, f"{item_key} x{qty}")
                await update.message.reply_text(f"✅ Memberi {qty}x {get_item_name(item_key)} ke user {target_id}")
            else:
                await update.message.reply_text(f"❌ Gagal: {msg}")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
        ctx.user_data.pop("adm_action", None)

    elif action == "set_coins":
        try:
            amount = int(text)
            target_id = int(ctx.user_data.get("adm_target_id"))
            await update_user(target_id, coins=amount)
            await log_admin_action(update.effective_user.id, "set_coins", target_id, str(amount))
            await update.message.reply_text(f"✅ Set Rp ke {amount:,} untuk user {target_id}")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
        ctx.user_data.pop("adm_action", None)

    elif action == "set_level":
        try:
            level = int(text)
            target_id = int(ctx.user_data.get("adm_target_id"))
            from game.data import LEVEL_THRESHOLDS
            xp = LEVEL_THRESHOLDS[min(level-1, len(LEVEL_THRESHOLDS)-1)]
            await update_user(target_id, level=level, xp=xp)
            await log_admin_action(update.effective_user.id, "set_level", target_id, str(level))
            await update.message.reply_text(f"✅ Set level ke {level} untuk user {target_id}")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
        ctx.user_data.pop("adm_action", None)

    elif action == "set_gems":
        try:
            gems = int(text)
            target_id = int(ctx.user_data.get("adm_target_id"))
            await update_user(target_id, gems=gems)
            await log_admin_action(update.effective_user.id, "set_gems", target_id, str(gems))
            await update.message.reply_text(f"✅ Set gems ke {gems} untuk user {target_id}")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
        ctx.user_data.pop("adm_action", None)

    elif action == "broadcast_msg":
        msg_text = text
        async with get_db() as db:
            rows = await fetchall(db, "SELECT user_id FROM users")
            user_ids = [r["user_id"] for r in rows]

        sent = 0
        failed = 0
        for uid in user_ids:
            try:
                await ctx.bot.send_message(uid, f"📢 Admin Announcement\n\n{msg_text}")
                sent += 1
            except Exception:
                failed += 1

        await log_admin_action(update.effective_user.id, "broadcast", None, msg_text[:100])
        await update.message.reply_text(f"📢 Siaran sent ke {sent} pemain. Gagal: {failed}")
        ctx.user_data.pop("adm_action", None)

    elif action == "add_item_db":
        # Format: key,name,emoji,grow_time,sell_price,xp,level_req,seed_cost
        try:
            parts = text.split(",")
            if len(parts) != 8:
                raise ValueError("Butuh 8 nilai dipisah koma")
            key, name, emoji, grow_time, sell_price, xp, level_req, seed_cost = [p.strip() for p in parts]
            CROPS[key] = {
                "name": name, "emoji": emoji,
                "grow_time": int(grow_time), "sell_price": int(sell_price),
                "xp": int(xp), "level_req": int(level_req), "seed_cost": int(seed_cost)
            }
            await update.message.reply_text(f"✅ Tanaman ditambahkan: {emoji} {name} ke database (runtime saja - tambahkan ke data.py untuk permanen)")
        except Exception as e:
            await update.message.reply_text(f"❌ Format: key,name,emoji,grow_time,sell_price,xp,level_req,seed_cost\nError: {e}")
        ctx.user_data.pop("adm_action", None)


# ─── USER MANAGEMENT ─────────────────────────────────────────────────────────

@admin_only
async def adm_users_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = 0
    # Check if page number in callback data
    if query.data.startswith("adm_users_page_"):
        page = int(query.data.split("_")[3])
    
    per_page = 10
    async with get_db() as db:
        total_row = await fetchone(db, "SELECT COUNT(*) as c FROM users")
        total = total_row["c"]
        rows = await fetchall(db, 
            "SELECT user_id, first_name, display_name, username, level, coins, xp FROM users ORDER BY level DESC, xp DESC LIMIT ? OFFSET ?",
            (per_page, page * per_page)
        )
        users = [dict(r) for r in rows]

    buttons = []
    for i, u in enumerate(users):
        rank = page * per_page + i + 1
        uname = f"@{u['username']}" if u["username"] else f"ID:{u['user_id']}"
        name = u["display_name"] if u.get("display_name") else u["first_name"]
        buttons.append([InlineKeyboardButton(
            f"#{rank} [Lv{u['level']}] {name} {uname} — Rp{u['coins']:,}",
            callback_data=f"adm_user_{u['user_id']}"
        )])

    # Pagination
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"adm_users_page_{page-1}"))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton("▶️ Next", callback_data=f"adm_users_page_{page+1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="adm_panel")])
    
    total_pages = (total + per_page - 1) // per_page
    await query.edit_message_text(
        f"👥 **Semua Pemain** ({total} total)\n"
        f"Halaman {page+1}/{total_pages} — ketuk untuk kelola:",
        reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN
    )

@admin_only
async def adm_user_detail_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = int(query.data.split("_")[2])
    user = await get_user(target_id)
    if not user:
        await query.answer("Pengguna tidak ditemukan!", show_alert=True)
        return

    silo = parse_json_field(user["silo_items"])
    barn = parse_json_field(user["barn_items"])
    text = (
        f"👤 **Pengguna: {user['first_name']}**\n"
        f"🪪 ID: `{user['user_id']}`\n"
        f"👑 Level: {user['level']} | XP: {user['xp']}\n"
        f"💵 Rp{user['coins']:,} | 💎 Permata: {user['gems']}\n"
        f"🌾 Panen: {user['total_harvests']}\n"
        f"📦 Gudang: {sum(silo.values())}/{user['silo_cap']}\n"
        f"🏚 Lumbung: {sum(barn.values())}/{user['barn_cap']}\n"
    )
    buttons = [
        [
            InlineKeyboardButton("💵 Atur Uang", callback_data=f"adm_setcoins_{target_id}"),
            InlineKeyboardButton("💎 Atur Permata", callback_data=f"adm_setgems_{target_id}"),
        ],
        [
            InlineKeyboardButton("👑 Atur Level", callback_data=f"adm_setlevel_{target_id}"),
            InlineKeyboardButton("🎁 Beri Item", callback_data=f"adm_giveitem_{target_id}"),
        ],
        [
            InlineKeyboardButton("🗑️ Reset Pengguna", callback_data=f"adm_resetuser_{target_id}"),
            InlineKeyboardButton("🚫 Ban/Unban", callback_data="noop"),
        ],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="adm_users")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)

@admin_only
async def adm_setcoins_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = int(query.data.split("_")[2])
    ctx.user_data["adm_action"] = "set_coins"
    ctx.user_data["adm_target_id"] = target_id
    await query.edit_message_text(f"💵 Kirim jumlah Rp baru untuk user {target_id}:")

@admin_only
async def adm_setlevel_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = int(query.data.split("_")[2])
    ctx.user_data["adm_action"] = "set_level"
    ctx.user_data["adm_target_id"] = target_id
    await query.edit_message_text(f"👑 Kirim level baru untuk user {target_id}:")

@admin_only
async def adm_setgems_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = int(query.data.split("_")[2])
    ctx.user_data["adm_action"] = "set_gems"
    ctx.user_data["adm_target_id"] = target_id
    await query.edit_message_text(f"💎 Kirim jumlah permata untuk user {target_id}:")

@admin_only
async def adm_giveitem_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = int(query.data.split("_")[2])
    ctx.user_data["adm_target_id"] = target_id

    all_keys = (
        list(CROPS.keys()) + list(UPGRADE_TOOLS.keys()) +
        list(EXPANSION_TOOLS.keys()) + list(CLEARING_TOOLS.keys())
    )
    buttons = []
    row = []
    for key in all_keys[:24]:
        emoji = get_item_emoji(key)
        row.append(InlineKeyboardButton(f"{emoji}{get_item_name(key)}", callback_data=f"adm_give2_{target_id}_{key}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅️ Batal", callback_data=f"adm_user_{target_id}")])
    await query.edit_message_text(f"🎁 Beri item ke user {target_id} — pilih item:", reply_markup=InlineKeyboardMarkup(buttons))

@admin_only
async def adm_give2_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    target_id = int(parts[2])
    item_key = "_".join(parts[3:])
    ctx.user_data["adm_action"] = "give_item_qty"
    ctx.user_data["adm_target_id"] = target_id
    ctx.user_data["adm_give_item"] = item_key
    emoji = get_item_emoji(item_key)
    name = get_item_name(item_key)
    await query.edit_message_text(f"🎁 Beri {emoji} {name} ke user {target_id}\nKirim jumlah:")

@admin_only
async def adm_resetuser_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = int(query.data.split("_")[2])
    ok = await _reset_user_data(target_id)
    if ok:
        await log_admin_action(query.from_user.id, "reset_user_full", target_id, "via UI")
        await query.answer(f"✅ Player {target_id} di-reset full ke nol!", show_alert=True)
    else:
        await query.answer(f"❌ Player {target_id} tidak ditemukan", show_alert=True)


# ─── BROADCAST ────────────────────────────────────────────────────────────────

@admin_only
async def adm_broadcast_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["adm_action"] = "broadcast_msg"
    await query.edit_message_text(
        "📢 **Pesan Siaran**\n\nKirim pesan untuk disiarkan ke SEMUA pemain:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Batal", callback_data="adm_panel")]]),
        parse_mode=ParseMode.MARKDOWN
    )


# ─── LOGS ────────────────────────────────────────────────────────────────────

@admin_only
async def adm_logs_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    async with get_db() as db:
        rows = await fetchall(db, 
            "SELECT * FROM admin_logs ORDER BY created_at DESC LIMIT 20"
        )
        logs = [dict(r) for r in rows]

    if not logs:
        text = "📋 Belum ada aksi admin yang tercatat."
    else:
        lines = ["📋 Aksi Admin Terbaru:\n"]
        for log in logs:
            lines.append(f"• [{log['created_at'][:16]}] Admin {log['admin_id']} → {log['action']} on {log['target_id']}: {log['details']}")
        text = "\n".join(lines)

    await query.edit_message_text(
        text[:4000],
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="adm_panel")]])
    )


# ─── ITEMS DB ─────────────────────────────────────────────────────────────────

@admin_only
async def adm_items_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lines = ["🌾 Tanaman di Database:\n"]
    for k, v in CROPS.items():
        lines.append(f"{v['emoji']} {v['name']} (key: {k}) Lv{v['level_req']} | {v['grow_time']}s | Rp{v['sell_price']}")
    lines.append("\n💡 Buat tambah tanaman baru permanen, pake command /addcrop")

    buttons = [
        [InlineKeyboardButton("⬅️ Kembali", callback_data="adm_panel")],
    ]
    await query.edit_message_text("\n".join(lines)[:4000], reply_markup=InlineKeyboardMarkup(buttons))

@admin_only
async def adm_addcrop_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """DEPRECATED — replaced by /addcrop command. Kept for backward compat."""
    query = update.callback_query
    await query.answer(
        "⚠️ Fitur lama. Pake command /addcrop biar tanaman persist di database!",
        show_alert=True
    )


# ─── GIVE COMMANDS ────────────────────────────────────────────────────────────

@admin_only
async def adm_give_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎁 **Beri Items ke Player**\n\nGunakan perintah:\n`/give <user_id> <item_key> <qty>`\n\nContoh:\n"
        "`/give 123456789 wheat 50`\n`/give 123456789 bolt 10`\n`/give 123456789 axe 5`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="adm_panel")]]),
        parse_mode=ParseMode.MARKDOWN
    )

@admin_only
async def give_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 3:
        await update.message.reply_text("Cara pakai: `/give <user_id> <item_key> <qty>`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        target_id = int(args[0])
        item_key = args[1].lower()
        qty = int(args[2])
    except ValueError:
        await update.message.reply_text("❌ Argumen tidak valid.")
        return

    user = await get_user(target_id)
    if not user:
        await update.message.reply_text(f"❌ Pengguna {target_id} tidak ditemukan.")
        return

    ok, msg = await add_to_inventory(target_id, item_key, qty)
    if ok:
        await log_admin_action(update.effective_user.id, "give_item", target_id, f"{item_key}x{qty}")
        emoji = get_item_emoji(item_key)
        await update.message.reply_text(f"✅ Memberi {qty}x {emoji} {get_item_name(item_key)} ke {user['first_name']} (ID:{target_id})")
        try:
            await ctx.bot.send_message(target_id, f"🎁 Admin memberimu {qty}x {emoji} {get_item_name(item_key)}!")
        except Exception:
            pass
    else:
        await update.message.reply_text(f"❌ {msg}")

@admin_only
async def givecoins_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Cara pakai: `/givecoins <user_id> <amount>`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        target_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid.")
        return

    user = await get_user(target_id)
    if not user:
        await update.message.reply_text(f"❌ Pengguna tidak ditemukan.")
        return

    await update_user(target_id, coins=user["coins"] + amount)
    await log_admin_action(update.effective_user.id, "give_coins", target_id, str(amount))
    await update.message.reply_text(f"✅ Memberi Rp{amount:,} ke {user['first_name']}.")
    try:
        await ctx.bot.send_message(target_id, f"🎁 Admin memberimu Rp{amount:,}!")
    except Exception:
        pass

# ─── SET PHOTO (Admin: reply foto + /setphoto item_key) ─────────────────────

@admin_only
async def setphoto_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin replies to a photo with /setphoto <item_key> to set item emoji/photo."""
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "📸 **Set Foto Item**\n\n"
            "Cara pakai: Reply foto dengan:\n"
            "`/setphoto <item_key>`\n\n"
            "Contoh: `/setphoto wheat`\n\n"
            "Item keys yang tersedia:\n"
            + ", ".join(f"`{k}`" for k in list(CROPS.keys())[:10]) + "...",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    item_key = args[0].lower()

    # Validate item exists
    all_keys = (
        list(CROPS.keys()) + list(UPGRADE_TOOLS.keys()) +
        list(EXPANSION_TOOLS.keys()) + list(CLEARING_TOOLS.keys())
    )
    for bld in BUILDINGS.values():
        all_keys.extend(bld["recipes"].keys())

    if item_key not in all_keys:
        await update.message.reply_text(f"❌ Item `{item_key}` tidak ditemukan.", parse_mode=ParseMode.MARKDOWN)
        return

    # Check if reply to photo
    reply = update.message.reply_to_message
    if not reply or not reply.photo:
        await update.message.reply_text("❌ Reply ke sebuah foto lalu ketik `/setphoto {item_key}`", parse_mode=ParseMode.MARKDOWN)
        return

    # Get photo file_id (largest size)
    photo = reply.photo[-1]
    file_id = photo.file_id

    # Store in game_settings as photo_<item_key>
    await set_setting(f"photo_{item_key}", file_id)
    await log_admin_action(update.effective_user.id, "set_photo", details=f"{item_key}={file_id[:20]}...")

    from game.data import get_item_name, get_item_emoji
    emoji = get_item_emoji(item_key)
    name = get_item_name(item_key)
    await update.message.reply_text(
        f"✅ Foto untuk {emoji} **{name}** (`{item_key}`) berhasil di-set!\n"
        f"File ID: `{file_id[:30]}...`",
        parse_mode=ParseMode.MARKDOWN
    )

@admin_only
async def viewphoto_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin checks which items have photos set."""
    args = ctx.args
    if args:
        # View specific item photo
        item_key = args[0].lower()
        photo_id = await get_setting(f"photo_{item_key}")
        if photo_id:
            from game.data import get_item_name, get_item_emoji
            emoji = get_item_emoji(item_key)
            name = get_item_name(item_key)
            try:
                await update.message.reply_photo(
                    photo=photo_id,
                    caption=f"{emoji} **{name}** (`{item_key}`)\n✅ Foto sudah di-set",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                await update.message.reply_text(f"❌ Gagal load foto: {e}")
        else:
            await update.message.reply_text(f"❌ Item `{item_key}` belum ada foto.", parse_mode=ParseMode.MARKDOWN)
        return

    # List all items with photos
    async with get_db() as db:
        rows = await fetchall(db, "SELECT key, value FROM game_settings WHERE key LIKE 'photo_%'")
        photos = [dict(r) for r in rows]

    if not photos:
        await update.message.reply_text("📸 Belum ada item yang di-set fotonya.\n\nGunakan: Reply foto + `/setphoto <item_key>`", parse_mode=ParseMode.MARKDOWN)
        return

    from game.data import get_item_name, get_item_emoji
    lines = ["📸 **Item dengan Foto:**\n"]
    for p in photos:
        item_key = p["key"].replace("photo_", "")
        emoji = get_item_emoji(item_key)
        name = get_item_name(item_key)
        lines.append(f"✅ {emoji} {name} (`{item_key}`)")

    lines.append(f"\nTotal: {len(photos)} item")
    lines.append("\nLihat foto: `/viewphoto <item_key>`")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

@admin_only
async def delphoto_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin deletes a photo for an item."""
    args = ctx.args
    if not args:
        await update.message.reply_text("Cara pakai: `/delphoto <item_key>`", parse_mode=ParseMode.MARKDOWN)
        return

    item_key = args[0].lower()
    photo_id = await get_setting(f"photo_{item_key}")
    if not photo_id:
        await update.message.reply_text(f"❌ Item `{item_key}` tidak punya foto.", parse_mode=ParseMode.MARKDOWN)
        return

    async with get_db() as db:
        await db.execute("DELETE FROM game_settings WHERE key = ?", (f"photo_{item_key}",))
        await db.commit()

    await log_admin_action(update.effective_user.id, "del_photo", details=item_key)
    from game.data import get_item_name, get_item_emoji
    emoji = get_item_emoji(item_key)
    name = get_item_name(item_key)
    await update.message.reply_text(f"✅ Foto {emoji} **{name}** (`{item_key}`) berhasil dihapus.", parse_mode=ParseMode.MARKDOWN)


# ─── SET GIF (Admin: reply GIF + /setgif item_key) ──────────────────────────
# Buat item rare/spesial yang lu mau punya animasi gerak

@admin_only
async def setgif_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin replies to a GIF/animation with /setgif <item_key>."""
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "🎞️ **Set GIF Item Rare**\n\n"
            "Cara pakai: Reply GIF/animasi dengan:\n"
            "`/setgif <item_key>`\n\n"
            "Contoh: `/setgif strawberry`\n\n"
            "💡 Tip: GIF cocok buat item rare/legendary biar keliatan istimewa.\n"
            "Kalau item punya GIF dan foto, GIF yang dipake.\n\n"
            "Lihat semua item ber-GIF: `/viewgif`\n"
            "Hapus GIF: `/delgif <item_key>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    item_key = args[0].lower()

    # Validate item exists (sama kayak setphoto)
    all_keys = (
        list(CROPS.keys()) + list(UPGRADE_TOOLS.keys()) +
        list(EXPANSION_TOOLS.keys()) + list(CLEARING_TOOLS.keys())
    )
    for bld in BUILDINGS.values():
        all_keys.extend(bld["recipes"].keys())

    if item_key not in all_keys:
        await update.message.reply_text(
            f"❌ Item `{item_key}` tidak ditemukan.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Check if reply to GIF/animation
    reply = update.message.reply_to_message
    if not reply or not reply.animation:
        await update.message.reply_text(
            "❌ Reply ke sebuah GIF/animasi dulu, baru ketik `/setgif <item_key>`\n\n"
            "_Note: Foto biasa pake `/setphoto`. GIF/animasi pake `/setgif`._",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    file_id = reply.animation.file_id

    # Store as gif_<key> in game_settings
    await set_setting(f"gif_{item_key}", file_id)
    await log_admin_action(
        update.effective_user.id, "set_gif",
        details=f"{item_key}={file_id[:20]}..."
    )

    from game.data import get_item_name, get_item_emoji
    emoji = get_item_emoji(item_key)
    name = get_item_name(item_key)
    await update.message.reply_text(
        f"✅ GIF untuk {emoji} **{name}** (`{item_key}`) berhasil di-set!\n"
        f"🎞️ Item ini sekarang tampil dengan animasi gerak.",
        parse_mode=ParseMode.MARKDOWN
    )


@admin_only
async def viewgif_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin checks which items have GIFs set."""
    args = ctx.args
    if args:
        # View specific item GIF
        item_key = args[0].lower()
        gif_id = await get_setting(f"gif_{item_key}")
        if gif_id:
            from game.data import get_item_name, get_item_emoji
            emoji = get_item_emoji(item_key)
            name = get_item_name(item_key)
            try:
                await update.message.reply_animation(
                    animation=gif_id,
                    caption=f"{emoji} **{name}** (`{item_key}`)\n✅ GIF sudah di-set",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                await update.message.reply_text(f"❌ Gagal load GIF: {e}")
        else:
            await update.message.reply_text(
                f"❌ Item `{item_key}` belum ada GIF.",
                parse_mode=ParseMode.MARKDOWN
            )
        return

    # List all items with GIFs
    async with get_db() as db:
        rows = await fetchall(db, "SELECT key, value FROM game_settings WHERE key LIKE 'gif_%'")
        gifs = [dict(r) for r in rows]

    if not gifs:
        await update.message.reply_text(
            "🎞️ Belum ada item ber-GIF.\n\n"
            "Gunakan: Reply GIF + `/setgif <item_key>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    from game.data import get_item_name, get_item_emoji
    lines = ["🎞️ **Item dengan GIF (Rare):**\n"]
    for g in gifs:
        item_key = g["key"].replace("gif_", "")
        emoji = get_item_emoji(item_key)
        name = get_item_name(item_key)
        lines.append(f"✨ {emoji} {name} (`{item_key}`)")

    lines.append(f"\nTotal: {len(gifs)} item rare")
    lines.append("\nLihat GIF: `/viewgif <item_key>`")
    lines.append("Hapus GIF: `/delgif <item_key>`")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


@admin_only
async def delgif_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin deletes a GIF for an item."""
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Cara pakai: `/delgif <item_key>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    item_key = args[0].lower()
    gif_id = await get_setting(f"gif_{item_key}")
    if not gif_id:
        await update.message.reply_text(
            f"❌ Item `{item_key}` tidak punya GIF.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    async with get_db() as db:
        await db.execute("DELETE FROM game_settings WHERE key = ?", (f"gif_{item_key}",))
        await db.commit()

    await log_admin_action(update.effective_user.id, "del_gif", details=item_key)
    from game.data import get_item_name, get_item_emoji
    emoji = get_item_emoji(item_key)
    name = get_item_name(item_key)
    await update.message.reply_text(
        f"✅ GIF {emoji} **{name}** (`{item_key}`) berhasil dihapus.\n"
        f"_(Foto biasa, kalo ada, masih kepake)_",
        parse_mode=ParseMode.MARKDOWN
    )


@admin_only
async def users_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin command to list all users."""
    async with get_db() as db:
        total_row = await fetchone(db, "SELECT COUNT(*) as c FROM users")
        total = total_row["c"]
        rows = await fetchall(db,
            "SELECT user_id, first_name, display_name, username, level, coins, xp, total_harvests, total_sales, created_at "
            "FROM users ORDER BY level DESC, xp DESC LIMIT 20"
        )
        users = [dict(r) for r in rows]

    lines = [f"👥 **Semua Pemain** ({total} total)\n"]
    for i, u in enumerate(users, 1):
        name = u["display_name"] if u.get("display_name") else u["first_name"]
        uname = f"@{u['username']}" if u["username"] else ""
        lines.append(
            f"**#{i}** {name} {uname}\n"
            f"   🪪 `{u['user_id']}`\n"
            f"   👑 Lv{u['level']} | 💵 Rp{u['coins']:,} | 📈 {u['xp']:,} XP\n"
            f"   🌾 {u['total_harvests']} panen | 🚚 {u['total_sales']} jual\n"
        )
    if total > 20:
        lines.append(f"\n_...dan {total - 20} pemain lainnya. Gunakan /admin → 👥 Kelola Pengguna untuk lihat semua._")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

# ─── SET MARKET CHANNEL ─────────────────────────────────────────────────────

@admin_only
async def setchannel_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin sets the market channel for listing broadcasts."""
    args = ctx.args
    if not args:
        current = await get_setting("market_channel")
        status = f"Channel saat ini: `{current}`" if current else "Belum ada channel yang di-set."
        await update.message.reply_text(
            f"📢 **Set Market Channel**\n\n"
            f"{status}\n\n"
            f"Cara pakai:\n"
            f"`/setchannel @namachannel`\n"
            f"`/setchannel -100123456789`\n\n"
            f"Bot harus jadi **admin** di channel tersebut!\n"
            f"Untuk hapus: `/setchannel off`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    channel = args[0].strip()
    if channel.lower() == "off":
        await set_setting("market_channel", "")
        await log_admin_action(update.effective_user.id, "set_channel", details="disabled")
        await update.message.reply_text("✅ Market channel dinonaktifkan.")
        return

    # Test send to channel
    try:
        test_msg = await ctx.bot.send_message(
            chat_id=channel,
            text="✅ **Greena Farm Market** terhubung ke channel ini!\n\nSemua listing pasar akan muncul di sini.",
            parse_mode=ParseMode.MARKDOWN
        )
        await set_setting("market_channel", channel)
        await log_admin_action(update.effective_user.id, "set_channel", details=channel)
        await update.message.reply_text(f"✅ Market channel di-set ke `{channel}`!", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(
            f"❌ Gagal kirim ke channel `{channel}`!\n\n"
            f"Pastikan:\n"
            f"1. Bot sudah jadi **admin** di channel\n"
            f"2. Channel ID/username benar\n\n"
            f"Error: `{e}`",
            parse_mode=ParseMode.MARKDOWN
        )


# ─── ADMIN: TOKO PERMATA & EVENT CODE ───────────────────────────────────────

@admin_only
async def givegems_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text(
            "Cara pakai: `/givegems <user_id> <jumlah>`\n"
            "Contoh: `/givegems 123456789 10`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    try:
        target_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ user_id & jumlah harus angka.")
        return
    from game.gems import give_gems
    ok = await give_gems(target_id, amount)
    if ok:
        await log_admin_action(update.effective_user.id, "give_gems", target_id, str(amount))
        await update.message.reply_text(f"✅ Sukses kasih **{amount}💎** ke user `{target_id}`",
                                        parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"❌ User `{target_id}` tidak ditemukan.",
                                        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def addgemitem_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Format: /addgemitem <harga> <type> <value> <emoji> | <nama> | <deskripsi>
    
    Type:
      coins  → value = jumlah Rp           (contoh: 100000)
      item   → value = item_key:qty        (contoh: wheat:50)
      custom → value = label apa aja, admin proses manual
    
    Contoh:
      /addgemitem 50 coins 100000 💰 | Bonus Rp100rb | Tambahan saldo instant
      /addgemitem 30 item wheat:50 🌾 | Paket Wheat 50 | 50 biji wheat instant
      /addgemitem 100 custom skin_emas 👑 | Skin Petani Emas | Skin eksklusif (manual)
    """
    raw = update.message.text or ""
    parts = raw.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text(
            "**Cara pakai:**\n"
            "`/addgemitem <harga> <type> <value> <emoji> | <nama> | <deskripsi>`\n\n"
            "**Type tersedia:**\n"
            "• `coins` — value = jumlah Rp (cth: `100000`)\n"
            "• `item` — value = `item_key:qty` (cth: `wheat:50`)\n"
            "• `title` — value = `title_key` (otomatis kirim gelar ke pembeli)\n"
            "• `custom` — value = label, admin proses manual\n\n"
            "**Contoh:**\n"
            "`/addgemitem 50 coins 100000 💰 | Bonus 100rb | Saldo Rp100.000`\n"
            "`/addgemitem 30 item wheat:50 🌾 | Paket Wheat | 50 biji wheat`\n"
            "`/addgemitem 100 title petani_emas 🎭 | Title Petani Emas | Gelar VIP`\n"
            "`/addgemitem 100 custom skin_emas 👑 | Skin Emas | Diproses manual`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    body = parts[1]
    pipe_parts = [p.strip() for p in body.split("|")]
    if len(pipe_parts) < 2:
        await update.message.reply_text("❌ Format salah. Pakai `|` buat pisah header dari nama/deskripsi.",
                                        parse_mode=ParseMode.MARKDOWN)
        return

    head = pipe_parts[0].split()
    if len(head) < 4:
        await update.message.reply_text("❌ Header butuh: `<harga> <type> <value> <emoji>`",
                                        parse_mode=ParseMode.MARKDOWN)
        return

    try:
        price = int(head[0])
    except ValueError:
        await update.message.reply_text("❌ Harga harus angka.")
        return
    rtype = head[1].lower()
    if rtype not in ("coins", "item", "custom", "title"):
        await update.message.reply_text("❌ Type harus: `coins`, `item`, `custom`, atau `title`.",
                                        parse_mode=ParseMode.MARKDOWN)
        return
    rvalue = head[2]
    emoji = head[3]
    name = pipe_parts[1]
    description = pipe_parts[2] if len(pipe_parts) > 2 else ""

    try:
        from game.gems import add_gem_item
        item_id = await add_gem_item(name, price, rtype, rvalue, emoji, description)
        await log_admin_action(update.effective_user.id, "add_gem_item",
                               details=f"id={item_id} {name}")
        await update.message.reply_text(
            f"✅ **Item ditambahkan!**\n\n"
            f"ID: `{item_id}`\n"
            f"{emoji} **{name}** — {price}💎\n"
            f"Type: `{rtype}` → `{rvalue}`\n"
            f"Deskripsi: _{description or '-'}_\n\n"
            f"Cek dengan `/listgemitems`",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


@admin_only
async def delgemitem_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text("Cara pakai: `/delgemitem <id>`",
                                        parse_mode=ParseMode.MARKDOWN)
        return
    try:
        item_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID harus angka.")
        return
    from game.gems import delete_gem_item
    ok = await delete_gem_item(item_id)
    if ok:
        await log_admin_action(update.effective_user.id, "del_gem_item", details=str(item_id))
        await update.message.reply_text(f"✅ Item ID `{item_id}` dihapus.",
                                        parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"❌ Item ID `{item_id}` tidak ditemukan.",
                                        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def togglegemitem_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text("Cara pakai: `/togglegemitem <id>`",
                                        parse_mode=ParseMode.MARKDOWN)
        return
    try:
        item_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID harus angka.")
        return
    from game.gems import toggle_gem_item
    ok, state = await toggle_gem_item(item_id)
    if ok:
        await update.message.reply_text(
            f"✅ Item ID `{item_id}` sekarang **{'AKTIF ✅' if state else 'NONAKTIF ❌'}**",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(f"❌ Item ID `{item_id}` tidak ditemukan.",
                                        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def listgemitems_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from game.gems import list_gem_items
    items = await list_gem_items(active_only=False)
    if not items:
        await update.message.reply_text("📭 Belum ada item di toko permata.\n\nTambahin pake `/addgemitem`",
                                        parse_mode=ParseMode.MARKDOWN)
        return
    lines = ["💎 **DAFTAR ITEM TOKO PERMATA**\n━━━━━━━━━━━━━━━━━━━━\n"]
    for it in items:
        status = "✅" if it["active"] else "❌"
        stock = "∞" if it["stock"] < 0 else str(it["stock"])
        lines.append(
            f"{status} `[{it['id']}]` {it['emoji']} **{it['name']}**\n"
            f"   💎 {it['price_gems']} | Stok: {stock} | Type: `{it['reward_type']}`\n"
            f"   Value: `{it['reward_value']}`\n"
        )
    lines.append(
        "\n**Command admin:**\n"
        "`/addgemitem` — tambah item\n"
        "`/delgemitem <id>` — hapus item\n"
        "`/togglegemitem <id>` — aktif/nonaktifkan"
    )
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "\n_(dipotong)_"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def createcode_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 3:
        await update.message.reply_text(
            "**Cara pakai:**\n"
            "`/createcode <KODE> <jumlah_gems> <max_klaim>`\n\n"
            "**Contoh:**\n"
            "`/createcode EVENT2026 10 100`\n"
            "→ Code `EVENT2026` kasih 10💎, max 100 user yang bisa klaim",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    code = args[0]
    try:
        gems = int(args[1])
        max_uses = int(args[2])
    except ValueError:
        await update.message.reply_text("❌ Jumlah gems & max klaim harus angka.")
        return

    from game.gems import create_redeem_code
    ok, msg = await create_redeem_code(code, gems, max_uses, update.effective_user.id)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    if ok:
        await log_admin_action(update.effective_user.id, "create_code",
                               details=f"{code}:{gems}x{max_uses}")


@admin_only
async def delcode_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text("Cara pakai: `/delcode <KODE>`",
                                        parse_mode=ParseMode.MARKDOWN)
        return
    from game.gems import delete_redeem_code
    ok = await delete_redeem_code(args[0])
    if ok:
        await update.message.reply_text(f"✅ Code `{args[0].upper()}` dihapus.",
                                        parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"❌ Code tidak ditemukan.")


@admin_only
async def listcodes_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from game.gems import list_redeem_codes
    codes = await list_redeem_codes()
    if not codes:
        await update.message.reply_text("📭 Belum ada redeem code.\n\nBuat pake `/createcode`",
                                        parse_mode=ParseMode.MARKDOWN)
        return
    lines = ["🎟 **REDEEM CODES AKTIF**\n━━━━━━━━━━━━━━━━━━━━\n"]
    for c in codes:
        full = "🔴 PENUH" if c["uses"] >= c["max_uses"] else "🟢 AKTIF"
        lines.append(
            f"{full} `{c['code']}`\n"
            f"   💎 {c['reward_gems']} per klaim\n"
            f"   📊 {c['uses']}/{c['max_uses']} klaim\n"
        )
    lines.append("\n**Command:**\n`/createcode <kode> <gems> <max>`\n`/delcode <kode>`")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ─── ADMIN: HEWAN CUSTOM ─────────────────────────────────────────────────────

@admin_only
async def addanimal_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Format:
    /addanimal <key> <emoji> <produk_key> <prod_emoji> <waktu_menit> <beli> <jual> <level> | <Nama Hewan> | <Nama Produk>
    
    Contoh:
    /addanimal kuda 🐎 surai 🎀 240 80000 9000 6 | Kuda | Surai Kuda
    /addanimal kelinci 🐰 bulu_halus 🧶 120 25000 4500 4 | Kelinci | Bulu Halus
    """
    raw = update.message.text or ""
    parts = raw.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text(
            "**Cara pakai:**\n"
            "`/addanimal <key> <emoji> <produk_key> <prod_emoji> <menit> <beli> <jual> <level> | Nama Hewan | Nama Produk`\n\n"
            "**Penjelasan:**\n"
            "• `key` — ID unik hewan (huruf kecil, no spasi). cth: `kuda`\n"
            "• `emoji` — emoji hewan. cth: 🐎\n"
            "• `produk_key` — ID produk (huruf kecil). cth: `surai`\n"
            "• `prod_emoji` — emoji produk. cth: 🎀\n"
            "• `menit` — waktu produksi dalam menit. cth: `240` (= 4 jam)\n"
            "• `beli` — harga beli hewan dalam Rp. cth: `80000`\n"
            "• `jual` — harga jual produk per unit. cth: `9000`\n"
            "• `level` — minimum level player buat unlock. cth: `6`\n"
            "• `Nama Hewan` — display name hewan\n"
            "• `Nama Produk` — display name produk\n\n"
            "**Contoh:**\n"
            "`/addanimal kuda 🐎 surai 🎀 240 80000 9000 6 | Kuda | Surai Kuda`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    body = parts[1]
    pipe_parts = [p.strip() for p in body.split("|")]
    if len(pipe_parts) < 3:
        await update.message.reply_text(
            "❌ Format salah. Harus ada 2 tanda `|` buat pisah Nama Hewan & Nama Produk.\n\n"
            "Contoh:\n"
            "`/addanimal kuda 🐎 surai 🎀 240 80000 9000 6 | Kuda | Surai Kuda`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    head = pipe_parts[0].split()
    if len(head) < 8:
        await update.message.reply_text(
            "❌ Header butuh 8 field: `<key> <emoji> <produk> <prod_emoji> <menit> <beli> <jual> <level>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    animal_key = head[0]
    emoji = head[1]
    product_key = head[2]
    prod_emoji = head[3]
    try:
        feed_time = int(head[4]) * 60  # menit -> detik
        buy_cost = int(head[5])
        sell_price = int(head[6])
        level_req = int(head[7])
    except ValueError:
        await update.message.reply_text("❌ Menit/harga/level harus angka.")
        return

    name = pipe_parts[1]
    product_name = pipe_parts[2]

    from game.custom_animals import add_custom_animal
    ok, msg = await add_custom_animal(
        animal_key, name, emoji, product_key, product_name, prod_emoji,
        feed_time, buy_cost, sell_price, level_req, update.effective_user.id
    )
    if ok:
        await log_admin_action(update.effective_user.id, "add_animal",
                               details=f"{animal_key}:{name}")
        await update.message.reply_text(
            f"✅ **Hewan ditambahkan!**\n\n"
            f"{emoji} **{name}** (`{animal_key}`)\n"
            f"📦 Produk: {prod_emoji} {product_name}\n"
            f"⏱ Produksi: {feed_time//60} menit\n"
            f"💵 Beli: Rp{buy_cost:,}\n"
            f"💵 Jual produk: Rp{sell_price:,}/unit\n"
            f"🔒 Level: {level_req}\n\n"
            f"Player Lv{level_req}+ udah bisa beli di menu Hewan!",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def delanimal_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Cara pakai: `/delanimal <key>`\nContoh: `/delanimal kuda`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    from game.custom_animals import delete_custom_animal
    ok, msg = await delete_custom_animal(args[0])
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    if ok:
        await log_admin_action(update.effective_user.id, "del_animal", details=args[0])


@admin_only
async def listanimals_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from game.custom_animals import list_custom_animals
    from game.data import ANIMALS
    custom = await list_custom_animals()

    lines = ["🐾 **DAFTAR SEMUA HEWAN**\n━━━━━━━━━━━━━━━━━━━━\n"]
    lines.append("**🔧 Default (hardcoded, nggak bisa dihapus):**")
    custom_keys = {c["animal_key"] for c in custom}
    for k, v in ANIMALS.items():
        if k in custom_keys:
            continue
        lines.append(
            f"  {v['emoji']} `{k}` — {v['name']} | "
            f"Lv{v['level_req']} | Rp{v['buy_cost']:,}"
        )

    lines.append("\n**✏️ Custom (bisa dihapus pake `/delanimal`):**")
    if not custom:
        lines.append("  _(belum ada)_")
    else:
        for c in custom:
            lines.append(
                f"  {c['emoji']} `{c['animal_key']}` — {c['name']} | "
                f"Lv{c['level_req']} | Rp{c['buy_cost']:,}\n"
                f"      → {c['prod_emoji']} {c['product_name']} (Rp{c['sell_price']:,}/unit, {c['feed_time']//60}m)"
            )

    lines.append(
        "\n**Command admin:**\n"
        "`/addanimal` — tambah hewan baru\n"
        "`/delanimal <key>` — hapus hewan custom"
    )
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "\n_(dipotong)_"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ─── ADMIN: TANAMAN CUSTOM ──────────────────────────────────────────────────

@admin_only
async def addcrop_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Format:
    /addcrop <key> <emoji> <menit> <harga_benih> <harga_jual> <xp> <level> | <Nama Tanaman>
    
    Contoh:
    /addcrop kopi ☕ 480 8000 16000 18 12 | Kopi
    /addcrop teh 🍵 240 4000 9000 10 8 | Daun Teh
    """
    raw = update.message.text or ""
    parts = raw.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text(
            "**Cara pakai:**\n"
            "`/addcrop <key> <emoji> <menit> <benih> <jual> <xp> <level> | Nama Tanaman`\n\n"
            "**Contoh:**\n"
            "`/addcrop kopi ☕ 480 8000 16000 18 12 | Kopi`\n"
            "→ Key `kopi`, tumbuh 480 menit (8 jam), benih Rp8rb, jual Rp16rb, +18 XP, Lv12",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    body = parts[1]
    pipe_parts = [p.strip() for p in body.split("|")]
    if len(pipe_parts) < 2:
        await update.message.reply_text("❌ Format salah. Pakai `|` buat pisah header dari Nama.",
                                        parse_mode=ParseMode.MARKDOWN)
        return

    head = pipe_parts[0].split()
    if len(head) < 7:
        await update.message.reply_text(
            "❌ Header butuh 7 field: `<key> <emoji> <menit> <benih> <jual> <xp> <level>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    crop_key = head[0]
    emoji = head[1]
    try:
        grow_time = int(head[2]) * 60
        seed_cost = int(head[3])
        sell_price = int(head[4])
        xp = int(head[5])
        level_req = int(head[6])
    except ValueError:
        await update.message.reply_text("❌ Menit/harga/xp/level harus angka.")
        return

    name = pipe_parts[1]

    from game.custom_crops import add_custom_crop
    ok, msg = await add_custom_crop(crop_key, name, emoji, grow_time,
                                     seed_cost, sell_price, xp, level_req,
                                     update.effective_user.id)
    if ok:
        await log_admin_action(update.effective_user.id, "add_crop", details=f"{crop_key}:{name}")
        await update.message.reply_text(
            f"✅ **Tanaman ditambahkan!**\n\n"
            f"{emoji} **{name}** (`{crop_key}`)\n"
            f"⏱ Tumbuh: {grow_time//60} menit\n"
            f"💵 Benih: Rp{seed_cost:,}\n"
            f"💵 Jual: Rp{sell_price:,}\n"
            f"⭐ XP: +{xp}\n"
            f"🔒 Level: {level_req}\n\n"
            f"Player Lv{level_req}+ langsung bisa nanem!",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def delcrop_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text("Cara pakai: `/delcrop <key>`",
                                        parse_mode=ParseMode.MARKDOWN)
        return
    from game.custom_crops import delete_custom_crop
    ok, msg = await delete_custom_crop(args[0])
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    if ok:
        await log_admin_action(update.effective_user.id, "del_crop", details=args[0])


@admin_only
async def listcrops_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from game.custom_crops import list_custom_crops
    from game.data import CROPS
    custom = await list_custom_crops()
    custom_keys = {c["crop_key"] for c in custom}

    lines = ["🌾 **DAFTAR SEMUA TANAMAN**\n━━━━━━━━━━━━━━━━━━━━\n"]
    lines.append("**🔧 Default:**")
    for k, v in CROPS.items():
        if k in custom_keys:
            continue
        lines.append(f"  {v['emoji']} `{k}` — {v['name']} | Lv{v['level_req']}")

    lines.append("\n**✏️ Custom:**")
    if not custom:
        lines.append("  _(belum ada)_")
    else:
        for c in custom:
            lines.append(
                f"  {c['emoji']} `{c['crop_key']}` — {c['name']} | "
                f"Lv{c['level_req']} | {c['grow_time']//60}m | "
                f"Rp{c['seed_cost']:,}→{c['sell_price']:,}"
            )

    lines.append("\n**Command:** `/addcrop`, `/delcrop <key>`")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "\n_(dipotong)_"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ─── ADMIN: RESEP PABRIK CUSTOM ─────────────────────────────────────────────

@admin_only
async def addrecipe_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Format:
    /addrecipe <pabrik> <recipe_key> <emoji> <inputs> <menit> <harga_jual> <xp> | <Nama Produk>
    
    inputs format: item1:qty1,item2:qty2
    
    Contoh:
    /addrecipe kitchen kopi_hitam ☕ kopi:2 30 25000 15 | Kopi Hitam
    /addrecipe dairy susu_kuda 🥛 surai:3,milk:2 120 45000 25 | Susu Kuda
    """
    raw = update.message.text or ""
    parts = raw.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text(
            "**Cara pakai:**\n"
            "`/addrecipe <pabrik> <recipe_key> <emoji> <inputs> <menit> <jual> <xp> | Nama Produk`\n\n"
            "**`inputs` format:** `item:qty,item:qty`\n"
            "cth: `kopi:2` atau `kopi:2,milk:1,honey:1`\n\n"
            "**Pabrik yang ada:** bakery, feed_mill, dairy, textile_mill, kitchen\n"
            "_(atau pabrik lain yang admin bikin nanti)_\n\n"
            "**Contoh:**\n"
            "`/addrecipe kitchen kopi_hitam ☕ kopi:2 30 25000 15 | Kopi Hitam`\n"
            "`/addrecipe dairy yogurt_surai 🥛 surai:3,milk:2 120 45000 25 | Yogurt Surai`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    body = parts[1]
    pipe_parts = [p.strip() for p in body.split("|")]
    if len(pipe_parts) < 2:
        await update.message.reply_text(
            "❌ Format salah. Pakai `|` buat pisah header dari Nama Produk.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    head = pipe_parts[0].split()
    if len(head) < 7:
        await update.message.reply_text(
            "❌ Header butuh 7 field: `<pabrik> <recipe_key> <emoji> <inputs> <menit> <jual> <xp>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    building_key = head[0].lower()
    recipe_key = head[1].lower()
    emoji = head[2]
    inputs_raw = head[3]
    try:
        time_seconds = int(head[4]) * 60
        sell_price = int(head[5])
        xp = int(head[6])
    except ValueError:
        await update.message.reply_text("❌ Menit/harga/xp harus angka.")
        return

    # Parse inputs: "kopi:2,milk:1" → {"kopi": 2, "milk": 1}
    inputs = {}
    try:
        for pair in inputs_raw.split(","):
            ik, qty = pair.split(":")
            inputs[ik.strip()] = int(qty)
    except Exception:
        await update.message.reply_text(
            "❌ Format inputs salah. Contoh benar: `kopi:2` atau `kopi:2,milk:1`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    name = pipe_parts[1]

    from game.custom_recipes import add_custom_recipe
    ok, msg = await add_custom_recipe(building_key, recipe_key, name, emoji,
                                       inputs, time_seconds, sell_price, xp,
                                       update.effective_user.id)
    if ok:
        await log_admin_action(update.effective_user.id, "add_recipe",
                               details=f"{building_key}:{recipe_key}")
        inputs_display = " + ".join(f"{q}x {k}" for k, q in inputs.items())
        await update.message.reply_text(
            f"✅ **Resep ditambahkan!**\n\n"
            f"{emoji} **{name}** (`{recipe_key}`)\n"
            f"🏭 Pabrik: `{building_key}`\n"
            f"📥 Bahan: {inputs_display}\n"
            f"⏱ Produksi: {time_seconds//60} menit\n"
            f"💵 Jual: Rp{sell_price:,}\n"
            f"⭐ XP: +{xp}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def delrecipe_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text("Cara pakai: `/delrecipe <recipe_key>`",
                                        parse_mode=ParseMode.MARKDOWN)
        return
    from game.custom_recipes import delete_custom_recipe
    ok, msg = await delete_custom_recipe(args[0])
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    if ok:
        await log_admin_action(update.effective_user.id, "del_recipe", details=args[0])


@admin_only
async def listrecipes_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from game.custom_recipes import list_custom_recipes
    from game.data import BUILDINGS
    custom = await list_custom_recipes()
    custom_keys = {c["recipe_key"] for c in custom}

    lines = ["🏭 **DAFTAR RESEP PABRIK**\n━━━━━━━━━━━━━━━━━━━━\n"]
    for bk, bv in BUILDINGS.items():
        lines.append(f"\n**{bv['emoji']} {bv['name']}** (`{bk}`)")
        for rk, rv in bv["recipes"].items():
            is_custom = rk in custom_keys
            marker = "✏️" if is_custom else "🔧"
            ins = " + ".join(f"{q}x{k}" for k, q in rv["inputs"].items())
            lines.append(
                f"  {marker} `{rk}` — `{ins}` → Rp{rv['sell_price']:,} "
                f"({rv['time']//60}m, +{rv['xp']}xp)"
            )

    lines.append("\n🔧 = default, ✏️ = custom (bisa dihapus)")
    lines.append("**Command:** `/addrecipe`, `/delrecipe <key>`")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "\n_(dipotong)_"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ─── ADMIN: TITLE / GELAR COSMETIC ───────────────────────────────────────────

@admin_only
async def addtitle_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Format:
    /addtitle <key> | <Display Text> | <Deskripsi>
    
    Contoh:
    /addtitle petani_emas | 👑 Petani Emas | Gelar eksklusif VIP
    /addtitle juragan | 💼 Juragan | Title untuk player sukses
    /addtitle legenda | 🏆 Legenda Greena | Top player lifetime
    """
    raw = update.message.text or ""
    parts = raw.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text(
            "**Cara pakai:**\n"
            "`/addtitle <key> | <Display Text> | <Deskripsi>`\n\n"
            "**Penjelasan:**\n"
            "• `key` — ID unik (huruf kecil, no spasi)\n"
            "• `Display Text` — teks gelar yang muncul di profil (boleh pake emoji)\n"
            "• `Deskripsi` — penjelasan singkat\n\n"
            "**Contoh:**\n"
            "`/addtitle petani_emas | 👑 Petani Emas | Gelar eksklusif VIP`\n"
            "`/addtitle juragan | 💼 Juragan | Title untuk player sukses`\n"
            "`/addtitle legenda | 🏆 Legenda Greena | Top player lifetime`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    body = parts[1]
    pipe_parts = [p.strip() for p in body.split("|")]
    if len(pipe_parts) < 2:
        await update.message.reply_text(
            "❌ Format salah. Pakai `|` buat pisah key, display, dan deskripsi.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    title_key = pipe_parts[0].split()[0] if pipe_parts[0] else ""
    display = pipe_parts[1]
    description = pipe_parts[2] if len(pipe_parts) > 2 else ""

    if not title_key or not display:
        await update.message.reply_text("❌ Key dan display text wajib diisi.")
        return

    from game.titles import add_title
    ok, msg = await add_title(title_key, display, description,
                               update.effective_user.id)
    if ok:
        await log_admin_action(update.effective_user.id, "add_title",
                               details=f"{title_key}:{display}")
        await update.message.reply_text(
            f"✅ **Title ditambahkan!**\n\n"
            f"Key: `{title_key}`\n"
            f"Display: {display}\n"
            f"Deskripsi: _{description or '-'}_\n\n"
            f"Cara kasih ke player:\n"
            f"1. Jual di toko permata: `/addgemitem <harga> title {title_key} 🎭 | Nama | Desc`\n"
            f"2. Kasih langsung: `/givetitle <user_id> {title_key}`",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def deltitle_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text("Cara pakai: `/deltitle <key>`",
                                        parse_mode=ParseMode.MARKDOWN)
        return
    from game.titles import delete_title
    ok = await delete_title(args[0])
    if ok:
        await log_admin_action(update.effective_user.id, "del_title", details=args[0])
        await update.message.reply_text(
            f"✅ Title `{args[0]}` dihapus.\n"
            f"_(Semua user yang punya title ini otomatis ke-unequip)_",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(f"❌ Title `{args[0]}` tidak ditemukan.",
                                        parse_mode=ParseMode.MARKDOWN)


@admin_only
async def listtitles_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from game.titles import list_all_titles
    titles = await list_all_titles()
    if not titles:
        await update.message.reply_text(
            "📭 Belum ada title.\n\nBikin pake `/addtitle`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    lines = ["🎭 **DAFTAR TITLE / GELAR**\n━━━━━━━━━━━━━━━━━━━━\n"]
    for t in titles:
        lines.append(
            f"`{t['title_key']}` — {t['display']}\n"
            f"  _{t['description'] or '-'}_\n"
        )
    lines.append("\n**Command:**")
    lines.append("`/addtitle` — tambah title")
    lines.append("`/deltitle <key>` — hapus title")
    lines.append("`/givetitle <user_id> <key>` — kasih title langsung")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "\n_(dipotong)_"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def givetitle_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text(
            "Cara pakai: `/givetitle <user_id> <title_key>`\n"
            "Contoh: `/givetitle 123456789 petani_emas`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ user_id harus angka.")
        return
    title_key = args[1]

    from game.titles import give_title_to_user
    ok, msg = await give_title_to_user(target_id, title_key)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    if ok:
        await log_admin_action(update.effective_user.id, "give_title",
                               target_id, title_key)
        try:
            from game.titles import get_title
            title = await get_title(title_key)
            await ctx.bot.send_message(
                target_id,
                f"🎭 Selamat! Admin memberimu gelar **{title['display']}**\n\n"
                f"Buka `/mytitles` buat pasang gelar kamu.",
                parse_mode="Markdown"
            )
        except Exception:
            pass


# ─── RESET PLAYER DATA (Full Reset) ──────────────────────────────────────────

async def _reset_user_data(user_id: int) -> bool:
    """
    Full reset 1 user balik ke kondisi awal (kayak baru /start).
    Reset:
    - coins (50k), gems (5), xp/level (0/1)
    - plots/pens/buildings/orders/listings/obstacles → DELETE all
    - silo/barn/land items → kosong {}
    - title koleksi → DELETE all
    - last_daily → null
    - total_harvests/sales → 0
    Disimpen:
    - user_id, username, first_name, display_name, created_at
    """
    async with get_db() as db:
        # Cek user ada
        u = await fetchone(db, "SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not u:
            return False

        # Delete user-related rows dari semua tabel
        await db.execute("DELETE FROM plots WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM animal_pens WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM buildings WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM orders WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM market_listings WHERE seller_id = ?", (user_id,))
        await db.execute("DELETE FROM obstacles WHERE user_id = ?", (user_id,))
        # Title koleksi (kalau tabel ada)
        try:
            await db.execute("DELETE FROM user_titles WHERE user_id = ?", (user_id,))
        except Exception:
            pass

        # Re-create starter rows kayak user baru daftar
        # 8 plots kosong + 2 animal_pens kosong (sama kayak create_user)
        for i in range(8):
            await db.execute(
                "INSERT INTO plots (user_id, slot, status) VALUES (?, ?, 'empty')",
                (user_id, i)
            )
        for i in range(2):
            await db.execute(
                "INSERT INTO animal_pens (user_id, slot, status) VALUES (?, ?, 'empty')",
                (user_id, i)
            )

        # Reset row di users table ke default
        await db.execute("""
            UPDATE users SET
                coins = 50000, gems = 5,
                xp = 0, level = 1,
                plots = 8, animal_pens = 2,
                silo_cap = 100, barn_cap = 50,
                silo_level = 1, barn_level = 1,
                silo_items = '{}', barn_items = '{}', land_items = '{}',
                last_daily = NULL,
                total_harvests = 0, total_sales = 0,
                equipped_title = ''
            WHERE user_id = ?
        """, (user_id,))
        await db.commit()
    return True


@admin_only
async def resetuser_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Reset 1 player ke nol (hard reset).
    Format: /resetuser <user_id>
    """
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "🗑️ **Reset Player ke Nol**\n\n"
            "Format: `/resetuser <user_id>`\n\n"
            "Contoh: `/resetuser 123456789`\n\n"
            "⚠️ **Yang di-reset:**\n"
            "• Coins → Rp50.000\n"
            "• Permata → 5\n"
            "• Level/XP → Lv1, 0 XP\n"
            "• Semua tanaman, hewan, pabrik → kosong\n"
            "• Semua item gudang/lumbung → kosong\n"
            "• Listing pasar, pesanan → dihapus\n"
            "• Title koleksi → dihapus\n\n"
            "✅ Yang DISIMPAN: nama, ID, username, tanggal join",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ user_id harus angka.")
        return

    ok = await _reset_user_data(target_id)
    if not ok:
        await update.message.reply_text(
            f"❌ User `{target_id}` tidak ditemukan.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    await log_admin_action(update.effective_user.id, "reset_user_full",
                           target_id, "full hard reset")
    await update.message.reply_text(
        f"✅ **Player `{target_id}` berhasil di-reset!**\n\n"
        f"Semua progress dihapus, balik ke kondisi awal seperti baru daftar.",
        parse_mode=ParseMode.MARKDOWN
    )

    # Notif ke player yang di-reset
    try:
        await ctx.bot.send_message(
            target_id,
            "⚠️ Akun kamu telah di-reset oleh admin.\n\n"
            "Semua progress dihapus dan kamu mulai dari awal lagi.\n"
            "Ketik /start untuk mulai bermain kembali."
        )
    except Exception:
        pass


@admin_only
async def resetall_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    NUCLEAR OPTION — reset SEMUA player ke nol.
    Butuh konfirmasi: /resetall CONFIRM
    """
    args = ctx.args

    if not args or args[0] != "CONFIRM":
        async with get_db() as db:
            row = await fetchone(db, "SELECT COUNT(*) as c FROM users")
            total = row["c"]

        await update.message.reply_text(
            "💀 **RESET SEMUA PLAYER**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ Ini akan **MERESET {total} PLAYER** ke kondisi awal!\n\n"
            "**Yang dihapus untuk SEMUA player:**\n"
            "• Semua coins, permata, XP, level\n"
            "• Semua tanaman, hewan, pabrik\n"
            "• Semua item gudang & lumbung\n"
            "• Semua listing pasar, pesanan\n"
            "• Semua title koleksi\n\n"
            "**Yang DISIMPAN:**\n"
            "• Nama & ID player\n"
            "• Custom hewan/tanaman/resep yang lu bikin\n"
            "• Title definition (cuma koleksi player yang dihapus)\n"
            "• Toko permata & event code\n\n"
            "🛑 **Aksi ini TIDAK BISA di-undo!**\n\n"
            "Kalau yakin, ketik:\n"
            "`/resetall CONFIRM`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Konfirmasi diterima — eksekusi
    async with get_db() as db:
        rows = await fetchall(db, "SELECT user_id FROM users")
        user_ids = [r["user_id"] for r in rows]

    success = 0
    failed = 0
    for uid in user_ids:
        try:
            ok = await _reset_user_data(uid)
            if ok:
                success += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    await log_admin_action(
        update.effective_user.id, "reset_all_players", None,
        f"success={success} failed={failed}"
    )

    await update.message.reply_text(
        f"💀 **RESET ALL SELESAI**\n\n"
        f"✅ Berhasil di-reset: {success} player\n"
        f"❌ Gagal: {failed} player\n\n"
        f"Semua player mulai dari nol lagi.",
        parse_mode=ParseMode.MARKDOWN
    )

    # Broadcast notif (best-effort, jangan crash kalau ada user yang block)
    notif_sent = 0
    for uid in user_ids:
        try:
            await ctx.bot.send_message(
                uid,
                "⚠️ SERVER RESET\n\n"
                "Semua data player Greena Farm telah di-reset oleh admin.\n"
                "Kamu mulai dari awal lagi.\n\n"
                "Ketik /start untuk mulai bermain."
            )
            notif_sent += 1
        except Exception:
            pass

    if notif_sent > 0:
        await update.message.reply_text(
            f"📢 Notif terkirim ke {notif_sent} player."
        )


# ─── ADMIN: ADD CUSTOM ORDER ─────────────────────────────────────────────────

@admin_only
async def addorder_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Nambahin pesanan custom ke 1 player.
    Format:
    /addorder <user_id> <reward_coins> <reward_xp> <item1:qty1,item2:qty2,...>

    Contoh:
    /addorder 123456789 50000 50 wheat:10,egg:5,bread:3
    """
    args = ctx.args
    if len(args) < 4:
        await update.message.reply_text(
            "📦 **Tambah Pesanan Custom**\n\n"
            "Format:\n"
            "`/addorder <user_id> <reward_coins> <reward_xp> <items>`\n\n"
            "Contoh items format: `wheat:10,egg:5,bread:3`\n\n"
            "Contoh lengkap:\n"
            "`/addorder 123456789 50000 50 wheat:10,egg:5,bread:3`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        target_id = int(args[0])
        reward_coins = int(args[1])
        reward_xp = int(args[2])
    except ValueError:
        await update.message.reply_text("❌ user_id, reward_coins, reward_xp harus angka.")
        return

    # Parse items (gabungin args[3:] biar bisa di-split dengan spasi atau komma)
    items_str = " ".join(args[3:])
    items_dict = {}
    try:
        for part in items_str.replace(" ", "").split(","):
            if not part:
                continue
            k, v = part.split(":")
            items_dict[k.strip().lower()] = int(v)
    except Exception:
        await update.message.reply_text(
            "❌ Format items salah.\n"
            "Pakai: `item1:qty1,item2:qty2`\n"
            "Contoh: `wheat:10,egg:5`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    from game.engine import admin_add_custom_order
    ok, msg = await admin_add_custom_order(target_id, items_dict, reward_coins, reward_xp)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    # Notif ke target player
    if ok:
        try:
            items_str = ", ".join([f"{v}x {k}" for k, v in items_dict.items()])
            await ctx.bot.send_message(
                target_id,
                f"📦 **PESANAN BARU DARI ADMIN!**\n\n"
                f"Items: {items_str}\n"
                f"💵 Reward: Rp{reward_coins:,}\n"
                f"⭐ XP: {reward_xp}\n\n"
                f"Cek di 🚚 Pesanan!",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass


@admin_only
async def addorderall_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Broadcast pesanan custom ke SEMUA player.
    Format:
    /addorderall <reward_coins> <reward_xp> <item1:qty1,item2:qty2,...>
    """
    args = ctx.args
    if len(args) < 3:
        await update.message.reply_text(
            "📢 **Broadcast Pesanan Custom**\n\n"
            "Format:\n"
            "`/addorderall <reward_coins> <reward_xp> <items>`\n\n"
            "Contoh:\n"
            "`/addorderall 100000 100 wheat:20,egg:10,milk:5`\n\n"
            "⚠️ Ini nambah pesanan ke SEMUA player!",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        reward_coins = int(args[0])
        reward_xp = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ reward_coins & reward_xp harus angka.")
        return

    items_str = " ".join(args[2:])
    items_dict = {}
    try:
        for part in items_str.replace(" ", "").split(","):
            if not part:
                continue
            k, v = part.split(":")
            items_dict[k.strip().lower()] = int(v)
    except Exception:
        await update.message.reply_text(
            "❌ Format items salah. Pakai: `item1:qty1,item2:qty2`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    from game.engine import admin_add_order_to_all
    count, msg = await admin_add_order_to_all(items_dict, reward_coins, reward_xp)
    await update.message.reply_text(msg)

    # Notif ke semua player
    if count > 0:
        items_display = ", ".join([f"{v}x {k}" for k, v in items_dict.items()])
        from database.db import get_db, fetchall
        async with get_db() as db:
            users = await fetchall(db, "SELECT user_id FROM users")
        sent = 0
        for u in users:
            try:
                await ctx.bot.send_message(
                    u["user_id"],
                    f"🎉 **PESANAN EVENT!**\n\n"
                    f"Admin baru aja nambah pesanan khusus buat semua player!\n\n"
                    f"📦 Items: {items_display}\n"
                    f"💵 Reward: Rp{reward_coins:,}\n"
                    f"⭐ XP: {reward_xp}\n\n"
                    f"Cek di 🚚 Pesanan sekarang!",
                    parse_mode=ParseMode.MARKDOWN
                )
                sent += 1
            except Exception:
                pass
        await update.message.reply_text(f"📢 Notif terkirim ke {sent}/{count} player.")


# ─── ADMIN: ADD BUILDING SLOT ────────────────────────────────────────────────

@admin_only
async def addslot_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Nambahin slot pabrik ke player. Max 6 slot.
    Format: /addslot <user_id> <building_key>

    Contoh: /addslot 123456789 bakery
    """
    args = ctx.args
    if len(args) < 2:
        from game.data import BUILDINGS
        bld_list = ", ".join(f"`{k}`" for k in BUILDINGS.keys())
        await update.message.reply_text(
            "📦 **Tambah Slot Pabrik**\n\n"
            "Format:\n"
            "`/addslot <user_id> <building_key>`\n\n"
            "Contoh:\n"
            "`/addslot 123456789 bakery`\n\n"
            f"**Building keys:** {bld_list}\n\n"
            "⚠️ Max 6 slot per pabrik per player.\n"
            "⚠️ Player harus udah punya pabrik ini dulu.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ user_id harus angka.")
        return

    building_key = args[1].lower().strip()

    from game.engine import admin_add_building_slot
    ok, msg = await admin_add_building_slot(target_id, building_key)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    # Notif ke target player kalau sukses
    if ok:
        try:
            from game.data import BUILDINGS
            bld = BUILDINGS.get(building_key, {})
            await ctx.bot.send_message(
                target_id,
                f"🎁 **SLOT PABRIK BARU DARI ADMIN!**\n\n"
                f"{bld.get('emoji','🏭')} **{bld.get('name','Pabrik')}** dapet +1 slot produksi!\n\n"
                f"Cek di 🏭 Pabrik sekarang, kamu bisa produksi lebih banyak barang barengan!",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass


# ─── ADMIN: EVENT SYSTEM ─────────────────────────────────────────────────────

@admin_only
async def event_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Bikin event bonus multiplier coin/xp.
    Format:
    /event <coin_mult> <xp_mult> <duration_hours> <name> | <description>

    Contoh:
    /event 2 2 24 Weekend Bonus | Double Rp & XP buat weekend!
    /event 1.5 3 12 XP Rush | XP 3x selama 12 jam
    """
    args_raw = " ".join(ctx.args) if ctx.args else ""
    if not args_raw or "|" not in args_raw:
        await update.message.reply_text(
            "🎉 **Bikin Event Baru**\n\n"
            "Format:\n"
            "`/event <coin_mult> <xp_mult> <jam> <nama> | <deskripsi>`\n\n"
            "Contoh:\n"
            "`/event 2 2 24 Weekend Bonus | Double Rp & XP selama 24 jam!`\n"
            "`/event 1.5 3 12 XP Rush | XP 3x selama 12 jam`\n\n"
            "⚠️ Multiplier harus ≥ 1.0\n"
            "⚠️ Durasi max 168 jam (7 hari)",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Split di tanda | untuk pisahin header dari description
    header_part, _, description = args_raw.partition("|")
    description = description.strip() or "Event bonus dari admin"

    parts = header_part.strip().split(None, 3)
    if len(parts) < 4:
        await update.message.reply_text(
            "❌ Format salah.\n"
            "Contoh: `/event 2 2 24 Weekend Bonus | Double Rp & XP!`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        coin_mult = float(parts[0])
        xp_mult = float(parts[1])
        duration = int(parts[2])
        name = parts[3].strip()
    except ValueError:
        await update.message.reply_text(
            "❌ coin_mult & xp_mult harus angka (desimal), duration harus angka bulat."
        )
        return

    if not name:
        await update.message.reply_text("❌ Nama event gak boleh kosong.")
        return

    from game.engine import admin_create_event
    admin_user = update.effective_user
    ok, msg, event_info = await admin_create_event(
        name, description, coin_mult, xp_mult, duration, admin_user.id
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    # Broadcast notif ke semua player
    if ok:
        from database.db import get_db, fetchall
        async with get_db() as db:
            users = await fetchall(db, "SELECT user_id FROM users")

        notif_text = (
            f"🎉 **EVENT DIMULAI!**\n\n"
            f"**{name}**\n"
            f"_{description}_\n\n"
            f"💰 Coin: **{coin_mult}x**\n"
            f"⭐ XP: **{xp_mult}x**\n"
            f"⏰ Durasi: **{duration} jam**\n\n"
            f"Buruan main sekarang! Bonus jalan otomatis 🚀"
        )
        sent = 0
        for u in users:
            try:
                await ctx.bot.send_message(
                    u["user_id"], notif_text, parse_mode=ParseMode.MARKDOWN
                )
                sent += 1
            except Exception:
                pass
        await update.message.reply_text(f"📢 Notif event terkirim ke {sent}/{len(users)} player.")


@admin_only
async def stopevent_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Stop event secara manual. Format: /stopevent <event_id>"""
    args = ctx.args
    if len(args) < 1:
        await update.message.reply_text(
            "🛑 **Stop Event**\n\n"
            "Format: `/stopevent <event_id>`\n"
            "Cek ID event pake `/listevents`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        event_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ event_id harus angka.")
        return

    from game.engine import admin_stop_event
    ok, msg = await admin_stop_event(event_id)
    await update.message.reply_text(msg)

    # Broadcast notif pas event stop
    if ok:
        from database.db import get_db, fetchall
        async with get_db() as db:
            users = await fetchall(db, "SELECT user_id FROM users")
        for u in users:
            try:
                await ctx.bot.send_message(
                    u["user_id"],
                    f"🏁 **Event Berakhir**\n\n{msg}\n\nTerima kasih udah ikut event!",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass


@admin_only
async def listevents_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """List event yang lagi aktif."""
    from game.engine import get_active_events
    events = await get_active_events()
    if not events:
        await update.message.reply_text("📭 Tidak ada event aktif.")
        return

    lines = ["🎉 **Event Aktif**\n"]
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    for e in events:
        ends = e.get("_ends_dt")
        if ends:
            remaining = ends - now
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            time_left = f"{hours}h {minutes}m"
        else:
            time_left = "?"
        lines.append(
            f"**ID {e['id']}** — {e['name']}\n"
            f"  💰 Coin: {e['coin_multiplier']}x | ⭐ XP: {e['xp_multiplier']}x\n"
            f"  ⏰ Sisa: {time_left}\n"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
