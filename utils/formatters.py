# utils/formatters.py - Message text formatters for Harvest Kingdom (Bahasa Indonesia)

from datetime import datetime, timezone
from game.data import (
    CROPS, ANIMALS, BUILDINGS, UPGRADE_TOOLS, EXPANSION_TOOLS, CLEARING_TOOLS,
    OBSTACLES, get_item_emoji, get_item_name, get_xp_for_next_level, PROCESSED_EMOJI
)
from database.db import parse_json_field, get_display_name
from game.engine import fmt_time


def fmt_farm(user: dict, plots: list[dict]) -> str:
    now = datetime.now(timezone.utc)
    level = user["level"]
    coins = user["coins"]
    xp = user["xp"]
    next_xp = get_xp_for_next_level(level)
    xp_bar = make_xp_bar(xp, next_xp, level)
    name = get_display_name(user)

    lines = [
        f"🏡 **Kebun {name}**",
        f"👑 Level {level}  💵 Rp{coins:,}  💎 {user['gems']} permata",
        f"📈 XP: {xp:,} / {next_xp:,}  {xp_bar}",
        "",
        f"🌾 **Lahan Pertanian** ({user['plots']} lahan):",
    ]

    for plot in plots:
        slot = plot["slot"]
        if plot["status"] == "empty":
            lines.append(f"  [{slot+1}] 🟩 Kosong — ketuk untuk menanam")
        elif plot["status"] == "infected":
            crop = CROPS.get(plot["crop"], {})
            lines.append(f"  [{slot+1}] 🐛 {crop.get('emoji','🌱')} {crop.get('name', plot['crop'])} — **KENA HAMA!** Semprot pestisida!")
        elif plot["status"] == "growing":
            crop = CROPS.get(plot["crop"], {})
            ready_at = datetime.fromisoformat(plot["ready_at"])
            if ready_at.tzinfo is None:
                ready_at = ready_at.replace(tzinfo=timezone.utc)
            if now >= ready_at:
                lines.append(f"  [{slot+1}] ✅ {crop.get('emoji','🌱')} {crop.get('name', plot['crop'])} — **SIAP PANEN!**")
            else:
                remaining = int((ready_at - now).total_seconds())
                lines.append(f"  [{slot+1}] 🌱 {crop.get('emoji','🌱')} {crop.get('name', plot['crop'])} — ⏳ {fmt_time(remaining)}")
        else:
            lines.append(f"  [{slot+1}] ❓ {plot['status']}")

    silo = parse_json_field(user["silo_items"])
    lines.append(f"\n📦 Gudang: {sum(silo.values())}/{user['silo_cap']}  🏚 Lumbung: {sum(parse_json_field(user['barn_items']).values())}/{user['barn_cap']}")
    return "\n".join(lines)


def fmt_animals(user: dict, pens: list[dict]) -> str:
    now = datetime.now(timezone.utc)
    lines = [f"🐾 **Kandang Hewan** ({user['animal_pens']} kandang):", ""]

    for pen in pens:
        slot = pen["slot"]
        if pen["status"] == "empty":
            lines.append(f"  [{slot+1}] 🟩 Kandang kosong — ketuk untuk beli hewan")
        elif pen["status"] == "producing":
            animal = ANIMALS.get(pen["animal"], {})
            ready_at = datetime.fromisoformat(pen["ready_at"])
            if ready_at.tzinfo is None:
                ready_at = ready_at.replace(tzinfo=timezone.utc)
            if now >= ready_at:
                lines.append(f"  [{slot+1}] ✅ {animal.get('emoji','🐾')} {animal.get('name', pen['animal'])} → {animal.get('prod_emoji','📦')} **SIAP AMBIL!**")
            else:
                remaining = int((ready_at - now).total_seconds())
                lines.append(f"  [{slot+1}] {animal.get('emoji','🐾')} {animal.get('name', pen['animal'])} → ⏳ {fmt_time(remaining)}")
        else:
            lines.append(f"  [{slot+1}] ❓ {pen['status']}")
    return "\n".join(lines)


def fmt_storage(user: dict, storage_type: str = "silo") -> str:
    if storage_type == "silo":
        items = parse_json_field(user["silo_items"])
        cap = user["silo_cap"]
        used = sum(items.values())
        level = user["silo_level"]
        title = f"🌾 **Gudang** (Level {level}) — {used}/{cap}"
    else:
        items = parse_json_field(user["barn_items"])
        cap = user["barn_cap"]
        used = sum(items.values())
        level = user["barn_level"]
        title = f"🏚 **Lumbung** (Level {level}) — {used}/{cap}"

    bar = make_capacity_bar(used, cap)
    lines = [title, bar, ""]

    if not items:
        lines.append("  (kosong)")
    else:
        for item_key, qty in sorted(items.items(), key=lambda x: -x[1]):
            emoji = get_item_emoji(item_key)
            name = get_item_name(item_key)
            lines.append(f"  {emoji} {name}: **{qty}**")
    return "\n".join(lines)


def fmt_factories(user: dict, buildings: list[dict]) -> str:
    now = datetime.now(timezone.utc)
    owned_keys = {b["building"] for b in buildings}

    if not owned_keys:
        lines = [
            "🏭 **Pabrik**",
            "",
            "Kamu belum punya pabrik!",
            "Beli pabrik pertamamu dari menu di bawah.",
        ]
    else:
        lines = ["🏭 **Pabrik**", ""]
        for bld_key in owned_keys:
            bld = BUILDINGS[bld_key]
            bld_slots = [b for b in buildings if b["building"] == bld_key]
            lines.append(f"{bld['emoji']} **{bld['name']}**")
            for s in bld_slots:
                slot_num = s["slot"] + 1
                if s["status"] == "idle":
                    lines.append(f"  Slot {slot_num}: 💤 Menganggur")
                elif s["status"] == "producing":
                    ready_at = datetime.fromisoformat(s["ready_at"])
                    if ready_at.tzinfo is None:
                        ready_at = ready_at.replace(tzinfo=timezone.utc)
                    if now >= ready_at:
                        emoji = PROCESSED_EMOJI.get(s["item"], "📦")
                        lines.append(f"  Slot {slot_num}: ✅ {emoji} {get_item_name(s['item'])} SIAP!")
                    else:
                        remaining = int((ready_at - now).total_seconds())
                        emoji = PROCESSED_EMOJI.get(s["item"], "📦")
                        lines.append(f"  Slot {slot_num}: ⏳ {emoji} {get_item_name(s['item'])} — {fmt_time(remaining)}")
    return "\n".join(lines)


def fmt_orders(orders: list[dict]) -> str:
    import json
    lines = [
        "🚚 **Pesanan Pengiriman**",
        "",
        "Punya item yang diminta? Ketuk pesanan buat kirim!",
        "Dapet 💵 Rp + ⭐ XP setiap selesai.",
        "",
    ]
    if not orders:
        lines.append("Tidak ada pesanan aktif. Cek lagi nanti!")
        return "\n".join(lines)

    for i, order in enumerate(orders, 1):
        items = json.loads(order["items"])
        item_parts = []
        for item_key, qty in items.items():
            emoji = get_item_emoji(item_key)
            name = get_item_name(item_key)
            item_parts.append(f"{qty}x {emoji} {name}")
        lines.append(f"📦 **#{i}** — {' + '.join(item_parts)}")
        lines.append(f"     💵 Rp{order['reward_coins']:,} | ⭐ {order['reward_xp']} XP")
        lines.append("")

    lines.append("_Ketuk pesanan di bawah untuk kirim._")
    return "\n".join(lines)


def fmt_market(listings: list[dict], page: int, total: int) -> str:
    lines = [
        "🏪 **Pasar Global**",
        f"📰 {total} item dijual | Halaman {page+1}",
        "",
    ]
    if not listings:
        lines.append("Belum ada barang dijual. Jadilah yang pertama berjualan!")
    for listing in listings:
        emoji = get_item_emoji(listing["item"])
        name = get_item_name(listing["item"])
        total_price = listing["price"] * listing["qty"]
        lines.append(f"{emoji} **{name}** x{listing['qty']}")
        lines.append(f"  💵 Rp{listing['price']:,}/satuan (Total: Rp{total_price:,}) | 👤 {listing['seller_name']}")
        lines.append("")
    lines.append("Ketuk item untuk membelinya.")
    return "\n".join(lines)


def fmt_profile(user: dict) -> str:
    name = get_display_name(user)
    level = user["level"]
    xp = user["xp"]
    next_xp = get_xp_for_next_level(level)
    xp_bar = make_xp_bar(xp, next_xp, level)

    # Rank medal
    rank_medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    rank = user.get("rank")
    rank_text = f"  {rank_medals.get(rank, '')} Peringkat #{rank}" if rank else ""

    silo = parse_json_field(user["silo_items"])
    barn = parse_json_field(user["barn_items"])
    silo_used = sum(silo.values())
    barn_used = sum(barn.values())

    lines = [
        f"━━━━━━━━━━━━━━━━━━━━",
        f"📊 **Profil — {name}**",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"🪪 ID: `{user['user_id']}`{rank_text}",
        "",
        f"👑 **Level {level}**",
        f"📈 XP: {xp:,} / {next_xp:,}",
        f"   {xp_bar}",
        "",
        f"💵 **Uang:** Rp{user['coins']:,}",
        f"💎 **Permata:** {user['gems']}",
        "",
        f"🌾 **Total Panen:** {user['total_harvests']:,}",
        f"🚚 **Total Penjualan:** {user['total_sales']:,}",
        "",
        f"🌱 **Kebun:** {user['plots']} lahan",
        f"🐾 **Kandang:** {user['animal_pens']} kandang",
        f"📦 **Gudang:** Lv{user['silo_level']} ({silo_used}/{user['silo_cap']})",
        f"🏚 **Lumbung:** Lv{user['barn_level']} ({barn_used}/{user['barn_cap']})",
        "",
        f"📅 **Bergabung:** {user['created_at'][:10]}",
        f"━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def fmt_leaderboard(users: list[dict], requester_id: int = None) -> str:
    medals = {0: "🥇", 1: "🥈", 2: "🥉"}

    lines = [
        "━━━━━━━━━━━━━━━━━━━━",
        "🏆 **LEADERBOARD — Harvest Kingdom**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not users:
        lines.append("Belum ada pemain.")
        return "\n".join(lines)

    for i, u in enumerate(users):
        medal = medals.get(i, f"#{i+1}")
        name = get_display_name(u)
        is_you = " ← 🫵 KAMU" if requester_id and u["user_id"] == requester_id else ""

        lines.append(
            f"{medal} **{name}**{is_you}\n"
            f"    👑 Lv{u['level']}  📈 {u['xp']:,} XP  💵 Rp{u['coins']:,}"
        )
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("Naikkan level & XP untuk jadi #1!")
    return "\n".join(lines)


def fmt_help() -> str:
    return """
❓ **HARVEST KINGDOM — BANTUAN & TUTORIAL**

👋 Selamat datang, Petani! Ini cara bermainnya:

━━━━━━━━━━━━━━━━━━━━
🌾 **BERTANI (Kebun Saya)**
━━━━━━━━━━━━━━━━━━━━
1. Ketuk **🏠 Kebun Saya** untuk lihat lahanmu
2. Ketuk lahan kosong 🟩 untuk pilih tanaman
3. Tanaman butuh Rp untuk benih dan tumbuh seiring waktu
4. Saat tanaman ✅ SIAP, ketuk untuk panen
5. Hasil panen masuk ke **Gudang**
6. Gunakan **🌾 Panen Semua** untuk panen sekaligus!
7. 🎁 Ada 5% kesempatan dapat alat bonus saat panen!

━━━━━━━━━━━━━━━━━━━━
🐾 **HEWAN TERNAK**
━━━━━━━━━━━━━━━━━━━━
1. Ketuk **🐾 Hewan** untuk lihat kandangmu
2. Ketuk kandang kosong 🟩 untuk beli hewan
3. Hewan otomatis menghasilkan produk seiring waktu
4. Ketuk kandang ✅ untuk ambil produknya (Telur, Susu, dll.)
5. Produk masuk ke **Gudang**
6. Perluas kandang untuk tampung lebih banyak hewan!

━━━━━━━━━━━━━━━━━━━━
🏭 **PABRIK**
━━━━━━━━━━━━━━━━━━━━
1. Ketuk **🏭 Pabrik** untuk lihat/beli bangunan
2. Gunakan hasil panen + produk hewan untuk buat **Barang Olahan**
3. Barang olahan dijual dengan harga jauh lebih tinggi!
4. Barang masuk ke **Lumbung**
5. Setiap pabrik punya beberapa slot produksi

Contoh rantai produksi:
🌾 Gandum → 🏭 Bakeri → 🍞 Roti

━━━━━━━━━━━━━━━━━━━━
📦 **PENYIMPANAN**
━━━━━━━━━━━━━━━━━━━━
🌾 **Gudang**: Menyimpan hasil panen & produk hewan
🏚 **Lumbung**: Menyimpan barang olahan & alat
- Upgrade untuk tambah kapasitas
- Upgrade butuh alat khusus (didapat dari bonus panen!)

━━━━━━━━━━━━━━━━━━━━
🚚 **PESANAN TRUK**
━━━━━━━━━━━━━━━━━━━━
- Selalu ada 9 pesanan pengiriman aktif
- Setiap pesanan butuh item tertentu dari penyimpananmu
- Menyelesaikan pesanan dapat **Rp + XP**
- Pesanan otomatis diperbarui setelah selesai

━━━━━━━━━━━━━━━━━━━━
🏪 **PASAR GLOBAL**
━━━━━━━━━━━━━━━━━━━━
- Beli item dari pemain lain
- Jual itemmu: Penyimpanan → ketuk item → Pasang di Pasar
- Tentukan hargamu dan tunggu pembeli!
- Maksimal 5 listing sekaligus

━━━━━━━━━━━━━━━━━━━━
🗺️ **PERLUASAN LAHAN**
━━━━━━━━━━━━━━━━━━━━
- Lahan baru ada rintangannya (Pohon, Batu, Rawa)
- Gunakan alat pembersih (Kapak, Dinamit, Sekop) untuk membersihkan
- Alat pembersih didapat sebagai **item bonus** saat panen
- Setelah dibersihkan, lahan jadi lahan pertanian baru!
- Perluas kebun dengan **Surat Tanah + Palu + Patok**

━━━━━━━━━━━━━━━━━━━━
💵 **TIPS BERMAIN**
━━━━━━━━━━━━━━━━━━━━
✅ Ambil 🎁 **Hadiah Harian** setiap hari!
✅ Olah hasil panen jadi barang — harga jual lebih tinggi!
✅ Selesaikan pesanan truk untuk bonus Rp & XP
✅ Level lebih tinggi = tanaman & hewan langka terbuka
✅ Cek pasar untuk item murah!
✅ Simpan alat untuk upgrade penyimpanan!

━━━━━━━━━━━━━━━━━━━━
📋 **PERINTAH**
━━━━━━━━━━━━━━━━━━━━
/start — Menu utama
/farm — Ke kebun
/storage — Cek penyimpanan
/market — Pasar global
/orders — Pesanan pengiriman
/daily — Ambil hadiah harian
/profile — Lihat statistikmu
/leaderboard — Papan peringkat
/setname — Ganti nama tampilan
/help — Halaman bantuan ini

Selamat bercocok tanam! 🌾👑
"""


def make_xp_bar(xp: int, next_xp: int, level: int) -> str:
    if next_xp <= 0:
        return "[LEVEL MAKS]"
    filled = int((xp / next_xp) * 10)
    filled = min(10, max(0, filled))
    return "[" + "█" * filled + "░" * (10 - filled) + "]"


def make_capacity_bar(used: int, cap: int) -> str:
    if cap <= 0:
        return "[███████████] PENUH"
    pct = min(1.0, used / cap)
    filled = int(pct * 10)
    bar = "[" + "█" * filled + "░" * (10 - filled) + f"] {used}/{cap}"
    return bar

def fmt_tutorial() -> str:
    return """
📖 **CARA MAIN — Harvest Kingdom**

Hai! Bingung cara mainnya? Tenang, gampang banget kok 😄

━━━━━━━━━━━━━━━━━━━━

🌾 **1. TANAM & PANEN**
Ini hal pertama yang harus kamu lakuin!

➡️ Buka **🏠 Kebun Saya**
➡️ Ketuk kotak hijau 🟩
➡️ Pilih tanaman (mulai dari Wheat aja)
➡️ Tunggu sampe muncul ✅
➡️ Ketuk lagi buat panen! Atau tekan **Panen Semua**

🌾 Wheat cuma 2 menit, cocok buat pemula!

━━━━━━━━━━━━━━━━━━━━

⬆️ **2. NAIKIN LEVEL**
Level naik = fitur baru kebuka!

Cara naikin:
➡️ Panen tanaman = dapet XP
➡️ Selesaiin pesanan = dapet XP + Rp
➡️ Ambil **🎁 Hadiah Harian** tiap hari

Lv2 → 🐔 Ayam & 🥕 Wortel
Lv3 → 🏭 Pabrik pertama
Lv5 → 🐄 Sapi
Lv7 → 🐷 Babi

━━━━━━━━━━━━━━━━━━━━

🐾 **3. TERNAK HEWAN**
Udah Level 2? Langsung beli hewan!

➡️ Buka **🐾 Hewan**
➡️ Ketuk kandang kosong 🟩
➡️ Pilih hewan → bayar → tunggu ✅
➡️ Ambil produknya (telur, susu, dll)
➡️ Tekan **🧺 Ambil Semua** biar cepet

Hewan otomatis produksi terus! 🔄

━━━━━━━━━━━━━━━━━━━━

🏭 **4. PABRIK**
Bikin barang olahan = harga jual JAUH lebih mahal!

Contoh:
🌾 Wheat → 🏭 → 🍞 Roti (5x lipat!)
🥛 Susu → 🏭 → 🧈 Mentega (3x lipat!)

➡️ Buka **🏭 Pabrik** → beli → pilih resep → tunggu → ambil

━━━━━━━━━━━━━━━━━━━━

🚚 **5. PESANAN**
Ini cara paling cepet dapet duit! 🤑

➡️ Buka **🚚 Pesanan**
➡️ Liat minta item apa
➡️ Kalau punya, ketuk pesanan → selesai!
➡️ Dapet **Rp + XP** gede

Pesanan susah? Tekan **🔄 Refresh** (1x/24jam)

━━━━━━━━━━━━━━━━━━━━

📦 **6. PENYIMPANAN & UPGRADE**
Gudang penuh? Upgrade dong!

➡️ Buka **📦 Penyimpanan**
➡️ Tekan **⬆️ Upgrade**
➡️ Butuh alat? Beli di **🛒 Toko Alat**

━━━━━━━━━━━━━━━━━━━━

🗺️ **7. PERLUAS LAHAN**
Mau lebih banyak lahan tanam?

➡️ Buka **🗺️ Lahan** → tekan **Perluas**
➡️ Lahan baru ada rintangan — bersihin dulu!
➡️ Butuh alat pembersih (beli di 🛒 Toko Alat)

━━━━━━━━━━━━━━━━━━━━

💡 **TIPS CEPET KAYA:**
✅ Ambil 🎁 Hadiah Harian tiap hari
✅ Spam tanam Wheat di awal
✅ Selesaiin pesanan = income terbesar
✅ Olah barang di pabrik sebelum jual
✅ Upgrade gudang biar muat banyak
✅ Cek 📚 Katalog Item buat liat semua info

Udah itu aja! Simpel kan? 🎮
Sekarang balik ke menu dan mulai farming! 🌾
"""


def fmt_items_crops() -> str:
    from game.engine import fmt_time
    lines = [
        "━━━━━━━━━━━━━━━━━━━━",
        "🌾 **DAFTAR TANAMAN**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "Tanam di lahan, tunggu tumbuh, lalu panen!",
        "Hasil panen masuk ke Gudang & bisa dijual.",
        "",
    ]
    for k, v in CROPS.items():
        profit = v["sell_price"] - v["seed_cost"]
        lines.append(
            f"{v['emoji']} **{v['name']}** (`{k}`)\n"
            f"   💵 Benih: Rp{v['seed_cost']:,} → Jual: Rp{v['sell_price']:,} (untung Rp{profit:,})\n"
            f"   ⏱ Waktu: {fmt_time(v['grow_time'])} | ⭐ +{v['xp']} XP | 🔒 Level {v['level_req']}\n"
        )
    return "\n".join(lines)


def fmt_items_animals() -> str:
    from game.engine import fmt_time
    lines = [
        "━━━━━━━━━━━━━━━━━━━━",
        "🐾 **DAFTAR HEWAN**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "Beli hewan, taruh di kandang.",
        "Otomatis produksi terus tanpa ditanam ulang!",
        "",
    ]
    for k, v in ANIMALS.items():
        lines.append(
            f"{v['emoji']} **{v['name']}** → {v['prod_emoji']} {v['product'].replace('_',' ').title()}\n"
            f"   💵 Beli: Rp{v['buy_cost']:,} | Jual produk: Rp{v['sell_price']:,}\n"
            f"   ⏱ Produksi: {fmt_time(v['feed_time'])} | 🔒 Level {v['level_req']}\n"
        )
    return "\n".join(lines)


def fmt_items_factories() -> str:
    from game.engine import fmt_time
    lines = [
        "━━━━━━━━━━━━━━━━━━━━",
        "🏭 **DAFTAR PABRIK & RESEP**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "Beli pabrik, olah bahan mentah jadi barang mahal!",
        "",
    ]
    for bk, bv in BUILDINGS.items():
        lines.append(f"{bv['emoji']} **{bv['name']}** — Rp{bv['buy_cost']:,} | 🔒 Level {bv['level_req']} | {bv['slots']} slot\n")
        for rk, rv in bv["recipes"].items():
            inputs = " + ".join(f"{q}x {get_item_name(i)}" for i, q in rv["inputs"].items())
            out_emoji = PROCESSED_EMOJI.get(rk, "📦")
            lines.append(
                f"  {out_emoji} **{get_item_name(rk)}**\n"
                f"     Bahan: {inputs}\n"
                f"     ⏱ {fmt_time(rv['time'])} | 💵 Jual: Rp{rv['sell_price']:,} | ⭐ +{rv['xp']} XP\n"
            )
    return "\n".join(lines)


def fmt_items_tools() -> str:
    lines = [
        "━━━━━━━━━━━━━━━━━━━━",
        "🔧 **DAFTAR ALAT & FUNGSI**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "Alat didapat dari: bonus panen (5%) atau beli di 🛒 Toko Alat",
        "",
        "**📌 Alat Upgrade Gudang:**",
        "Butuh 3x📌Nail + 2x🔧Screw + 1x🪟Wood Panel + Rp800",
        "",
        "**🔩 Alat Upgrade Lumbung:**",
        "Butuh 3x🔩Bolt + 2x🪵Plank + 1x🩹Duct Tape + Rp1,000",
        "",
        "**📜 Alat Perluasan Lahan:**",
        "Butuh 📜Land Deed + 🪛Mallet + 📍Marker Stake",
        "",
        "**🐾 Alat Perluasan Kandang:**",
        "Butuh 📜Land Deed + 📋Construction Permit",
        "",
        "**🪓 Alat Pembersih Rintangan:**",
        "🌱 Small Tree → butuh 🪓 Axe (bonus Rp50)",
        "🌳 Big Tree → butuh 🔪 Saw (bonus Rp120)",
        "🪨 Rock → butuh 🧨 Dynamite (bonus Rp100)",
        "⛰️ Big Rock → butuh 💣 TNT Barrel (bonus Rp250)",
        "🌿 Swamp → butuh 🪚 Shovel (bonus Rp80)",
        "🪵 Dead Bush → butuh ⚒️ Rusty Hoe (bonus Rp40)",
    ]
    return "\n".join(lines)

def fmt_all_items(category: str = "all") -> str:
    """Generate item encyclopedia. Reads from game data dynamically."""
    from game.data import CROPS, ANIMALS, BUILDINGS, TOOL_SHOP, PROCESSED_EMOJI
    from game.engine import fmt_time

    sections = []

    if category in ("all", "crops"):
        lines = ["🌾 **TANAMAN**", "━━━━━━━━━━━━━━━━━━━━", ""]
        for key, c in CROPS.items():
            lines.append(
                f"{c['emoji']} **{c['name']}** (`{key}`)\n"
                f"   🌱 Waktu tumbuh: {fmt_time(c['grow_time'])}\n"
                f"   💵 Benih: Rp{c['seed_cost']:,} | Jual: Rp{c['sell_price']:,}\n"
                f"   ⭐ XP: {c['xp']} | 🔓 Level {c['level_req']}\n"
            )
        sections.append("\n".join(lines))

    if category in ("all", "animals"):
        lines = ["🐾 **HEWAN TERNAK**", "━━━━━━━━━━━━━━━━━━━━", ""]
        for key, a in ANIMALS.items():
            lines.append(
                f"{a['emoji']} **{a['name']}** (`{key}`)\n"
                f"   {a['prod_emoji']} Produk: {a['product'].replace('_',' ').title()}\n"
                f"   ⏳ Waktu produksi: {fmt_time(a['feed_time'])}\n"
                f"   💵 Beli: Rp{a['buy_cost']:,} | Jual produk: Rp{a['sell_price']:,}\n"
                f"   🔓 Level {a['level_req']}\n"
            )
        sections.append("\n".join(lines))

    if category in ("all", "products"):
        lines = ["🏭 **BARANG OLAHAN**", "━━━━━━━━━━━━━━━━━━━━", ""]
        for bld_key, bld in BUILDINGS.items():
            lines.append(f"\n{bld['emoji']} **{bld['name']}** (💵 Rp{bld['buy_cost']:,} | 🔓 Lv{bld['level_req']})")
            for rec_key, rec in bld["recipes"].items():
                emoji = PROCESSED_EMOJI.get(rec_key, "📦")
                inputs = " + ".join(f"{qty}x {ing.replace('_',' ').title()}" for ing, qty in rec["inputs"].items())
                lines.append(
                    f"  {emoji} **{rec_key.replace('_',' ').title()}**\n"
                    f"     📋 Bahan: {inputs}\n"
                    f"     ⏳ {fmt_time(rec['time'])} | 💵 Jual: Rp{rec['sell_price']:,} | ⭐ {rec['xp']} XP"
                )
            lines.append("")
        sections.append("\n".join(lines))

    if category in ("all", "tools"):
        lines = ["🛒 **ALAT (TOKO)**", "━━━━━━━━━━━━━━━━━━━━", ""]
        # Group by category
        cats = {}
        for key, t in TOOL_SHOP.items():
            cat = t["category"]
            if cat not in cats:
                cats[cat] = []
            cats[cat].append((key, t))
        for cat, tools in cats.items():
            lines.append(f"**{cat}:**")
            for key, t in tools:
                lines.append(f"  {t['emoji']} {t['name']} (`{key}`) — 💵 Rp{t['price']:,}")
            lines.append("")
        sections.append("\n".join(lines))

    if category == "all":
        header = "📚 **ENSIKLOPEDIA ITEM — Harvest Kingdom**\n━━━━━━━━━━━━━━━━━━━━\n\nSemua item yang tersedia di game:\n"
        return header + "\n\n".join(sections)
    return "\n\n".join(sections)
