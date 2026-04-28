#!/usr/bin/env python3
# main.py - Greena Farm Bot Entry Point

import os
import logging
import asyncio
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

from database.db import init_db
from handlers.main_handlers import (
    start_handler, menu_callback, farm_callback, farm_cmd, farm_page_callback,
    plot_plant_callback, plant_callback, plot_harvest_callback,
    harvest_all_callback, expand_farm_callback,
    plot_spray_callback, spray_all_callback, fertilize_menu_callback, fertilize_callback,
    animals_callback, pen_buy_callback, buyanimal_callback,
    pen_collect_callback, expand_pens_callback, collect_all_animals_callback,
    pens_page_callback,
    pen_detail_callback, pen_remove_callback, pen_dope_callback,
    transfer_cmd,
    factories_callback, buy_building_callback, factory_detail_callback,
    upgrade_building_callback, upgrade_building_confirm_callback,
    produce_callback, collect_callback,
    storage_callback, storage_silo_callback, storage_barn_callback,
    storage_page_callback, sell_menu_callback, sell_callback,
    upgrade_silo_callback, upgrade_barn_callback,
    orders_callback, orders_cmd, fulfill_callback, refresh_orders_callback,
    market_callback, market_page_callback, market_cmd,
    mkt_buy_callback, confirm_buy_callback, my_listings_callback, rmlist_callback,
    market_list_callback, listitem_cmd, listing_sold_callback,
    land_callback, clear_callback,
    shop_callback, shop_cmd, shopbuy_callback,
    profile_callback, profile_cmd,
    leaderboard_callback, leaderboard_cmd,
    setname_callback, setname_cmd, user_text_input,
    setavatar_callback, setavatar_cmd, user_photo_input,
    tutorial_callback, tutorial_cmd,
    items_callback, items_cmd,
    daily_callback, daily_cmd,
    help_callback, help_cmd, help_page_callback, fixme_cmd,
    weeklyrank_callback, weeklyrank_cmd,
    noop_callback, locked_callback,
    gemshop_callback, gemshop_cmd, gembuy_callback, gemconfirm_callback,
    redeem_prompt_callback, redeem_cmd,
    mytitles_cmd, mytitles_callback, title_equip_callback, title_unequip_callback,
)
from handlers.admin_handlers import (
    admin_cmd, adm_panel_callback, adm_stats_callback,
    adm_settings_callback, adm_toggle_setting,
    adm_users_callback, adm_user_detail_callback,
    adm_setcoins_callback, adm_setlevel_callback, adm_setgems_callback, adm_setxp_callback,
    adm_giveitem_callback, adm_give2_callback, adm_resetuser_callback,
    adm_broadcast_callback, adm_logs_callback,
    adm_broadcast_confirm_callback, adm_broadcast_cancel_callback,
    adm_items_callback, adm_addcrop_callback,
    adm_give_callback, adm_text_input,
    give_cmd, givecoins_cmd, setphoto_cmd, viewphoto_cmd, delphoto_cmd,
    setgif_cmd, viewgif_cmd, delgif_cmd,
    setchannel_cmd, users_cmd,
    get_admin_ids,
    givegems_cmd, addgemitem_cmd, delgemitem_cmd, togglegemitem_cmd,
    listgemitems_cmd, createcode_cmd, delcode_cmd, listcodes_cmd,
    addanimal_cmd, delanimal_cmd, listanimals_cmd,
    addcrop_cmd, delcrop_cmd, listcrops_cmd,
    addrecipe_cmd, delrecipe_cmd, listrecipes_cmd,
    addtitle_cmd, deltitle_cmd, listtitles_cmd, givetitle_cmd,
    resetuser_cmd, resetall_cmd,
    addorder_cmd, addorderall_cmd,
    addslot_cmd,
    weeklyreward_cmd,
    event_cmd, stopevent_cmd, listevents_cmd,
)

load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling update:", exc_info=ctx.error)
    if isinstance(update, Update):
        if update.callback_query:
            try:
                await update.callback_query.answer("⚠️ Ada yang salah. Silakan coba lagi.", show_alert=True)
            except Exception:
                pass
        elif update.message:
            try:
                await update.message.reply_text("⚠️ Terjadi kesalahan. Silakan coba lagi.")
            except Exception:
                pass


def register_handlers(app: Application):
    # ─── COMMANDS ─────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("farm", farm_cmd))
    app.add_handler(CommandHandler("storage", storage_callback_cmd))
    app.add_handler(CommandHandler("market", market_cmd))
    app.add_handler(CommandHandler("orders", orders_cmd))
    app.add_handler(CommandHandler("daily", daily_cmd))
    app.add_handler(CommandHandler("profile", profile_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("fixme", fixme_cmd))
    app.add_handler(CommandHandler("weeklyrank", weeklyrank_cmd))
    app.add_handler(CallbackQueryHandler(weeklyrank_callback, pattern="^weeklyrank$"))
    app.add_handler(CommandHandler("transfer", transfer_cmd))
    app.add_handler(CommandHandler("listitem", listitem_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CommandHandler("setname", setname_cmd))
    app.add_handler(CommandHandler("setavatar", setavatar_cmd))
    app.add_handler(CommandHandler("shop", shop_cmd))
    app.add_handler(CommandHandler("tutorial", tutorial_cmd))
    app.add_handler(CommandHandler("items", items_cmd))
    app.add_handler(CommandHandler("gemshop", gemshop_cmd))
    app.add_handler(CommandHandler("redeem", redeem_cmd))
    app.add_handler(CommandHandler("mytitles", mytitles_cmd))

    # Admin commands
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("give", give_cmd))
    app.add_handler(CommandHandler("givecoins", givecoins_cmd))
    app.add_handler(CommandHandler("givegems", givegems_cmd))
    app.add_handler(CommandHandler("addgemitem", addgemitem_cmd))
    app.add_handler(CommandHandler("delgemitem", delgemitem_cmd))
    app.add_handler(CommandHandler("togglegemitem", togglegemitem_cmd))
    app.add_handler(CommandHandler("listgemitems", listgemitems_cmd))
    app.add_handler(CommandHandler("createcode", createcode_cmd))
    app.add_handler(CommandHandler("delcode", delcode_cmd))
    app.add_handler(CommandHandler("listcodes", listcodes_cmd))
    app.add_handler(CommandHandler("addanimal", addanimal_cmd))
    app.add_handler(CommandHandler("delanimal", delanimal_cmd))
    app.add_handler(CommandHandler("listanimals", listanimals_cmd))
    app.add_handler(CommandHandler("addcrop", addcrop_cmd))
    app.add_handler(CommandHandler("delcrop", delcrop_cmd))
    app.add_handler(CommandHandler("listcrops", listcrops_cmd))
    app.add_handler(CommandHandler("addrecipe", addrecipe_cmd))
    app.add_handler(CommandHandler("delrecipe", delrecipe_cmd))
    app.add_handler(CommandHandler("listrecipes", listrecipes_cmd))
    app.add_handler(CommandHandler("addtitle", addtitle_cmd))
    app.add_handler(CommandHandler("deltitle", deltitle_cmd))
    app.add_handler(CommandHandler("listtitles", listtitles_cmd))
    app.add_handler(CommandHandler("givetitle", givetitle_cmd))
    app.add_handler(CommandHandler("setphoto", setphoto_cmd))
    app.add_handler(CommandHandler("viewphoto", viewphoto_cmd))
    app.add_handler(CommandHandler("delphoto", delphoto_cmd))
    app.add_handler(CommandHandler("setgif", setgif_cmd))
    app.add_handler(CommandHandler("viewgif", viewgif_cmd))
    app.add_handler(CommandHandler("delgif", delgif_cmd))
    app.add_handler(CommandHandler("setchannel", setchannel_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("resetuser", resetuser_cmd))
    app.add_handler(CommandHandler("resetall", resetall_cmd))
    app.add_handler(CommandHandler("addorder", addorder_cmd))
    app.add_handler(CommandHandler("addorderall", addorderall_cmd))
    app.add_handler(CommandHandler("addslot", addslot_cmd))
    app.add_handler(CommandHandler("weeklyreward", weeklyreward_cmd))
    app.add_handler(CommandHandler("event", event_cmd))
    app.add_handler(CommandHandler("stopevent", stopevent_cmd))
    app.add_handler(CommandHandler("listevents", listevents_cmd))

    # ─── ADMIN TEXT INPUT (must be before generic message handler) ─────────────
    admin_ids = get_admin_ids()
    if admin_ids:
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.User(user_id=admin_ids),
            adm_text_input
        ))

    # ─── USER TEXT INPUT (for setname etc.) ────────────────────────────────────
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        user_text_input
    ))

    # ─── USER PHOTO INPUT (for setavatar) ─────────────────────────────────────
    app.add_handler(MessageHandler(
        filters.PHOTO,
        user_photo_input
    ))

    # ─── CALLBACK QUERIES ─────────────────────────────────────────────────────
    # Menu
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu$"))

    # Farm
    app.add_handler(CallbackQueryHandler(farm_callback, pattern="^farm$"))
    app.add_handler(CallbackQueryHandler(farm_page_callback, pattern=r"^farm_page_\d+$"))
    app.add_handler(CallbackQueryHandler(plot_plant_callback, pattern=r"^plot_plant_\d+$"))
    app.add_handler(CallbackQueryHandler(plot_harvest_callback, pattern=r"^plot_harvest_\d+$"))
    app.add_handler(CallbackQueryHandler(plant_callback, pattern=r"^plant_\d+_.+$"))
    app.add_handler(CallbackQueryHandler(harvest_all_callback, pattern="^harvest_all$"))
    app.add_handler(CallbackQueryHandler(expand_farm_callback, pattern="^expand_farm$"))

    # Pest & Fertilizer
    app.add_handler(CallbackQueryHandler(plot_spray_callback, pattern=r"^plot_spray_\d+$"))
    app.add_handler(CallbackQueryHandler(spray_all_callback, pattern="^spray_all$"))
    app.add_handler(CallbackQueryHandler(fertilize_menu_callback, pattern="^fertilize_menu$"))
    app.add_handler(CallbackQueryHandler(fertilize_callback, pattern=r"^fert_\d+_.+$"))

    # Animals
    app.add_handler(CallbackQueryHandler(animals_callback, pattern="^animals$"))
    app.add_handler(CallbackQueryHandler(pens_page_callback, pattern=r"^pens_page_\d+$"))
    app.add_handler(CallbackQueryHandler(pen_buy_callback, pattern=r"^pen_buy_\d+$"))
    app.add_handler(CallbackQueryHandler(buyanimal_callback, pattern=r"^buyanimal_\d+_.+$"))
    app.add_handler(CallbackQueryHandler(pen_collect_callback, pattern=r"^pen_collect_\d+$"))
    app.add_handler(CallbackQueryHandler(pen_detail_callback, pattern=r"^pen_detail_\d+$"))
    app.add_handler(CallbackQueryHandler(pen_remove_callback, pattern=r"^pen_remove_\d+$"))
    app.add_handler(CallbackQueryHandler(pen_dope_callback, pattern=r"^pen_dope_\d+$"))
    app.add_handler(CallbackQueryHandler(collect_all_animals_callback, pattern="^collect_all_animals$"))
    app.add_handler(CallbackQueryHandler(expand_pens_callback, pattern="^expand_pens$"))

    # Factories
    app.add_handler(CallbackQueryHandler(factories_callback, pattern="^factories$"))
    app.add_handler(CallbackQueryHandler(buy_building_callback, pattern=r"^buy_building_.+$"))
    app.add_handler(CallbackQueryHandler(upgrade_building_confirm_callback, pattern=r"^upgrade_bldok_.+$"))
    app.add_handler(CallbackQueryHandler(upgrade_building_callback, pattern=r"^upgrade_bld_.+$"))
    app.add_handler(CallbackQueryHandler(factory_detail_callback, pattern=r"^factory_.+$"))
    app.add_handler(CallbackQueryHandler(produce_callback, pattern=r"^produce_.+$"))
    app.add_handler(CallbackQueryHandler(collect_callback, pattern=r"^collect_.+$"))

    # Storage
    app.add_handler(CallbackQueryHandler(storage_callback, pattern="^storage$"))
    app.add_handler(CallbackQueryHandler(storage_silo_callback, pattern="^storage_silo$"))
    app.add_handler(CallbackQueryHandler(storage_barn_callback, pattern="^storage_barn$"))
    app.add_handler(CallbackQueryHandler(storage_page_callback, pattern=r"^storage_(silo|barn)_page_\d+$"))
    app.add_handler(CallbackQueryHandler(sell_menu_callback, pattern=r"^sell_menu_.+$"))
    app.add_handler(CallbackQueryHandler(sell_callback, pattern=r"^sell_.+_\d+$"))
    app.add_handler(CallbackQueryHandler(upgrade_silo_callback, pattern="^upgrade_silo$"))
    app.add_handler(CallbackQueryHandler(upgrade_barn_callback, pattern="^upgrade_barn$"))

    # Orders
    app.add_handler(CallbackQueryHandler(orders_callback, pattern="^orders$"))
    app.add_handler(CallbackQueryHandler(fulfill_callback, pattern=r"^fulfill_\d+$"))
    app.add_handler(CallbackQueryHandler(refresh_orders_callback, pattern="^refresh_orders$"))

    # Market
    app.add_handler(CallbackQueryHandler(market_callback, pattern="^market$"))
    app.add_handler(CallbackQueryHandler(market_page_callback, pattern=r"^market_page_\d+$"))
    app.add_handler(CallbackQueryHandler(mkt_buy_callback, pattern=r"^mkt_buy_\d+$"))
    app.add_handler(CallbackQueryHandler(confirm_buy_callback, pattern=r"^confirm_buy_\d+$"))
    app.add_handler(CallbackQueryHandler(my_listings_callback, pattern="^my_listings$"))
    app.add_handler(CallbackQueryHandler(rmlist_callback, pattern=r"^rmlist_\d+$"))
    app.add_handler(CallbackQueryHandler(market_list_callback, pattern=r"^market_list_.+$"))
    app.add_handler(CallbackQueryHandler(listing_sold_callback, pattern=r"^listing_sold$"))

    # Land
    app.add_handler(CallbackQueryHandler(land_callback, pattern="^land$"))
    app.add_handler(CallbackQueryHandler(clear_callback, pattern=r"^clear_\d+$"))

    # Shop
    app.add_handler(CallbackQueryHandler(shop_callback, pattern="^shop$"))
    app.add_handler(CallbackQueryHandler(shopbuy_callback, pattern=r"^shopbuy_.+$"))

    # Profile / Daily / Help / Leaderboard / Setname / Tutorial
    app.add_handler(CallbackQueryHandler(profile_callback, pattern="^profile$"))
    app.add_handler(CallbackQueryHandler(leaderboard_callback, pattern="^leaderboard$"))
    app.add_handler(CallbackQueryHandler(setname_callback, pattern="^setname$"))
    app.add_handler(CallbackQueryHandler(setavatar_callback, pattern="^setavatar$"))
    app.add_handler(CallbackQueryHandler(tutorial_callback, pattern="^tutorial$"))
    app.add_handler(CallbackQueryHandler(items_callback, pattern=r"^items_(crops|animals|products|tools|all)$"))
    app.add_handler(CallbackQueryHandler(daily_callback, pattern="^daily$"))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^help$"))
    app.add_handler(CallbackQueryHandler(help_page_callback, pattern=r"^help_page_\d+$"))
    app.add_handler(CallbackQueryHandler(noop_callback, pattern="^noop$"))
    app.add_handler(CallbackQueryHandler(locked_callback, pattern="^locked$"))

    # Toko Permata
    app.add_handler(CallbackQueryHandler(gemshop_callback, pattern="^gemshop$"))
    app.add_handler(CallbackQueryHandler(gembuy_callback, pattern=r"^gembuy_\d+$"))
    app.add_handler(CallbackQueryHandler(gemconfirm_callback, pattern=r"^gemconfirm_\d+$"))
    app.add_handler(CallbackQueryHandler(redeem_prompt_callback, pattern="^redeem_prompt$"))

    # Title / Gelar cosmetic
    app.add_handler(CallbackQueryHandler(mytitles_callback, pattern="^mytitles$"))
    app.add_handler(CallbackQueryHandler(title_equip_callback, pattern=r"^title_eq_.+$"))
    app.add_handler(CallbackQueryHandler(title_unequip_callback, pattern="^title_unequip$"))

    # Admin panel callbacks
    app.add_handler(CallbackQueryHandler(adm_panel_callback, pattern="^adm_panel$"))
    app.add_handler(CallbackQueryHandler(adm_stats_callback, pattern="^adm_stats$"))
    app.add_handler(CallbackQueryHandler(adm_settings_callback, pattern="^adm_settings$"))
    app.add_handler(CallbackQueryHandler(adm_toggle_setting, pattern=r"^adm_set_.+$"))
    app.add_handler(CallbackQueryHandler(adm_users_callback, pattern="^adm_users$"))
    app.add_handler(CallbackQueryHandler(adm_users_callback, pattern=r"^adm_users_page_\d+$"))
    app.add_handler(CallbackQueryHandler(adm_user_detail_callback, pattern=r"^adm_user_\d+$"))
    app.add_handler(CallbackQueryHandler(adm_setcoins_callback, pattern=r"^adm_setcoins_\d+$"))
    app.add_handler(CallbackQueryHandler(adm_setlevel_callback, pattern=r"^adm_setlevel_\d+$"))
    app.add_handler(CallbackQueryHandler(adm_setxp_callback, pattern=r"^adm_setxp_"))
    app.add_handler(CallbackQueryHandler(adm_setgems_callback, pattern=r"^adm_setgems_\d+$"))
    app.add_handler(CallbackQueryHandler(adm_giveitem_callback, pattern=r"^adm_giveitem_\d+$"))
    app.add_handler(CallbackQueryHandler(adm_give2_callback, pattern=r"^adm_give2_\d+_.+$"))
    app.add_handler(CallbackQueryHandler(adm_resetuser_callback, pattern=r"^adm_resetuser_\d+$"))
    app.add_handler(CallbackQueryHandler(adm_broadcast_callback, pattern="^adm_broadcast$"))
    app.add_handler(CallbackQueryHandler(adm_broadcast_confirm_callback, pattern="^adm_broadcast_confirm$"))
    app.add_handler(CallbackQueryHandler(adm_broadcast_cancel_callback, pattern="^adm_broadcast_cancel$"))
    app.add_handler(CallbackQueryHandler(adm_logs_callback, pattern="^adm_logs$"))
    app.add_handler(CallbackQueryHandler(adm_items_callback, pattern="^adm_items$"))
    app.add_handler(CallbackQueryHandler(adm_addcrop_callback, pattern="^adm_addcrop$"))
    app.add_handler(CallbackQueryHandler(adm_give_callback, pattern="^adm_give$"))

    app.add_error_handler(error_handler)


async def storage_callback_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from handlers.main_handlers import safe_send
    from database.db import get_or_create_user, parse_json_field
    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.username, user.first_name)
    silo = parse_json_field(db_user["silo_items"])
    barn = parse_json_field(db_user["barn_items"])
    from utils.keyboards import storage_keyboard
    text = (
        f"📦 **Ringkasan Penyimpanan**\n\n"
        f"🌾 Gudang (Lv{db_user['silo_level']}): {sum(silo.values())}/{db_user['silo_cap']}\n"
        f"🏚 Lumbung (Lv{db_user['barn_level']}): {sum(barn.values())}/{db_user['barn_cap']}\n\n"
        f"Pilih penyimpanan untuk lihat item:"
    )
    await safe_send(update, text, storage_keyboard())


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("❌ BOT_TOKEN not set! Add it to your environment variables.")

    async def post_init(app: Application):
        await init_db()
        from game.gems import init_gem_tables
        await init_gem_tables()
        from game.custom_animals import init_custom_animals_table, load_custom_animals
        await init_custom_animals_table()
        await load_custom_animals()
        from game.custom_crops import init_custom_crops_table, load_custom_crops
        await init_custom_crops_table()
        await load_custom_crops()
        from game.custom_recipes import init_custom_recipes_table, load_custom_recipes
        await init_custom_recipes_table()
        await load_custom_recipes()
        from game.titles import init_title_tables
        await init_title_tables()
        logger.info("✅ Database initialized")
        admin_ids = get_admin_ids()
        if admin_ids:
            logger.info(f"✅ Admin IDs: {admin_ids}")
        else:
            logger.warning("⚠️ No ADMIN_IDS set. Admin panel will be inaccessible.")

        # ─── WEEKLY RANK SCHEDULER ────────────────────────────────────
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        import pytz

        wib_tz = pytz.timezone("Asia/Jakarta")

        async def weekly_rank_job():
            """Auto-distribute weekly rank rewards every Monday 07:00 WIB."""
            logger.info("🏆 Weekly Rank: distributing rewards...")
            from game.engine import distribute_weekly_rewards
            try:
                summary = await distribute_weekly_rewards(bot=app.bot)
                logger.info(f"🏆 Weekly Rank done: {summary[:200]}")
            except Exception as e:
                logger.error(f"🏆 Weekly Rank error: {e}")

        scheduler = AsyncIOScheduler(timezone=wib_tz)
        scheduler.add_job(
            weekly_rank_job,
            CronTrigger(day_of_week="mon", hour=7, minute=0, timezone=wib_tz),
            id="weekly_rank_reset",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("✅ Weekly Rank scheduler: every Monday 07:00 WIB")

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .concurrent_updates(True)   # Proses update paralel = jauh lebih cepet
        .build()
    )

    register_handlers(app)
    logger.info("🌾 Greena Farm Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
