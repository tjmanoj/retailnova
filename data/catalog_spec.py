"""Nova Bazaar reference data: 7 stores and a 72-SKU festive catalog (synthetic).

Names, ids, categories and sizes follow docs/contracts.md §1. Nova Bazaar is a fictional retailer;
no real brands are used. Import STORES, CATEGORIES and PRODUCTS from here; everything else in
data/ derives from this file.
"""
from __future__ import annotations

SEED = 2026

# --------------------------------------------------------------------------------------------
# Stores (contracts §1.1). `region` and `scale` are generator-only fields (not written to Firestore).
# --------------------------------------------------------------------------------------------
STORES = [
    {"store_id": "CHN-TNG", "name": "T. Nagar", "city": "Chennai", "type": "store",
     "languages": ["ta", "en"], "lat": 13.0418, "lng": 80.2341, "region": "tn", "scale": 1.30},
    {"store_id": "CHN-ANN", "name": "Anna Nagar", "city": "Chennai", "type": "store",
     "languages": ["ta", "en"], "lat": 13.0850, "lng": 80.2101, "region": "tn", "scale": 0.95},
    {"store_id": "BLR-JAY", "name": "Jayanagar", "city": "Bengaluru", "type": "store",
     "languages": ["kn", "en", "hi"], "lat": 12.9299, "lng": 77.5826, "region": "ka", "scale": 1.05},
    {"store_id": "BLR-IND", "name": "Indiranagar", "city": "Bengaluru", "type": "store",
     "languages": ["kn", "en", "hi"], "lat": 12.9784, "lng": 77.6408, "region": "ka", "scale": 0.95},
    {"store_id": "CBE-RSP", "name": "RS Puram", "city": "Coimbatore", "type": "store",
     "languages": ["ta", "en"], "lat": 11.0089, "lng": 76.9500, "region": "kongu", "scale": 0.60},
    {"store_id": "HYD-BNJ", "name": "Banjara Hills", "city": "Hyderabad", "type": "store",
     "languages": ["te", "hi", "en"], "lat": 17.4156, "lng": 78.4347, "region": "ts", "scale": 0.65},
    {"store_id": "ONLINE", "name": "Online store", "city": "—", "type": "online",
     "languages": ["en", "hi", "ta"], "lat": None, "lng": None, "region": "online", "scale": 1.80},
]
STORE_IDS = [s["store_id"] for s in STORES]
STORE_BY_ID = {s["store_id"]: s for s in STORES}

# --------------------------------------------------------------------------------------------
# Categories (contracts §1.2). `base` = typical units/day for an average SKU at a scale-1.0 store.
# --------------------------------------------------------------------------------------------
CATEGORIES = [
    {"category": "sarees", "label": "Sarees", "prefix": "SAR", "sizes": ["FREE"], "base": 1.6},
    {"category": "kurta_sets", "label": "Women's Kurta Sets", "prefix": "KUR",
     "sizes": ["S", "M", "L", "XL"], "base": 2.0},
    {"category": "mens_ethnic", "label": "Men's Ethnic", "prefix": "MEN",
     "sizes": ["S", "M", "L", "XL", "XXL"], "base": 1.6},
    {"category": "home_decor", "label": "Festive Home Decor", "prefix": "DEC", "sizes": ["FREE"], "base": 1.8},
    {"category": "gifting", "label": "Festive Gifting", "prefix": "GFT", "sizes": ["FREE"], "base": 1.7},
    {"category": "footwear", "label": "Ethnic Footwear", "prefix": "FTW",
     "sizes": ["6", "7", "8", "9", "10"], "base": 1.4},
]
CATEGORY_BY_ID = {c["category"]: c for c in CATEGORIES}

# Share of units by size (used to split SKU-level stock and to pick sizes in signals).
SIZE_CURVES = {
    "FREE": {"FREE": 1.0},
    "kurta_sets": {"S": 0.20, "M": 0.32, "L": 0.30, "XL": 0.18},
    "mens_ethnic": {"S": 0.10, "M": 0.25, "L": 0.30, "XL": 0.22, "XXL": 0.13},
    "footwear": {"6": 0.16, "7": 0.26, "8": 0.26, "9": 0.20, "10": 0.12},
}

# --------------------------------------------------------------------------------------------
# Products. Tuple order:
# (sku, name, subcategory, color, color_family, material, occasion, price_inr, mrp_inr, tags,
#  description, popularity)
# popularity is generator-only: a relative demand weight (1.0 = typical SKU).
# --------------------------------------------------------------------------------------------
_P = [
    # ---------------- Sarees (₹1,499 – ₹14,999), size FREE ----------------
    ("SAR-001", "Maroon Kanchipuram Silk Saree, gold zari border", "kanchipuram", "maroon", "red", "silk",
     ["diwali", "wedding", "festive"], 4799, 5999,
     ["kanchipuram", "pure silk", "zari", "temple border", "south indian", "deepavali", "maroon"],
     "A rich maroon Kanchipuram silk saree woven with a classic gold zari border and a contrast pallu. "
     "The heavy silk drapes beautifully and holds its shape through long festive days. A timeless pick for "
     "Deepavali, weddings and temple visits.", 1.45),
    ("SAR-002", "Ruby Red Banarasi Silk Saree with floral buttis", "banarasi", "red", "red", "silk",
     ["wedding", "diwali", "reception"], 6499, 7999,
     ["banarasi", "brocade", "zari buttis", "bridal", "red"],
     "A ruby red Banarasi silk saree scattered with gold floral buttis and a brocade pallu. "
     "Its lustrous weave catches the light at evening functions. Made for weddings, receptions and Diwali pujas.", 1.0),
    ("SAR-003", "Mustard Yellow Cotton-Silk Saree with temple border", "cotton_silk", "mustard", "yellow",
     "cotton silk", ["pongal", "festive", "daily wear"], 2299, 2799,
     ["temple border", "lightweight", "cotton silk", "mustard", "haldi"],
     "A mustard yellow cotton-silk saree with a woven temple border in deep green. Light and breathable, "
     "it is comfortable from morning puja to evening visits. Ideal for Pongal, haldi functions and festive office days.", 0.9),
    ("SAR-004", "Bottle Green Kanchipuram Silk Saree, contrast pink border", "kanchipuram", "green", "green",
     "silk", ["wedding", "diwali", "festive"], 7999, 9999,
     ["kanchipuram", "pure silk", "contrast border", "zari", "green"],
     "A deep bottle green Kanchipuram silk saree paired with a bright rani pink border and gold zari checks. "
     "The contrast is traditional and striking. A favourite for wedding guests and Deepavali family gatherings.", 0.85),
    ("SAR-005", "Wine Maroon Soft Silk Saree with copper zari", "soft_silk", "maroon", "red", "soft silk",
     ["diwali", "festive", "party"], 3299, 3999,
     ["soft silk", "copper zari", "lightweight", "maroon", "wine"],
     "A wine maroon soft silk saree with fine copper zari stripes and a woven pallu. It is lighter than "
     "traditional silk and easy to drape. A graceful, budget-friendly choice for Diwali parties.", 1.0),
    ("SAR-006", "Peacock Blue Mysore Crepe Silk Saree", "mysore_silk", "blue", "blue", "crepe silk",
     ["festive", "party", "office"], 3999, 4799,
     ["mysore silk", "crepe", "plain body", "zari border", "peacock blue"],
     "A peacock blue Mysore crepe silk saree with a slim gold zari border. The fluid crepe falls softly and "
     "resists creasing. Elegant for Dasara, festive office days and evening functions.", 0.9),
    ("SAR-007", "Ivory and Gold Kerala Kasavu Saree", "kasavu", "ivory", "white", "cotton",
     ["onam", "vishu", "temple"], 1899, 2299,
     ["kasavu", "kerala", "handloom", "gold border", "onam"],
     "A handloom ivory Kerala kasavu saree with a broad gold border. Crisp cotton keeps it cool in the heat. "
     "The classic choice for Onam, Vishu and temple visits.", 0.75),
    ("SAR-008", "Deep Maroon Bridal Kanchipuram Silk Saree, heavy zari pallu", "kanchipuram", "maroon", "red",
     "silk", ["wedding", "bridal"], 12999, 15999,
     ["bridal", "kanchipuram", "heavy zari", "pure silk", "maroon", "muhurtham"],
     "A deep maroon bridal Kanchipuram silk saree with a heavy gold zari pallu and a densely woven border. "
     "Rich mango and peacock motifs run through the body. Made for the muhurtham and other wedding rituals.", 0.55),
    ("SAR-009", "Magenta Pink Chanderi Silk Saree", "chanderi", "magenta", "pink", "chanderi silk",
     ["festive", "party", "daily wear"], 2799, 3299,
     ["chanderi", "sheer", "lightweight", "zari buttis", "pink"],
     "A magenta pink Chanderi silk saree with a sheer weave and small zari buttis. It is feather-light and "
     "easy to carry all day. Lovely for Navratri evenings and festive get-togethers.", 0.85),
    ("SAR-010", "Navy Blue Georgette Saree with sequin border", "georgette", "navy", "blue", "georgette",
     ["party", "reception", "diwali"], 2499, 2999,
     ["georgette", "sequins", "party wear", "navy", "ready to drape"],
     "A navy blue georgette saree finished with a shimmering sequin border. The flowing fabric drapes easily "
     "and photographs well at night. Perfect for Diwali parties and receptions.", 0.9),
    ("SAR-011", "Rust Orange Linen Saree with zari stripes", "linen", "rust", "orange", "linen",
     ["office", "daily wear", "festive"], 1499, 1899,
     ["linen", "handloom", "breathable", "rust", "zari stripes"],
     "A rust orange linen saree with thin zari stripes and tassels on the pallu. Breathable linen keeps it "
     "comfortable through warm days. A smart pick for festive office wear.", 0.8),
    ("SAR-012", "Crimson Red Paithani Silk Saree, peacock pallu", "paithani", "red", "red", "silk",
     ["wedding", "diwali", "festive"], 9499, 11999,
     ["paithani", "peacock motif", "pure silk", "zari", "red"],
     "A crimson red Paithani silk saree with the signature woven peacock pallu and a rich zari border. "
     "A treasured heirloom weave. Stunning for Diwali, weddings and family celebrations.", 0.6),

    # ---------------- Women's kurta sets (₹999 – ₹4,499), sizes S M L XL ----------------
    ("KUR-001", "Maroon Anarkali Kurta Set with dupatta", "anarkali", "maroon", "red", "chanderi",
     ["diwali", "festive", "party"], 2999, 3799,
     ["anarkali", "flared", "dupatta", "zari", "maroon"],
     "A flared maroon Anarkali kurta in Chanderi with zari yoke work, paired with matching pants and a sheer "
     "dupatta. The swirl of the hem makes it a festive favourite. Great for Diwali pujas and family dinners.", 1.1),
    ("KUR-002", "Mint Green Cotton Straight Kurta Set", "straight", "mint", "green", "cotton",
     ["daily wear", "office", "festive"], 1299, 1599,
     ["cotton", "straight cut", "comfortable", "mint", "pants"],
     "A mint green straight kurta in soft cotton with delicate thread embroidery at the neckline, paired with "
     "straight pants. Easy to wear from morning to evening. A comfortable everyday festive option.", 1.0),
    ("KUR-003", "Royal Blue Silk-Blend Kurta Palazzo Set", "palazzo", "blue", "blue", "silk blend",
     ["festive", "party", "diwali"], 2499, 2999,
     ["silk blend", "palazzo", "royal blue", "zari", "dupatta"],
     "A royal blue silk-blend kurta with gold zari detailing, paired with wide palazzos and a matching dupatta. "
     "It has a soft sheen that suits evening celebrations. A polished pick for Diwali gatherings.", 0.95),
    ("KUR-004", "Mustard Chikankari Kurta Set", "chikankari", "mustard", "yellow", "cotton",
     ["festive", "haldi", "daily wear"], 2199, 2699,
     ["chikankari", "lucknowi", "hand embroidery", "mustard", "breathable"],
     "A mustard kurta set with Lucknowi chikankari hand embroidery on breathable cotton. Light and graceful, "
     "with matching pants and a mulmul dupatta. Ideal for haldi ceremonies and daytime festivities.", 0.95),
    ("KUR-005", "Rani Pink Bandhani Kurta Set", "bandhani", "pink", "pink", "cotton silk",
     ["navratri", "festive", "party"], 1799, 2199,
     ["bandhani", "tie and dye", "rani pink", "gota", "dupatta"],
     "A rani pink kurta set in traditional bandhani tie-and-dye with gota trims and a matching dupatta. "
     "Bright and celebratory. A natural choice for Navratri and festive evenings.", 0.9),
    ("KUR-006", "Ivory Gota Patti Kurta Sharara Set", "sharara", "ivory", "white", "georgette",
     ["wedding", "eid", "reception"], 4299, 5199,
     ["sharara", "gota patti", "ivory", "georgette", "wedding guest"],
     "An ivory georgette kurta with shimmering gota patti work, paired with a flared sharara and an organza "
     "dupatta. Elegant and festive without being heavy. Made for Eid, receptions and wedding functions.", 0.75),
    ("KUR-007", "Teal Block-Print Cotton Kurta Set", "straight", "teal", "blue", "cotton",
     ["daily wear", "office"], 999, 1299,
     ["block print", "cotton", "teal", "everyday", "pants"],
     "A teal kurta set in hand block-printed cotton with straight pants. Soft, breathable and easy to wash. "
     "An affordable everyday piece that still feels special.", 0.95),
    ("KUR-008", "Red Silk-Blend Kurta Set with zari yoke", "straight", "red", "red", "silk blend",
     ["diwali", "festive", "wedding"], 2799, 3499,
     ["silk blend", "zari yoke", "red", "festive", "dupatta"],
     "A red silk-blend kurta set with an intricate zari yoke, slim pants and a contrast dupatta. "
     "A classic festive red that photographs beautifully. Perfect for Diwali and wedding functions.", 1.0),
    ("KUR-009", "Lavender Organza Kurta Set", "straight", "lavender", "purple", "organza",
     ["party", "reception", "festive"], 3499, 4199,
     ["organza", "lavender", "pastel", "sequins", "dupatta"],
     "A pastel lavender organza kurta set with fine sequin and thread work and a matching dupatta. "
     "Light, airy and modern. Lovely for day receptions and festive brunches.", 0.7),
    ("KUR-010", "Black Mirror-Work Kurta Set", "straight", "black", "black", "rayon",
     ["party", "navratri", "festive"], 1999, 2499,
     ["mirror work", "black", "rayon", "embroidered", "pants"],
     "A black rayon kurta set with colourful mirror work and thread embroidery, paired with straight pants. "
     "Bold and fun to wear. A standout for Navratri garba nights and festive parties.", 0.85),
    ("KUR-011", "Peach Floral Printed Anarkali Kurta", "anarkali", "peach", "orange", "rayon",
     ["daily wear", "festive"], 1499, 1899,
     ["anarkali", "floral print", "peach", "rayon", "lightweight"],
     "A peach Anarkali kurta in flowing rayon with a soft floral print and a flared hem. Easy to style with "
     "leggings or palazzos. A cheerful, budget-friendly festive pick.", 0.9),
    ("KUR-012", "Emerald Green Velvet Kurta Set", "straight", "emerald", "green", "velvet",
     ["wedding", "reception", "christmas"], 4499, 5499,
     ["velvet", "emerald", "winter wedding", "zari", "dupatta"],
     "An emerald green velvet kurta set with zari embroidery at the neck and sleeves, with a contrast dupatta. "
     "Plush and regal for cooler evenings. Ideal for winter weddings and receptions.", 0.6),

    # ---------------- Men's ethnic (₹899 – ₹5,999), sizes S M L XL XXL ----------------
    ("MEN-001", "Ivory Cotton Kurta Pyjama Set", "kurta_set", "ivory", "white", "cotton",
     ["festive", "puja", "daily wear"], 1499, 1799,
     ["kurta pyjama", "cotton", "ivory", "classic", "comfortable"],
     "A classic ivory kurta pyjama set in soft, breathable cotton with subtle self-weave texture. "
     "Clean and versatile for any family occasion. A dependable choice for pujas and festive mornings.", 1.05),
    ("MEN-002", "Maroon Silk-Blend Kurta with churidar", "kurta_set", "maroon", "red", "silk blend",
     ["diwali", "wedding", "festive"], 2299, 2799,
     ["silk blend", "maroon", "churidar", "festive", "mandarin collar"],
     "A maroon silk-blend kurta with a mandarin collar and fabric buttons, paired with a fitted churidar. "
     "It has a rich sheen for evening celebrations. A smart match for Diwali and family weddings.", 1.0),
    ("MEN-003", "Mustard Jacquard Nehru Jacket", "nehru_jacket", "mustard", "yellow", "jacquard",
     ["wedding", "festive", "party"], 1999, 2499,
     ["nehru jacket", "jacquard", "mustard", "layering", "sleeveless"],
     "A mustard jacquard Nehru jacket with a tonal woven pattern and a band collar. Layer it over any plain "
     "kurta to instantly dress it up. Great for weddings and festive parties.", 0.85),
    ("MEN-004", "Royal Blue Silk-Blend Kurta", "kurta", "blue", "blue", "silk blend",
     ["diwali", "festive", "wedding"], 1899, 2399,
     ["silk blend", "royal blue", "kurta", "festive", "straight cut"],
     "A royal blue silk-blend kurta with a straight cut, mandarin collar and a subtle sheen. It pairs well with "
     "white churidar or pyjama. A confident colour for Diwali evenings and wedding functions.", 1.15),
    ("MEN-005", "Classic White Cotton Short Kurta", "kurta", "white", "white", "cotton",
     ["daily wear", "pongal", "office"], 899, 1199,
     ["short kurta", "cotton", "white", "casual", "everyday"],
     "A crisp white short kurta in breathable cotton with a band collar and side slits. Easy to pair with jeans "
     "or a veshti. A comfortable everyday ethnic staple.", 1.0),
    ("MEN-006", "Navy Blue Bandhgala Jacket Set", "bandhgala", "navy", "blue", "terry rayon",
     ["wedding", "reception"], 5999, 7499,
     ["bandhgala", "jodhpuri", "navy", "formal", "trousers"],
     "A navy blue bandhgala jacket with matching trousers, structured shoulders and metal buttons. "
     "Sharp, formal and regal. Made for receptions, sangeets and wedding ceremonies.", 0.55),
    ("MEN-007", "Cream Silk Kurta and Veshti Set", "kurta_set", "cream", "white", "silk",
     ["pongal", "wedding", "temple"], 3499, 4299,
     ["veshti", "silk", "cream", "south indian", "gold border"],
     "A cream silk kurta paired with a matching veshti finished with a gold zari border. Traditional South "
     "Indian festive dressing made easy. A natural choice for Pongal, temple visits and weddings.", 0.75),
    ("MEN-008", "Peacock Green Printed Kurta", "kurta", "green", "green", "cotton",
     ["festive", "daily wear"], 1299, 1599,
     ["printed", "cotton", "peacock green", "casual", "festive"],
     "A peacock green cotton kurta with a fine ethnic print and a mandarin collar. Light and easy to wear "
     "all day. A relaxed festive look for family visits.", 0.85),
    ("MEN-009", "Sky Blue Chikankari Kurta", "kurta", "sky blue", "blue", "cotton",
     ["festive", "eid", "daily wear"], 1699, 2099,
     ["chikankari", "sky blue", "hand embroidery", "cotton", "lucknowi"],
     "A sky blue cotton kurta with delicate Lucknowi chikankari embroidery down the placket. Soft, airy and "
     "understated. Ideal for Eid, daytime pujas and festive brunches.", 0.9),
    ("MEN-010", "Black Embroidered Sherwani-Style Kurta Set", "sherwani", "black", "black", "art silk",
     ["wedding", "reception", "party"], 4999, 5999,
     ["sherwani", "embroidered", "black", "art silk", "churidar"],
     "A black art-silk sherwani-style long kurta with tonal embroidery, paired with a churidar. "
     "Dramatic and elegant under evening lights. A strong pick for receptions and sangeet nights.", 0.6),
    ("MEN-011", "Rust Linen-Blend Kurta", "kurta", "rust", "orange", "linen blend",
     ["festive", "office", "daily wear"], 1599, 1999,
     ["linen", "rust", "breathable", "straight cut", "casual"],
     "A rust linen-blend kurta with a straight cut and wooden buttons. Breathable and naturally textured. "
     "Smart enough for festive office days and casual celebrations.", 0.8),
    ("MEN-012", "Gold Jacquard Kurta with Nehru Jacket Set", "kurta_set", "gold", "gold", "silk blend",
     ["wedding", "diwali", "reception"], 3999, 4999,
     ["jacquard", "nehru jacket", "gold", "three piece", "festive"],
     "A three-piece set with an ivory kurta, churidar and a gold jacquard Nehru jacket. Coordinated and "
     "ready to wear. Made for Diwali nights, weddings and receptions.", 0.75),

    # ---------------- Festive home decor (₹199 – ₹2,999), size FREE ----------------
    ("DEC-001", "Hand-Painted Terracotta Diyas, set of 12", "diyas", "multicolour", "multi", "terracotta",
     ["diwali", "karthigai deepam", "puja"], 299, 399,
     ["diya", "terracotta", "hand painted", "oil lamp", "deepavali"],
     "A set of 12 hand-painted terracotta diyas in bright festive colours. Fill them with oil or ghee and a "
     "cotton wick. A must for Deepavali and Karthigai Deepam.", 1.3),
    ("DEC-002", "Brass Diya Set of 5, engraved", "diyas", "gold", "gold", "brass",
     ["diwali", "puja", "housewarming"], 1299, 1599,
     ["brass", "diya", "engraved", "puja", "reusable", "oil lamp"],
     "A set of five solid brass diyas with hand-engraved floral patterns. They are heavy, reusable and polish "
     "to a warm shine. A lasting addition to the puja room for Diwali and every festival after.", 1.25),
    ("DEC-003", "Marigold and Mango Leaf Toran", "toran", "orange", "orange", "fabric",
     ["diwali", "housewarming", "pongal"], 449, 599,
     ["toran", "door hanging", "marigold", "mango leaf", "reusable"],
     "A reusable door toran of fabric marigolds and mango leaves with small brass bells. It brings an "
     "auspicious welcome to any entrance. Perfect for Diwali, Pongal and housewarmings.", 1.05),
    ("DEC-004", "Brass Kuthu Vilakku Oil Lamp, 12 inch", "lamps", "gold", "gold", "brass",
     ["diwali", "puja", "wedding", "housewarming"], 2999, 3499,
     ["kuthu vilakku", "brass", "oil lamp", "south indian", "puja"],
     "A 12-inch traditional brass kuthu vilakku with five wicks and a peacock finial. Sturdy and beautifully "
     "finished. A centrepiece for pujas, weddings and housewarming ceremonies.", 0.7),
    ("DEC-005", "Rangoli Colour and Stencil Kit", "rangoli", "multicolour", "multi", "colour powder",
     ["diwali", "pongal", "onam"], 349, 449,
     ["rangoli", "kolam", "stencils", "colours", "diy"],
     "A rangoli kit with ten vibrant colour powders, reusable stencils and a filler tool. Makes neat kolam and "
     "rangoli designs easy for beginners. Fun for Diwali and Pongal mornings.", 1.0),
    ("DEC-006", "Warm White LED Fairy Lights, 10 m", "lights", "warm white", "gold", "copper wire",
     ["diwali", "christmas", "party"], 399, 499,
     ["fairy lights", "led", "string lights", "plug-in", "decoration"],
     "Ten metres of warm white LED fairy lights on thin copper wire with eight lighting modes. "
     "Wrap them around balconies, doors or plants. Bright, safe and low on power for Diwali nights.", 1.2),
    ("DEC-007", "Sandalwood Scented Candle Set in glass jars", "candles", "white", "white", "soy wax",
     ["diwali", "christmas", "gifting"], 799, 999,
     ["candles", "scented", "sandalwood", "soy wax", "set of 3"],
     "A set of three sandalwood-scented soy wax candles in reusable glass jars. Each burns clean for about "
     "20 hours. A calm, fragrant touch for Diwali evenings or as a gift.", 0.85),
    ("DEC-008", "Brass Urli Bowl for floating flowers", "urli", "gold", "gold", "brass",
     ["diwali", "housewarming", "onam"], 1799, 2199,
     ["urli", "brass", "floating flowers", "centrepiece", "traditional"],
     "A wide brass urli bowl for floating flowers and diyas at the entrance or living room. Heavy, polished "
     "and traditional. A graceful centrepiece for Diwali and Onam.", 0.7),
    ("DEC-009", "Maroon and Gold Embroidered Cushion Covers, set of 2", "soft_furnishing", "maroon", "red",
     "silk blend", ["diwali", "housewarming"], 699, 899,
     ["cushion covers", "embroidered", "maroon", "gold", "living room"],
     "A pair of maroon silk-blend cushion covers with gold thread embroidery and zip closures. "
     "An easy way to refresh the living room for guests. Sized for standard 16-inch cushions.", 0.8),
    ("DEC-010", "Sheesham Wood Pooja Chowki with brass inlay", "puja_furniture", "brown", "brown",
     "sheesham wood", ["puja", "diwali", "housewarming"], 1499, 1899,
     ["pooja chowki", "wooden", "brass inlay", "puja", "handcrafted"],
     "A low sheesham wood pooja chowki with brass inlay work on the top and legs. Sturdy enough for idols, "
     "lamps and the puja thali. A handcrafted base for Diwali and Lakshmi puja.", 0.6),
    ("DEC-011", "Peacock Metal Tealight Holder", "candle_holder", "blue", "blue", "metal",
     ["diwali", "gifting"], 599, 799,
     ["tealight holder", "peacock", "metal", "enamel", "decor"],
     "A peacock-shaped metal tealight holder with blue and green enamel work. It throws pretty patterns of "
     "light when lit. A charming Diwali accent or small gift.", 0.8),
    ("DEC-012", "Ready-to-Stick Floral Rangoli Mat", "rangoli", "multicolour", "multi", "acrylic",
     ["diwali", "pongal", "housewarming"], 199, 249,
     ["rangoli", "sticker", "reusable", "floral", "no mess"],
     "A reusable floral rangoli mat with a gentle adhesive back that sticks to floors without mess. "
     "Ready in seconds and easy to store after the festival. Great for apartments and busy mornings.", 1.0),

    # ---------------- Festive gifting (₹349 – ₹2,499), size FREE ----------------
    ("GFT-001", "Dry Fruit Gift Box, 400 g", "dry_fruits", "gold", "gold", "dry fruits",
     ["diwali", "corporate", "gifting"], 899, 1099,
     ["dry fruits", "almonds", "cashews", "raisins", "gift box", "under 1000"],
     "A festive gift box of 400 g premium almonds, cashews and raisins in a gold-foil box. "
     "A crowd-pleasing Diwali gift that suits family, neighbours and colleagues.", 1.3),
    ("GFT-002", "Premium Dry Fruit Hamper in brass-finish box, 750 g", "dry_fruits", "gold", "gold",
     "dry fruits", ["diwali", "corporate", "wedding"], 1899, 2299,
     ["dry fruits", "pistachios", "hamper", "premium", "brass box"],
     "A premium 750 g hamper of almonds, cashews, pistachios and apricots in a reusable brass-finish box. "
     "Elegant enough for clients and elders. A standout Diwali and wedding gift.", 0.9),
    ("GFT-003", "Assorted Mithai Box, 500 g", "sweets", "multicolour", "multi", "sweets",
     ["diwali", "pongal", "gifting"], 549, 649,
     ["mithai", "kaju katli", "mysore pak", "laddu", "sweets"],
     "An assorted 500 g mithai box with kaju katli, Mysore pak and besan laddu, freshly packed. "
     "Classic festive sweets for sharing. Best enjoyed within ten days.", 1.2),
    ("GFT-004", "Handmade Chocolate Gift Box, 16 pieces", "chocolates", "brown", "brown", "chocolate",
     ["diwali", "christmas", "gifting"], 749, 899,
     ["chocolates", "handmade", "assorted", "gift box", "under 1000"],
     "A box of 16 handmade chocolates with fillings like almond praline, orange and cardamom. "
     "A modern alternative to mithai. Lovely for Diwali and Christmas gifting.", 1.0),
    ("GFT-005", "Silver-Plated Pooja Thali Set", "puja", "silver", "silver", "silver-plated brass",
     ["diwali", "wedding", "puja"], 1499, 1899,
     ["pooja thali", "silver plated", "puja set", "kumkum", "diya"],
     "A silver-plated pooja thali with a diya, kumkum bowls, bell and incense holder. Polished and tarnish "
     "resistant. A thoughtful gift for Diwali, weddings and housewarmings.", 0.8),
    ("GFT-006", "Dry Fruit Jute Potli Pack, set of 4", "dry_fruits", "multicolour", "multi", "dry fruits",
     ["diwali", "gifting", "return gifts"], 649, 799,
     ["dry fruits", "potli", "jute", "return gifts", "under 1000"],
     "Four small jute potlis filled with almonds, cashews, raisins and dates. Easy to hand out to guests and "
     "colleagues. A budget-friendly Diwali return gift.", 1.0),
    ("GFT-007", "Brass Ganesha Idol, 4 inch", "idols", "gold", "gold", "brass",
     ["diwali", "housewarming", "ganesh chaturthi"], 1199, 1499,
     ["ganesha", "idol", "brass", "puja", "auspicious"],
     "A 4-inch solid brass Ganesha idol with fine detailing and an antique finish. Auspicious for new "
     "beginnings. A meaningful gift for Diwali and housewarmings.", 0.8),
    ("GFT-008", "Festive Tea Sampler Gift Box", "tea", "green", "green", "tea",
     ["diwali", "corporate", "gifting"], 599, 749,
     ["tea", "assam", "darjeeling", "nilgiri", "sampler"],
     "A sampler of Assam, Darjeeling and Nilgiri teas with a masala chai blend, in a printed gift box. "
     "A warm gift for tea lovers. Great for colleagues and neighbours.", 0.75),
    ("GFT-009", "Scented Diya and Candle Gift Hamper", "hamper", "multicolour", "multi", "wax",
     ["diwali", "gifting"], 899, 1099,
     ["diya", "candles", "hamper", "scented", "under 1000"],
     "A gift hamper of scented gel diyas, two jar candles and a brass tealight stand in a festive box. "
     "Ready to gift. Brings Diwali glow to any home.", 0.95),
    ("GFT-010", "Copper Water Bottle and Tumbler Gift Set", "wellness", "copper", "brown", "copper",
     ["diwali", "corporate", "wedding"], 1299, 1599,
     ["copper", "bottle", "tumbler", "wellness", "ayurvedic"],
     "A hammered copper water bottle with two matching tumblers in a gift box. Leak-proof and long lasting. "
     "A useful, healthy gift for Diwali and corporate gifting.", 0.8),
    ("GFT-011", "Corporate Diwali Hamper with dry fruits and diya", "hamper", "gold", "gold", "mixed",
     ["diwali", "corporate"], 2499, 2999,
     ["corporate", "hamper", "dry fruits", "diya", "greeting card"],
     "A premium hamper with dry fruits, a brass diya, chocolates and a greeting card in a keepsake box. "
     "Designed for clients and teams. Bulk orders are popular before Diwali.", 0.65),
    ("GFT-012", "Meenakari Kumkum and Haldi Box Set", "puja", "multicolour", "multi", "metal",
     ["diwali", "navratri", "return gifts"], 349, 449,
     ["kumkum box", "haldi", "meenakari", "return gifts", "navratri"],
     "A pair of meenakari kumkum and haldi boxes with colourful enamel lids. Small, pretty and practical. "
     "A favourite return gift for Navratri golu and haldi-kumkum gatherings.", 1.0),

    # ---------------- Ethnic footwear (₹699 – ₹2,499), sizes 6 7 8 9 10 ----------------
    ("FTW-001", "Women's Gold Embroidered Mojaris", "mojari", "gold", "gold", "faux leather",
     ["wedding", "diwali", "festive"], 1199, 1499,
     ["mojari", "embroidered", "gold", "women", "cushioned"],
     "Women's gold mojaris with dense zari embroidery and a cushioned insole. They go with sarees, lehengas "
     "and kurta sets alike. Comfortable for long festive evenings.", 1.0),
    ("FTW-002", "Men's Tan Leather Kolhapuri Chappals", "kolhapuri", "tan", "brown", "leather",
     ["festive", "daily wear"], 999, 1299,
     ["kolhapuri", "leather", "men", "handcrafted", "tan"],
     "Handcrafted men's Kolhapuri chappals in genuine tan leather with a braided toe strap. "
     "They soften with wear. Pair with kurtas or veshti for festive days.", 1.0),
    ("FTW-003", "Women's Embroidered Juttis, maroon and gold", "jutti", "maroon", "red", "velvet",
     ["diwali", "wedding", "festive"], 1299, 1599,
     ["jutti", "punjabi jutti", "embroidered", "women", "maroon", "velvet"],
     "Women's maroon velvet juttis with gold thread and bead embroidery and a padded footbed. "
     "A perfect match for silk sarees and Anarkalis. Comfortable enough to dance in at Diwali parties.", 1.15),
    ("FTW-004", "Men's Black Embroidered Mojaris", "mojari", "black", "black", "faux leather",
     ["wedding", "reception"], 1499, 1799,
     ["mojari", "men", "embroidered", "black", "wedding"],
     "Men's black mojaris with tonal thread embroidery and a slightly pointed toe. They finish off a "
     "sherwani or bandhgala neatly. Made for weddings and receptions.", 0.75),
    ("FTW-005", "Women's Silver Kundan Block-Heel Sandals", "sandals", "silver", "silver", "faux leather",
     ["party", "wedding", "reception"], 1799, 2199,
     ["block heel", "kundan", "silver", "women", "party"],
     "Women's silver block-heel sandals with kundan-studded straps and an ankle buckle. Stable, sparkly and "
     "easy to walk in. Great for receptions and Diwali parties.", 0.8),
    ("FTW-006", "Men's Cream Nagra Juttis", "jutti", "cream", "white", "faux leather",
     ["wedding", "festive", "eid"], 1199, 1499,
     ["nagra", "jutti", "men", "cream", "embroidered"],
     "Men's cream nagra juttis with a curled toe and fine thread embroidery. Light and comfortable. "
     "They complement ivory and pastel kurtas for Eid and weddings.", 0.75),
    ("FTW-007", "Women's Pink Kolhapuri Flats", "kolhapuri", "pink", "pink", "leather",
     ["daily wear", "festive"], 849, 1099,
     ["kolhapuri", "flats", "pink", "women", "leather"],
     "Women's pink leather Kolhapuri flats with a woven upper and soft footbed. Easy everyday ethnic "
     "footwear. Pairs well with cotton kurtas and sarees.", 0.9),
    ("FTW-008", "Women's Mirror-Work Juttis, multicolour", "jutti", "multicolour", "multi", "fabric",
     ["navratri", "festive", "party"], 999, 1299,
     ["jutti", "mirror work", "multicolour", "women", "navratri"],
     "Women's multicolour juttis with mirror work and bright thread embroidery. Fun, festive and comfortable. "
     "Perfect for garba nights and Navratri celebrations.", 0.85),
    ("FTW-009", "Men's Brown Leather Ethnic Sandals", "sandals", "brown", "brown", "leather",
     ["festive", "daily wear"], 1599, 1999,
     ["sandals", "leather", "men", "brown", "cushioned"],
     "Men's brown leather sandals with crossover straps and a cushioned sole. Smart enough for festivals and "
     "sturdy for daily wear. Pair with kurtas or veshtis.", 0.8),
    ("FTW-010", "Women's Gold Wedge Sandals", "sandals", "gold", "gold", "faux leather",
     ["wedding", "party", "diwali"], 2499, 2999,
     ["wedge", "gold", "women", "comfort heel", "party"],
     "Women's gold wedge sandals with embellished straps and a comfort wedge heel. Extra height without the "
     "wobble. Ideal for weddings and long Diwali evenings.", 0.65),
    ("FTW-011", "Women's Blue Embroidered Juttis", "jutti", "blue", "blue", "velvet",
     ["festive", "wedding"], 1099, 1399,
     ["jutti", "embroidered", "blue", "women", "velvet"],
     "Women's royal blue velvet juttis with silver thread embroidery and a padded insole. A striking match "
     "for blue and ivory outfits. Comfortable for festive days.", 0.75),
    ("FTW-012", "Women's Tan Kolhapuri Chappals", "kolhapuri", "tan", "brown", "leather",
     ["daily wear", "festive"], 699, 899,
     ["kolhapuri", "women", "tan", "leather", "everyday"],
     "Women's tan leather Kolhapuri chappals with a classic toe loop and handcrafted braid detail. "
     "Durable and easy to wear. An everyday ethnic essential.", 0.95),
]

_CAT_BY_PREFIX = {c["prefix"]: c for c in CATEGORIES}


def _image_alt(name: str, category: str, color: str, material: str) -> str:
    kind = {"sarees": "folded saree", "kurta_sets": "kurta set", "mens_ethnic": "men's ethnic wear",
            "home_decor": "festive decor item", "gifting": "festive gift", "footwear": "pair of footwear"}[category]
    return f"Studio photo of the {name} ({color} {material}), a {kind} on a plain off-white background"


def _build_products() -> list[dict]:
    out = []
    for (sku, name, sub, color, family, material, occasion, price, mrp, tags, desc, pop) in _P:
        cat = _CAT_BY_PREFIX[sku[:3]]
        assert cat["prefix"] == sku[:3]
        out.append({
            "sku": sku, "name": name, "category": cat["category"], "subcategory": sub,
            "color": color, "color_family": family, "material": material,
            "occasion": list(occasion), "sizes": list(cat["sizes"]),
            "price_inr": int(price), "mrp_inr": int(mrp), "description": desc,
            "image_url": f"/products/{sku}.webp",
            "image_alt": _image_alt(name, cat["category"], color, material),
            "tags": list(tags), "popularity": float(pop),
        })
    return out


PRODUCTS = _build_products()
PRODUCT_BY_SKU = {p["sku"]: p for p in PRODUCTS}

# Fields written to Firestore `products` (contracts §2) - generator-only fields excluded.
PRODUCT_FIELDS = ["sku", "name", "category", "subcategory", "color", "color_family", "material", "occasion",
                  "sizes", "price_inr", "mrp_inr", "description", "image_url", "image_alt", "tags"]
STORE_FIELDS = ["store_id", "name", "city", "type", "languages", "lat", "lng"]

PRICE_RANGES = {"sarees": (1499, 14999), "kurta_sets": (999, 4499), "mens_ethnic": (899, 5999),
                "home_decor": (199, 2999), "gifting": (349, 2499), "footwear": (699, 2499)}


def validate() -> None:
    assert len(STORES) == 7
    assert len(PRODUCTS) == 72, len(PRODUCTS)
    assert len({p["sku"] for p in PRODUCTS}) == 72
    for c in CATEGORIES:
        skus = sorted(p["sku"] for p in PRODUCTS if p["category"] == c["category"])
        assert skus == [f"{c['prefix']}-{i:03d}" for i in range(1, 13)], skus
    for p in PRODUCTS:
        lo, hi = PRICE_RANGES[p["category"]]
        assert lo <= p["price_inr"] <= hi, (p["sku"], p["price_inr"])
        assert p["mrp_inr"] >= p["price_inr"], p["sku"]
        assert isinstance(p["price_inr"], int) and isinstance(p["mrp_inr"], int)
        n_sent = p["description"].count(". ") + 1
        assert 2 <= n_sent <= 3, (p["sku"], n_sent)
    h = PRODUCT_BY_SKU["SAR-001"]
    assert h["name"] == "Maroon Kanchipuram Silk Saree, gold zari border"
    assert (h["category"], h["color"], h["material"], h["price_inr"], h["mrp_inr"]) == \
        ("sarees", "maroon", "silk", 4799, 5999)
    m = PRODUCT_BY_SKU["MEN-004"]
    assert (m["name"], m["category"], m["color"]) == ("Royal Blue Silk-Blend Kurta", "mens_ethnic", "blue")
    assert "brass" in PRODUCT_BY_SKU["DEC-002"]["name"].lower() and "diya" in PRODUCT_BY_SKU["DEC-002"]["name"].lower()
    assert "jutti" in PRODUCT_BY_SKU["FTW-003"]["name"].lower() and "women" in PRODUCT_BY_SKU["FTW-003"]["name"].lower()


validate()

if __name__ == "__main__":
    for p in PRODUCTS:
        print(f"{p['sku']}  ₹{p['price_inr']:>6,} / ₹{p['mrp_inr']:>6,}  {p['color']:<12} {p['name']}")
    print(f"{len(PRODUCTS)} products, {len(STORES)} stores: OK")
