# utils/keyboards.py - Keyboard builders for Harvest Kingdom

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from game.data import CROPS, ANIMALS, BUILDINGS, get_item_emoji, get_item_name, OBSTACLES


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏠 Kebun Saya", callback_data="farm"),
            InlineKeyboardButton("🐾 Hewan", callback_data="animals"),
        ],
        [
            InlineKeyboardButton("🏭 Pabrik", callback_data="factories"),
            InlineKeyboardButton("📦 Penyimpanan", callback_data="storage"),
        ],
        [
            InlineKeyboardButton("🚚 Pesanan", callback_data="orders"),
            InlineKeyboardButton("🏪 Pasar", callback_data="market"),
        ],
        [
            InlineKeyboardButton("🛒 Toko Alat", callback_data="shop"),
            InlineKeyboardButton("💎 Toko Permata", callback_data="gemshop"),
        ],
        [
            InlineKeyboardButton("🗺️ Lahan", callback_data="land"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"),
        ],
        [
            InlineKeyboardButton("📊 Profil", callback_data="profile"),
            InlineKeyboardButton("🎁 Hadiah Harian", callback_data="daily"),
        ],
        [
            InlineKeyboardButton("❓ Bantuan", callback_data="help"),
        ],
    ])

def back_to_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu")]])

def help_slide_keyboard(page: int, total: int):
    """Keyboard buat slide help. Prev/Next + jump halaman + back to menu."""
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Sebelum", callback_data=f"help_page_{page-1}"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("Lanjut ▶️", callback_data=f"help_page_{page+1}"))

    buttons = []
    if nav:
        buttons.append(nav)

    # Jump baris (halaman 1-4 dan 5-8)
    page_labels = ["📖", "🌾", "🐾", "🏭", "🚚", "🏪", "📦", "💎", "📋"]
    row1 = []
    for i in range(min(5, total)):
        marker = "•" if i == page else page_labels[i]
        row1.append(InlineKeyboardButton(f"{marker}{i+1 if i != page else ''}", callback_data=f"help_page_{i}"))
    buttons.append(row1)
    if total > 5:
        row2 = []
        for i in range(5, total):
            marker = "•" if i == page else page_labels[i] if i < len(page_labels) else "📖"
            row2.append(InlineKeyboardButton(f"{marker}{i+1 if i != page else ''}", callback_data=f"help_page_{i}"))
        buttons.append(row2)

    buttons.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)

def farm_keyboard(plots: list[dict], user_level: int):
    buttons = []
    row = []
    has_infected = False
    has_growing = False
    for i, plot in enumerate(plots):
        slot = plot["slot"]
        if plot["status"] == "empty":
            label = f"🟩 {slot+1}"
            cb = f"plot_plant_{slot}"
        elif plot["status"] == "infected":
            label = f"🐛 {slot+1}"
            cb = f"plot_spray_{slot}"
            has_infected = True
        elif plot["status"] == "growing":
            from datetime import datetime, timezone
            ready_at = datetime.fromisoformat(plot["ready_at"])
            if ready_at.tzinfo is None:
                ready_at = ready_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if now >= ready_at:
                label = f"✅ {slot+1}"
            else:
                label = f"🌱 {slot+1}"
                has_growing = True
            cb = f"plot_harvest_{slot}"
        else:
            label = f"❓ {slot+1}"
            cb = f"plot_{slot}"

        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    action_row = [
        InlineKeyboardButton("🌾 Panen Semua", callback_data="harvest_all"),
    ]
    if has_growing:
        action_row.append(InlineKeyboardButton("🧪 Pupuk", callback_data="fertilize_menu"))
    if has_infected:
        action_row.append(InlineKeyboardButton("🧴 Semprot", callback_data="spray_all"))
    buttons.append(action_row)

    buttons.append([
        InlineKeyboardButton("🔧 Perluas", callback_data="expand_farm"),
        InlineKeyboardButton("🏠 Menu", callback_data="menu"),
    ])
    return InlineKeyboardMarkup(buttons)

def plant_keyboard(user_level: int, slot: int):
    buttons = []
    row = []
    for crop_key, crop in CROPS.items():
        if crop["level_req"] <= user_level:
            label = f"{crop['emoji']} {crop['name']}"
            row.append(InlineKeyboardButton(label, callback_data=f"plant_{slot}_{crop_key}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="farm")])
    return InlineKeyboardMarkup(buttons)

def animals_keyboard(pens: list[dict], user_level: int):
    buttons = []
    row = []
    for pen in pens:
        slot = pen["slot"]
        if pen["status"] == "empty":
            label = f"🟩 {slot+1}"
            cb = f"pen_buy_{slot}"
        elif pen["status"] == "producing":
            from datetime import datetime, timezone
            ready_at = datetime.fromisoformat(pen["ready_at"])
            if ready_at.tzinfo is None:
                ready_at = ready_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if now >= ready_at:
                label = f"✅ {ANIMALS[pen['animal']]['emoji']}{slot+1}"
                cb = f"pen_collect_{slot}"
            else:
                label = f"{ANIMALS[pen['animal']]['emoji']} {slot+1}"
                # Ke detail buat opsi hapus/doping
                cb = f"pen_detail_{slot}"
        else:
            label = f"❓ {slot+1}"
            cb = f"pen_{slot}"
        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("🧺 Ambil Semua", callback_data="collect_all_animals"),
        InlineKeyboardButton("🐾 Perluas Kandang", callback_data="expand_pens"),
    ])
    buttons.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


def pen_detail_keyboard(slot: int, animal_key: str, has_doping: bool = False):
    """Keyboard detail kandang: opsi doping, hapus hewan, kembali."""
    buttons = []
    if has_doping:
        buttons.append([
            InlineKeyboardButton("💊 Pake Doping (-30% waktu)", callback_data=f"pen_dope_{slot}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton("💊 Doping (butuh: 1x 💉 Suntikan)", callback_data=f"pen_dope_{slot}")
        ])
    buttons.append([
        InlineKeyboardButton("🗑️ Hapus Hewan (refund 50%)", callback_data=f"pen_remove_{slot}")
    ])
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="animals")])
    return InlineKeyboardMarkup(buttons)

def buy_animal_keyboard(user_level: int, slot: int):
    buttons = []
    row = []
    for a_key, a in ANIMALS.items():
        if a["level_req"] <= user_level:
            label = f"{a['emoji']} {a['name']}"
            row.append(InlineKeyboardButton(label, callback_data=f"buyanimal_{slot}_{a_key}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="animals")])
    return InlineKeyboardMarkup(buttons)

def factories_keyboard(user_buildings: list[dict], user_level: int):
    from game.data import BUILDINGS
    buttons = []
    owned = {b["building"] for b in user_buildings}

    for bld_key, bld in BUILDINGS.items():
        if bld_key in owned:
            buttons.append([InlineKeyboardButton(f"{bld['emoji']} {bld['name']}", callback_data=f"factory_{bld_key}")])
        elif bld["level_req"] <= user_level:
            buttons.append([InlineKeyboardButton(f"🔓 Beli {bld['emoji']} {bld['name']} (Rp{bld['buy_cost']:,})", callback_data=f"buy_building_{bld_key}")])
        else:
            buttons.append([InlineKeyboardButton(f"🔒 {bld['name']} (Lv{bld['level_req']})", callback_data="locked")])

    buttons.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)

def factory_detail_keyboard(building_key: str, slots: list[dict]):
    from game.data import BUILDINGS, PROCESSED_EMOJI
    bld = BUILDINGS[building_key]
    buttons = []

    for rec_key, rec in bld["recipes"].items():
        emoji = PROCESSED_EMOJI.get(rec_key, "📦")
        ingredients = ", ".join(f"{qty}x {get_item_name(k)}" for k, qty in rec["inputs"].items())
        label = f"{emoji} {get_item_name(rec_key)} ({ingredients})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"produce_{building_key}_{rec_key}")])

    for s in slots:
        if s["status"] == "producing":
            from datetime import datetime, timezone
            ready_at = datetime.fromisoformat(s["ready_at"])
            if ready_at.tzinfo is None:
                ready_at = ready_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if now >= ready_at:
                label = f"✅ Slot {s['slot']+1}: {get_item_name(s['item'])} READY"
            else:
                from game.engine import fmt_time
                remaining = int((ready_at - now).total_seconds())
                label = f"⏳ Slot {s['slot']+1}: {get_item_name(s['item'])} ({fmt_time(remaining)})"
            buttons.append([InlineKeyboardButton(label, callback_data=f"collect_{building_key}_{s['slot']}")])

    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="factories")])
    return InlineKeyboardMarkup(buttons)

def storage_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌾 Gudang (Hasil Panen)", callback_data="storage_silo"),
            InlineKeyboardButton("🏚 Lumbung (Alat & Olahan)", callback_data="storage_barn"),
        ],
        [
            InlineKeyboardButton("⬆️ Upgrade Gudang", callback_data="upgrade_silo"),
            InlineKeyboardButton("⬆️ Upgrade Lumbung", callback_data="upgrade_barn"),
        ],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu")],
    ])

def storage_items_keyboard(items: dict, storage_type: str, page: int = 0):
    buttons = []
    item_list = list(items.items())
    per_page = 8
    start = page * per_page
    end = start + per_page
    page_items = item_list[start:end]

    for item_key, qty in page_items:
        emoji = get_item_emoji(item_key)
        name = get_item_name(item_key)
        buttons.append([
            InlineKeyboardButton(f"{emoji} {name} x{qty}", callback_data=f"sell_menu_{item_key}"),
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"storage_{storage_type}_page_{page-1}"))
    if end < len(item_list):
        nav.append(InlineKeyboardButton("▶️ Next", callback_data=f"storage_{storage_type}_page_{page+1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="storage")])
    return InlineKeyboardMarkup(buttons)

def sell_keyboard(item_key: str, qty: int):
    buttons = []
    amounts = [1, 5, 10, qty]
    amounts = sorted(set(a for a in amounts if a <= qty and a > 0))
    row = []
    for amt in amounts:
        row.append(InlineKeyboardButton(f"Jual {amt}", callback_data=f"sell_{item_key}_{amt}"))
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("📢 Pasang di Pasar", callback_data=f"market_list_{item_key}")])
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="storage")])
    return InlineKeyboardMarkup(buttons)

def orders_keyboard(orders: list[dict]):
    buttons = []
    for i, order in enumerate(orders, 1):
        import json
        items = json.loads(order["items"])
        emojis = " ".join(f"{qty}x{get_item_emoji(k)}" for k, qty in items.items())
        label = f"📦 #{i} {emojis} → Rp{order['reward_coins']:,}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"fulfill_{order['id']}")])

    buttons.append([InlineKeyboardButton("🔄 Refresh Pesanan (24jam)", callback_data="refresh_orders")])
    buttons.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)

def market_keyboard(listings: list[dict], page: int = 0, total: int = 0, per_page: int = 9):
    buttons = []
    for listing in listings:
        emoji = get_item_emoji(listing["item"])
        name = get_item_name(listing["item"])
        label = f"{emoji}{name} x{listing['qty']} @ Rp{listing['price']:,} [{listing['seller_name']}]"
        buttons.append([InlineKeyboardButton(label[:50], callback_data=f"mkt_buy_{listing['id']}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"market_page_{page-1}"))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton("▶️ Next", callback_data=f"market_page_{page+1}"))
    if nav:
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton("📢 Listing Saya", callback_data="my_listings"),
        InlineKeyboardButton("🏠 Menu", callback_data="menu"),
    ])
    return InlineKeyboardMarkup(buttons)

def land_keyboard(obstacles: list[dict], plots: list[dict]):
    buttons = []
    obs_slots = {o["slot"]: o for o in obstacles}
    for obs_slot, obs_data in obs_slots.items():
        obs = OBSTACLES[obs_data["obstacle"]]
        buttons.append([InlineKeyboardButton(
            f"{obs['emoji']} {obs['name']} → butuh {get_item_emoji(obs['tool'])}",
            callback_data=f"clear_{obs_slot}"
        )])

    if not obs_slots:
        buttons.append([InlineKeyboardButton("✅ Semua bersih!", callback_data="noop")])

    buttons.append([
        InlineKeyboardButton("🌱 + Lahan", callback_data="expand_farm"),
        InlineKeyboardButton("🐾 + Kandang", callback_data="expand_pens"),
    ])
    buttons.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)

def profile_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Ganti Nama", callback_data="setname"),
            InlineKeyboardButton("🖼️ Set Avatar", callback_data="setavatar"),
        ],
        [
            InlineKeyboardButton("🎭 Gelar Saya", callback_data="mytitles"),
        ],
        [
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"),
            InlineKeyboardButton("🏠 Menu Utama", callback_data="menu"),
        ],
    ])


def leaderboard_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Profil Saya", callback_data="profile"),
            InlineKeyboardButton("🏠 Menu Utama", callback_data="menu"),
        ],
    ])


def shop_keyboard():
    from game.data import TOOL_SHOP
    buttons = []

    # Group by category
    categories = {}
    for key, tool in TOOL_SHOP.items():
        cat = tool["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((key, tool))

    for cat, tools in categories.items():
        row = []
        for key, tool in tools:
            label = f"{tool['emoji']} {tool['name']} Rp{tool['price']:,}"
            row.append(InlineKeyboardButton(label, callback_data=f"shopbuy_{key}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

    buttons.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


def items_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌾 Tanaman", callback_data="items_crops"),
            InlineKeyboardButton("🐾 Hewan", callback_data="items_animals"),
        ],
        [
            InlineKeyboardButton("🏭 Barang Olahan", callback_data="items_products"),
            InlineKeyboardButton("🛒 Alat", callback_data="items_tools"),
        ],
        [
            InlineKeyboardButton("📚 Semua Item", callback_data="items_all"),
        ],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu")],
    ])
