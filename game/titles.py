# game/titles.py - Sistem Title / Gelar cosmetic player

from database.db import get_db, fetchone, fetchall


async def init_title_tables():
    """Buat tabel titles + migration kolom equipped_title."""
    async with get_db() as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS titles (
            title_key TEXT PRIMARY KEY,
            display TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now')))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS user_titles (
            user_id INTEGER NOT NULL,
            title_key TEXT NOT NULL,
            acquired_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, title_key))""")
        # Migration: kolom equipped_title di users
        try:
            await db.execute("ALTER TABLE users ADD COLUMN equipped_title TEXT DEFAULT ''")
        except Exception:
            pass  # kolom udah ada
        await db.commit()


# ─── ADMIN: KELOLA TITLE ─────────────────────────────────────────────────────

async def add_title(title_key: str, display: str, description: str,
                    admin_id: int) -> tuple[bool, str]:
    title_key = title_key.lower().strip()
    async with get_db() as db:
        existing = await fetchone(db, "SELECT title_key FROM titles WHERE title_key = ?",
                                  (title_key,))
        if existing:
            return False, f"❌ Title `{title_key}` udah ada."
        await db.execute(
            "INSERT INTO titles (title_key, display, description, created_by) VALUES (?, ?, ?, ?)",
            (title_key, display, description, admin_id)
        )
        await db.commit()
    return True, f"✅ Title `{title_key}` dibuat: {display}"


async def delete_title(title_key: str) -> bool:
    title_key = title_key.lower().strip()
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM titles WHERE title_key = ?", (title_key,))
        # Hapus juga dari user_titles & unequip yang lagi pake
        await db.execute("DELETE FROM user_titles WHERE title_key = ?", (title_key,))
        await db.execute("UPDATE users SET equipped_title = '' WHERE equipped_title = ?",
                         (title_key,))
        await db.commit()
        return cursor.rowcount > 0


async def list_all_titles() -> list[dict]:
    async with get_db() as db:
        rows = await fetchall(db, "SELECT * FROM titles ORDER BY created_at DESC")
        return [dict(r) for r in rows]


async def get_title(title_key: str) -> dict | None:
    async with get_db() as db:
        row = await fetchone(db, "SELECT * FROM titles WHERE title_key = ?", (title_key,))
        return dict(row) if row else None


# ─── KEPEMILIKAN & EQUIP ─────────────────────────────────────────────────────

async def give_title_to_user(user_id: int, title_key: str) -> tuple[bool, str]:
    title_key = title_key.lower().strip()
    title = await get_title(title_key)
    if not title:
        return False, f"❌ Title `{title_key}` tidak ditemukan."

    async with get_db() as db:
        user = await fetchone(db, "SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not user:
            return False, f"❌ User `{user_id}` tidak terdaftar."
        # Cek udah punya belum
        owned = await fetchone(db,
            "SELECT user_id FROM user_titles WHERE user_id = ? AND title_key = ?",
            (user_id, title_key))
        if owned:
            return False, f"⚠️ User udah punya title `{title_key}`."
        await db.execute(
            "INSERT INTO user_titles (user_id, title_key) VALUES (?, ?)",
            (user_id, title_key)
        )
        await db.commit()
    return True, f"✅ Title {title['display']} dikasih ke user `{user_id}`"


async def user_has_title(user_id: int, title_key: str) -> bool:
    async with get_db() as db:
        row = await fetchone(db,
            "SELECT user_id FROM user_titles WHERE user_id = ? AND title_key = ?",
            (user_id, title_key))
        return row is not None


async def get_user_titles(user_id: int) -> list[dict]:
    """List semua title yang dimiliki user, lengkap dengan display & description."""
    async with get_db() as db:
        rows = await fetchall(db, """
            SELECT t.title_key, t.display, t.description, ut.acquired_at
            FROM user_titles ut
            JOIN titles t ON t.title_key = ut.title_key
            WHERE ut.user_id = ?
            ORDER BY ut.acquired_at DESC
        """, (user_id,))
        return [dict(r) for r in rows]


async def equip_title(user_id: int, title_key: str) -> tuple[bool, str]:
    title_key = title_key.lower().strip()
    if title_key == "":
        # Unequip
        async with get_db() as db:
            await db.execute("UPDATE users SET equipped_title = '' WHERE user_id = ?", (user_id,))
            await db.commit()
        return True, "✅ Gelar di-lepas."

    if not await user_has_title(user_id, title_key):
        return False, "❌ Kamu belum punya gelar ini."

    async with get_db() as db:
        await db.execute("UPDATE users SET equipped_title = ? WHERE user_id = ?",
                         (title_key, user_id))
        await db.commit()
    title = await get_title(title_key)
    return True, f"✅ Gelar {title['display']} di-pasang!"


async def get_equipped_title_display(user_id: int) -> str:
    """Return display text dari title yang lagi dipake, atau '' kalau kosong."""
    async with get_db() as db:
        row = await fetchone(db,
            "SELECT equipped_title FROM users WHERE user_id = ?", (user_id,))
        if not row or not row["equipped_title"]:
            return ""
        title = await fetchone(db,
            "SELECT display FROM titles WHERE title_key = ?", (row["equipped_title"],))
        return title["display"] if title else ""
