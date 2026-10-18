"""Sequential chat-latency benchmark against the deployed API (fresh session per turn).

Writes evals/latency_bench.json with wall-clock p50/p95 to `done`, time to first event and first text, and stage timings.
"""
from __future__ import annotations

import json
import statistics
import time
import urllib.request
import uuid
from pathlib import Path

API = "https://retailnova-api-569310655517.asia-south1.run.app"
PROMPTS = [
    "Diwali ke liye maroon silk saree chahiye, 5000 tak, T-Nagar se pickup",
    "Do you have a royal blue kurta in size L?",
    "Gift ideas under 1000 for Diwali",
    "Brass diya set for the puja room",
    "Kanchipuram pattu pudavai irukka? Budget 6000",
    "Women's juttis size 7",
    "Silk kurta set for a wedding, size M, under 4000",
    "Something festive for my mother, budget 3000",
    "Diwali ke liye juttis chahiye, size 8",
    "Men's Nehru jacket for a reception",
]


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 2)


def turn(msg: str) -> dict:
    body = json.dumps({"session_id": str(uuid.uuid4()), "message": msg, "store_id": "CHN-TNG", "new_chat": True}).encode()
    req = urllib.request.Request(API + "/api/chat", data=body, headers={"Content-Type": "application/json"})
    t0 = time.time(); first = first_text = None; done = {}
    with urllib.request.urlopen(req, timeout=120) as r:
        ev = None
        for raw in r:
            line = raw.decode().rstrip("\n")
            if line.startswith("event:"):
                ev = line[6:].strip()
                first = first or time.time() - t0
                if ev == "text" and first_text is None:
                    first_text = time.time() - t0
            elif line.startswith("data:") and ev == "done":
                done = json.loads(line[5:])
    return {"wall_s": round(time.time() - t0, 2), "first_event_s": round(first or 0, 3),
            "first_text_s": round(first_text or 0, 2), "model": done.get("model"), "timings": done.get("timings")}


def main() -> None:
    runs = [turn(p) for p in PROMPTS]
    walls = [r["wall_s"] for r in runs]
    out = {"api": API, "n": len(runs), "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "wall_total_s": {"p50": pct(walls, 0.5), "p95": pct(walls, 0.95)},
           "first_event_s": {"p50": pct([r["first_event_s"] for r in runs], 0.5)},
           "first_text_s": {"p50": pct([r["first_text_s"] for r in runs], 0.5)},
           "runs": runs}
    Path(__file__).with_name("latency_bench.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: out[k] for k in ("wall_total_s", "first_event_s", "first_text_s")}))
    print("models:", [r["model"] for r in runs])


if __name__ == "__main__":
    main()
