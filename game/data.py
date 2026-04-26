# game/data.py - Master game data for Harvest Kingdom

CROPS = {
    "wheat":      {"name": "Wheat",      "emoji": "🌾", "grow_time": 120,    "sell_price": 500,   "xp": 1,  "level_req": 1,  "seed_cost": 500},
    "corn":       {"name": "Corn",       "emoji": "🌽", "grow_time": 300,    "sell_price": 1200,  "xp": 2,  "level_req": 1,  "seed_cost": 1000},
    "carrot":     {"name": "Carrot",     "emoji": "🥕", "grow_time": 300,    "sell_price": 2000,  "xp": 3,  "level_req": 2,  "seed_cost": 1500},
    "soybean":    {"name": "Soybean",    "emoji": "🫘", "grow_time": 1200,   "sell_price": 3000,  "xp": 4,  "level_req": 3,  "seed_cost": 2500},
    "sugarcane":  {"name": "Sugarcane",  "emoji": "🎋", "grow_time": 1800,   "sell_price": 4500,  "xp": 5,  "level_req": 4,  "seed_cost": 3500},
    "rice":       {"name": "Rice",       "emoji": "🌾", "grow_time": 2700,   "sell_price": 6000,  "xp": 6,  "level_req": 5,  "seed_cost": 5000},
    "pumpkin":    {"name": "Pumpkin",    "emoji": "🎃", "grow_time": 3600,   "sell_price": 9000,  "xp": 8,  "level_req": 7,  "seed_cost": 7500},
    "cotton":     {"name": "Cotton",     "emoji": "☁️", "grow_time": 7200,   "sell_price": 14000, "xp": 10, "level_req": 10, "seed_cost": 11000},
    "potato":     {"name": "Potato",     "emoji": "🥔", "grow_time": 10800,  "sell_price": 20000, "xp": 12, "level_req": 12, "seed_cost": 16000},
    "tomato":     {"name": "Tomato",     "emoji": "🍅", "grow_time": 21600,  "sell_price": 34000, "xp": 15, "level_req": 15, "seed_cost": 28000},
    "strawberry": {"name": "Strawberry", "emoji": "🍓", "grow_time": 28800,  "sell_price": 50000, "xp": 20, "level_req": 18, "seed_cost": 40000},
}

ANIMALS = {
    "chicken": {"name": "Chicken", "emoji": "🐔", "product": "egg",         "prod_emoji": "🥚", "feed_time": 3600,   "buy_cost": 15000,  "sell_price": 3000,  "level_req": 2},
    "cow":     {"name": "Cow",     "emoji": "🐄", "product": "milk",        "prod_emoji": "🥛", "feed_time": 7200,   "buy_cost": 45000,  "sell_price": 6000,  "level_req": 5},
    "pig":     {"name": "Pig",     "emoji": "🐷", "product": "bacon",       "prod_emoji": "🥩", "feed_time": 10800,  "buy_cost": 60000,  "sell_price": 8000,  "level_req": 7},
    "sheep":   {"name": "Sheep",   "emoji": "🐑", "product": "wool",        "prod_emoji": "🧶", "feed_time": 14400,  "buy_cost": 80000,  "sell_price": 10000, "level_req": 9},
    "goat":    {"name": "Goat",    "emoji": "🐐", "product": "goat_milk",   "prod_emoji": "🧴", "feed_time": 10800,  "buy_cost": 70000,  "sell_price": 9000,  "level_req": 10},
    "bee":     {"name": "Bee",     "emoji": "🐝", "product": "honey",       "prod_emoji": "🍯", "feed_time": 18000,  "buy_cost": 100000, "sell_price": 13000, "level_req": 12},
    "duck":    {"name": "Duck",    "emoji": "🦆", "product": "feather",     "prod_emoji": "🪶", "feed_time": 7200,   "buy_cost": 35000,  "sell_price": 5000,  "level_req": 8},
    "fish":    {"name": "Fish",    "emoji": "🐟", "product": "fish",        "prod_emoji": "🐠", "feed_time": 5400,   "buy_cost": 40000,  "sell_price": 7000,  "level_req": 6},
    "lobster": {"name": "Lobster", "emoji": "🦞", "product": "lobster",     "prod_emoji": "🦀", "feed_time": 21600,  "buy_cost": 150000, "sell_price": 20000, "level_req": 15},
    "buffalo": {"name": "Buffalo", "emoji": "🐃", "product": "mozzarella",  "prod_emoji": "🧀", "feed_time": 28800,  "buy_cost": 200000, "sell_price": 26000, "level_req": 18},
}

BUILDINGS = {
    "bakery": {
        "name": "Bakery", "emoji": "🏭", "slots": 2,
        "buy_cost": 80000, "level_req": 3,
        "recipes": {
            "bread":      {"inputs": {"wheat": 3}, "time": 300, "xp": 5, "sell_price": 3500},
            "popcorn":    {"inputs": {"corn": 2},  "time": 600, "xp": 8, "sell_price": 5500},
        }
    },
    "feed_mill": {
        "name": "Feed Mill", "emoji": "⚙️", "slots": 2,
        "buy_cost": 60000, "level_req": 2,
        "recipes": {
            "chicken_feed": {"inputs": {"wheat": 2, "corn": 1}, "time": 180, "xp": 3, "sell_price": 2000},
            "cow_feed":     {"inputs": {"corn": 3, "soybean": 1}, "time": 360, "xp": 5, "sell_price": 3500},
        }
    },
    "dairy": {
        "name": "Dairy", "emoji": "🧈", "slots": 2,
        "buy_cost": 120000, "level_req": 6,
        "recipes": {
            "butter":      {"inputs": {"milk": 2},                    "time": 900,  "xp": 12, "sell_price": 9000},
            "cheese":      {"inputs": {"milk": 3, "goat_milk": 1},    "time": 1800, "xp": 20, "sell_price": 16000},
            "syrup":       {"inputs": {"sugarcane": 4},               "time": 1200, "xp": 15, "sell_price": 12000},
        }
    },
    "textile_mill": {
        "name": "Textile Mill", "emoji": "🧵", "slots": 2,
        "buy_cost": 180000, "level_req": 11,
        "recipes": {
            "cotton_fabric": {"inputs": {"cotton": 2},              "time": 1800, "xp": 20, "sell_price": 18000},
            "wool_sweater":  {"inputs": {"wool": 3},                "time": 3600, "xp": 30, "sell_price": 28000},
        }
    },
    "kitchen": {
        "name": "Kitchen", "emoji": "👨‍🍳", "slots": 3,
        "buy_cost": 250000, "level_req": 14,
        "recipes": {
            "pumpkin_pie":          {"inputs": {"pumpkin": 2, "butter": 1, "sugar": 2},            "time": 3600,  "xp": 35, "sell_price": 38000},
            "pizza":                {"inputs": {"bread": 1, "tomato": 2, "cheese": 1},             "time": 5400,  "xp": 50, "sell_price": 55000},
            "strawberry_ice_cream": {"inputs": {"strawberry": 3, "milk": 2},                       "time": 7200,  "xp": 60, "sell_price": 70000},
            "carrot_juice":         {"inputs": {"carrot": 4},                                      "time": 1200,  "xp": 18, "sell_price": 16000},
            "chocolate_cake":       {"inputs": {"wheat": 4, "egg": 2, "milk": 2, "honey": 1},     "time": 10800, "xp": 80, "sell_price": 95000},
            "sugar":                {"inputs": {"sugarcane": 2},                                   "time": 600,   "xp": 8,  "sell_price": 6000},
        }
    },
}

UPGRADE_TOOLS = {
    # Barn tools
    "bolt":          {"name": "Bolt",         "emoji": "🔩", "type": "barn"},
    "plank":         {"name": "Plank",        "emoji": "🪵", "type": "barn"},
    "duct_tape":     {"name": "Duct Tape",    "emoji": "🩹", "type": "barn"},
    # Silo tools
    "nail":          {"name": "Nail",         "emoji": "📌", "type": "silo"},
    "screw":         {"name": "Screw",        "emoji": "🔧", "type": "silo"},
    "wood_panel":    {"name": "Wood Panel",   "emoji": "🪟", "type": "silo"},
    # General upgrade
    "paint":         {"name": "Paint",        "emoji": "🎨", "type": "general"},
    "brick":         {"name": "Brick",        "emoji": "🧱", "type": "general"},
    "cement":        {"name": "Cement",       "emoji": "🪣", "type": "general"},
    "sledgehammer":  {"name": "Sledgehammer", "emoji": "🔨", "type": "general"},
}

EXPANSION_TOOLS = {
    "land_deed":           {"name": "Land Deed",           "emoji": "📜"},
    "mallet":              {"name": "Mallet",              "emoji": "🪛"},
    "marker_stake":        {"name": "Marker Stake",        "emoji": "📍"},
    "construction_permit": {"name": "Construction Permit", "emoji": "📋"},
    "map_piece":           {"name": "Map Piece",           "emoji": "🗺️"},
    "compass":             {"name": "Compass",             "emoji": "🧭"},
    "mayors_signature":    {"name": "Mayor's Signature",   "emoji": "✍️"},
    "wire_cutter":         {"name": "Wire Cutter",         "emoji": "✂️"},
    "notary_letter":       {"name": "Notary Letter",       "emoji": "📩"},
    "city_plan":           {"name": "City Plan",           "emoji": "🏙️"},
}

CLEARING_TOOLS = {
    "axe":          {"name": "Axe",          "emoji": "🪓"},
    "saw":          {"name": "Saw",          "emoji": "🔪"},
    "dynamite":     {"name": "Dynamite",     "emoji": "🧨"},
    "tnt_barrel":   {"name": "TNT Barrel",   "emoji": "💣"},
    "shovel":       {"name": "Shovel",       "emoji": "🪚"},
    "crowbar":      {"name": "Crowbar",      "emoji": "🔱"},
    "rusty_hoe":    {"name": "Rusty Hoe",    "emoji": "⚒️"},
    "pest_spray":   {"name": "Pest Spray",   "emoji": "💨"},
    "trash_cart":   {"name": "Trash Cart",   "emoji": "🛒"},
    "mini_tractor": {"name": "Mini Tractor", "emoji": "🚜"},
}

OBSTACLES = {
    "small_tree":  {"name": "Small Tree",  "emoji": "🌱", "tool": "axe",      "coins": 5000,  "xp": 5},
    "big_tree":    {"name": "Big Tree",    "emoji": "🌳", "tool": "saw",      "coins": 12000, "xp": 12},
    "rock":        {"name": "Rock",        "emoji": "🪨", "tool": "dynamite", "coins": 10000, "xp": 10},
    "big_rock":    {"name": "Big Rock",    "emoji": "⛰️",  "tool": "tnt_barrel","coins": 25000, "xp": 25},
    "swamp":       {"name": "Swamp",       "emoji": "🌿", "tool": "shovel",   "coins": 8000,  "xp": 8},
    "dead_bush":   {"name": "Dead Bush",   "emoji": "🪵", "tool": "rusty_hoe","coins": 4000,  "xp": 4},
}

LEVEL_THRESHOLDS = [
    0, 50, 130, 250, 420, 650, 950, 1320, 1770, 2310,
    2950, 3700, 4570, 5570, 6710, 8000, 9450, 11070, 12870, 14860,
    17050, 19450, 22070, 24920, 28010, 31350, 34950, 38820, 42970, 47410,
]

BARN_UPGRADE = {
    "base_capacity": 50,
    "upgrade_amount": 25,
    "tools_needed": {"bolt": 3, "plank": 2, "duct_tape": 1},
    "cost_per_upgrade": 100000,
}

SILO_UPGRADE = {
    "base_capacity": 100,
    "upgrade_amount": 50,
    "tools_needed": {"nail": 3, "screw": 2, "wood_panel": 1},
    "cost_per_upgrade": 80000,
}

PLOTS_PER_EXPANSION = 4
BASE_PLOTS = 8
BASE_ANIMAL_PENS = 2
BONUS_DROP_RATE = 0.05

# ─── TOKO ALAT (beli alat pakai Rp) ─────────────────────────────────────────
TOOL_SHOP = {
    # Alat upgrade Gudang (silo)
    "nail":          {"price": 15000,  "emoji": "📌", "name": "Nail",         "category": "Upgrade Gudang"},
    "screw":         {"price": 20000,  "emoji": "🔧", "name": "Screw",        "category": "Upgrade Gudang"},
    "wood_panel":    {"price": 35000,  "emoji": "🪟", "name": "Wood Panel",   "category": "Upgrade Gudang"},
    # Alat upgrade Lumbung (barn)
    "bolt":          {"price": 15000,  "emoji": "🔩", "name": "Bolt",         "category": "Upgrade Lumbung"},
    "plank":         {"price": 20000,  "emoji": "🪵", "name": "Plank",        "category": "Upgrade Lumbung"},
    "duct_tape":     {"price": 30000,  "emoji": "🩹", "name": "Duct Tape",    "category": "Upgrade Lumbung"},
    # Alat perluasan lahan
    "land_deed":           {"price": 50000,  "emoji": "📜", "name": "Land Deed",           "category": "Perluasan"},
    "mallet":              {"price": 25000,  "emoji": "🪛", "name": "Mallet",              "category": "Perluasan"},
    "marker_stake":        {"price": 25000,  "emoji": "📍", "name": "Marker Stake",        "category": "Perluasan"},
    "construction_permit": {"price": 40000,  "emoji": "📋", "name": "Construction Permit", "category": "Perluasan"},
    # Alat pembersih rintangan
    "axe":           {"price": 20000,  "emoji": "🪓", "name": "Axe",          "category": "Pembersih"},
    "saw":           {"price": 30000,  "emoji": "🔪", "name": "Saw",          "category": "Pembersih"},
    "dynamite":      {"price": 35000,  "emoji": "🧨", "name": "Dynamite",     "category": "Pembersih"},
    "tnt_barrel":    {"price": 50000,  "emoji": "💣", "name": "TNT Barrel",   "category": "Pembersih"},
    "shovel":        {"price": 25000,  "emoji": "🪚", "name": "Shovel",       "category": "Pembersih"},
    "rusty_hoe":     {"price": 15000,  "emoji": "⚒️",  "name": "Rusty Hoe",    "category": "Pembersih"},
    # Pupuk & Pestisida
    "pesticide":     {"price": 10000,  "emoji": "🧴", "name": "Pestisida",    "category": "Pertanian"},
    "fertilizer":    {"price": 10000,  "emoji": "🧪", "name": "Pupuk Biasa (30%)",  "category": "Pertanian"},
    "super_fertilizer": {"price": 22000, "emoji": "⚗️", "name": "Pupuk Super (50%)", "category": "Pertanian"},
    # Doping hewan (sistem mirip pupuk tapi buat hewan)
    "animal_doping": {"price": 30000, "emoji": "💉", "name": "Doping Hewan (-30% waktu)", "category": "Peternakan"},
}

ALL_ITEMS = {}
ALL_ITEMS.update({k: {"name": v["name"], "emoji": v["emoji"], "category": "crop"} for k, v in CROPS.items()})
ALL_ITEMS.update({k: {"name": v["name"], "emoji": v["emoji"], "category": "animal_product"} for k, v in {
    "egg": {"name": "Egg", "emoji": "🥚"},
    "milk": {"name": "Milk", "emoji": "🥛"},
    "bacon": {"name": "Bacon", "emoji": "🥩"},
    "wool": {"name": "Wool", "emoji": "🧶"},
    "goat_milk": {"name": "Goat Milk", "emoji": "🧴"},
    "honey": {"name": "Honey", "emoji": "🍯"},
    "feather": {"name": "Feather", "emoji": "🪶"},
    "fish": {"name": "Fish", "emoji": "🐠"},
    "lobster": {"name": "Lobster", "emoji": "🦀"},
    "mozzarella": {"name": "Mozzarella", "emoji": "🧀"},
}.items()})
for b_data in BUILDINGS.values():
    for r_key in b_data["recipes"]:
        ALL_ITEMS[r_key] = {"name": r_key.replace("_", " ").title(), "emoji": "🍽️", "category": "processed"}

ALL_ITEMS.update({k: {"name": v["name"], "emoji": v["emoji"], "category": "upgrade_tool"} for k, v in UPGRADE_TOOLS.items()})
ALL_ITEMS.update({k: {"name": v["name"], "emoji": v["emoji"], "category": "expansion_tool"} for k, v in EXPANSION_TOOLS.items()})
ALL_ITEMS.update({k: {"name": v["name"], "emoji": v["emoji"], "category": "clearing_tool"} for k, v in CLEARING_TOOLS.items()})

# Aliases for processed goods emojis
PROCESSED_EMOJI = {
    "bread": "🍞", "popcorn": "🍿", "butter": "🧈", "sugar": "🍬",
    "cotton_fabric": "🧵", "syrup": "🍯", "cheese": "🧀", "pumpkin_pie": "🥧",
    "wool_sweater": "🧥", "pizza": "🍕", "strawberry_ice_cream": "🍦",
    "carrot_juice": "🥤", "chocolate_cake": "🎂", "chicken_feed": "🌾",
    "cow_feed": "🌿",
}

# Registry runtime untuk hewan custom yang ditambahin admin lewat /addanimal
# Diisi dari database pas bot start oleh game/custom_animals.py
CUSTOM_ANIMAL_PRODUCTS = {}      # {product_key: emoji}
CUSTOM_ANIMAL_PRODUCT_NAMES = {} # {product_key: display_name}

# Registry runtime untuk produk olahan custom dari resep tambahan
CUSTOM_PROCESSED_EMOJI = {}      # {recipe_key: emoji}
CUSTOM_PROCESSED_NAMES = {}      # {recipe_key: display_name}


def get_item_emoji(item_key: str) -> str:
    if item_key in CROPS:
        return CROPS[item_key]["emoji"]
    if item_key in UPGRADE_TOOLS:
        return UPGRADE_TOOLS[item_key]["emoji"]
    if item_key in EXPANSION_TOOLS:
        return EXPANSION_TOOLS[item_key]["emoji"]
    if item_key in CLEARING_TOOLS:
        return CLEARING_TOOLS[item_key]["emoji"]
    if item_key in PROCESSED_EMOJI:
        return PROCESSED_EMOJI[item_key]
    if item_key in CUSTOM_PROCESSED_EMOJI:
        return CUSTOM_PROCESSED_EMOJI[item_key]
    if item_key in CUSTOM_ANIMAL_PRODUCTS:
        return CUSTOM_ANIMAL_PRODUCTS[item_key]
    animal_products = {
        "egg": "🥚", "milk": "🥛", "bacon": "🥩", "wool": "🧶",
        "goat_milk": "🧴", "honey": "🍯", "feather": "🪶", "fish": "🐠",
        "lobster": "🦀", "mozzarella": "🧀",
    }
    return animal_products.get(item_key, "📦")

def get_item_name(item_key: str) -> str:
    for db in [CROPS, UPGRADE_TOOLS, EXPANSION_TOOLS, CLEARING_TOOLS]:
        if item_key in db:
            return db[item_key]["name"]
    if item_key in CUSTOM_PROCESSED_NAMES:
        return CUSTOM_PROCESSED_NAMES[item_key]
    for b in BUILDINGS.values():
        if item_key in b["recipes"]:
            return item_key.replace("_", " ").title()
    if item_key in CUSTOM_ANIMAL_PRODUCT_NAMES:
        return CUSTOM_ANIMAL_PRODUCT_NAMES[item_key]
    animal_products = {
        "egg": "Egg", "milk": "Milk", "bacon": "Bacon", "wool": "Wool",
        "goat_milk": "Goat Milk", "honey": "Honey", "feather": "Feather",
        "fish": "Fish", "lobster": "Lobster", "mozzarella": "Mozzarella",
    }
    return animal_products.get(item_key, item_key.replace("_", " ").title())

def get_level_from_xp(xp: int) -> int:
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp >= threshold:
            level = i + 1
        else:
            break
    return min(level, len(LEVEL_THRESHOLDS))

def get_xp_for_next_level(level: int) -> int:
    if level >= len(LEVEL_THRESHOLDS):
        return LEVEL_THRESHOLDS[-1]
    return LEVEL_THRESHOLDS[level]
