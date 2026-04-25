# game/engine.py - FIXED VERSION (Market + Pabrik + Panen + Event)

import json
import random
import logging
from datetime import datetime, timedelta, timezone

from database.db import get_db, fetchone, fetchall, parse_json_field, dump_json_field, get_setting
from game.data import (
    CROPS, ANIMALS, BUILDINGS, UPGRADE_TOOLS, EXPANSION_TOOLS, CLEARING_TOOLS,
    OBSTACLES, BONUS_DROP_RATE, get_level_from_xp, get_xp_for_next_level,
    get_item_emoji, get_item_name, PROCESSED_EMOJI,
    CUSTOM_ANIMAL_PRODUCTS, CUSTOM_PROCESSED_NAMES
)

logger = logging.getLogger(__name__)

def utcnow():
    return datetime.now(timezone.utc)

def fmt_time(seconds: int) -> str:
    if seconds <= 0: return "Siap!"
    if seconds < 60: return f"{seconds}s"
    if seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}m {s}s"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m"

# ==================== INVENTORY (FIXED) ====================
async def add_to_inventory(user_id: int, item_key: str, qty: int = 1) -> tuple[bool, str]:
    if qty <= 0:
        return False, "❌ Jumlah tidak valid."

    async with get_db() as db:
        row = await fetchone(db, "SELECT silo_items, barn_items, silo_cap, barn_cap FROM users WHERE user_id = ?", (user_id,))
        silo = parse_json_field(row["silo_items"])
        barn = parse_json_field(row["barn_items"])

        if is_silo_item(item_key):
            used = sum(silo.values())
            if used + qty > row["silo_cap"]:
                return False, f"🌾 LUMBUNG PENUH! ({used}/{row['silo_cap']})"
            silo[item_key] = silo.get(item_key, 0) + qty
            await db.execute("UPDATE users SET silo_items = ? WHERE user_id = ?", (dump_json_field(silo), user_id))
        elif is_barn_item(item_key):
            used = sum(barn.values())
            if used + qty > row["barn_cap"]:
                return False, f"🏚 GUDANG PENUH! ({used}/{row['barn_cap']})"
            barn[item_key] = barn.get(item_key, 0) + qty
            await db.execute("UPDATE users SET barn_items = ? WHERE user_id = ?", (dump_json_field(barn), user_id))
        else:
            return False, f"❓ Item tidak dikenal: {item_key}"

        await db.commit()
        return True, "ok"

def is_silo_item(item_key: str) -> bool:
    if item_key in CROPS: return True
    if item_key in {"egg","milk","bacon","wool","goat_milk","honey","feather","fish","lobster","mozzarella"}: return True
    if item_key in CUSTOM_ANIMAL_PRODUCTS: return True
    return False

def is_barn_item(item_key: str) -> bool:
    if item_key in UPGRADE_TOOLS or item_key in EXPANSION_TOOLS or item_key in CLEARING_TOOLS: return True
    if item_key in ("pesticide", "fertilizer", "super_fertilizer", "animal_doping"): return True
    for b in BUILDINGS.values():
        if item_key in b["recipes"]: return True
    if item_key in CUSTOM_PROCESSED_NAMES: return True
    return False

# ==================== EVENT MULTIPLIER (FIXED) ====================
async def get_event_multipliers() -> tuple[float, float]:
    events = await get_active_events()
    coin_total = xp_total = 1.0
    for e in events:
        coin_total *= float(e.get("coin_multiplier", 1.0))
        xp_total *= float(e.get("xp_multiplier", 1.0))
    return coin_total, xp_total

async def add_xp_and_check_level(user_id: int, xp_gain: int):
    _, xp_mult = await get_event_multipliers()
    xp_gain = int(xp_gain * xp_mult)

    async with get_db() as db:
        row = await fetchone(db, "SELECT xp, level FROM users WHERE user_id = ?", (user_id,))
        new_xp = row["xp"] + xp_gain
        new_level = get_level_from_xp(new_xp)
        leveled_up = new_level > row["level"]
        await db.execute("UPDATE users SET xp = ?, level = ? WHERE user_id = ?", (new_xp, new_level, user_id))
        await db.commit()
    return new_level, leveled_up, new_xp

# ==================== PLANT CROP - ATOMIC (FIX SALDO TETAPI TIDAK TANAM) ====================
async def plant_crop(user_id: int, slot: int, crop_key: str) -> tuple[bool, str]:
    if crop_key not in CROPS: return False, "❓ Tanaman tidak dikenal."
    crop = CROPS[crop_key]

    async with get_db() as db:   # SATU TRANSACTION
        user = dict(await fetchone(db, "SELECT * FROM users WHERE user_id = ?", (user_id,)))
        if crop["level_req"] > user["level"]:
            return False, f"🔒 Butuh Level {crop['level_req']}."

        plot = await fetchone(db, "SELECT status FROM plots WHERE user_id = ? AND slot = ?", (user_id, slot))
        if not plot or plot["status"] != "empty":
            return False, "🌱 Lahan ini tidak kosong."

        if user["coins"] < crop["seed_cost"]:
            return False, f"💸 Uang tidak cukup! Butuh Rp{crop['seed_cost']:,}"

        now = utcnow()
        ready_at = now + timedelta(seconds=crop["grow_time"])

        await db.execute(
            "UPDATE plots SET crop=?, planted_at=?, ready_at=?, status='growing' WHERE user_id=? AND slot=?",
            (crop_key, now.isoformat(), ready_at.isoformat(), user_id, slot)
        )
        await db.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (crop["seed_cost"], user_id))
        await db.commit()

    await check_pest_on_plant(user_id, user["plots"])
    return True, f"✅ Ditanam {crop['emoji']} {crop['name']}! Siap dalam {fmt_time(crop['grow_time'])}."

# ==================== HARVEST ALL (FIXED) ====================
async def harvest_all(user_id: int) -> tuple[int, int, str]:
    plots = await get_plots(user_id)
    now = utcnow()
    harvested = 0
    for p in plots:
        if p["status"] == "growing":
            ready_at = datetime.fromisoformat(p["ready_at"]).replace(tzinfo=timezone.utc) if not hasattr(datetime.fromisoformat(p["ready_at"]), 'tzinfo') else datetime.fromisoformat(p["ready_at"])
            if now >= ready_at:
                ok, _ = await harvest_crop(user_id, p["slot"])
                if ok:
                    harvested += 1
    return harvested, 0, ""

# ==================== MARKET FIX (LISTING & BUY) ====================
async def list_item_on_market(user_id: int, seller_name: str, item_key: str, qty: int, price: int) -> tuple[bool, str, int]:
    max_listings = int(await get_setting("max_market_listings", "5"))
    async with get_db() as db:
        count = (await fetchone(db, "SELECT COUNT(*) as c FROM market_listings WHERE seller_id = ?", (user_id,)))["c"]
        if count >= max_listings:
            return False, f"❌ Maksimal {max_listings} listing aktif!", 0

    ok, msg = await remove_from_inventory(user_id, item_key, qty)
    if not ok: return False, msg, 0

    async with get_db() as db:
        cursor = await db.execute("INSERT INTO market_listings (seller_id, seller_name, item, qty, price) VALUES (?, ?, ?, ?, ?)",
                                  (user_id, seller_name, item_key, qty, price))
        listing_id = cursor.lastrowid
        await db.commit()
    return True, f"✅ Listing berhasil!", listing_id

async def buy_from_market(buyer_id: int, listing_id: int) -> tuple[bool, str]:
    async with get_db() as db:
        listing = dict(await fetchone(db, "SELECT * FROM market_listings WHERE id = ?", (listing_id,)))
        if not listing: return False, "❌ Listing tidak ditemukan."

        total_cost = listing["price"] * listing["qty"]
        buyer_coins = (await fetchone(db, "SELECT coins FROM users WHERE user_id = ?", (buyer_id,)))["coins"]
        if buyer_coins < total_cost:
            return False, f"💵 Uang tidak cukup!"

        ok, msg = await add_to_inventory(buyer_id, listing["item"], listing["qty"])
        if not ok:
            return False, f"❌ Gagal masuk storage: {msg}"

        await db.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (total_cost, buyer_id))
        await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (total_cost, listing["seller_id"]))
        await db.execute("DELETE FROM market_listings WHERE id = ?", (listing_id,))
        await db.commit()

    return True, f"✅ Berhasil beli {listing['qty']}x {get_item_name(listing['item'])}!"

# ==================== COLLECT PRODUCTION (FIX) ====================
async def collect_production(user_id: int, building_key: str, slot: int) -> tuple[bool, str]:
    async with get_db() as db:
        row = await fetchone(db, "SELECT * FROM buildings WHERE user_id=? AND building=? AND slot=?", (user_id, building_key, slot))
        if not row or row["status"] != "producing":
            return False, "Tidak ada produksi."

        ready_at = datetime.fromisoformat(row["ready_at"])
        if ready_at.tzinfo is None: ready_at = ready_at.replace(tzinfo=timezone.utc)
        if utcnow() < ready_at:
            return False, "Produksi belum selesai."

        recipe_key = row["item"]
        recipe = BUILDINGS[building_key]["recipes"].get(recipe_key, {})

        ok, msg = await add_to_inventory(user_id, recipe_key, 1)
        if not ok:
            logger.error(f"Collect failed: {msg}")
            return False, msg

        await db.execute("UPDATE buildings SET item=NULL, started_at=NULL, ready_at=NULL, status='idle' WHERE user_id=? AND building=? AND slot=?", 
                         (user_id, building_key, slot))
        await db.commit()

    await add_xp_and_check_level(user_id, recipe.get("xp", 5))
    return True, f"✅ Diambil {get_item_emoji(recipe_key)} {get_item_name(recipe_key)}!"
