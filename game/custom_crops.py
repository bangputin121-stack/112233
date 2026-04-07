# game/custom_crops.py - Sistem tanaman custom

from database.db import get_db, fetchone, fetchall
from game.data import CROPS


async def init_custom_crops_table():
    async with get_db() as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS custom_crops (
            crop_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            emoji TEXT NOT NULL,
            grow_time INTEGER NOT NULL,
            seed_cost INTEGER NOT NULL,
            sell_price INTEGER NOT NULL,
            xp INTEGER NOT NULL,
            level_req INTEGER NOT NULL,
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now')))""")
        await db.commit()


async def load_custom_crops():
    async with get_db() as db:
        rows = await fetchall(db, "SELECT * FROM custom_crops")
    for r in rows:
        r = dict(r)
        CROPS[r["crop_key"]] = {
            "name": r["name"],
            "emoji": r["emoji"],
            "grow_time": r["grow_time"],
            "seed_cost": r["seed_cost"],
            "sell_price": r["sell_price"],
            "xp": r["xp"],
            "level_req": r["level_req"],
        }


async def add_custom_crop(crop_key: str, name: str, emoji: str,
                          grow_time: int, seed_cost: int, sell_price: int,
                          xp: int, level_req: int, admin_id: int) -> tuple[bool, str]:
    crop_key = crop_key.lower().strip()
    if crop_key in CROPS:
        return False, f"❌ Tanaman `{crop_key}` udah ada."

    async with get_db() as db:
        await db.execute(
            """INSERT INTO custom_crops
               (crop_key, name, emoji, grow_time, seed_cost, sell_price, xp, level_req, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (crop_key, name, emoji, grow_time, seed_cost, sell_price, xp, level_req, admin_id)
        )
        await db.commit()

    CROPS[crop_key] = {
        "name": name, "emoji": emoji, "grow_time": grow_time,
        "seed_cost": seed_cost, "sell_price": sell_price,
        "xp": xp, "level_req": level_req,
    }
    return True, f"✅ Tanaman `{crop_key}` ({emoji} {name}) ditambahkan!"


async def delete_custom_crop(crop_key: str) -> tuple[bool, str]:
    crop_key = crop_key.lower().strip()
    async with get_db() as db:
        row = await fetchone(db, "SELECT * FROM custom_crops WHERE crop_key = ?", (crop_key,))
        if not row:
            return False, f"❌ Tanaman custom `{crop_key}` tidak ditemukan.\n_(Tanaman default nggak bisa dihapus)_"
        await db.execute("DELETE FROM custom_crops WHERE crop_key = ?", (crop_key,))
        await db.commit()
    CROPS.pop(crop_key, None)
    return True, f"✅ Tanaman `{crop_key}` dihapus."


async def list_custom_crops() -> list[dict]:
    async with get_db() as db:
        rows = await fetchall(db,
            "SELECT * FROM custom_crops ORDER BY level_req ASC, created_at ASC")
        return [dict(r) for r in rows]
