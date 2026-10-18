"""Deterministic synthetic data generator for RetailNova (fictional retailer Nova Bazaar).

Everything here is SIMULATED. The point of the simulation is that TRUE demand is known, so we can show that
stock-outs censor sales data and that captured "unmet demand" signals recover part of what was lost.

Pipeline (SEED = 2026, fully reproducible):
  1. true demand per store x SKU x day  = base x weekday x seasons x festivals x trend x weather x footfall, Poisson
  2. inventory simulation (SKU level): weekly Monday review, order-up-to level from TRAILING 4-WEEK SALES,
     7-day supplier lead time. sold = min(demand, stock), lost = demand - sold. Because orders follow censored
     sales, stock-outs shrink sales, which shrink the next order (the feedback loop), especially on festive ramps.
  3. captured unmet demand: each lost unit is captured as a conversation signal with probability 0.35
     (common random numbers, so captures at other rates are nested: see `captured_unmet`).
  4. 200 synthetic customers, inventory snapshot for 2026-10-18 (size level) with the hero gaps of
     docs/contracts.md §1.3, and individual `demand_signals` docs for the last 30 days.

Outputs (data/out/, gitignored): stores, products, sales_daily, eval_ground_truth, signals_daily, forecast_input,
inventory, customers (.parquet) and demand_signals.json. Prints a reproducibility hash.

Run from the repo root:  .venv/bin/python data/generate.py
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# data/calendar.py would shadow the stdlib `calendar` module if data/ were on sys.path.
_HERE = _Path(__file__).resolve().parent
_sys.path[:] = [p for p in _sys.path if _Path(p or ".").resolve() != _HERE]
_sys.path.insert(0, str(_HERE.parent))

import datetime as dt  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from data import calendar as cal  # noqa: E402
from data.catalog_spec import (CATEGORIES, CATEGORY_BY_ID, PRODUCT_BY_SKU, PRODUCT_FIELDS, PRODUCTS, SEED,  # noqa: E402
                               SIZE_CURVES, STORE_BY_ID, STORE_FIELDS, STORES)

OUT = _HERE / "out"
START = pd.Timestamp("2024-10-01")
END = pd.Timestamp("2026-10-17")           # last day of history
DEMO_TODAY = pd.Timestamp("2026-10-18")
DATES = pd.date_range(START, END, freq="D")
T = len(DATES)
CAPTURE_RATE = 0.35
LEAD_DAYS = 7
REVIEW_DAYS = 7
SAFETY = 1.30
PREBUILD = 0.5            # planners pre-build only half of the calendar's expected festive uplift
SIGNAL_WINDOW_DAYS = 30
SNAPSHOT_UPDATED_AT = "2026-10-18T03:30:00Z"   # 09:00 IST on demo day

STORE_IDS = [s["store_id"] for s in STORES]
SKUS = [p["sku"] for p in PRODUCTS]
NS, NK = len(STORE_IDS), len(SKUS)
SERIES = [(s, k) for s in STORE_IDS for k in SKUS]      # series index = s_i * NK + k_i
N = len(SERIES)

# Store x category affinity (regional tastes; online over-indexes on gifting and decor).
STORE_CAT_AFFINITY = {
    "CHN-TNG": dict(sarees=1.25, kurta_sets=0.95, mens_ethnic=1.0, home_decor=1.0, gifting=0.95, footwear=0.95),
    "CHN-ANN": dict(sarees=1.15, kurta_sets=1.0, mens_ethnic=1.0, home_decor=1.0, gifting=1.0, footwear=1.0),
    "BLR-JAY": dict(sarees=1.05, kurta_sets=1.1, mens_ethnic=1.0, home_decor=1.05, gifting=1.0, footwear=1.0),
    "BLR-IND": dict(sarees=0.85, kurta_sets=1.2, mens_ethnic=1.05, home_decor=1.0, gifting=1.05, footwear=1.1),
    "CBE-RSP": dict(sarees=1.2, kurta_sets=0.95, mens_ethnic=1.0, home_decor=1.0, gifting=0.9, footwear=0.9),
    "HYD-BNJ": dict(sarees=1.0, kurta_sets=1.1, mens_ethnic=1.15, home_decor=0.95, gifting=1.0, footwear=1.05),
    "ONLINE": dict(sarees=1.0, kurta_sets=1.05, mens_ethnic=0.95, home_decor=1.2, gifting=1.3, footwear=1.1),
}
ANNUAL_GROWTH = 1.10

LANG_MIX = {
    "CHN-TNG": {"ta": 0.45, "en": 0.47, "hi": 0.08}, "CHN-ANN": {"ta": 0.40, "en": 0.52, "hi": 0.08},
    "CBE-RSP": {"ta": 0.55, "en": 0.40, "hi": 0.05}, "BLR-JAY": {"en": 0.68, "hi": 0.27, "ta": 0.05},
    "BLR-IND": {"en": 0.75, "hi": 0.22, "ta": 0.03}, "HYD-BNJ": {"en": 0.52, "hi": 0.46, "ta": 0.02},
    "ONLINE": {"en": 0.60, "hi": 0.25, "ta": 0.15},
}


def rng_for(*keys: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([SEED, *keys]))


def didx(d: str | pd.Timestamp) -> int:
    return int((pd.Timestamp(d) - START).days)


# ------------------------------------------------------------------------------------------------
# 1. True demand
# ------------------------------------------------------------------------------------------------
def base_rates() -> np.ndarray:
    """Expected units/day per series before calendar effects."""
    med = {c["category"]: float(np.median([p["price_inr"] for p in PRODUCTS if p["category"] == c["category"]]))
           for c in CATEGORIES}
    b = np.zeros(N)
    for i, (s, k) in enumerate(SERIES):
        p, st = PRODUCT_BY_SKU[k], STORE_BY_ID[s]
        price_f = (p["price_inr"] / med[p["category"]]) ** -0.30
        b[i] = (st["scale"] * CATEGORY_BY_ID[p["category"]]["base"] * p["popularity"] * price_f
                * STORE_CAT_AFFINITY[s][p["category"]])
    return b


EXT_DATES = pd.date_range(START, END + pd.Timedelta(days=21), freq="D")   # planner looks ahead past END


def calendar_multipliers() -> tuple[np.ndarray, np.ndarray]:
    """(N, T) demand multiplier: weekday x seasons x festivals x trend x weather x footfall noise, and the
    (N, T+21) planner calendar (seasons x festivals only: what a merchandiser knows in advance)."""
    r_weather, r_foot = rng_for(1), rng_for(2)
    years = ((DATES - START).days.to_numpy() / 365.25)
    trend = ANNUAL_GROWTH ** years
    # heavy-rain days per region (shared by stores in the same city region)
    rain = {}
    months = DATES.month.to_numpy()
    u = r_weather.random((len(cal.REGIONS), T))
    for ri, reg in enumerate(cal.REGIONS):
        probs = np.array([cal.RAIN_DAY_PROB.get(reg, {}).get(m, 0.0) for m in months])
        rain[reg] = u[ri] < probs
    # online sees a small lift on days it rains in the big cities
    city_rain = np.mean([rain[r] for r in ("tn", "ka", "ts")], axis=0)
    foot = np.exp(r_foot.normal(0, 0.12, (NS, T)) - 0.12 ** 2 / 2)
    M = np.zeros((N, T))
    P = np.zeros((N, len(EXT_DATES)))
    cache: dict = {}
    pcache: dict = {}
    for i, (s, k) in enumerate(SERIES):
        st, p = STORE_BY_ID[s], PRODUCT_BY_SKU[k]
        key = (st["region"], st["type"], p["category"], tuple(p["occasion"]))
        if key not in cache:
            pcache[key] = (cal.season_factor(EXT_DATES, p["category"], st["region"], st["type"], p["occasion"])
                           * cal.festival_lift(EXT_DATES, p["category"], st["region"], p["occasion"]))
            cache[key] = cal.weekday_factor(DATES, st["type"]) * pcache[key][:T]
        P[i] = pcache[key]
        if st["type"] == "online":
            weather = 1 + (cal.RAIN_FACTOR["online"] - 1) * city_rain
        else:
            weather = np.where(rain[st["region"]], cal.RAIN_FACTOR["store"], 1.0)
        M[i] = cache[key] * trend * weather * foot[STORE_IDS.index(s)]
    return M, P


HERO = ("CHN-TNG", "SAR-001")
# Maroon is this season's colour at T. Nagar: the hero SKU's demand climbs through October 2026.
HERO_TREND_FROM, HERO_TREND_TO, HERO_TREND_PEAK = "2026-09-28", "2026-10-17", 2.0
# Last 7 days of hero demand (Oct 11-17) and the captured unmet signals on those days (rising day by day).
HERO_LAST7_DEMAND = [8, 9, 10, 11, 12, 13, 15]
HERO_LAST7_CAPTURED_TARGET = [2, 3, 4, 4, 5, 6, 7]     # all CHN-TNG maroon-saree unmet signals per day


def true_demand() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    b = base_rates()
    M, P = calendar_multipliers()
    lam = b[:, None] * M
    i = SERIES.index(HERO)
    a, z = didx(HERO_TREND_FROM), didx(HERO_TREND_TO)
    lam[i, a:z + 1] *= np.linspace(1.0, HERO_TREND_PEAK, z - a + 1)
    # Other maroon sarees at T. Nagar get a milder lift from the same trend.
    for k in ("SAR-005", "SAR-008"):
        j = SERIES.index(("CHN-TNG", k))
        lam[j, a:z + 1] *= np.linspace(1.0, 1.3, z - a + 1)
    D = rng_for(3).poisson(lam).astype(np.int64)
    D[i, T - 7:] = HERO_LAST7_DEMAND
    return D, b, P


# ------------------------------------------------------------------------------------------------
# 2. Inventory simulation (SKU level)
# ------------------------------------------------------------------------------------------------
# Planted end-of-history states (contracts §1.3): force the opening stock on a date so that the series
# ends at the target, and freeze replenishment for that series from `freeze`.
OVERRIDES = {
    # stocked out since ~Oct 10: opening stock on Oct 5 covers Oct 5-9 plus 2 units, then nothing arrives
    ("CHN-TNG", "SAR-001"): dict(force_date="2026-10-05", end_target=None, cover_until="2026-10-09", extra=2,
                                 freeze="2026-09-28"),
    ("CBE-RSP", "SAR-001"): dict(force_date="2026-10-12", end_target=14, freeze="2026-10-05"),
    # the same maroon trend has nearly cleared Anna Nagar too, so the transfer source is RS Puram
    ("CHN-ANN", "SAR-001"): dict(force_date="2026-10-12", end_target=2, freeze="2026-10-05"),
    ("BLR-JAY", "DEC-002"): dict(force_date="2026-10-12", end_target=3, freeze="2026-10-05"),
    ("CHN-TNG", "MEN-004"): dict(force_date="2026-10-12", end_target=11, freeze=None),
    ("HYD-BNJ", "FTW-003"): dict(force_date="2026-10-12", end_target=9, freeze=None),
}


def simulate_inventory(D: np.ndarray, b: np.ndarray, P: np.ndarray) -> dict:
    """Weekly order-up-to replenishment driven by trailing 4-week (censored) sales.

    S = avg_daily_sales(last 28 days) x (review + lead days) x SAFETY x festive_prebuild + min_stock, where
    festive_prebuild = 1 + PREBUILD x (calendar intensity of the coming cover window / of the last 28 days - 1).
    """
    min_stock = np.array([3 if s == "ONLINE" else 2 for s, _ in SERIES])
    est = b * 1.0                                         # planner's initial daily-rate estimate
    on_hand = np.ceil(est * (REVIEW_DAYS + LEAD_DAYS) * SAFETY).astype(np.int64) + min_stock
    arrivals = np.zeros((T + LEAD_DAYS + 1, N), np.int64)
    stock_open = np.zeros((N, T), np.int64)
    sold = np.zeros((N, T), np.int64)
    ov_idx = {SERIES.index(k): v for k, v in OVERRIDES.items()}
    force_at: dict[int, list] = {}
    frozen_from = np.full(N, T + 99)
    for i, o in ov_idx.items():
        t0 = didx(o["force_date"])
        if o["end_target"] is not None:
            val = o["end_target"] + int(D[i, t0:].sum())
        else:
            val = int(D[i, t0:didx(o["cover_until"]) + 1].sum()) + o["extra"]
        force_at.setdefault(t0, []).append((i, val))
        if o["freeze"]:
            frozen_from[i] = didx(o["freeze"])
    mondays = DATES.dayofweek.to_numpy() == 0
    for t in range(T):
        frozen = frozen_from <= t
        arr = arrivals[t].copy()
        arr[frozen] = 0                                   # supplier backlog: open POs not delivered
        on_hand += arr
        for i, val in force_at.get(t, []):
            on_hand[i] = val
        if mondays[t]:
            lo = max(0, t - 28)
            hist = sold[:, lo:t].sum(axis=1)
            avg = (hist + est * (28 - (t - lo))) / 28.0   # blend in the initial estimate during warm-up
            ahead = P[:, t + LEAD_DAYS:t + LEAD_DAYS + REVIEW_DAYS].mean(axis=1)
            behind = P[:, lo:t].mean(axis=1) if t > lo else P[:, 0]
            prebuild = 1 + PREBUILD * (ahead / behind - 1)
            S = np.ceil(avg * (REVIEW_DAYS + LEAD_DAYS) * SAFETY * prebuild).astype(np.int64) + min_stock
            on_order = arrivals[t + 1:t + LEAD_DAYS + 1].sum(axis=0)
            q = np.maximum(0, S - on_hand - on_order)
            q[frozen] = 0
            arrivals[t + LEAD_DAYS] += q
        stock_open[:, t] = on_hand
        s_t = np.minimum(D[:, t], on_hand)
        sold[:, t] = s_t
        on_hand -= s_t
    pipeline = arrivals[T:].copy()                         # orders arriving after the last history day
    pipeline[:, frozen_from <= T] = 0
    return dict(stock_open=stock_open, sold=sold, lost=D - sold, end_on_hand=on_hand.copy(),
                pipeline=pipeline)


# ------------------------------------------------------------------------------------------------
# 3. Captured unmet demand
# ------------------------------------------------------------------------------------------------
def captured_unmet(lost: np.ndarray, rate: float) -> np.ndarray:
    """Each lost unit is captured as a conversation signal with probability `rate`.

    `lost` is any int array (e.g. (N, T) or the flat `lost_units` column of eval_ground_truth sorted by
    store_id, sku, date). Common random numbers: every lost unit gets one fixed uniform draw, so captures at a
    higher rate always contain the captures at a lower rate. Same input + same rate -> same output.
    """
    flat = np.asarray(lost, dtype=np.int64).ravel()
    idx = np.repeat(np.arange(flat.size), flat)
    u = rng_for(4).random(idx.size)
    out = np.bincount(idx[u < rate], minlength=flat.size)
    return out.reshape(np.shape(lost))


def captured_unmet_frame(gt: pd.DataFrame, rate: float) -> pd.DataFrame:
    """Regenerate captured unmet units at another capture rate from eval_ground_truth (backtest sensitivity).

    Returns date, store_id, sku, category, unmet_units for the catalog (stock-related) signals. The 0.35 result
    equals signals_daily before the planted demo-day hero adjustments (which only touch 2026-10).
    """
    g = gt.sort_values(["store_id", "sku", "date"]).reset_index(drop=True)
    expected = pd.MultiIndex.from_product([STORE_IDS, SKUS])
    assert len(g) == N * T, "eval_ground_truth must contain the full store x sku x date grid"
    order = pd.MultiIndex.from_arrays([g["store_id"], g["sku"]])[::T]
    assert (order == expected.sort_values()).all()
    # map sorted (store, sku) order back to SERIES order used at generation time
    lost_sorted = g["lost_units"].to_numpy().reshape(N, T)
    pos = {key: n for n, key in enumerate(order)}
    lost = np.stack([lost_sorted[pos[key]] for key in SERIES])
    cap = captured_unmet(lost, rate)
    out = g[["date", "store_id", "sku", "category"]].copy()
    cap_sorted = np.stack([cap[SERIES.index(key)] for key in order])
    out["unmet_units"] = cap_sorted.ravel()
    return out


def scale_unmet(unmet, rate: float):
    """Estimated lost units from captured unmet units: round half up of unmet / capture rate."""
    return np.floor(np.asarray(unmet, dtype=float) / rate + 0.5).astype(np.int64)


def noise_asks(rate: float) -> np.ndarray:
    """Unmet asks not tied to stock (not carried / price too high), store x category x day, captured at `rate`."""
    lam = np.zeros((NS, len(CATEGORIES), T))
    for si, s in enumerate(STORE_IDS):
        st = STORE_BY_ID[s]
        for ci, c in enumerate(CATEGORIES):
            lam[si, ci] = 0.10 * st["scale"] * cal.festival_lift(DATES, c["category"], st["region"], [])
    latent = rng_for(5).poisson(lam)
    return captured_unmet(latent, rate) if rate > 0 else np.zeros_like(latent)


# ------------------------------------------------------------------------------------------------
# 4a. Customers
# ------------------------------------------------------------------------------------------------
NAMES = {
    "tn": ["Priya", "Lakshmi", "Karthik", "Divya", "Arun", "Meena", "Vignesh", "Deepa", "Senthil", "Kavya",
           "Harini", "Saravanan", "Anitha", "Bharath", "Revathi", "Gokul", "Nithya", "Surya", "Janani", "Prakash",
           "Sangeetha", "Ramesh", "Aarthi", "Dinesh", "Yamini"],
    "kongu": ["Gowri", "Manikandan", "Sowmya", "Kumaresan", "Abirami", "Dhanush", "Keerthana", "Murugan",
              "Pavithra", "Sathish"],
    "ka": ["Ananya", "Rakesh", "Shreya", "Kiran", "Pooja", "Sneha", "Varun", "Nikhil", "Aishwarya", "Manjunath",
           "Bhavana", "Chetan", "Rashmi", "Suhas", "Tejaswini", "Pradeep", "Spoorthi", "Girish"],
    "ts": ["Sravani", "Venkat", "Harika", "Sai", "Lavanya", "Ravi", "Keerthi", "Srinivas", "Sana", "Imran",
           "Ayesha", "Mounika", "Naveen", "Swathi", "Farhan", "Bhargavi"],
    "online": ["Neha", "Rohan", "Aditi", "Rahul", "Ishita", "Kabir", "Meera", "Arjun", "Tanvi", "Siddharth",
               "Riya", "Aditya", "Nandini", "Vikram", "Zoya", "Anjali"],
}
ONLINE_CITIES = ["Chennai", "Bengaluru", "Hyderabad", "Coimbatore", "Madurai", "Mysuru", "Pune", "Mumbai"]
CUST_LANGS = {"tn": {"ta": 0.55, "en": 0.40, "hi": 0.05}, "kongu": {"ta": 0.6, "en": 0.4},
              "ka": {"kn": 0.40, "en": 0.45, "hi": 0.15}, "ts": {"te": 0.45, "hi": 0.25, "en": 0.30},
              "online": {"en": 0.55, "hi": 0.30, "ta": 0.15}}


def make_customers() -> pd.DataFrame:
    r = rng_for(6)
    store_w = np.array([0.20, 0.14, 0.15, 0.13, 0.09, 0.10, 0.19])
    families = sorted({p["color_family"] for p in PRODUCTS} - {"multi"})
    rows = []
    for n in range(200):
        s = STORE_IDS[r.choice(NS, p=store_w)]
        reg = STORE_BY_ID[s]["region"]
        name = NAMES[reg][r.integers(len(NAMES[reg]))]
        city = ONLINE_CITIES[r.integers(len(ONLINE_CITIES))] if s == "ONLINE" else STORE_BY_ID[s]["city"]
        langs = CUST_LANGS[reg]
        lang = list(langs)[r.choice(len(langs), p=np.array(list(langs.values())) / sum(langs.values()))]
        cats = [c["category"] for c in CATEGORIES]
        pc = sorted(r.choice(cats, size=int(r.integers(1, 4)), replace=False).tolist())
        cols = sorted(r.choice(families, size=int(r.integers(1, 4)), replace=False).tolist())
        budget = int(r.choice([1500, 2500, 3000, 5000, 8000, 15000], p=[0.15, 0.22, 0.2, 0.23, 0.12, 0.08]))
        rows.append({"customer_id": f"C{n + 1:04d}", "first_name": name, "city": city, "home_store_id": s,
                     "language": lang,
                     "preferences": {"categories": pc, "colors": cols, "budget_max_inr": budget}})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------
# 4b. Inventory snapshot (size level) for 2026-10-18
# ------------------------------------------------------------------------------------------------
def _sizes_for(p: dict) -> dict[str, float]:
    return SIZE_CURVES["FREE"] if p["sizes"] == ["FREE"] else SIZE_CURVES[p["category"]]


# Demo transfer sources (lead request): reorder points lowered so the planner sees real surplus. on_hand unchanged.
#   CBE-RSP SAR-001 (hero source, 14 on hand, ~1.5 units/day locally): computed 11 -> 2
#   HYD-BNJ SAR-005 (wine maroon soft silk, 25 on hand, ~17 days of cover): computed 11 -> 4
REORDER_POINT_OVERRIDES = {"CBE-RSP__SAR-001__FREE": 2, "HYD-BNJ__SAR-005__FREE": 4}


def make_snapshot(sim: dict) -> pd.DataFrame:
    r = rng_for(7)
    sold = sim["sold"]
    rows = []
    for i, (s, k) in enumerate(SERIES):
        p = PRODUCT_BY_SKU[k]
        curve = _sizes_for(p)
        sizes, w = list(curve), np.array(list(curve.values()))
        total = int(sim["end_on_hand"][i])
        inc_total = int(sim["pipeline"][:, i].sum())
        arr_days = np.nonzero(sim["pipeline"][:, i])[0]
        eta = (END + pd.Timedelta(days=int(arr_days[0]) + 1)).strftime("%Y-%m-%d") if len(arr_days) else None
        n_sz = len(sizes)
        if total >= n_sz:                                   # merchandisers keep a full size run when they can
            oh = 1 + r.multinomial(total - n_sz, w)
        else:
            oh = r.multinomial(total, w) if total > 0 else np.zeros(n_sz, np.int64)
        inc = r.multinomial(inc_total, w) if inc_total > 0 else np.zeros(len(sizes), np.int64)
        avg = sold[i, T - 28:].mean()
        rp = np.maximum(1, np.ceil(avg * LEAD_DAYS * w)).astype(int)
        oh, inc = oh.copy(), inc.copy()
        # ---- planted hero sizes (contracts §1.3) ----
        if (s, k) == ("CHN-TNG", "MEN-004"):
            L = sizes.index("L")
            moved, oh[L] = oh[L], 0
            for tgt in ("M", "XL"):
                oh[sizes.index(tgt)] += moved // 2
            oh[sizes.index("M")] += moved % 2
            for j, sz in enumerate(sizes):           # every other size has at least one piece
                if sz != "L" and oh[j] == 0:
                    donor = int(np.argmax(oh))
                    oh[donor] -= 1
                    oh[j] += 1
            inc[L] = 0
        if (s, k) == ("HYD-BNJ", "FTW-003"):
            j7 = sizes.index("7")
            moved, oh[j7] = oh[j7], 0
            oh[sizes.index("6")] += moved // 2
            oh[sizes.index("8")] += moved - moved // 2
            inc[j7] = 0
        for j, sz in enumerate(sizes):
            rows.append({"store_id": s, "sku": k, "size": sz, "category": p["category"],
                         "on_hand": int(oh[j]), "incoming": int(inc[j]),
                         "incoming_eta": eta if inc[j] > 0 else None,
                         "reorder_point": int(rp[j]), "updated_at": SNAPSHOT_UPDATED_AT})
    df = pd.DataFrame(rows)
    df.insert(0, "doc_id", df["store_id"] + "__" + df["sku"] + "__" + df["size"])
    for doc_id, rp in REORDER_POINT_OVERRIDES.items():
        df.loc[df["doc_id"] == doc_id, "reorder_point"] = rp
    return df


# ------------------------------------------------------------------------------------------------
# 4c. Firestore demand_signals docs (last 30 days)
# ------------------------------------------------------------------------------------------------
NOT_CARRIED = {
    "sarees": [("Pochampally ikat silk saree", {"color": "green", "material": "silk"}),
               ("organza saree in pastel lavender", {"color": "lavender", "material": "organza"}),
               ("Kota doria saree for office", {"color": "white", "material": "cotton"})],
    "kurta_sets": [("kurta set in 3XL size", {"size": "3XL"}),
                   ("co-ord set with jacket", {"color": "beige", "material": "cotton"})],
    "mens_ethnic": [("Pathani suit in olive", {"color": "olive", "material": "cotton"}),
                    ("silk veshti with silver border", {"color": "white", "material": "silk"})],
    "home_decor": [("electric diya string lights", {"material": "plastic"}),
                   ("marble Lakshmi idol", {"material": "marble"})],
    "gifting": [("sugar-free mithai box", {"material": "sweets"}),
                ("personalised name hamper", {"material": "mixed"})],
    "footwear": [("juttis in size 11", {"size": "11"}),
                 ("kids' ethnic sandals", {"size": "kids"})],
}
CHANNELS = {"store": (["store_assist", "chat", "image_search"], [0.55, 0.33, 0.12]),
            "online": (["chat", "image_search"], [0.72, 0.28])}


def _short(name: str) -> str:
    return name.split(",")[0]


def _ts(r: np.random.Generator, day: pd.Timestamp, online: bool) -> str:
    if online:
        mins = int(np.clip(r.normal(19.5 * 60, 190), 7 * 60, 23 * 60 + 30))
    else:
        mins = int(np.clip(r.normal(17.5 * 60, 150), 10 * 60 + 30, 21 * 60 + 30))
    secs = int(r.integers(60))
    ist = day + pd.Timedelta(minutes=mins, seconds=secs)
    return (ist - pd.Timedelta(hours=5, minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _occasion_for(p: dict, day: pd.Timestamp) -> str:
    occ = p["occasion"]
    d = (cal.DIWALI[2026] - day).days
    if "navratri" in occ and day >= pd.Timestamp("2026-10-04"):
        return "navratri"
    if "diwali" in occ and d <= 45:
        return "diwali"
    return occ[0]


def _band(price: int) -> dict:
    return {"min_inr": int(math.floor(price * 0.6 / 100) * 100), "max_inr": int(math.ceil(price * 1.15 / 100) * 100)}


def _alternatives() -> dict[str, list[str]]:
    alts = {}
    for p in PRODUCTS:
        cands = [q for q in PRODUCTS if q["category"] == p["category"] and q["sku"] != p["sku"]]
        cands.sort(key=lambda q: (q["color_family"] != p["color_family"], abs(q["price_inr"] - p["price_inr"])))
        alts[p["sku"]] = [q["sku"] for q in cands[:3]]
    return alts


def make_signal_docs(sim: dict, cap: np.ndarray, pairs: np.ndarray, noise: np.ndarray) -> list[dict]:
    r = rng_for(8)
    alts = _alternatives()
    t0 = T - SIGNAL_WINDOW_DAYS
    docs: list[dict] = []

    def lang(s: str) -> str:
        m = LANG_MIX[s]
        return list(m)[r.choice(len(m), p=np.array(list(m.values())))]

    def channel(s: str) -> str:
        ch, w = CHANNELS["online" if s == "ONLINE" else "store"]
        return ch[r.choice(len(ch), p=w)]

    def base_doc(s, day, cat, sku, outcome, reason, qty, value, intent, summary, attrs, band) -> dict:
        return {"ts": _ts(r, day, s == "ONLINE"), "date": day.strftime("%Y-%m-%d"), "source": "simulated",
                "session_id": None, "store_id": s, "channel": channel(s), "category": cat, "sku": sku,
                "attributes": attrs, "price_band": band, "outcome": outcome, "reason": reason,
                "quantity": int(qty), "est_value_inr": int(value), "intent_strength": round(float(intent), 2),
                "summary": summary[:120], "language": lang(s)}

    for t in range(t0, T):
        day = DATES[t]
        for i, (s, k) in enumerate(SERIES):
            p = PRODUCT_BY_SKU[k]
            store = STORE_BY_ID[s]["name"]
            sizes = list(_sizes_for(p))
            w = np.array(list(_sizes_for(p).values()))
            sized = sizes != ["FREE"]
            n_cap = int(cap[i, t])
            if n_cap:
                n_pair = int(pairs[i, t])
                qtys = [2] * n_pair + [1] * (n_cap - 2 * n_pair)
                for q in qtys:
                    attrs = {"color": p["color"], "material": p["material"], "occasion": _occasion_for(p, day)}
                    reason = "out_of_stock"
                    if sized:
                        attrs["size"] = sizes[r.choice(len(sizes), p=w)]
                        if sim["stock_open"][i, t] > 0 and r.random() < 0.6:
                            reason = "size_unavailable"
                    if reason == "size_unavailable":
                        summ = f"Asked for {_short(p['name'])} in size {attrs['size']}; size unavailable at {store}"
                    else:
                        summ = f"Wanted {_short(p['name'])} for {attrs['occasion']}; out of stock at {store}"
                    docs.append(base_doc(s, day, p["category"], k, "unmet", reason, q, q * p["price_inr"],
                                         r.uniform(0.6, 0.95), summ, attrs,
                                         _band(p["price_inr"]) if r.random() < 0.6 else None))
            # substitutions: some uncaptured lost asks where the shopper took an alternative
            n_sub = int(r.binomial(int(sim["lost"][i, t] - cap[i, t]), 0.15))
            for _ in range(n_sub):
                alt = PRODUCT_BY_SKU[alts[k][r.integers(len(alts[k]))]]
                attrs = {"color": p["color"], "material": p["material"], "occasion": _occasion_for(p, day),
                         "substitute_sku": alt["sku"]}
                if sized:
                    attrs["size"] = sizes[r.choice(len(sizes), p=w)]
                summ = f"Wanted {_short(p['name'])}; chose {_short(alt['name'])} instead"
                docs.append(base_doc(s, day, p["category"], k, "substituted", "out_of_stock", 1, alt["price_inr"],
                                     r.uniform(0.5, 0.85), summ, attrs, None))
            # fulfilled asks: a small sample of assisted sales
            n_ful = int(r.binomial(int(sim["sold"][i, t]), 0.011))
            for _ in range(n_ful):
                attrs = {"color": p["color"], "material": p["material"], "occasion": _occasion_for(p, day)}
                if sized:
                    attrs["size"] = sizes[r.choice(len(sizes), p=w)]
                verb = "reserved" if r.random() < 0.3 else "bought"
                summ = f"Found {_short(p['name'])}" + (f" in size {attrs['size']}" if sized else "") + \
                       f"; {verb} at {store}"
                docs.append(base_doc(s, day, p["category"], k, "fulfilled", None, 1, p["price_inr"],
                                     r.uniform(0.55, 0.95), summ, attrs,
                                     _band(p["price_inr"]) if r.random() < 0.4 else None))
        # asks not tied to stock: not carried / price too high (sku null)
        for si, s in enumerate(STORE_IDS):
            for ci, c in enumerate(CATEGORIES):
                for _ in range(int(noise[si, ci, t])):
                    cat = c["category"]
                    if r.random() < 0.6:
                        what, attrs = NOT_CARRIED[cat][r.integers(len(NOT_CARRIED[cat]))]
                        summ = f"Looked for {what}; not carried"
                        val = int(np.median([p["price_inr"] for p in PRODUCTS if p["category"] == cat]))
                        docs.append(base_doc(s, day, cat, None, "unmet", "not_carried", 1, val,
                                             r.uniform(0.45, 0.8), summ, dict(attrs), None))
                    else:
                        cands = [p for p in PRODUCTS if p["category"] == cat]
                        cands.sort(key=lambda p: -p["price_inr"])
                        p = cands[r.integers(4)]
                        cap_inr = int(p["price_inr"] * 0.55 // 100 * 100)
                        summ = f"Liked {_short(p['name'])} but budget was under Rs {cap_inr:,}"
                        docs.append(base_doc(s, day, cat, None, "unmet", "price_too_high", 1, cap_inr,
                                             r.uniform(0.4, 0.75), summ,
                                             {"color": p["color"], "material": p["material"]},
                                             {"min_inr": int(cap_inr * 0.6 // 100 * 100), "max_inr": cap_inr}))
    docs.sort(key=lambda d: (d["ts"], d["store_id"], d["category"], d["sku"] or "", d["summary"]))
    for n, d in enumerate(docs):
        d["signal_id"] = f"sim_{d['date'].replace('-', '')}_{n:05d}"
    return [{"signal_id": d.pop("signal_id"), **d} for d in docs]


# ------------------------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------------------------
def frame_hash(df: pd.DataFrame) -> str:
    h = hashlib.sha256()
    h.update(",".join(map(str, df.columns)).encode())
    h.update(pd.util.hash_pandas_object(df.astype(str), index=False).to_numpy().tobytes())
    return h.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    D, b, P = true_demand()
    sim = simulate_inventory(D, b, P)
    lost = sim["lost"]

    # captured unmet demand at 35%, then the planted hero trend for the last 7 days
    cap = captured_unmet(lost, CAPTURE_RATE)
    hi = SERIES.index(HERO)
    others = sum(cap[SERIES.index(("CHN-TNG", k))] for k in ("SAR-005", "SAR-008"))
    for j, t in enumerate(range(T - 7, T)):
        cap[hi, t] = int(min(lost[hi, t], max(1, HERO_LAST7_CAPTURED_TARGET[j] - others[t])))
    # some decor/gifting asks are for two units (one signal, quantity 2)
    r_pairs = rng_for(9)
    pairs = np.zeros_like(cap)
    for i, (s, k) in enumerate(SERIES):
        if PRODUCT_BY_SKU[k]["category"] in ("home_decor", "gifting"):
            pairs[i] = r_pairs.binomial(cap[i] // 2, 0.2)
    noise = noise_asks(CAPTURE_RATE)

    # ---------------- tables ----------------
    store_col = np.repeat(np.array([s for s, _ in SERIES]), T)
    sku_col = np.repeat(np.array([k for _, k in SERIES]), T)
    cat_col = np.array([PRODUCT_BY_SKU[k]["category"] for k in sku_col])
    date_col = np.tile(DATES.date, N)
    price = np.repeat(np.array([PRODUCT_BY_SKU[k]["price_inr"] for _, k in SERIES]), T)
    sales = pd.DataFrame({"date": date_col, "store_id": store_col, "sku": sku_col, "category": cat_col,
                          "units_sold": sim["sold"].ravel(), "revenue_inr": sim["sold"].ravel() * price,
                          "stock_open": sim["stock_open"].ravel()})
    gt = pd.DataFrame({"date": date_col, "store_id": store_col, "sku": sku_col, "category": cat_col,
                       "true_demand": D.ravel(), "lost_units": lost.ravel()})
    sig_cat = pd.DataFrame({"date": date_col, "store_id": store_col, "category": cat_col, "sku": sku_col,
                            "unmet_units": cap.ravel(), "signals": (cap - pairs).ravel()})
    sig_cat = sig_cat[sig_cat["unmet_units"] > 0]
    nz = np.argwhere(noise > 0)
    sig_noise = pd.DataFrame({"date": DATES.date[nz[:, 2]], "store_id": np.array(STORE_IDS)[nz[:, 0]],
                              "category": np.array([c["category"] for c in CATEGORIES])[nz[:, 1]],
                              "sku": None, "unmet_units": noise[nz[:, 0], nz[:, 1], nz[:, 2]],
                              "signals": noise[nz[:, 0], nz[:, 1], nz[:, 2]]})
    signals_daily = pd.concat([sig_cat, sig_noise], ignore_index=True)
    signals_daily["source"] = "simulated"
    signals_daily = signals_daily.sort_values(["date", "store_id", "category", "sku"], na_position="last") \
        .reset_index(drop=True)

    # forecast_input: store x category x day. Demand-sensed = estimated true demand = sales + captured stock-related
    # unmet units / capture rate (catalog-SKU signals only). In a real deployment the capture rate is calibrated with
    # store audits; here it is the simulation's 35%.
    fi = sales.groupby(["date", "store_id", "category"], as_index=False)["units_sold"].sum() \
        .rename(columns={"units_sold": "units_sales"})
    um = sig_cat.groupby(["date", "store_id", "category"], as_index=False)["unmet_units"].sum()
    fi = fi.merge(um, on=["date", "store_id", "category"], how="left").fillna({"unmet_units": 0})
    fi["units_demand_sensed"] = (fi["units_sales"] + scale_unmet(fi["unmet_units"], CAPTURE_RATE)).astype("int64")
    fi = fi.drop(columns="unmet_units")

    stores = pd.DataFrame([{k: s[k] for k in STORE_FIELDS} for s in STORES])
    products = pd.DataFrame([{k: p[k] for k in PRODUCT_FIELDS} for p in PRODUCTS])
    customers = make_customers()
    inventory = make_snapshot(sim)
    docs = make_signal_docs(sim, cap, pairs, noise)

    # ---------------- checks ----------------
    inv = inventory.set_index("doc_id")
    assert inv.loc["CHN-TNG__SAR-001__FREE", "on_hand"] == 0
    assert inv.loc["CBE-RSP__SAR-001__FREE", "on_hand"] == 14
    men = inv[(inv.store_id == "CHN-TNG") & (inv.sku == "MEN-004")]
    assert men.loc["CHN-TNG__MEN-004__L", "on_hand"] == 0 and (men.on_hand > 0).sum() >= 3
    assert inv.loc["HYD-BNJ__FTW-003__7", "on_hand"] == 0
    dec = inv.loc["BLR-JAY__DEC-002__FREE"]
    assert dec.on_hand <= 5 and dec.on_hand < dec.reorder_point
    assert inv.loc["CBE-RSP__SAR-001__FREE", "reorder_point"] == 2
    last7 = sorted({d["date"] for d in docs})[-7:]
    hero_daily = [sum(1 for d in docs if d["date"] == day and d["store_id"] == "CHN-TNG" and d["outcome"] == "unmet"
                      and d["category"] == "sarees" and (d["sku"] == "SAR-001"
                                                         or d["attributes"].get("color") == "maroon"))
                  for day in last7]
    assert sum(hero_daily) >= 25, hero_daily
    assert all(a <= b2 for a, b2 in zip(hero_daily, hero_daily[1:])), hero_daily
    # Firestore docs agree with signals_daily over the window
    win = signals_daily[signals_daily["date"] >= DATES[T - SIGNAL_WINDOW_DAYS].date()]
    n_unmet_docs = sum(1 for d in docs if d["outcome"] == "unmet")
    assert n_unmet_docs == int(win["signals"].sum()), (n_unmet_docs, int(win["signals"].sum()))

    # ---------------- write ----------------
    tables = {"stores": stores, "products": products, "sales_daily": sales, "eval_ground_truth": gt,
              "signals_daily": signals_daily, "forecast_input": fi, "inventory": inventory,
              "customers": customers}
    for name, df in tables.items():
        df.to_parquet(OUT / f"{name}.parquet", index=False)
    (OUT / "demand_signals.json").write_text(json.dumps(docs, ensure_ascii=False, indent=0))

    h = hashlib.sha256()
    parts = {}
    for name, df in tables.items():
        parts[name] = frame_hash(df)
        h.update(parts[name].encode())
    parts["demand_signals"] = hashlib.sha256(json.dumps(docs, sort_keys=True).encode()).hexdigest()
    h.update(parts["demand_signals"].encode())
    digest = h.hexdigest()
    (OUT / "manifest.json").write_text(json.dumps({"seed": SEED, "hash": digest, "parts": parts,
                                                   "rows": {k: len(v) for k, v in tables.items()},
                                                   "demand_signals": len(docs)}, indent=2))

    # ---------------- summary ----------------
    tot_d, tot_s = int(D.sum()), int(sim["sold"].sum())
    print(f"history {START.date()} -> {END.date()} ({T} days), {N} store x SKU series")
    print(f"true demand {tot_d:,} units, sold {tot_s:,}, lost {tot_d - tot_s:,} ({(tot_d - tot_s) / tot_d:.1%})")
    print(f"captured unmet (35%): {int(cap.sum()):,} units; signals_daily rows {len(signals_daily):,}")
    print(f"revenue {int(sales.revenue_inr.sum()) / 1e7:,.1f} crore INR")
    for name, df in tables.items():
        print(f"  {name:<18} {len(df):>8,} rows")
    oc = pd.Series([d["outcome"] for d in docs]).value_counts().to_dict()
    print(f"  demand_signals     {len(docs):>8,} docs  {oc}")
    print(f"hero CHN-TNG maroon/SAR-001 unmet signals, last 7 days {last7[0]}..{last7[-1]}: {hero_daily} "
          f"= {sum(hero_daily)}")
    print(f"snapshot stock-outs (SKU level): {(inventory.groupby(['store_id', 'sku']).on_hand.sum() == 0).sum()} "
          f"of {N}; size-level zeros {(inventory.on_hand == 0).sum()} of {len(inventory)}")
    print(f"REPRODUCIBILITY HASH {digest}")


if __name__ == "__main__":
    main()
