"""Indian festive retail calendar, 2024-10-01 -> 2026-12-31 (approximate dates; synthetic demand drivers).

Demand multiplier for a store x SKU on a date =
    weekday(store type) x seasons(category, region, store type) x festival_lift(category, region, SKU occasions)

festival_lift = 1 + sum_f shape_f(date) * (peak_f[category] - 1) * region_f[region] * affinity_f(SKU)

- shape_f rises over a pre-festival ramp (convex, so the last few days dominate), stays high through
  multi-day festivals, dips on the main day (people celebrate rather than shop), then a short tail.
- affinity_f boosts SKUs whose `occasion` list names the festival (e.g. kasavu saree for Onam).
Regions: "tn" (Chennai), "kongu" (Coimbatore), "ka" (Bengaluru), "ts" (Hyderabad), "online".
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# data/calendar.py would shadow the stdlib `calendar` module if data/ were on sys.path: import siblings as
# the `data` package from the repo root instead.
_HERE = _Path(__file__).resolve().parent
_sys.path[:] = [p for p in _sys.path if _Path(p or ".").resolve() != _HERE]
_sys.path.insert(0, str(_HERE.parent))

import datetime as dt

import numpy as np
import pandas as pd

REGIONS = ["tn", "kongu", "ka", "ts", "online"]
CATS = ["sarees", "kurta_sets", "mens_ethnic", "home_decor", "gifting", "footwear"]


def _d(s: str) -> pd.Timestamp:
    return pd.Timestamp(s)


def _cat(sarees, kurta_sets, mens_ethnic, home_decor, gifting, footwear) -> dict:
    return dict(sarees=sarees, kurta_sets=kurta_sets, mens_ethnic=mens_ethnic,
                home_decor=home_decor, gifting=gifting, footwear=footwear)


def _reg(tn, kongu, ka, ts, online) -> dict:
    return dict(tn=tn, kongu=kongu, ka=ka, ts=ts, online=online)


# Festival families: category peaks, regional weights, ramp, main-day factor and the occasion keyword
# that earns a SKU an extra affinity boost.
FAMILIES = {
    "diwali": dict(peak=_cat(3.2, 2.6, 2.6, 6.0, 6.5, 2.2), region=_reg(1.0, 1.0, 1.0, 1.0, 1.0),
                   ramp=14, day_factor=0.35, tail=2, keyword="diwali", affinity=1.35),
    "navratri_dussehra": dict(peak=_cat(1.8, 1.9, 1.4, 1.5, 1.6, 1.5), region=_reg(0.8, 0.8, 1.0, 1.0, 0.9),
                              ramp=7, day_factor=0.6, tail=1, keyword="navratri", affinity=1.4),
    "pongal": dict(peak=_cat(2.2, 1.5, 2.0, 1.8, 1.4, 1.3), region=_reg(1.0, 1.0, 0.3, 0.4, 0.45),
                   ramp=10, day_factor=0.5, tail=1, keyword="pongal", affinity=1.5),
    "onam": dict(peak=_cat(2.0, 1.3, 1.4, 1.4, 1.2, 1.2), region=_reg(0.1, 0.5, 0.15, 0.0, 0.2),
                 ramp=10, day_factor=0.4, tail=1, keyword="onam", affinity=2.5),
    "ugadi": dict(peak=_cat(1.6, 1.4, 1.4, 1.5, 1.3, 1.2), region=_reg(0.15, 0.15, 1.0, 1.0, 0.4),
                  ramp=8, day_factor=0.5, tail=1, keyword="ugadi", affinity=1.2),
    "puthandu": dict(peak=_cat(1.4, 1.2, 1.3, 1.3, 1.2, 1.1), region=_reg(1.0, 1.0, 0.0, 0.0, 0.2),
                     ramp=6, day_factor=0.5, tail=1, keyword="vishu", affinity=1.5),
    "eid_al_fitr": dict(peak=_cat(1.1, 1.6, 1.8, 1.1, 1.5, 1.5), region=_reg(0.5, 0.4, 0.6, 1.0, 0.6),
                        ramp=10, day_factor=0.4, tail=1, keyword="eid", affinity=1.4),
    "christmas": dict(peak=_cat(1.1, 1.15, 1.1, 1.6, 1.8, 1.1), region=_reg(0.7, 0.6, 0.8, 0.6, 0.9),
                      ramp=10, day_factor=0.4, tail=6, keyword="christmas", affinity=1.4),
    "raksha_bandhan": dict(peak=_cat(1.05, 1.1, 1.05, 1.0, 1.7, 1.0), region=_reg(0.3, 0.3, 0.5, 0.6, 0.8),
                           ramp=7, day_factor=0.5, tail=0, keyword="gifting", affinity=1.1),
    "ganesh_chaturthi": dict(peak=_cat(1.2, 1.2, 1.1, 1.5, 1.3, 1.05), region=_reg(0.6, 0.5, 0.9, 0.8, 0.6),
                             ramp=7, day_factor=0.6, tail=1, keyword="ganesh chaturthi", affinity=1.5),
    "varalakshmi_vratham": dict(peak=_cat(1.5, 1.1, 1.0, 1.2, 1.1, 1.0), region=_reg(0.8, 0.7, 0.9, 0.8, 0.3),
                                ramp=6, day_factor=0.6, tail=0, keyword="puja", affinity=1.1),
    "karthigai_deepam": dict(peak=_cat(1.1, 1.0, 1.0, 2.2, 1.1, 1.0), region=_reg(1.0, 1.0, 0.1, 0.1, 0.3),
                             ramp=7, day_factor=0.6, tail=0, keyword="karthigai deepam", affinity=1.6),
}

# Festival occurrences: (family, start, end). Single-day festivals have start == end (the main day).
# Dates are approximate (lunar calendars vary by region) but close to the published 2024-2026 dates.
EVENTS = [
    ("navratri_dussehra", "2024-10-03", "2024-10-12"),
    ("diwali", "2024-11-01", "2024-11-01"),
    ("karthigai_deepam", "2024-12-13", "2024-12-13"),
    ("christmas", "2024-12-25", "2024-12-25"),
    ("pongal", "2025-01-14", "2025-01-15"),
    ("ugadi", "2025-03-30", "2025-03-30"),
    ("eid_al_fitr", "2025-03-31", "2025-03-31"),
    ("puthandu", "2025-04-14", "2025-04-14"),
    ("varalakshmi_vratham", "2025-08-08", "2025-08-08"),
    ("raksha_bandhan", "2025-08-09", "2025-08-09"),
    ("ganesh_chaturthi", "2025-08-27", "2025-08-27"),
    ("onam", "2025-09-05", "2025-09-05"),
    ("navratri_dussehra", "2025-09-22", "2025-10-02"),
    ("diwali", "2025-10-20", "2025-10-20"),
    ("karthigai_deepam", "2025-12-04", "2025-12-04"),
    ("christmas", "2025-12-25", "2025-12-25"),
    ("pongal", "2026-01-14", "2026-01-15"),
    ("ugadi", "2026-03-19", "2026-03-19"),
    ("eid_al_fitr", "2026-03-20", "2026-03-20"),
    ("puthandu", "2026-04-14", "2026-04-14"),
    ("varalakshmi_vratham", "2026-08-21", "2026-08-21"),
    ("onam", "2026-08-26", "2026-08-26"),
    ("raksha_bandhan", "2026-08-28", "2026-08-28"),
    ("ganesh_chaturthi", "2026-09-14", "2026-09-14"),
    ("navratri_dussehra", "2026-10-11", "2026-10-20"),
    ("diwali", "2026-11-08", "2026-11-08"),
    ("karthigai_deepam", "2026-11-24", "2026-11-24"),
    ("christmas", "2026-12-25", "2026-12-25"),
]

DIWALI = {2024: _d("2024-11-01"), 2025: _d("2025-10-20"), 2026: _d("2026-11-08")}

# Wedding seasons (muhurtham-heavy months) and weather windows.
WEDDING_SEASONS = [("11-15", "02-28"), ("04-15", "06-30")]
WEDDING_LIFT = _cat(1.30, 1.15, 1.25, 1.0, 1.15, 1.20)
WEDDING_AFFINITY = 1.25            # extra for SKUs with "wedding"/"bridal" occasions
MONSOON = ("06-01", "09-30")       # south-west monsoon: footfall dip (all four cities)
MONSOON_FACTOR = {"store": 0.86, "online": 0.97}
NE_MONSOON = ("10-15", "12-15")    # north-east monsoon: Chennai and Coimbatore
NE_MONSOON_FACTOR = {"tn": 0.93, "kongu": 0.96}
POST_DIWALI_LULL = (2, 16, 0.80)   # days after Diwali (from, to, factor)

WEEKDAY = {  # Monday=0 .. Sunday=6
    "store": np.array([0.82, 0.85, 0.90, 0.95, 1.08, 1.30, 1.40]),
    "online": np.array([1.00, 1.00, 0.98, 0.98, 1.00, 1.03, 1.06]),
}

# Probability of a heavy-rain day by city and month (footfall shock for physical stores).
RAIN_DAY_PROB = {
    "tn": {10: 0.12, 11: 0.22, 12: 0.12},
    "kongu": {6: 0.10, 7: 0.10, 8: 0.10, 9: 0.08, 10: 0.10, 11: 0.10},
    "ka": {6: 0.10, 7: 0.10, 8: 0.15, 9: 0.18, 10: 0.15},
    "ts": {6: 0.10, 7: 0.18, 8: 0.18, 9: 0.15, 10: 0.08},
}
RAIN_FACTOR = {"store": 0.62, "online": 1.06}


def _shape(dates: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp, ramp: int,
           day_factor: float, tail: int) -> np.ndarray:
    """0..1 intensity of one festival occurrence on each date."""
    t = ((dates - start).days).to_numpy()          # days relative to start
    span = (end - start).days
    s = np.zeros(len(dates))
    pre = (t >= -ramp) & (t < 0)
    s[pre] = ((t[pre] + ramp + 1) / (ramp + 1)) ** 1.8
    during = (t >= 0) & (t < span)
    s[during] = 0.85                                # multi-day festival (e.g. Navratri) plateau
    main = t == span
    s[main] = day_factor
    if tail > 0:
        post = (t > span) & (t <= span + tail)
        s[post] = day_factor * (1 - (t[post] - span) / (tail + 1))
    return s


def _md_mask(dates: pd.DatetimeIndex, a: str, b: str) -> np.ndarray:
    md = dates.strftime("%m-%d").to_numpy()
    return (md >= a) & (md <= b) if a <= b else (md >= a) | (md <= b)


def festival_lift(dates: pd.DatetimeIndex, category: str, region: str, occasions: list[str]) -> np.ndarray:
    lift = np.ones(len(dates))
    occ = {o.lower() for o in occasions}
    for fam_name, start, end in EVENTS:
        fam = FAMILIES[fam_name]
        w = fam["region"][region]
        if w <= 0:
            continue
        aff = fam["affinity"] if fam["keyword"] in occ else 1.0
        sh = _shape(dates, _d(start), _d(end), fam["ramp"], fam["day_factor"], fam["tail"])
        lift += sh * (fam["peak"][category] - 1.0) * w * aff
    return lift


def season_factor(dates: pd.DatetimeIndex, category: str, region: str, store_type: str,
                  occasions: list[str]) -> np.ndarray:
    f = np.ones(len(dates))
    wed = np.zeros(len(dates), bool)
    for a, b in WEDDING_SEASONS:
        wed |= _md_mask(dates, a, b)
    aff = WEDDING_AFFINITY if ({"wedding", "bridal"} & {o.lower() for o in occasions}) else 1.0
    f[wed] *= 1 + (WEDDING_LIFT[category] - 1) * aff
    mon = _md_mask(dates, *MONSOON)
    f[mon] *= MONSOON_FACTOR["online" if store_type == "online" else "store"]
    if region in NE_MONSOON_FACTOR and store_type != "online":
        f[_md_mask(dates, *NE_MONSOON)] *= NE_MONSOON_FACTOR[region]
    a, b, lull = POST_DIWALI_LULL
    for dd in DIWALI.values():
        t = (dates - dd).days.to_numpy()
        f[(t >= a) & (t <= b)] *= lull
    return f


def weekday_factor(dates: pd.DatetimeIndex, store_type: str) -> np.ndarray:
    return WEEKDAY["online" if store_type == "online" else "store"][dates.dayofweek.to_numpy()]


def festivals_table(start: str = "2024-10-01", end: str = "2026-12-31") -> pd.DataFrame:
    rows = [{"festival": f, "start": s, "end": e} for f, s, e in EVENTS if start <= e and s <= end]
    return pd.DataFrame(rows)


def days_to_diwali(d: dt.date) -> int:
    ts = pd.Timestamp(d)
    nxt = min(v for v in DIWALI.values() if v >= ts)
    return (nxt - ts).days


if __name__ == "__main__":
    idx = pd.date_range("2025-09-01", "2025-10-25")
    lift = festival_lift(idx, "sarees", "tn", ["diwali"]) * season_factor(idx, "sarees", "tn", "store", ["diwali"])
    for d, v in zip(idx, lift):
        print(d.date(), f"{v:5.2f}", "#" * int(v * 10))
    print(festivals_table())
