# game/custom_animals.py - Sistem hewan custom yang bisa ditambah admin lewat command

from database.db import get_db, fetchone, fetchall
from game.data import ANIMALS, CUSTOM_ANIMAL_PRODUCTS, CUSTOM_ANIMAL_PRODUCT_NAMES


async def init_custom_animals_table():
    """Buat tabel custom_animals. Dipanggil di post_init."""
    async with get_db() as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS custom_animals (
            animal_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            emoji TEXT NOT NULL,
            product_key TEXT NOT NULL,
            product_name TEXT NOT NULL,
            prod_emoji TEXT NOT NULL,
            feed_time INTEGER NOT NULL,
            buy_cost INTEGER NOT NULL,
            sell_price INTEGER NOT NULL,
            level_req INTEGER NOT NULL,
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now')))""")
        await db.commit()


async def load_custom_animals():
    """Load semua hewan custom dari DB ke dict ANIMALS in-memory.
    Dipanggil sekali pas startup, dan dipanggil ulang setiap kali ada perubahan."""
    async with get_db() as db:
        rows = await fetchall(db, "SELECT * FROM custom_animals")
    for r in rows:
        r = dict(r)
        ANIMALS[r["animal_key"]] = {
            "name": r["name"],
            "emoji": r["emoji"],
            "product": r["product_key"],
            "prod_emoji": r["prod_emoji"],
            "feed_time": r["feed_time"],
            "buy_cost": r["buy_cost"],
            "sell_price": r["sell_price"],
            "level_req": r["level_req"],
        }
        CUSTOM_ANIMAL_PRODUCTS[r["product_key"]] = r["prod_emoji"]
        CUSTOM_ANIMAL_PRODUCT_NAMES[r["product_key"]] = r["product_name"]


async def add_custom_animal(animal_key: str, name: str, emoji: str,
                            product_key: str, product_name: str, prod_emoji: str,
                            feed_time: int, buy_cost: int, sell_price: int,
                            level_req: int, admin_id: int) -> tuple[bool, str]:
    animal_key = animal_key.lower().strip()
    product_key = product_key.lower().strip()

    # Validasi: key unik di seluruh game (jangan tabrakan sama hewan default)
    if animal_key in ANIMALS:
        return False, f"❌ Key `{animal_key}` udah ada di hewan lain."

    async with get_db() as db:
        existing = await fetchone(db, "SELECT animal_key FROM custom_animals WHERE animal_key = ?",
                                  (animal_key,))
        if existing:
            return False, f"❌ Hewan `{animal_key}` udah ada."
        await db.execute(
            """INSERT INTO custom_animals
               (animal_key, name, emoji, product_key, product_name, prod_emoji,
                feed_time, buy_cost, sell_price, level_req, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (animal_key, name, emoji, product_key, product_name, prod_emoji,
             feed_time, buy_cost, sell_price, level_req, admin_id)
        )
        await db.commit()

    # Update in-memory dicts langsung biar instant ke-effect
    ANIMALS[animal_key] = {
        "name": name, "emoji": emoji, "product": product_key,
        "prod_emoji": prod_emoji, "feed_time": feed_time,
        "buy_cost": buy_cost, "sell_price": sell_price, "level_req": level_req,
    }
    CUSTOM_ANIMAL_PRODUCTS[product_key] = prod_emoji
    CUSTOM_ANIMAL_PRODUCT_NAMES[product_key] = product_name

    return True, f"✅ Hewan `{animal_key}` ({emoji} {name}) berhasil ditambahkan!"


async def delete_custom_animal(animal_key: str) -> tuple[bool, str]:
    animal_key = animal_key.lower().strip()
    async with get_db() as db:
        row = await fetchone(db, "SELECT * FROM custom_animals WHERE animal_key = ?",
                             (animal_key,))
        if not row:
            return False, f"❌ Hewan custom `{animal_key}` tidak ditemukan.\n_(Hewan default tidak bisa dihapus)_"
        row = dict(row)
        await db.execute("DELETE FROM custom_animals WHERE animal_key = ?", (animal_key,))
        await db.commit()

    # Hapus dari in-memory dicts
    ANIMALS.pop(animal_key, None)
    CUSTOM_ANIMAL_PRODUCTS.pop(row["product_key"], None)
    CUSTOM_ANIMAL_PRODUCT_NAMES.pop(row["product_key"], None)

    return True, f"✅ Hewan `{animal_key}` dihapus."


async def list_custom_animals() -> list[dict]:
    async with get_db() as db:
        rows = await fetchall(db,
            "SELECT * FROM custom_animals ORDER BY level_req ASC, created_at ASC")
        return [dict(r) for r in rows]
