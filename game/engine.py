# game/engine.py - Core game logic for Harvest Kingdom

import json
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite

from database.db import get_db, fetchone, fetchall, parse_json_field, dump_json_field, get_setting
from game.data import (
    CROPS, ANIMALS, BUILDINGS, UPGRADE_TOOLS, EXPANSION_TOOLS,
    CLEARING_TOOLS, OBSTACLES, BONUS_DROP_RATE, BARN_UPGRADE, SILO_UPGRADE,
    PLOTS_PER_EXPANSION, get_level_from_xp, get_xp_for_next_level,
    get_item_emoji, get_item_name, PROCESSED_EMOJI
)

logger = logging.getLogger(__name__)

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def fmt_time(seconds: int) -> str:
    if seconds <= 0:
        return "Siap!"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}m {s}s"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m"

async def get_silo_used(user_id: int, silo_items: dict) -> int:
    return sum(silo_items.values())

async def get_barn_used(user_id: int, barn_items: dict) -> int:
    return sum(barn_items.values())

def is_silo_item(item_key: str) -> bool:
    if item_key in CROPS:
        return True
    animal_raw = {"egg", "milk", "bacon", "wool", "goat_milk", "honey", "feather", "fish", "lobster", "mozzarella"}
    if item_key in animal_raw:
        return True
    # Produk hewan custom yang ditambahin admin lewat /addanimal
    from game.data import CUSTOM_ANIMAL_PRODUCTS
    if item_key in CUSTOM_ANIMAL_PRODUCTS:
        return True
    return False

def is_barn_item(item_key: str) -> bool:
    if item_key in UPGRADE_TOOLS or item_key in EXPANSION_TOOLS or item_key in CLEARING_TOOLS:
        return True
    if item_key in ("pesticide", "fertilizer", "super_fertilizer", "animal_doping"):
        return True
    for b in BUILDINGS.values():
        if item_key in b["recipes"]:
            return True
    return False


# ─── INVENTORY ───────────────────────────────────────────────────────────────

async def add_to_inventory(user_id: int, item_key: str, qty: int = 1) -> tuple[bool, str]:
    async with get_db() as db:
        row = await fetchone(db, "SELECT silo_items, barn_items, silo_cap, barn_cap FROM users WHERE user_id = ?", (user_id,))
        silo = parse_json_field(row["silo_items"])
        barn = parse_json_field(row["barn_items"])
        silo_cap = row["silo_cap"]
        barn_cap = row["barn_cap"]

        if is_silo_item(item_key):
            used = sum(silo.values())
            if used + qty > silo_cap:
                return False, (
                    f"📦 GUDANG PENUH!\n\n"
                    f"Kapasitas: {used}/{silo_cap}\n"
                    f"Mau masukin: {qty} item\n\n"
                    f"💡 Jual hasil panen di Gudang\n"
                    f"   atau Upgrade Gudang dulu!"
                )
            silo[item_key] = silo.get(item_key, 0) + qty
            await db.execute("UPDATE users SET silo_items = ? WHERE user_id = ?", (dump_json_field(silo), user_id))
        elif is_barn_item(item_key):
            used = sum(barn.values())
            if used + qty > barn_cap:
                return False, (
                    f"🏚 LUMBUNG PENUH!\n\n"
                    f"Kapasitas: {used}/{barn_cap}\n"
                    f"Mau masukin: {qty} item\n\n"
                    f"💡 Jual produk olahan dulu\n"
                    f"   atau Upgrade Lumbung!"
                )
            barn[item_key] = barn.get(item_key, 0) + qty
            await db.execute("UPDATE users SET barn_items = ? WHERE user_id = ?", (dump_json_field(barn), user_id))
        else:
            return False, f"❓ Item tidak dikenal: {item_key}"

        await db.commit()
        return True, "ok"

async def remove_from_inventory(user_id: int, item_key: str, qty: int = 1) -> tuple[bool, str]:
    async with get_db() as db:
        row = await fetchone(db, "SELECT silo_items, barn_items FROM users WHERE user_id = ?", (user_id,))
        silo = parse_json_field(row["silo_items"])
        barn = parse_json_field(row["barn_items"])

        if is_silo_item(item_key):
            have = silo.get(item_key, 0)
            if have < qty:
                return False, f"Kurang {get_item_name(item_key)} di lumbung (punya {have}, butuh {qty})"
            silo[item_key] = have - qty
            if silo[item_key] == 0:
                del silo[item_key]
            await db.execute("UPDATE users SET silo_items = ? WHERE user_id = ?", (dump_json_field(silo), user_id))
        elif is_barn_item(item_key):
            have = barn.get(item_key, 0)
            if have < qty:
                return False, f"Kurang {get_item_name(item_key)} di lumbung (punya {have}, butuh {qty})"
            barn[item_key] = have - qty
            if barn[item_key] == 0:
                del barn[item_key]
            await db.execute("UPDATE users SET barn_items = ? WHERE user_id = ?", (dump_json_field(barn), user_id))
        else:
            return False, f"Item tidak dikenal: {item_key}"

        await db.commit()
        return True, "ok"

async def get_item_count(user_id: int, item_key: str) -> int:
    async with get_db() as db:
        row = await fetchone(db, "SELECT silo_items, barn_items FROM users WHERE user_id = ?", (user_id,))
        if is_silo_item(item_key):
            return parse_json_field(row["silo_items"]).get(item_key, 0)
        return parse_json_field(row["barn_items"]).get(item_key, 0)

async def add_xp_and_check_level(user_id: int, xp_gain: int) -> tuple[int, bool, int]:
    async with get_db() as db:
        row = await fetchone(db, "SELECT xp, level FROM users WHERE user_id = ?", (user_id,))
        old_xp = row["xp"]
        old_level = row["level"]
        new_xp = old_xp + xp_gain
        new_level = get_level_from_xp(new_xp)
        leveled_up = new_level > old_level
        await db.execute("UPDATE users SET xp = ?, level = ? WHERE user_id = ?", (new_xp, new_level, user_id))
        await db.commit()
        return new_level, leveled_up, new_xp


# ─── CROPS ───────────────────────────────────────────────────────────────────

async def get_plots(user_id: int) -> list[dict]:
    async with get_db() as db:
        rows = await fetchall(db, 
            "SELECT * FROM plots WHERE user_id = ? ORDER BY slot", (user_id,)
        )
        return [dict(r) for r in rows]

async def plant_crop(user_id: int, slot: int, crop_key: str) -> tuple[bool, str]:
    if crop_key not in CROPS:
        return False, "❓ Tanaman tidak dikenal."
    crop = CROPS[crop_key]

    async with get_db() as db:
        user = dict(await fetchone(db, "SELECT * FROM users WHERE user_id = ?", (user_id,)))
        if crop["level_req"] > user["level"]:
            return False, f"🔒 Butuh Level {crop['level_req']}."

        plot = await fetchone(db, "SELECT * FROM plots WHERE user_id = ? AND slot = ?", (user_id, slot))
        if not plot or plot["status"] not in ("empty",):
            return False, "🌱 Lahan ini tidak kosong."

        seed_cost = crop["seed_cost"]
        if user["coins"] < seed_cost:
            kurang = seed_cost - user["coins"]
            return False, (
                f"💸 SALDO TIDAK CUKUP!\n\n"
                f"Butuh: Rp{seed_cost:,}\n"
                f"Punya: Rp{user['coins']:,}\n"
                f"Kurang: Rp{kurang:,}\n\n"
                f"💡 Jual hasil panen di Gudang dulu!"
            )

        now = utcnow()
        ready_at = now + timedelta(seconds=crop["grow_time"])

        await db.execute(
            "UPDATE plots SET crop=?, planted_at=?, ready_at=?, status='growing' WHERE user_id=? AND slot=?",
            (crop_key, now.isoformat(), ready_at.isoformat(), user_id, slot)
        )
        await db.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (seed_cost, user_id))
        await db.commit()

    # Check for pest attack
    await check_pest_on_plant(user_id, user["plots"])
    return True, f"✅ Ditanam {crop['emoji']} {crop['name']}! Siap dalam {fmt_time(crop['grow_time'])}."

async def harvest_crop(user_id: int, slot: int) -> tuple[bool, str]:
    async with get_db() as db:
        plot = await fetchone(db, 
            "SELECT * FROM plots WHERE user_id = ? AND slot = ?", (user_id, slot)
        )
        if not plot or plot["status"] != "growing":
            return False, "Tidak ada yang bisa dipanen di sini."

        ready_at = datetime.fromisoformat(plot["ready_at"])
        if ready_at.tzinfo is None:
            ready_at = ready_at.replace(tzinfo=timezone.utc)
        now = utcnow()

        if now < ready_at:
            remaining = int((ready_at - now).total_seconds())
            return False, f"⏳ {CROPS[plot['crop']]['emoji']} {CROPS[plot['crop']]['name']} belum siap! ({fmt_time(remaining)} lagi)"

        crop_key = plot["crop"]
        crop = CROPS[crop_key]

        ok, msg = await add_to_inventory(user_id, crop_key, 1)
        if not ok:
            return False, msg

        await db.execute("UPDATE plots SET crop=NULL, planted_at=NULL, ready_at=NULL, status='empty' WHERE user_id=? AND slot=?",
                         (user_id, slot))

        bonus_drop = ""
        bonus_rate = float(await get_setting("bonus_drop_rate", BONUS_DROP_RATE))
        if random.random() < bonus_rate:
            all_tools = list(UPGRADE_TOOLS.keys()) + list(CLEARING_TOOLS.keys()) + list(EXPANSION_TOOLS.keys())
            bonus_item = random.choice(all_tools)
            ok2, _ = await add_to_inventory(user_id, bonus_item, 1)
            if ok2:
                b_emoji = get_item_emoji(bonus_item)
                b_name = get_item_name(bonus_item)
                bonus_drop = f"\n🎁 Bonus item: {b_emoji} {b_name}!"

        await db.execute("UPDATE users SET total_harvests = total_harvests + 1 WHERE user_id = ?", (user_id,))
        await db.commit()

    new_level, leveled_up, _ = await add_xp_and_check_level(user_id, crop["xp"])
    level_msg = f"\n🎉 Naik Level! Kamu sekarang Level {new_level}!" if leveled_up else ""
    return True, f"✅ Dipanen {crop['emoji']} {crop['name']}! +{crop['xp']} XP{bonus_drop}{level_msg}"

async def harvest_all(user_id: int) -> tuple[int, int, str]:
    plots = await get_plots(user_id)
    now = utcnow()
    harvested = 0
    failed = 0
    details = []
    for p in plots:
        if p["status"] == "growing":
            ready_at = datetime.fromisoformat(p["ready_at"])
            if ready_at.tzinfo is None:
                ready_at = ready_at.replace(tzinfo=timezone.utc)
            if now >= ready_at:
                ok, msg = await harvest_crop(user_id, p["slot"])
                if ok:
                    harvested += 1
                else:
                    failed += 1
    return harvested, failed, ""


# ─── HAMA & PUPUK ────────────────────────────────────────────────────────────

async def check_pest_on_plant(user_id: int, total_plots: int):
    """Random chance to infect a growing plot with pests after planting."""
    if total_plots < 25:
        return  # No pests for small farms
    
    chance = 0.10 if total_plots < 50 else 0.20

    if random.random() < chance:
        async with get_db() as db:
            # Find a random growing plot to infect
            rows = await fetchall(db,
                "SELECT slot FROM plots WHERE user_id = ? AND status = 'growing'", (user_id,))
            if rows:
                target = random.choice([dict(r) for r in rows])
                await db.execute(
                    "UPDATE plots SET status = 'infected' WHERE user_id = ? AND slot = ?",
                    (user_id, target["slot"]))
                await db.commit()


async def spray_pesticide(user_id: int, slot: int) -> tuple[bool, str]:
    """Spray pesticide on infected plot. Cures pest, plant regrows at 50% original time."""
    have = await get_item_count(user_id, "pesticide")
    if have < 1:
        return False, "❌ Kamu tidak punya 🧴 Pestisida!\nBeli di 🛒 **Toko Alat** (Rp100)."

    async with get_db() as db:
        plot = await fetchone(db,
            "SELECT * FROM plots WHERE user_id = ? AND slot = ?", (user_id, slot))
        if not plot:
            return False, "❌ Lahan tidak ditemukan."
        if plot["status"] != "infected":
            return False, "🌱 Tanaman ini tidak kena hama."

        crop_key = plot["crop"]
        if crop_key not in CROPS:
            return False, "❌ Tanaman tidak dikenal."
        crop = CROPS[crop_key]

        # Use pesticide
        await remove_from_inventory(user_id, "pesticide", 1)

        # Regrow at 50% of original time
        now = utcnow()
        regrow_time = int(crop["grow_time"] * 0.5)
        new_ready = now + timedelta(seconds=regrow_time)

        await db.execute(
            "UPDATE plots SET status='growing', planted_at=?, ready_at=? WHERE user_id=? AND slot=?",
            (now.isoformat(), new_ready.isoformat(), user_id, slot))
        await db.commit()

    return True, f"✅ 🧴 Pestisida disemprot! {crop['emoji']} {crop['name']} tumbuh lagi dalam {fmt_time(regrow_time)}."


async def use_fertilizer(user_id: int, slot: int, fert_type: str) -> tuple[bool, str]:
    """Use fertilizer on a growing plot to speed it up."""
    if fert_type not in ("fertilizer", "super_fertilizer"):
        return False, "❌ Jenis pupuk tidak dikenal."

    have = await get_item_count(user_id, fert_type)
    if have < 1:
        name = "🧪 Pupuk Biasa" if fert_type == "fertilizer" else "⚗️ Pupuk Super"
        return False, f"❌ Kamu tidak punya {name}!\nBeli di 🛒 **Toko Alat**."

    async with get_db() as db:
        plot = await fetchone(db,
            "SELECT * FROM plots WHERE user_id = ? AND slot = ?", (user_id, slot))
        if not plot:
            return False, "❌ Lahan tidak ditemukan."
        if plot["status"] != "growing":
            return False, "🌱 Hanya bisa pakai pupuk di tanaman yang sedang tumbuh."

        ready_at = datetime.fromisoformat(plot["ready_at"])
        if ready_at.tzinfo is None:
            ready_at = ready_at.replace(tzinfo=timezone.utc)
        now = utcnow()

        if now >= ready_at:
            return False, "✅ Tanaman sudah siap panen! Tidak perlu pupuk."

        remaining = (ready_at - now).total_seconds()
        speed = 0.30 if fert_type == "fertilizer" else 0.50
        reduction = int(remaining * speed)
        new_ready = ready_at - timedelta(seconds=reduction)

        await remove_from_inventory(user_id, fert_type, 1)
        await db.execute(
            "UPDATE plots SET ready_at=? WHERE user_id=? AND slot=?",
            (new_ready.isoformat(), user_id, slot))
        await db.commit()

    crop = CROPS.get(plot["crop"], {})
    new_remaining = max(0, int((new_ready - now).total_seconds()))
    pct = "30%" if fert_type == "fertilizer" else "50%"
    name = "🧪 Pupuk Biasa" if fert_type == "fertilizer" else "⚗️ Pupuk Super"
    return True, f"✅ {name} dipakai! {crop.get('emoji','🌱')} {crop.get('name','')} {pct} lebih cepat!\nSiap dalam {fmt_time(new_remaining)}."


# ─── ANIMALS ─────────────────────────────────────────────────────────────────

async def get_animal_pens(user_id: int) -> list[dict]:
    async with get_db() as db:
        rows = await fetchall(db, 
            "SELECT * FROM animal_pens WHERE user_id = ? ORDER BY slot", (user_id,)
        )
        return [dict(r) for r in rows]

async def buy_animal(user_id: int, slot: int, animal_key: str) -> tuple[bool, str]:
    if animal_key not in ANIMALS:
        return False, "❓ Hewan tidak dikenal."
    animal = ANIMALS[animal_key]
    async with get_db() as db:
        user = dict(await fetchone(db, "SELECT * FROM users WHERE user_id = ?", (user_id,)))
        if animal["level_req"] > user["level"]:
            return False, f"🔒 Butuh Level {animal['level_req']}."
        if user["coins"] < animal["buy_cost"]:
            return False, f"💵 Butuh Rp{animal['buy_cost']:,} (kamu punya Rp{user['coins']:,})."

        pen = await fetchone(db, "SELECT * FROM animal_pens WHERE user_id = ? AND slot = ?", (user_id, slot))
        if not pen:
            return False, "❌ Invalid pen slot."
        if pen["status"] != "empty":
            return False, f"🐾 Kandang ini sudah ada {pen['animal']}."

        now = utcnow()
        ready_at = now + timedelta(seconds=animal["feed_time"])
        await db.execute(
            "UPDATE animal_pens SET animal=?, fed_at=?, ready_at=?, status='producing' WHERE user_id=? AND slot=?",
            (animal_key, now.isoformat(), ready_at.isoformat(), user_id, slot)
        )
        await db.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (animal["buy_cost"], user_id))
        await db.commit()
        return True, f"✅ {animal['emoji']} {animal['name']} masuk! Produk pertama siap dalam {fmt_time(animal['feed_time'])}."

async def collect_animal(user_id: int, slot: int) -> tuple[bool, str]:
    async with get_db() as db:
        pen = await fetchone(db, "SELECT * FROM animal_pens WHERE user_id = ? AND slot = ?", (user_id, slot))
        if not pen or pen["status"] == "empty":
            return False, "Tidak ada hewan di sini."
        if pen["status"] != "producing":
            return False, "Hewan belum siap."

        ready_at = datetime.fromisoformat(pen["ready_at"])
        if ready_at.tzinfo is None:
            ready_at = ready_at.replace(tzinfo=timezone.utc)
        now = utcnow()

        if now < ready_at:
            remaining = int((ready_at - now).total_seconds())
            animal = ANIMALS[pen["animal"]]
            return False, f"⏳ {animal['emoji']} {animal['name']} butuh {fmt_time(remaining)} lagi."

        animal_key = pen["animal"]
        animal = ANIMALS[animal_key]
        product = animal["product"]

        ok, msg = await add_to_inventory(user_id, product, 1)
        if not ok:
            return False, msg

        next_ready = now + timedelta(seconds=animal["feed_time"])
        await db.execute(
            "UPDATE animal_pens SET fed_at=?, ready_at=?, status='producing' WHERE user_id=? AND slot=?",
            (now.isoformat(), next_ready.isoformat(), user_id, slot)
        )
        await db.commit()

    new_level, leveled_up, _ = await add_xp_and_check_level(user_id, 3)
    level_msg = f"\n🎉 Naik Level! Kamu sekarang Level {new_level}!" if leveled_up else ""
    return True, f"✅ Diambil {animal['prod_emoji']} {get_item_name(product)} dari {animal['emoji']} {animal['name']}!{level_msg}"


async def transfer_item_to_player(sender_id: int, receiver_id: int, item_key: str, qty: int) -> tuple[bool, str]:
    """Transfer item antar player. Limit 5x sehari per sender.
    Aturan:
    - Sender harus punya item yg cukup
    - Receiver harus terdaftar di bot
    - Receiver harus punya kapasitas penyimpanan
    - Limit 5 transfer/hari per sender (reset jam 07:00 WIB)
    - Tidak bisa transfer ke diri sendiri
    """
    if sender_id == receiver_id:
        return False, "❌ Tidak bisa transfer ke diri sendiri."

    if qty <= 0:
        return False, "❌ Jumlah harus lebih dari 0."

    # Cek receiver ada di DB
    async with get_db() as db:
        recv = await fetchone(db, "SELECT user_id, first_name FROM users WHERE user_id = ?", (receiver_id,))
        if not recv:
            return False, f"❌ User dengan ID `{receiver_id}` tidak ditemukan di bot."

        # Cek limit harian sender (reset jam 07 WIB)
        from datetime import datetime, timedelta, timezone as tz_mod
        wib = tz_mod(timedelta(hours=7))
        now_wib = datetime.now(wib)
        daily_day = (now_wib - timedelta(hours=7)).date().isoformat()

        sender = dict(await fetchone(db, "SELECT * FROM users WHERE user_id = ?", (sender_id,)))
        # last_transfer_day & transfer_count_today disimpen di game_settings
        # supaya nggak nambah kolom DB
        from database.db import get_setting, set_setting
        key_day = f"transfer_day_{sender_id}"
        key_cnt = f"transfer_cnt_{sender_id}"
        last_day = await get_setting(key_day, "")
        if last_day == daily_day:
            count = int(await get_setting(key_cnt, "0"))
        else:
            count = 0

        if count >= 5:
            next_reset = now_wib.replace(hour=7, minute=0, second=0, microsecond=0)
            if now_wib >= next_reset:
                next_reset = next_reset + timedelta(days=1)
            jam_lagi = int((next_reset - now_wib).total_seconds() // 3600)
            return False, (
                f"❌ LIMIT TRANSFER HARIAN HABIS!\n\n"
                f"Maks 5 transfer/hari\n"
                f"Reset: jam 07:00 WIB ({jam_lagi} jam lagi)"
            )

    # Cek stock sender
    have = await get_item_count(sender_id, item_key)
    if have < qty:
        return False, f"❌ Stok tidak cukup. Punya: {have}, butuh: {qty}"

    # Cek receiver capacity (try add dulu — kalau gagal nggak jadi)
    # Kurangi dari sender dulu
    ok_remove, msg_remove = await remove_from_inventory(sender_id, item_key, qty)
    if not ok_remove:
        return False, msg_remove

    ok_add, msg_add = await add_to_inventory(receiver_id, item_key, qty)
    if not ok_add:
        # Refund balik ke sender
        await add_to_inventory(sender_id, item_key, qty)
        return False, f"❌ Gagal kirim: {msg_add}\n\n_(Item sudah dikembalikan ke kamu)_"

    # Update counter
    from database.db import set_setting
    await set_setting(key_day, daily_day)
    await set_setting(key_cnt, str(count + 1))

    emoji = get_item_emoji(item_key)
    name = get_item_name(item_key)
    recv_name = recv["first_name"] or "Petani"
    return True, (
        f"✅ Transfer berhasil!\n\n"
        f"📤 Kirim: {qty}x {emoji} {name}\n"
        f"📥 Ke: **{recv_name}** (`{receiver_id}`)\n"
        f"📊 Sisa kuota hari ini: {5 - (count + 1)}/5"
    )


async def apply_animal_doping(user_id: int, slot: int) -> tuple[bool, str]:
    """Pake doping ke hewan: kurangin waktu produksi 30%."""
    async with get_db() as db:
        # Cek inventory player
        user = dict(await fetchone(db, "SELECT barn_items FROM users WHERE user_id = ?", (user_id,)))
        barn = parse_json_field(user["barn_items"])
        if barn.get("animal_doping", 0) < 1:
            return False, (
                "💉 KAMU TIDAK PUNYA DOPING!\n\n"
                "Beli di 🛒 Toko Alat → kategori Peternakan\n"
                "Harga: Rp30.000/biji"
            )

        pen = await fetchone(db, "SELECT * FROM animal_pens WHERE user_id = ? AND slot = ?", (user_id, slot))
        if not pen or pen["status"] != "producing":
            return False, "❌ Kandang ini kosong atau hewan belum aktif."

        ready_at = datetime.fromisoformat(pen["ready_at"])
        if ready_at.tzinfo is None:
            ready_at = ready_at.replace(tzinfo=timezone.utc)
        now = utcnow()
        if now >= ready_at:
            return False, "✅ Hewan udah siap panen, ngapain pake doping?"

        # Kurangin waktu sisa 30%
        remaining = (ready_at - now).total_seconds()
        new_remaining = remaining * 0.7  # 30% lebih cepet
        new_ready_at = now + timedelta(seconds=new_remaining)

        # Pake 1 doping
        barn["animal_doping"] -= 1
        if barn["animal_doping"] <= 0:
            del barn["animal_doping"]

        await db.execute(
            "UPDATE animal_pens SET ready_at=? WHERE user_id=? AND slot=?",
            (new_ready_at.isoformat(), user_id, slot)
        )
        await db.execute(
            "UPDATE users SET barn_items = ? WHERE user_id = ?",
            (dump_json_field(barn), user_id)
        )
        await db.commit()

    saved = int(remaining * 0.3)
    animal = ANIMALS.get(pen["animal"], {})
    return True, (
        f"💉 Doping berhasil dipake!\n\n"
        f"{animal.get('emoji', '🐾')} {animal.get('name', 'Hewan')} sekarang siap dalam {fmt_time(int(new_remaining))}\n"
        f"⚡ Hemat: {fmt_time(saved)}"
    )


async def remove_animal(user_id: int, slot: int) -> tuple[bool, str]:
    """Hapus hewan dari kandang. Refund 50% dari harga beli."""
    async with get_db() as db:
        pen = await fetchone(db, "SELECT * FROM animal_pens WHERE user_id = ? AND slot = ?", (user_id, slot))
        if not pen or pen["status"] == "empty":
            return False, "❌ Kandang ini kosong, tidak ada hewan yang bisa dihapus."

        animal_key = pen["animal"]
        # Cek hewan default + custom
        if animal_key in ANIMALS:
            animal = ANIMALS[animal_key]
        else:
            return False, "❌ Hewan tidak dikenal."

        # Refund 50% biar player nggak rugi total
        refund = animal["buy_cost"] // 2

        await db.execute(
            "UPDATE animal_pens SET animal=NULL, fed_at=NULL, ready_at=NULL, status='empty' WHERE user_id=? AND slot=?",
            (user_id, slot)
        )
        await db.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id = ?",
            (refund, user_id)
        )
        await db.commit()

    return True, (
        f"🗑️ {animal['emoji']} {animal['name']} dihapus dari kandang.\n"
        f"💵 Refund: Rp{refund:,} (50%)\n\n"
        f"Kandang sekarang kosong, siap diisi hewan baru!"
    )


async def collect_all_animals(user_id: int) -> tuple[int, int, str]:
    """Collect all ready animal products at once."""
    pens = await get_animal_pens(user_id)
    now = utcnow()
    collected = 0
    failed = 0
    for pen in pens:
        if pen["status"] == "producing" and pen["ready_at"]:
            ready_at = datetime.fromisoformat(pen["ready_at"])
            if ready_at.tzinfo is None:
                ready_at = ready_at.replace(tzinfo=timezone.utc)
            if now >= ready_at:
                ok, _ = await collect_animal(user_id, pen["slot"])
                if ok:
                    collected += 1
                else:
                    failed += 1
    return collected, failed, ""


# ─── BUILDINGS ───────────────────────────────────────────────────────────────

async def get_user_buildings(user_id: int) -> list[dict]:
    async with get_db() as db:
        rows = await fetchall(db, 
            "SELECT * FROM buildings WHERE user_id = ? ORDER BY building, slot", (user_id,)
        )
        return [dict(r) for r in rows]

async def buy_building(user_id: int, building_key: str) -> tuple[bool, str]:
    if building_key not in BUILDINGS:
        return False, "❓ Bangunan tidak dikenal."
    bld = BUILDINGS[building_key]
    async with get_db() as db:
        user = dict(await fetchone(db, "SELECT * FROM users WHERE user_id = ?", (user_id,)))
        if bld["level_req"] > user["level"]:
            return False, f"🔒 Butuh Level {bld['level_req']}."
        if user["coins"] < bld["buy_cost"]:
            return False, f"💵 Butuh Rp{bld['buy_cost']:,}."

        existing = await fetchone(db, 
            "SELECT id FROM buildings WHERE user_id = ? AND building = ? AND slot = 0", (user_id, building_key)
        )
        if existing:
            return False, f"🏭 Kamu sudah punya {bld['name']}."

        for slot in range(bld["slots"]):
            await db.execute("""
                INSERT OR IGNORE INTO buildings (user_id, building, slot, status)
                VALUES (?, ?, ?, 'idle')
            """, (user_id, building_key, slot))

        await db.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (bld["buy_cost"], user_id))
        await db.commit()
        return True, f"✅ {bld['emoji']} {bld['name']} dibangun! Kamu punya {bld['slots']} slot produksi."

async def start_production(user_id: int, building_key: str, recipe_key: str) -> tuple[bool, str]:
    if building_key not in BUILDINGS:
        return False, "❓ Bangunan tidak dikenal."
    bld = BUILDINGS[building_key]
    if recipe_key not in bld["recipes"]:
        return False, "❓ Resep tidak dikenal."
    recipe = bld["recipes"][recipe_key]

    async with get_db() as db:
        slots = await fetchall(db, 
            "SELECT * FROM buildings WHERE user_id = ? AND building = ? ORDER BY slot", (user_id, building_key)
        )
        slots = [dict(s) for s in slots]
        if not slots:
            return False, f"🏭 Kamu tidak punya {bld['name']}. Beli dulu!"

        free_slot = next((s for s in slots if s["status"] == "idle"), None)
        if not free_slot:
            return False, f"⚙️ Semua {bld['name']} slot sedang sibuk!"

        # Check and consume ingredients
        for ing, qty in recipe["inputs"].items():
            count = await get_item_count(user_id, ing)
            if count < qty:
                ing_emoji = get_item_emoji(ing)
                return False, f"❌ Butuh {qty}x {ing_emoji} {get_item_name(ing)} (you have {count})."

        for ing, qty in recipe["inputs"].items():
            await remove_from_inventory(user_id, ing, qty)

        now = utcnow()
        ready_at = now + timedelta(seconds=recipe["time"])
        await db.execute("""
            UPDATE buildings SET item=?, started_at=?, ready_at=?, status='producing'
            WHERE user_id=? AND building=? AND slot=?
        """, (recipe_key, now.isoformat(), ready_at.isoformat(), user_id, building_key, free_slot["slot"]))
        await db.commit()

        out_emoji = PROCESSED_EMOJI.get(recipe_key, "📦")
        return True, f"✅ {out_emoji} {get_item_name(recipe_key)} production started! Siap dalam {fmt_time(recipe['time'])}."

async def collect_production(user_id: int, building_key: str, slot: int) -> tuple[bool, str]:
    async with get_db() as db:
        bld_slot = await fetchone(db, 
            "SELECT * FROM buildings WHERE user_id=? AND building=? AND slot=?", (user_id, building_key, slot)
        )
        if not bld_slot:
            return False, "❓ Slot bangunan tidak ditemukan."
        bld_slot = dict(bld_slot)
        if bld_slot["status"] != "producing":
            return False, "Tidak ada yang bisa diambil di sini."

        ready_at = datetime.fromisoformat(bld_slot["ready_at"])
        if ready_at.tzinfo is None:
            ready_at = ready_at.replace(tzinfo=timezone.utc)
        if utcnow() < ready_at:
            remaining = int((ready_at - utcnow()).total_seconds())
            item_emoji = PROCESSED_EMOJI.get(bld_slot["item"], "📦")
            return False, f"⏳ {item_emoji} {get_item_name(bld_slot['item'])} siap dalam {fmt_time(remaining)}."

        recipe_key = bld_slot["item"]
        bld = BUILDINGS[building_key]
        recipe = bld["recipes"].get(recipe_key, {})

        ok, msg = await add_to_inventory(user_id, recipe_key, 1)
        if not ok:
            return False, msg

        await db.execute("UPDATE buildings SET item=NULL, started_at=NULL, ready_at=NULL, status='idle' WHERE user_id=? AND building=? AND slot=?",
                         (user_id, building_key, slot))
        await db.commit()

    new_level, leveled_up, _ = await add_xp_and_check_level(user_id, recipe.get("xp", 5))
    level_msg = f"\n🎉 Naik Level! Kamu sekarang Level {new_level}!" if leveled_up else ""
    out_emoji = PROCESSED_EMOJI.get(recipe_key, "📦")
    return True, f"✅ Diambil {out_emoji} {get_item_name(recipe_key)}! +{recipe.get('xp',5)} XP{level_msg}"


# ─── ORDERS ──────────────────────────────────────────────────────────────────

import random as _random

def _generate_order(user_level: int) -> dict:
    all_items = []
    for crop_k, crop_v in CROPS.items():
        if crop_v["level_req"] <= user_level:
            all_items.append((crop_k, crop_v["sell_price"]))
    # Only include recipes from buildings the user's level can access
    for bld in BUILDINGS.values():
        if bld["level_req"] <= user_level:
            for rec_k, rec_v in bld["recipes"].items():
                all_items.append((rec_k, rec_v["sell_price"]))

    if not all_items:
        all_items = [("wheat", 5)]

    num_items = _random.randint(1, min(3, len(all_items)))
    selected = _random.sample(all_items, num_items)
    items = {}
    total_value = 0
    for item_key, base_price in selected:
        qty = _random.randint(1, 4)
        items[item_key] = qty
        total_value += base_price * qty

    reward_coins = int(total_value * 1.4)
    reward_xp = max(5, int(total_value // 10))
    return {"items": items, "reward_coins": reward_coins, "reward_xp": reward_xp}

async def ensure_orders(user_id: int, user_level: int):
    """Ensure 9 orders exist. Auto-refresh all orders older than 48h."""
    now = utcnow()

    async with get_db() as db:
        # Clean up old completed orders first
        await db.execute("DELETE FROM orders WHERE user_id = ? AND status = 'completed'", (user_id,))

        # Check if 48h auto-refresh needed
        user = await fetchone(db, "SELECT last_orders_refresh FROM users WHERE user_id = ?", (user_id,))
        last_refresh = user["last_orders_refresh"] if user and user["last_orders_refresh"] else None

        need_full_refresh = False
        if last_refresh:
            try:
                lr = datetime.fromisoformat(last_refresh)
                if lr.tzinfo is None:
                    lr = lr.replace(tzinfo=timezone.utc)
                if (now - lr).total_seconds() >= 48 * 3600:
                    need_full_refresh = True
            except Exception:
                need_full_refresh = True
        else:
            await db.execute("UPDATE users SET last_orders_refresh = ? WHERE user_id = ?",
                             (now.isoformat(), user_id))

        if need_full_refresh:
            await db.execute("DELETE FROM orders WHERE user_id = ?", (user_id,))
            await db.execute("UPDATE users SET last_orders_refresh = ? WHERE user_id = ?",
                             (now.isoformat(), user_id))
            for slot in range(9):
                order = _generate_order(user_level)
                await db.execute("""
                    INSERT OR REPLACE INTO orders (user_id, slot, items, reward_coins, reward_xp, status)
                    VALUES (?, ?, ?, ?, ?, 'active')
                """, (user_id, slot, json.dumps(order["items"]), order["reward_coins"], order["reward_xp"]))
            await db.commit()
            return

        # Fill empty slots
        existing = await fetchall(db,
            "SELECT slot FROM orders WHERE user_id = ? AND status = 'active'", (user_id,)
        )
        used_slots = {r["slot"] for r in existing}
        for slot in range(9):
            if slot not in used_slots:
                order = _generate_order(user_level)
                await db.execute("""
                    INSERT OR REPLACE INTO orders (user_id, slot, items, reward_coins, reward_xp, status)
                    VALUES (?, ?, ?, ?, ?, 'active')
                """, (user_id, slot, json.dumps(order["items"]), order["reward_coins"], order["reward_xp"]))
        await db.commit()


async def refresh_orders(user_id: int, user_level: int) -> tuple[bool, str]:
    """Manual refresh — max once per 24h."""
    now = utcnow()
    async with get_db() as db:
        user = await fetchone(db, "SELECT last_orders_refresh FROM users WHERE user_id = ?", (user_id,))
        last_refresh = user["last_orders_refresh"] if user and user["last_orders_refresh"] else None

        if last_refresh:
            try:
                lr = datetime.fromisoformat(last_refresh)
                if lr.tzinfo is None:
                    lr = lr.replace(tzinfo=timezone.utc)
                diff = (now - lr).total_seconds()
                if diff < 24 * 3600:
                    remaining = int(24 * 3600 - diff)
                    return False, f"⏳ Refresh tersedia dalam {fmt_time(remaining)} lagi."
            except Exception:
                pass

        # Do refresh — delete ALL orders and regenerate
        await db.execute("DELETE FROM orders WHERE user_id = ?", (user_id,))
        await db.execute("UPDATE users SET last_orders_refresh = ? WHERE user_id = ?",
                         (now.isoformat(), user_id))
        for slot in range(9):
            order = _generate_order(user_level)
            await db.execute("""
                INSERT OR REPLACE INTO orders (user_id, slot, items, reward_coins, reward_xp, status)
                VALUES (?, ?, ?, ?, ?, 'active')
            """, (user_id, slot, json.dumps(order["items"]), order["reward_coins"], order["reward_xp"]))
        await db.commit()
    return True, "✅ Pesanan berhasil di-refresh! 9 pesanan baru tersedia."

async def get_orders(user_id: int) -> list[dict]:
    async with get_db() as db:
        rows = await fetchall(db, 
            "SELECT * FROM orders WHERE user_id = ? AND status = 'active' ORDER BY slot", (user_id,)
        )
        return [dict(r) for r in rows]

async def fulfill_order(user_id: int, order_id: int) -> tuple[bool, str]:
    async with get_db() as db:
        order = await fetchone(db, 
            "SELECT * FROM orders WHERE id = ? AND user_id = ? AND status = 'active'", (order_id, user_id)
        )
        if not order:
            return False, "❌ Pesanan tidak ditemukan."
        order = dict(order)
        items_needed = json.loads(order["items"])

        # Check all items available
        for item_key, qty in items_needed.items():
            have = await get_item_count(user_id, item_key)
            if have < qty:
                emoji = get_item_emoji(item_key)
                return False, f"❌ Butuh {qty}x {emoji} {get_item_name(item_key)} (punya {have})."

        # Remove items
        for item_key, qty in items_needed.items():
            await remove_from_inventory(user_id, item_key, qty)

        # Give rewards
        coins = order["reward_coins"]
        double = await get_setting("double_coins", "0")
        if double == "1":
            coins *= 2

        await db.execute("UPDATE users SET coins = coins + ?, total_sales = total_sales + 1 WHERE user_id = ?", (coins, user_id))
        await db.execute("UPDATE orders SET status = 'completed' WHERE id = ?", (order_id,))
        await db.commit()

    # Generate replacement — delete old completed order first to avoid UNIQUE conflict
    user_row = await get_user_full(user_id)
    new_order = _generate_order(user_row["level"])
    async with get_db() as db:
        await db.execute("DELETE FROM orders WHERE user_id = ? AND slot = ? AND status = 'completed'",
                         (user_id, order["slot"]))
        await db.execute("""
            INSERT OR REPLACE INTO orders (user_id, slot, items, reward_coins, reward_xp, status)
            VALUES (?, ?, ?, ?, ?, 'active')
        """, (user_id, order["slot"], json.dumps(new_order["items"]), new_order["reward_coins"], new_order["reward_xp"]))
        await db.commit()

    new_level, leveled_up, _ = await add_xp_and_check_level(user_id, order["reward_xp"])
    level_msg = f"\n🎉 Naik Level! Kamu sekarang Level {new_level}!" if leveled_up else ""
    return True, f"✅ Pesanan selesai! +Rp{coins:,} +{order['reward_xp']} XP{level_msg}"


# ─── MARKET ──────────────────────────────────────────────────────────────────

async def list_item_on_market(user_id: int, seller_name: str, item_key: str, qty: int, price: int) -> tuple[bool, str, int]:
    max_price = int(await get_setting("max_market_price", "9999999"))
    max_listings = int(await get_setting("max_market_listings", "5"))

    if price > max_price:
        return False, f"💵 Harga maksimal Rp{max_price:,} per item.", 0
    if qty < 1 or price < 1:
        return False, "❌ Jumlah dan harga harus positif.", 0

    async with get_db() as db:
        count = await fetchone(db, 
            "SELECT COUNT(*) as c FROM market_listings WHERE seller_id = ?", (user_id,)
        )
        if count["c"] >= max_listings:
            return False, f"🏪 Kamu hanya bisa punya {max_listings} listing. Hapus salah satu dulu.", 0

    ok, msg = await remove_from_inventory(user_id, item_key, qty)
    if not ok:
        return False, msg, 0

    async with get_db() as db:
        cursor = await db.execute("""
            INSERT INTO market_listings (seller_id, seller_name, item, qty, price)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, seller_name, item_key, qty, price))
        listing_id = cursor.lastrowid
        await db.commit()

    emoji = get_item_emoji(item_key)
    return True, f"✅ Terdaftar {qty}x {emoji} {get_item_name(item_key)} @ Rp{price:,}/satuan.", listing_id

async def get_market_listings(page: int = 0, per_page: int = 9) -> list[dict]:
    async with get_db() as db:
        rows = await fetchall(db, 
            "SELECT * FROM market_listings ORDER BY listed_at DESC LIMIT ? OFFSET ?",
            (per_page, page * per_page)
        )
        return [dict(r) for r in rows]

async def buy_from_market(buyer_id: int, listing_id: int) -> tuple[bool, str]:
    async with get_db() as db:
        listing = await fetchone(db, "SELECT * FROM market_listings WHERE id = ?", (listing_id,))
        if not listing:
            return False, "❌ Listing tidak ditemukan."
        listing = dict(listing)

        if listing["seller_id"] == buyer_id:
            return False, "❌ You can't buy your own listing!"

        buyer = dict(await fetchone(db, "SELECT * FROM users WHERE user_id = ?", (buyer_id,)))
        total_cost = listing["price"] * listing["qty"]
        if buyer["coins"] < total_cost:
            return False, f"💵 Kurang uang! Butuh Rp{total_cost:,} (punya Rp{buyer['coins']:,})."

        ok, msg = await add_to_inventory(buyer_id, listing["item"], listing["qty"])
        if not ok:
            return False, msg

        await db.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (total_cost, buyer_id))
        await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (total_cost, listing["seller_id"]))
        await db.execute("DELETE FROM market_listings WHERE id = ?", (listing_id,))
        await db.commit()

        emoji = get_item_emoji(listing["item"])
        return True, f"✅ Dibeli {listing['qty']}x {emoji} {get_item_name(listing['item'])} seharga Rp{total_cost:,}!"

async def remove_market_listing(user_id: int, listing_id: int) -> tuple[bool, str]:
    async with get_db() as db:
        listing = await fetchone(db, 
            "SELECT * FROM market_listings WHERE id = ? AND seller_id = ?", (listing_id, user_id)
        )
        if not listing:
            return False, "❌ Listing tidak ditemukan."
        listing = dict(listing)

        ok, msg = await add_to_inventory(user_id, listing["item"], listing["qty"])
        if not ok:
            return False, f"❌ Gagal mengembalikan item: {msg}"

        await db.execute("DELETE FROM market_listings WHERE id = ?", (listing_id,))
        await db.commit()
        return True, f"✅ Listing removed. Items returned to your storage."


# ─── LAND CLEARING ───────────────────────────────────────────────────────────

async def get_obstacles(user_id: int) -> list[dict]:
    async with get_db() as db:
        rows = await fetchall(db, 
            "SELECT * FROM obstacles WHERE user_id = ? ORDER BY slot", (user_id,)
        )
        return [dict(r) for r in rows]

async def generate_obstacles_for_expansion(user_id: int, new_slots: list[int]):
    obstacle_types = list(OBSTACLES.keys())
    async with get_db() as db:
        for slot in new_slots:
            obs = _random.choice(obstacle_types)
            await db.execute(
                "INSERT OR IGNORE INTO obstacles (user_id, slot, obstacle) VALUES (?, ?, ?)",
                (user_id, slot, obs)
            )
        await db.commit()

async def clear_obstacle(user_id: int, slot: int) -> tuple[bool, str]:
    async with get_db() as db:
        obs_row = await fetchone(db, "SELECT * FROM obstacles WHERE user_id=? AND slot=?", (user_id, slot))
        if not obs_row:
            return False, "Tidak ada rintangan di sini."
        obs_row = dict(obs_row)
        obs = OBSTACLES[obs_row["obstacle"]]

        tool = obs["tool"]
        have = await get_item_count(user_id, tool)
        if have < 1:
            tool_emoji = get_item_emoji(tool)
            return False, f"❌ Kamu butuh {tool_emoji} {get_item_name(tool)} untuk membersihkan {obs['emoji']} {obs['name']}."

        await remove_from_inventory(user_id, tool, 1)
        await db.execute("DELETE FROM obstacles WHERE user_id=? AND slot=?", (user_id, slot))

        # Now create a new empty plot at this slot
        await db.execute("INSERT OR IGNORE INTO plots (user_id, slot, status) VALUES (?, ?, 'empty')", (user_id, slot))
        await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (obs["coins"], user_id))
        await db.commit()

    new_level, leveled_up, _ = await add_xp_and_check_level(user_id, obs["xp"])
    level_msg = f"\n🎉 Naik Level! Kamu sekarang Level {new_level}!" if leveled_up else ""
    return True, f"✅ Dibersihkan {obs['emoji']} {obs['name']}! +Rp{obs['coins']:,} +{obs['xp']} XP{level_msg}"


# ─── UPGRADES ────────────────────────────────────────────────────────────────

async def upgrade_silo(user_id: int) -> tuple[bool, str]:
    async with get_db() as db:
        user = dict(await fetchone(db, "SELECT * FROM users WHERE user_id = ?", (user_id,)))
        barn = parse_json_field(user["barn_items"])
        cost = SILO_UPGRADE["cost_per_upgrade"]
        tools = SILO_UPGRADE["tools_needed"]

        if user["coins"] < cost:
            return False, f"💵 Butuh Rp{cost:,} (punya Rp{user['coins']:,})."

        missing = []
        for tool, qty in tools.items():
            have = barn.get(tool, 0)
            if have < qty:
                emoji = get_item_emoji(tool)
                missing.append(f"{qty}x {emoji} {get_item_name(tool)} (punya {have})")
        if missing:
            return False, "❌ Missing: " + ", ".join(missing)

        for tool, qty in tools.items():
            barn[tool] = barn.get(tool, 0) - qty
            if barn[tool] <= 0:
                del barn[tool]

        new_cap = user["silo_cap"] + SILO_UPGRADE["upgrade_amount"]
        new_lv = user["silo_level"] + 1
        await db.execute("UPDATE users SET silo_cap=?, silo_level=?, barn_items=?, coins=coins-? WHERE user_id=?",
                         (new_cap, new_lv, dump_json_field(barn), cost, user_id))
        await db.commit()
        return True, f"✅ Gudang diupgrade ke Level {new_lv}! Kapasitas: {new_cap} 📦"

async def upgrade_barn(user_id: int) -> tuple[bool, str]:
    async with get_db() as db:
        user = dict(await fetchone(db, "SELECT * FROM users WHERE user_id = ?", (user_id,)))
        barn = parse_json_field(user["barn_items"])
        cost = BARN_UPGRADE["cost_per_upgrade"]
        tools = BARN_UPGRADE["tools_needed"]

        if user["coins"] < cost:
            return False, f"💵 Butuh Rp{cost:,} (punya Rp{user['coins']:,})."

        missing = []
        for tool, qty in tools.items():
            have = barn.get(tool, 0)
            if have < qty:
                emoji = get_item_emoji(tool)
                missing.append(f"{qty}x {emoji} {get_item_name(tool)} (punya {have})")
        if missing:
            return False, "❌ Missing: " + ", ".join(missing)

        for tool, qty in tools.items():
            barn[tool] = barn.get(tool, 0) - qty
            if barn[tool] <= 0:
                del barn[tool]

        new_cap = user["barn_cap"] + BARN_UPGRADE["upgrade_amount"]
        new_lv = user["barn_level"] + 1
        await db.execute("UPDATE users SET barn_cap=?, barn_level=?, barn_items=?, coins=coins-? WHERE user_id=?",
                         (new_cap, new_lv, dump_json_field(barn), cost, user_id))
        await db.commit()
        return True, f"✅ Lumbung diupgrade ke Level {new_lv}! Kapasitas: {new_cap} 📦"

async def expand_farm(user_id: int) -> tuple[bool, str]:
    async with get_db() as db:
        user = dict(await fetchone(db, "SELECT * FROM users WHERE user_id = ?", (user_id,)))
        barn = parse_json_field(user["barn_items"])

        # Check expansion tools
        required = {"land_deed": 1, "mallet": 1, "marker_stake": 1}
        missing = []
        for tool, qty in required.items():
            have = barn.get(tool, 0)
            if have < qty:
                emoji = get_item_emoji(tool)
                missing.append(f"{emoji} {get_item_name(tool)}")
        if missing:
            return False, f"❌ Lahan tidak dapat diperluas karena bahan tidak ada!\n\n🛒 Beli bahan berikut di **Toko Alat**:\n{', '.join(missing)}\n\nKetuk 🛒 **Toko Alat** di menu utama untuk beli."

        cost = user["plots"] * 200
        if user["coins"] < cost:
            return False, f"💵 Perluasan butuh Rp{cost:,} (punya Rp{user['coins']:,})."

        for tool, qty in required.items():
            barn[tool] = barn.get(tool, 0) - qty
            if barn[tool] <= 0:
                del barn[tool]

        current_plots = user["plots"]
        new_plots = current_plots + PLOTS_PER_EXPANSION
        new_slots = list(range(current_plots, new_plots))

        await db.execute("UPDATE users SET plots=?, barn_items=?, coins=coins-? WHERE user_id=?",
                         (new_plots, dump_json_field(barn), cost, user_id))
        await db.commit()

    await generate_obstacles_for_expansion(user_id, new_slots)
    return True, f"✅ Kebun diperluas! +{PLOTS_PER_EXPANSION} lahan (sekarang {new_plots} total).\n\n⚠️ Lahan baru ada rintangannya!\nBuka 🗺️ **Lahan** di menu utama untuk bersihkan.\nButuh alat? Beli di 🛒 **Toko Alat**."

async def expand_animal_pens(user_id: int) -> tuple[bool, str]:
    async with get_db() as db:
        user = dict(await fetchone(db, "SELECT * FROM users WHERE user_id = ?", (user_id,)))
        barn = parse_json_field(user["barn_items"])

        required = {"land_deed": 1, "construction_permit": 1}
        missing = []
        for tool, qty in required.items():
            have = barn.get(tool, 0)
            if have < qty:
                emoji = get_item_emoji(tool)
                missing.append(f"{emoji} {get_item_name(tool)}")
        if missing:
            return False, f"❌ Kandang tidak dapat diperluas karena bahan tidak ada!\n\n🛒 Beli bahan berikut di **Toko Alat**:\n{', '.join(missing)}\n\nKetuk 🛒 **Toko Alat** di menu utama untuk beli."

        cost = user["animal_pens"] * 500
        if user["coins"] < cost:
            return False, f"💵 Butuh Rp{cost:,} (punya Rp{user['coins']:,})."

        for tool, qty in required.items():
            barn[tool] = barn.get(tool, 0) - qty
            if barn[tool] <= 0:
                del barn[tool]

        current_pens = user["animal_pens"]
        new_pens = current_pens + 2

        for slot in range(current_pens, new_pens):
            await db.execute("INSERT OR IGNORE INTO animal_pens (user_id, slot, status) VALUES (?, ?, 'empty')", (user_id, slot))

        await db.execute("UPDATE users SET animal_pens=?, barn_items=?, coins=coins-? WHERE user_id=?",
                         (new_pens, dump_json_field(barn), cost, user_id))
        await db.commit()
        return True, f"✅ +2 kandang hewan! (sekarang {new_pens} total)"


# ─── SELL / DAILY ─────────────────────────────────────────────────────────────

async def sell_item(user_id: int, item_key: str, qty: int) -> tuple[bool, str]:
    price = 0
    if item_key in CROPS:
        price = CROPS[item_key]["sell_price"]
    else:
        # Cek produk hewan default (egg, milk, bacon, wool, dll)
        for a_key, a_val in ANIMALS.items():
            if a_val.get("product") == item_key:
                price = a_val.get("sell_price", 0)
                break
        # Cek produk hewan custom (CUSTOM_ANIMAL_PRODUCTS dari /addanimal)
        if price == 0:
            from game.data import CUSTOM_ANIMAL_PRODUCTS
            if item_key in CUSTOM_ANIMAL_PRODUCTS:
                price = CUSTOM_ANIMAL_PRODUCTS[item_key].get("sell_price", 0)
        # Cek produk olahan pabrik
        if price == 0:
            for bld in BUILDINGS.values():
                if item_key in bld["recipes"]:
                    price = bld["recipes"][item_key]["sell_price"]
                    break

    if price == 0:
        return False, "❌ Item ini tidak bisa dijual langsung."

    ok, msg = await remove_from_inventory(user_id, item_key, qty)
    if not ok:
        return False, msg

    total = price * qty
    double = await get_setting("double_coins", "0")
    if double == "1":
        total *= 2

    async with get_db() as db:
        await db.execute("UPDATE users SET coins = coins + ?, total_sales = total_sales + 1 WHERE user_id = ?", (total, user_id))
        await db.commit()

    emoji = get_item_emoji(item_key)
    return True, f"✅ Terjual {qty}x {emoji} {get_item_name(item_key)} seharga Rp{total:,}!"

async def claim_daily(user_id: int) -> tuple[bool, str]:
    """Daily reset di jam 07:00 WIB (UTC+7).
    'Hari' di sini = periode 07:00 WIB hari A sampai 06:59 WIB hari A+1.
    Caranya: pake waktu sekarang dalam WIB, kurangin 7 jam, ambil tanggalnya.
    Dengan begitu, jam 06:59 WIB tanggal 10 = "tanggal 9", jam 07:00 WIB = "tanggal 10".
    """
    from datetime import datetime, timedelta, timezone
    wib = timezone(timedelta(hours=7))
    now_wib = datetime.now(wib)
    # Geser 7 jam mundur biar pergantian "hari" jadi jam 07:00 WIB
    daily_day = (now_wib - timedelta(hours=7)).date().isoformat()

    async with get_db() as db:
        user = dict(await fetchone(db, "SELECT * FROM users WHERE user_id = ?", (user_id,)))
        if user["last_daily"] == daily_day:
            # Hitung kapan reset berikutnya buat info
            next_reset = (now_wib.replace(hour=7, minute=0, second=0, microsecond=0))
            if now_wib >= next_reset:
                next_reset = next_reset + timedelta(days=1)
            jam_lagi = int((next_reset - now_wib).total_seconds() // 3600)
            menit_lagi = int(((next_reset - now_wib).total_seconds() % 3600) // 60)
            return False, (
                f"⏰ Hadiah hari ini SUDAH DIAMBIL!\n\n"
                f"Reset berikutnya: jam 07:00 WIB\n"
                f"({jam_lagi} jam {menit_lagi} menit lagi)"
            )

        coins = 10000 + (user["level"] * 1000)
        xp = 20 + (user["level"] * 2)
        await db.execute(
            "UPDATE users SET coins = coins + ?, last_daily = ? WHERE user_id = ?",
            (coins, daily_day, user_id)
        )
        await db.commit()

    new_level, leveled_up, _ = await add_xp_and_check_level(user_id, xp)
    level_msg = f"\n🎉 Naik Level! Kamu sekarang Level {new_level}!" if leveled_up else ""
    return True, f"🎁 Hadiah harian diambil!\n+Rp{coins:,}  +{xp} XP{level_msg}"


# ─── TOKO ALAT ───────────────────────────────────────────────────────────────

async def buy_tool(user_id: int, tool_key: str, qty: int = 1) -> tuple[bool, str]:
    from game.data import TOOL_SHOP
    if tool_key not in TOOL_SHOP:
        return False, "❓ Alat tidak ditemukan di toko."
    tool = TOOL_SHOP[tool_key]
    total_price = tool["price"] * qty

    async with get_db() as db:
        user = dict(await fetchone(db, "SELECT coins FROM users WHERE user_id = ?", (user_id,)))
        if user["coins"] < total_price:
            return False, f"💵 Kurang uang! Butuh Rp{total_price:,} (punya Rp{user['coins']:,})."

        await db.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (total_price, user_id))
        await db.commit()

    ok, msg = await add_to_inventory(user_id, tool_key, qty)
    if not ok:
        # Refund
        async with get_db() as db:
            await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (total_price, user_id))
            await db.commit()
        return False, msg

    emoji = get_item_emoji(tool_key)
    return True, f"✅ Dibeli {qty}x {emoji} {tool['name']} seharga Rp{total_price:,}!"


# ─── HELPERS ─────────────────────────────────────────────────────────────────

async def get_user_full(user_id: int) -> dict | None:
    async with get_db() as db:
        row = await fetchone(db, "SELECT * FROM users WHERE user_id = ?", (user_id,))
        if row:
            return dict(row)
        return None
