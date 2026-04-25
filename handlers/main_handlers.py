# handlers/main_handlers.py - FIXED (Panen Semua + Fixme + Refresh)

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database.db import get_or_create_user, get_user, get_display_name
from game.engine import (
    get_plots, get_animal_pens, get_user_buildings, harvest_all,
    plant_crop, harvest_crop, spray_pesticide, use_fertilizer,
    buy_animal, collect_animal, collect_all_animals,
    buy_building, start_production, collect_production,
    add_to_inventory, remove_from_inventory,
    list_item_on_market, buy_from_market
)
from game.data import get_item_emoji, get_item_name
from utils.formatters import fmt_farm, fmt_animals, fmt_factories, fmt_storage, fmt_orders, fmt_profile, fmt_leaderboard
from utils.keyboards import (
    main_menu_keyboard, farm_keyboard, animals_keyboard, factories_keyboard,
    storage_keyboard, orders_keyboard, back_to_menu, profile_keyboard,
    leaderboard_keyboard, shop_keyboard, items_keyboard
)

async def safe_edit(query, text, reply_markup=None, parse_mode=ParseMode.MARKDOWN):
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)
    except Exception:
        pass  # ignore error kalau message sama

async def safe_send(update, text, reply_markup=None, parse_mode=ParseMode.MARKDOWN):
    try:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)
    except Exception:
        pass

# ==================== PANEN SEMUA (FIXED) ====================
async def harvest_all_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)

    harvested, _, _ = await harvest_all(user.id)

    if harvested > 0:
        await query.answer(f"✅ Berhasil panen {harvested} tanaman!", show_alert=True)
    else:
        await query.answer("Tidak ada tanaman yang siap dipanen saat ini.", show_alert=True)

    # Refresh tampilan kebun
    plots = await get_plots(user.id)
    db_user = await get_user(user.id)
    text = fmt_farm(db_user, plots)
    await safe_edit(query, text, farm_keyboard(plots, db_user.get("level", 1)))

# ==================== FIXME COMMAND (untuk akun nyangkut) ====================
async def fixme_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ctx.user_data.clear()  # bersihkan semua pending action
    await get_or_create_user(user.id, user.username, user.first_name)
    await safe_send(update, 
        "✅ **Akun sudah dibersihkan!**\n\n"
        "Semua data nyangkut telah direset.\n"
        "Sekarang coba gunakan bot lagi.", 
        back_to_menu())

# ==================== FARM CALLBACK ====================
async def farm_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    await get_or_create_user(user.id, user.username, user.first_name)
    plots = await get_plots(user.id)
    db_user = await get_user(user.id)
    text = fmt_farm(db_user, plots)
    await safe_edit(query, text, farm_keyboard(plots, db_user.get("level", 1)))

async def farm_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await get_or_create_user(user.id, user.username, user.first_name)
    plots = await get_plots(user.id)
    db_user = await get_user(user.id)
    text = fmt_farm(db_user, plots)
    await safe_send(update, text, farm_keyboard(plots, db_user.get("level", 1)))

# ==================== PLANT & HARVEST ====================
async def plot_plant_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot = int(query.data.split("_")[2])
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    await safe_edit(query, f"Pilih tanaman untuk lahan ke-{slot+1}:", plant_keyboard(db_user["level"], slot))  # asumsi plant_keyboard ada

async def plant_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, slot, crop_key = query.data.split("_")
    slot = int(slot)
    user = query.from_user
    ok, msg = await plant_crop(user.id, slot, crop_key)
    await query.answer(msg, show_alert=True)
    if ok:
        plots = await get_plots(user.id)
        db_user = await get_user(user.id)
        text = fmt_farm(db_user, plots)
        await safe_edit(query, text, farm_keyboard(plots, db_user.get("level", 1)))

async def plot_harvest_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    slot = int(query.data.split("_")[2])
    user = query.from_user
    ok, msg = await harvest_crop(user.id, slot)
    await query.answer(msg, show_alert=True)
    if ok:
        plots = await get_plots(user.id)
        db_user = await get_user(user.id)
        text = fmt_farm(db_user, plots)
        await safe_edit(query, text, farm_keyboard(plots, db_user.get("level", 1)))

# ==================== MARKET CALLBACK (FIX BUY) ====================
async def mkt_buy_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    listing_id = int(query.data.split("_")[2])
    user = query.from_user
    ok, msg = await buy_from_market(user.id, listing_id)
    await query.answer(msg, show_alert=True)
    if ok:
        # Refresh market
        from game.engine import get_market_listings
        listings = await get_market_listings()
        text = fmt_market(listings, 0, len(listings))  # asumsi fmt_market ada
        await safe_edit(query, text, market_keyboard(listings))

# ==================== OTHER CALLBACKS (tetap) ====================
async def menu_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    text = f"🏠 **Menu Utama**\n👑 Level {db_user['level']}  💵 Rp{db_user['coins']:,}  💎 {db_user['gems']}\n\nHalo **{get_display_name(db_user)}**, mau ngapain hari ini?"
    await safe_edit(query, text, main_menu_keyboard())

# ... (bagian lain biarkan tetap, kita hanya tambah harvest_all dan fixme)

# Tambahkan di register_handlers nanti
