# game/custom_recipes.py - Sistem resep pabrik custom

import json
from database.db import get_db, fetchone, fetchall
from game.data import BUILDINGS, CUSTOM_PROCESSED_EMOJI, CUSTOM_PROCESSED_NAMES


async def init_custom_recipes_table():
    async with get_db() as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS custom_recipes (
            recipe_key TEXT PRIMARY KEY,
            building_key TEXT NOT NULL,
            name TEXT NOT NULL,
            emoji TEXT NOT NULL,
            inputs TEXT NOT NULL,
            time_seconds INTEGER NOT NULL,
            sell_price INTEGER NOT NULL,
            xp INTEGER NOT NULL,
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now')))""")
        await db.commit()


async def load_custom_recipes():
    """Baca semua custom recipes dari DB dan inject ke BUILDINGS[building_key]['recipes']."""
    async with get_db() as db:
        rows = await fetchall(db, "SELECT * FROM custom_recipes")
    for r in rows:
        r = dict(r)
        bkey = r["building_key"]
        if bkey not in BUILDINGS:
            continue  # skip kalau bangunan sudah tidak ada
        try:
            inputs = json.loads(r["inputs"])
        except Exception:
            continue
        BUILDINGS[bkey]["recipes"][r["recipe_key"]] = {
            "inputs": inputs,
            "time": r["time_seconds"],
            "xp": r["xp"],
            "sell_price": r["sell_price"],
        }
        CUSTOM_PROCESSED_EMOJI[r["recipe_key"]] = r["emoji"]
        CUSTOM_PROCESSED_NAMES[r["recipe_key"]] = r["name"]


async def add_custom_recipe(building_key: str, recipe_key: str, name: str,
                            emoji: str, inputs: dict, time_seconds: int,
                            sell_price: int, xp: int, admin_id: int) -> tuple[bool, str]:
    building_key = building_key.lower().strip()
    recipe_key = recipe_key.lower().strip()

    if building_key not in BUILDINGS:
        return False, f"❌ Pabrik `{building_key}` tidak ada.\nPabrik yang ada: {', '.join(BUILDINGS.keys())}"

    if recipe_key in BUILDINGS[building_key]["recipes"]:
        return False, f"❌ Resep `{recipe_key}` sudah ada di pabrik `{building_key}`."

    # Cek recipe_key udah dipake di pabrik lain atau bukan
    for bk, bv in BUILDINGS.items():
        if recipe_key in bv["recipes"]:
            return False, f"❌ Key `{recipe_key}` sudah dipake di pabrik `{bk}`."

    async with get_db() as db:
        await db.execute(
            """INSERT INTO custom_recipes
               (recipe_key, building_key, name, emoji, inputs, time_seconds, sell_price, xp, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (recipe_key, building_key, name, emoji, json.dumps(inputs),
             time_seconds, sell_price, xp, admin_id)
        )
        await db.commit()

    BUILDINGS[building_key]["recipes"][recipe_key] = {
        "inputs": inputs,
        "time": time_seconds,
        "xp": xp,
        "sell_price": sell_price,
    }
    CUSTOM_PROCESSED_EMOJI[recipe_key] = emoji
    CUSTOM_PROCESSED_NAMES[recipe_key] = name

    return True, f"✅ Resep `{recipe_key}` ({emoji} {name}) ditambahkan ke `{building_key}`!"


async def delete_custom_recipe(recipe_key: str) -> tuple[bool, str]:
    recipe_key = recipe_key.lower().strip()
    async with get_db() as db:
        row = await fetchone(db, "SELECT * FROM custom_recipes WHERE recipe_key = ?", (recipe_key,))
        if not row:
            return False, f"❌ Resep custom `{recipe_key}` tidak ditemukan."
        row = dict(row)
        await db.execute("DELETE FROM custom_recipes WHERE recipe_key = ?", (recipe_key,))
        await db.commit()

    bkey = row["building_key"]
    if bkey in BUILDINGS:
        BUILDINGS[bkey]["recipes"].pop(recipe_key, None)
    CUSTOM_PROCESSED_EMOJI.pop(recipe_key, None)
    CUSTOM_PROCESSED_NAMES.pop(recipe_key, None)

    return True, f"✅ Resep `{recipe_key}` dihapus."


async def list_custom_recipes() -> list[dict]:
    async with get_db() as db:
        rows = await fetchall(db,
            "SELECT * FROM custom_recipes ORDER BY building_key, created_at")
        return [dict(r) for r in rows]
