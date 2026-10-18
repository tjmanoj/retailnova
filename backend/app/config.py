"""Static configuration and reference data for the RetailNova API."""
from __future__ import annotations

import os
from datetime import date, timedelta


# Gemini runs on Agent Platform via the global endpoint (no API keys). Set defaults
# before any google-genai / ADK client is created.
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "retailnova-ai")


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


VERSION = os.getenv("APP_VERSION", "1.1.0")
PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "retailnova-ai")
BQ_DATASET = os.getenv("BQ_DATASET", "retailnova")
BQ_LOCATION = os.getenv("REGION", "asia-south1")

# Demo clock (contracts: header)
DEMO_TODAY = "2026-10-18"
DIWALI_DATE = "2026-11-08"
DAYS_TO_DIWALI = 21
TODAY = date.fromisoformat(DEMO_TODAY)


def day_offset(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


# Models (contracts §6)
MODEL_AGENT = os.getenv("MODEL_AGENT", "gemini-3.6-flash")
MODEL_LITE = os.getenv("MODEL_LITE", "gemini-3.5-flash-lite")
MODEL_EMBED = os.getenv("MODEL_EMBED", "gemini-embedding-2")
EMBED_DIM = 768

# Seconds to wait for the first streamed chunk from the primary model before
# hedging to the fallback model. Flash latency on the global endpoint varies a lot.
PRIMARY_FIRST_CHUNK_TIMEOUT_S = float(os.getenv("PRIMARY_FIRST_CHUNK_TIMEOUT_S", "7"))
PLANNER_TIMEOUT_S = float(os.getenv("PLANNER_TIMEOUT_S", "12"))
PLANNER_TOTAL_TIMEOUT_S = float(os.getenv("PLANNER_TOTAL_TIMEOUT_S", "16"))
EXTRACTOR_WAIT_S = float(os.getenv("EXTRACTOR_WAIT_S", "5"))
CHAT_TURN_TIMEOUT_S = float(os.getenv("CHAT_TURN_TIMEOUT_S", "35"))

ENABLE_TRENDS = _env_bool("ENABLE_TRENDS", True)
ENABLE_VOICE = _env_bool("ENABLE_VOICE", True)
ENABLE_STORE_ASSIST = _env_bool("ENABLE_STORE_ASSIST", True)
GUIDED_DEMO = _env_bool("GUIDED_DEMO", True)
WARM_ON_STARTUP = _env_bool("WARM_ON_STARTUP", True)
ALLOWED_ORIGINS = [o for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o]

DEFAULT_STORE = "CHN-TNG"

# contracts §1.1 (lat/lng are approximate and only used for "nearest store")
STORES: dict[str, dict] = {
    "CHN-TNG": {"store_id": "CHN-TNG", "name": "T. Nagar", "city": "Chennai", "type": "store", "languages": ["ta", "en"], "lat": 13.0418, "lng": 80.2341},
    "CHN-ANN": {"store_id": "CHN-ANN", "name": "Anna Nagar", "city": "Chennai", "type": "store", "languages": ["ta", "en"], "lat": 13.0850, "lng": 80.2101},
    "BLR-JAY": {"store_id": "BLR-JAY", "name": "Jayanagar", "city": "Bengaluru", "type": "store", "languages": ["kn", "en", "hi"], "lat": 12.9250, "lng": 77.5938},
    "BLR-IND": {"store_id": "BLR-IND", "name": "Indiranagar", "city": "Bengaluru", "type": "store", "languages": ["kn", "en", "hi"], "lat": 12.9784, "lng": 77.6408},
    "CBE-RSP": {"store_id": "CBE-RSP", "name": "RS Puram", "city": "Coimbatore", "type": "store", "languages": ["ta", "en"], "lat": 11.0089, "lng": 76.9504},
    "HYD-BNJ": {"store_id": "HYD-BNJ", "name": "Banjara Hills", "city": "Hyderabad", "type": "store", "languages": ["te", "hi", "en"], "lat": 17.4156, "lng": 78.4347},
    "ONLINE": {"store_id": "ONLINE", "name": "Online store", "city": None, "type": "online", "languages": ["en", "hi", "ta"], "lat": None, "lng": None},
}
STORE_ORDER = list(STORES.keys())


def store_name(store_id: str | None) -> str:
    if not store_id:
        return ""
    s = STORES.get(store_id)
    return s["name"] if s else store_id


# contracts §1.2
CATEGORIES: list[dict] = [
    {"category": "sarees", "label": "Sarees", "prefix": "SAR", "sizes": ["FREE"]},
    {"category": "kurta_sets", "label": "Women's Kurta Sets", "prefix": "KUR", "sizes": ["S", "M", "L", "XL"]},
    {"category": "mens_ethnic", "label": "Men's Ethnic", "prefix": "MEN", "sizes": ["S", "M", "L", "XL", "XXL"]},
    {"category": "home_decor", "label": "Festive Home Decor", "prefix": "DEC", "sizes": ["FREE"]},
    {"category": "gifting", "label": "Festive Gifting", "prefix": "GFT", "sizes": ["FREE"]},
    {"category": "footwear", "label": "Ethnic Footwear", "prefix": "FTW", "sizes": ["6", "7", "8", "9", "10"]},
]
CATEGORY_IDS = [c["category"] for c in CATEGORIES]
CATEGORY_LABEL = {c["category"]: c["label"] for c in CATEGORIES}
PREFIX_TO_CATEGORY = {c["prefix"]: c["category"] for c in CATEGORIES}

# Supplier lead times in days, used for reorder ETAs (not in the data model;
# documented as an additive assumption in contracts).
SUPPLIER_LEAD_DAYS = {
    "sarees": 10,
    "kurta_sets": 7,
    "mens_ethnic": 7,
    "home_decor": 5,
    "gifting": 4,
    "footwear": 8,
}
TRANSFER_DAYS = 2

SAMPLE_PROMPTS = {
    "shopper": [
        "Diwali ke liye maroon silk saree chahiye, 5000 tak, T-Nagar se pickup",
        "Do you have a royal blue kurta in size L?",
        "Gift ideas under ₹1000 for Diwali",
        "Kanchipuram pattu pudavai irukka? Budget 6000",
    ],
    "manager": [
        "Why are we losing saree sales at T. Nagar this week?",
        "Generate my Diwali action plan for sarees",
        "Which stores have surplus I can transfer?",
    ],
}

# Limits (contracts §5)
MAX_MESSAGE_CHARS = 1000
MAX_IMAGE_BYTES = int(1.5 * 1024 * 1024)
CHAT_RATE = (20, 600)  # 20 requests per 10 minutes per session
PLAN_RATE = (6, 600)
