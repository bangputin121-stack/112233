# game/gems.py - Sistem Toko Permata & Event Code Greena Farm

from database.db import get_db, fetchone, fetchall
from game.engine import add_to_inventory


async def init_gem_tables():
    """Buat tabel-tabel sistem permata. Dipanggil dari main.py post_init."""
    async with get_db() as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS gem_shop_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            emoji TEXT DEFAULT '💎',
            description TEXT DEFAULT '',
            price_gems INTEGER NOT NULL,
            reward_type TEXT NOT NULL,
            reward_value TEXT NOT NULL,
            stock INTEGER DEFAULT -1,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS gem_redeem_codes (
            code TEXT PRIMARY KEY,
            reward_gems INTEGER NOT NULL,
            max_uses INTEGER DEFAULT 1,
            uses INTEGER DEFAULT 0,
            expires_at TEXT,
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now')))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS gem_redeem_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            redeemed_at TEXT DEFAULT (datetime('now')),
            UNIQUE(code, user_id))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS gem_purchase_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            item_name TEXT,
            gems_spent INTEGER NOT NULL,
            purchased_at TEXT DEFAULT (datetime('now')))""")
        await db.commit()


# ─── KELOLA ITEM TOKO ────────────────────────────────────────────────────────

async def add_gem_item(name: str, price_gems: int, reward_type: str,
                       reward_value: str, emoji: str = "💎",
                       description: str = "", stock: int = -1) -> int:
    if reward_type not in ("coins", "item", "custom"):
        raise ValueError("reward_type harus 'coins', 'item', atau 'custom'")
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO gem_shop_items
               (name, emoji, description, price_gems, reward_type, reward_value, stock)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, emoji, description, price_gems, reward_type, reward_value, stock)
        )
        await db.commit()
        return cursor.lastrowid


async def delete_gem_item(item_id: int) -> bool:
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM gem_shop_items WHERE id = ?", (item_id,))
        await db.commit()
        return cursor.rowcount > 0


async def toggle_gem_item(item_id: int) -> tuple[bool, int]:
    async with get_db() as db:
        row = await fetchone(db, "SELECT active FROM gem_shop_items WHERE id = ?", (item_id,))
        if not row:
            return False, 0
        new_state = 0 if row["active"] else 1
        await db.execute("UPDATE gem_shop_items SET active = ? WHERE id = ?", (new_state, item_id))
        await db.commit()
        return True, new_state


async def list_gem_items(active_only: bool = False) -> list[dict]:
    async with get_db() as db:
        if active_only:
            rows = await fetchall(db,
                "SELECT * FROM gem_shop_items WHERE active = 1 AND (stock != 0) ORDER BY price_gems ASC")
        else:
            rows = await fetchall(db,
                "SELECT * FROM gem_shop_items ORDER BY active DESC, price_gems ASC")
        return [dict(r) for r in rows]


async def get_gem_item(item_id: int) -> dict | None:
    async with get_db() as db:
        row = await fetchone(db, "SELECT * FROM gem_shop_items WHERE id = ?", (item_id,))
        return dict(row) if row else None


# ─── PEMBELIAN ───────────────────────────────────────────────────────────────

async def buy_gem_item(user_id: int, item_id: int) -> tuple[bool, str, dict | None]:
    """Return (success, message, info_dict_for_admin_notification)."""
    async with get_db() as db:
        item = await fetchone(db, "SELECT * FROM gem_shop_items WHERE id = ?", (item_id,))
        if not item:
            return False, "❌ Item tidak ditemukan.", None
        item = dict(item)
        if not item["active"]:
            return False, "❌ Item ini sedang tidak aktif.", None
        if item["stock"] == 0:
            return False, "❌ Stok habis!", None

        user_row = await fetchone(db, "SELECT gems FROM users WHERE user_id = ?", (user_id,))
        user_gems = user_row["gems"] if user_row else 0
        if user_gems < item["price_gems"]:
            return False, (
                f"💎 Permata kurang!\n"
                f"Butuh: {item['price_gems']}💎\n"
                f"Punya: {user_gems}💎"
            ), None

        # Potong permata
        await db.execute("UPDATE users SET gems = gems - ? WHERE user_id = ?",
                         (item["price_gems"], user_id))
        # Kurangi stok kalau terbatas
        if item["stock"] > 0:
            await db.execute("UPDATE gem_shop_items SET stock = stock - 1 WHERE id = ?", (item_id,))
        # Log
        await db.execute(
            "INSERT INTO gem_purchase_log (user_id, item_id, item_name, gems_spent) VALUES (?, ?, ?, ?)",
            (user_id, item_id, item["name"], item["price_gems"])
        )
        await db.commit()

    # Kirim hadiah
    rt = item["reward_type"]
    rv = item["reward_value"]
    delivery_msg = ""
    needs_admin = False

    if rt == "coins":
        try:
            amount = int(rv)
            async with get_db() as db:
                await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
                await db.commit()
            delivery_msg = f"💵 +Rp{amount:,} masuk saldo!"
        except ValueError:
            delivery_msg = "⚠️ Format coins error, hubungi admin."
            needs_admin = True
    elif rt == "item":
        try:
            item_key, qty_str = rv.split(":")
            qty = int(qty_str)
            ok, msg = await add_to_inventory(user_id, item_key, qty)
            if ok:
                delivery_msg = f"📦 +{qty}x {item_key} masuk gudang/lumbung!"
            else:
                delivery_msg = f"⚠️ Gagal kirim: {msg}\nHubungi admin."
                needs_admin = True
        except Exception:
            delivery_msg = "⚠️ Format item error, hubungi admin."
            needs_admin = True
    elif rt == "custom":
        delivery_msg = "📨 Pesananmu akan diproses admin secara manual. Tunggu ya!"
        needs_admin = True

    return True, (
        f"✅ **Pembelian Sukses!**\n\n"
        f"{item['emoji']} {item['name']}\n"
        f"💎 -{item['price_gems']} permata\n\n"
        f"{delivery_msg}"
    ), {"item": item, "needs_admin": needs_admin}


# ─── REDEEM CODE (EVENT) ─────────────────────────────────────────────────────

async def create_redeem_code(code: str, reward_gems: int, max_uses: int,
                              admin_id: int, expires_at: str = None) -> tuple[bool, str]:
    code = code.upper().strip()
    async with get_db() as db:
        existing = await fetchone(db, "SELECT code FROM gem_redeem_codes WHERE code = ?", (code,))
        if existing:
            return False, f"❌ Code `{code}` sudah ada."
        await db.execute(
            """INSERT INTO gem_redeem_codes (code, reward_gems, max_uses, expires_at, created_by)
               VALUES (?, ?, ?, ?, ?)""",
            (code, reward_gems, max_uses, expires_at, admin_id)
        )
        await db.commit()
    return True, f"✅ Code `{code}` dibuat: **{reward_gems}💎** × {max_uses} klaim"


async def delete_redeem_code(code: str) -> bool:
    code = code.upper().strip()
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM gem_redeem_codes WHERE code = ?", (code,))
        await db.commit()
        return cursor.rowcount > 0


async def list_redeem_codes() -> list[dict]:
    async with get_db() as db:
        rows = await fetchall(db,
            "SELECT * FROM gem_redeem_codes ORDER BY created_at DESC")
        return [dict(r) for r in rows]


async def redeem_code(user_id: int, code: str) -> tuple[bool, str]:
    code = code.upper().strip()
    async with get_db() as db:
        row = await fetchone(db, "SELECT * FROM gem_redeem_codes WHERE code = ?", (code,))
        if not row:
            return False, "❌ Code tidak valid."
        row = dict(row)
        if row["uses"] >= row["max_uses"]:
            return False, "❌ Code sudah penuh / habis dipakai."

        if row["expires_at"]:
            from datetime import datetime
            try:
                exp = datetime.fromisoformat(row["expires_at"])
                if datetime.now() > exp:
                    return False, "❌ Code sudah kedaluwarsa."
            except Exception:
                pass

        already = await fetchone(db,
            "SELECT id FROM gem_redeem_log WHERE code = ? AND user_id = ?", (code, user_id))
        if already:
            return False, "❌ Kamu sudah pernah pakai code ini."

        await db.execute("UPDATE gem_redeem_codes SET uses = uses + 1 WHERE code = ?", (code,))
        await db.execute("UPDATE users SET gems = gems + ? WHERE user_id = ?",
                         (row["reward_gems"], user_id))
        await db.execute(
            "INSERT INTO gem_redeem_log (code, user_id) VALUES (?, ?)", (code, user_id))
        await db.commit()

    return True, f"🎉 **Code berhasil ditukar!**\n+{row['reward_gems']} 💎 permata masuk ke akunmu!"


async def give_gems(user_id: int, amount: int) -> bool:
    async with get_db() as db:
        user = await fetchone(db, "SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not user:
            return False
        await db.execute("UPDATE users SET gems = gems + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
        return True
