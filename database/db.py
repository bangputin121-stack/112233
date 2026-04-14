# database/db.py - Database manager for Greena Farm

import aiosqlite
import json
import os
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)
DB_PATH = os.getenv("DB_PATH", "harvest_kingdom.db")

@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Optimasi SQLite buat handle banyak concurrent user
        await db.execute("PRAGMA journal_mode=WAL")        # Multi-reader concurrent
        await db.execute("PRAGMA synchronous=NORMAL")      # Lebih cepet, masih aman
        await db.execute("PRAGMA cache_size=-20000")       # 20MB cache (negative = KB)
        await db.execute("PRAGMA temp_store=MEMORY")       # Temp table di RAM
        await db.execute("PRAGMA mmap_size=268435456")     # 256MB mmap
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("PRAGMA busy_timeout=5000")       # Wait 5s kalau locked
        yield db

async def fetchone(db, sql: str, params: tuple = ()):
    cursor = await db.execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    return row

async def fetchall(db, sql: str, params: tuple = ()):
    cursor = await db.execute(sql, params)
    rows = await cursor.fetchall()
    await cursor.close()
    return rows

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Optimasi SQLite (sama kayak get_db)
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA cache_size=-20000")
        await db.execute("PRAGMA temp_store=MEMORY")
        await db.execute("PRAGMA mmap_size=268435456")
        await db.execute("PRAGMA busy_timeout=5000")
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
            coins INTEGER DEFAULT 50000, gems INTEGER DEFAULT 5,
            display_name TEXT DEFAULT '',
            xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
            plots INTEGER DEFAULT 8, animal_pens INTEGER DEFAULT 2,
            silo_cap INTEGER DEFAULT 100, barn_cap INTEGER DEFAULT 50,
            silo_level INTEGER DEFAULT 1, barn_level INTEGER DEFAULT 1,
            silo_items TEXT DEFAULT '{}', barn_items TEXT DEFAULT '{}',
            land_items TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')), last_daily TEXT,
            total_harvests INTEGER DEFAULT 0, total_sales INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS plots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            slot INTEGER NOT NULL, crop TEXT, planted_at TEXT, ready_at TEXT,
            status TEXT DEFAULT 'empty',
            FOREIGN KEY(user_id) REFERENCES users(user_id), UNIQUE(user_id, slot))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS animal_pens (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            slot INTEGER NOT NULL, animal TEXT, fed_at TEXT, ready_at TEXT,
            status TEXT DEFAULT 'empty',
            FOREIGN KEY(user_id) REFERENCES users(user_id), UNIQUE(user_id, slot))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS buildings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            building TEXT NOT NULL, slot INTEGER NOT NULL DEFAULT 0,
            item TEXT, started_at TEXT, ready_at TEXT, status TEXT DEFAULT 'idle',
            FOREIGN KEY(user_id) REFERENCES users(user_id), UNIQUE(user_id, building, slot))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            slot INTEGER NOT NULL, items TEXT NOT NULL,
            reward_coins INTEGER NOT NULL, reward_xp INTEGER NOT NULL,
            status TEXT DEFAULT 'active', created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(user_id), UNIQUE(user_id, slot))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS market_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER NOT NULL,
            seller_name TEXT, item TEXT NOT NULL, qty INTEGER NOT NULL,
            price INTEGER NOT NULL, listed_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(seller_id) REFERENCES users(user_id))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS obstacles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            slot INTEGER NOT NULL, obstacle TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id), UNIQUE(user_id, slot))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER,
            action TEXT, target_id INTEGER, details TEXT,
            created_at TEXT DEFAULT (datetime('now')))""")
        # Level pabrik per player per building (buat fitur upgrade pabrik)
        await db.execute("""CREATE TABLE IF NOT EXISTS building_levels (
            user_id INTEGER NOT NULL, building TEXT NOT NULL,
            level INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, building),
            FOREIGN KEY(user_id) REFERENCES users(user_id))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS game_settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
        await db.execute("""INSERT OR IGNORE INTO game_settings (key, value) VALUES
            ('bonus_drop_rate','0.05'),('maintenance_mode','0'),
            ('double_xp','0'),('double_coins','0'),
            ('welcome_message','Selamat datang di Greena Farm! 🌾👑'),
            ('max_market_listings','5'),('max_market_price','9999999')""")
        # Migration: add display_name column if not exists
        try:
            await db.execute("ALTER TABLE users ADD COLUMN display_name TEXT DEFAULT ''")
        except Exception:
            pass  # column already exists
        # Migration: add last_orders_refresh column
        try:
            await db.execute("ALTER TABLE users ADD COLUMN last_orders_refresh TEXT")
        except Exception:
            pass
        # Migration: add original_ready_at for pest system
        try:
            await db.execute("ALTER TABLE plots ADD COLUMN original_grow_time INTEGER DEFAULT 0")
        except Exception:
            pass
        # Migration: add channel_msg_id for market channel
        try:
            await db.execute("ALTER TABLE market_listings ADD COLUMN channel_msg_id INTEGER")
        except Exception:
            pass
        await db.commit()
        logger.info("Database initialized successfully")

async def get_user(user_id: int) -> dict | None:
    async with get_db() as db:
        row = await fetchone(db, "SELECT * FROM users WHERE user_id = ?", (user_id,))
        return dict(row) if row else None

async def create_user(user_id: int, username: str, first_name: str) -> dict:
    async with get_db() as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                         (user_id, username or "", first_name or "Farmer"))
        for i in range(8):
            await db.execute("INSERT OR IGNORE INTO plots (user_id, slot, status) VALUES (?, ?, 'empty')", (user_id, i))
        for i in range(2):
            await db.execute("INSERT OR IGNORE INTO animal_pens (user_id, slot, status) VALUES (?, ?, 'empty')", (user_id, i))
        await db.commit()
        row = await fetchone(db, "SELECT * FROM users WHERE user_id = ?", (user_id,))
        return dict(row)

async def update_user(user_id: int, **kwargs) -> None:
    if not kwargs:
        return
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [user_id]
    async with get_db() as db:
        await db.execute(f"UPDATE users SET {fields} WHERE user_id = ?", values)
        await db.commit()

async def get_or_create_user(user_id: int, username: str, first_name: str) -> dict:
    user = await get_user(user_id)
    if not user:
        user = await create_user(user_id, username, first_name)
    else:
        await update_user(user_id, username=username or "", first_name=first_name or "Farmer")
        user["username"] = username or ""
        user["first_name"] = first_name or "Farmer"
    return user

def parse_json_field(data: str | None) -> dict:
    if not data:
        return {}
    try:
        return json.loads(data)
    except Exception:
        return {}

def dump_json_field(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)

async def get_setting(key: str, default=None):
    async with get_db() as db:
        row = await fetchone(db, "SELECT value FROM game_settings WHERE key = ?", (key,))
        return row["value"] if row else default

async def set_setting(key: str, value: str):
    async with get_db() as db:
        await db.execute("INSERT OR REPLACE INTO game_settings (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()

async def log_admin_action(admin_id: int, action: str, target_id: int = None, details: str = ""):
    async with get_db() as db:
        await db.execute("INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?, ?, ?, ?)",
                         (admin_id, action, target_id, details))
        await db.commit()

def get_display_name(user: dict) -> str:
    """Get the best display name for a user."""
    if user.get("display_name"):
        return user["display_name"]
    return user.get("first_name", "Farmer")

async def set_display_name(user_id: int, name: str):
    await update_user(user_id, display_name=name)

async def get_leaderboard(limit: int = 10) -> list[dict]:
    async with get_db() as db:
        rows = await fetchall(db,
            "SELECT user_id, first_name, display_name, level, xp, coins, total_harvests, total_sales "
            "FROM users ORDER BY level DESC, xp DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

async def set_avatar(user_id: int, file_id: str):
    """Save user avatar photo file_id."""
    await set_setting(f"avatar_{user_id}", file_id)

async def get_avatar(user_id: int) -> str | None:
    """Get user avatar photo file_id."""
    return await get_setting(f"avatar_{user_id}")
