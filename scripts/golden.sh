#!/usr/bin/env bash
# RetailNova golden checks: 10 end-to-end API checks against ${BASE:-http://localhost:8080}.
# Each check prints PASS/FAIL; the script exits non-zero if any check fails.
# Needs: curl, python3. Resets demo data first (GOLDEN_PRERESET=0 to skip) and again at the end.
set -u
BASE="${BASE:-http://localhost:8080}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
SESSION="golden-$(date +%s)-$RANDOM"
FAILS=0
PY="${PYTHON:-python3}"

pass() { printf 'PASS  %-2s %s\n' "$1" "$2"; }
fail() { printf 'FAIL  %-2s %s\n' "$1" "$2"; FAILS=$((FAILS + 1)); }

# POST an SSE request; saves the raw stream to $TMP/$1.sse
sse() { curl -sN --max-time 90 -X POST "$BASE$2" -H 'content-type: application/json' -d @"$3" > "$TMP/$1.sse"; }

# Parse an SSE file into a JSON summary on stdout
sse_summary() {
  "$PY" - "$1" <<'PY'
import json, sys
ev, events = None, []
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.rstrip("\n")
    if line.startswith("event: "): ev = line[7:]
    elif line.startswith("data: "): events.append((ev, json.loads(line[6:])))
names = [e for e, _ in events]
text = "".join(d.get("delta", "") for e, d in events if e == "text")
cards = [c for e, d in events if e == "products" for c in d["items"]]
print(json.dumps({"names": names, "text": text, "cards": cards,
                  "proposals": [d["proposal"] for e, d in events if e == "proposal"],
                  "steps": [d["step"] for e, d in events if e == "step"],
                  "done": next((d for e, d in events if e == "done"), None),
                  "signal": next((d["signal"] for e, d in events if e == "signal"), None)}))
PY
}

if [ "${GOLDEN_PRERESET:-1}" = "1" ]; then
  curl -s --max-time 60 -X POST "$BASE/api/demo/reset" > /dev/null || true
fi

# 1. health
if curl -s --max-time 15 "$BASE/api/health" | "$PY" -c 'import json,sys; assert json.load(sys.stdin)["status"]=="ok"' 2>/dev/null; then
  pass 1 "health"; else fail 1 "health"; fi

# 2. bootstrap
if curl -s --max-time 15 "$BASE/api/bootstrap" | "$PY" -c '
import json,sys; d=json.load(sys.stdin)
assert d["demo_today"]=="2026-10-18" and d["days_to_diwali"]==21 and len(d["stores"])==7
assert len(d["categories"])==6 and len(d["sample_prompts"]["shopper"])>=4 and len(d["sample_prompts"]["manager"])>=3' 2>/dev/null; then
  pass 2 "bootstrap"; else fail 2 "bootstrap"; fi

# 3. English chat returns products + done
printf '{"session_id":"%s-en","message":"Gift ideas under ₹1000 for Diwali","store_id":"CHN-TNG"}' "$SESSION" > "$TMP/c3.json"
sse c3 /api/chat "$TMP/c3.json"
R=$(sse_summary "$TMP/c3.sse" | "$PY" -c '
import json,sys; d=json.load(sys.stdin)
ok = len(d["cards"])>0 and d["names"][-1]=="done" and d["names"].count("done")==1 and d["text"].strip()!=""
print(("OK " if ok else "BAD ") + "cards=%s done_ms=%s" % ([c["sku"] for c in d["cards"]], (d["done"] or {}).get("latency_ms")))')
case "$R" in OK*) pass 3 "english chat: ${R#OK }";; *) fail 3 "english chat: ${R#BAD }";; esac

# 4. Hinglish hero prompt: SAR-001, out of stock at CHN-TNG, available at CBE-RSP
printf '{"session_id":"%s","message":"Diwali ke liye maroon silk saree chahiye, 5000 tak, T-Nagar se pickup","store_id":"CHN-TNG"}' "$SESSION" > "$TMP/c4.json"
sse c4 /api/chat "$TMP/c4.json"
R=$(sse_summary "$TMP/c4.sse" | "$PY" -c '
import json,re,sys; d=json.load(sys.stdin)
card = next((c for c in d["cards"] if c["sku"]=="SAR-001"), None)
facts = bool(card) and card["requested_store_on_hand"]==0 and any(a["store_id"]=="CBE-RSP" and a["on_hand"]>0 for a in card["availability"])
t = d["text"].lower()
oos = re.search(r"out of stock|stock mein nahi|stock me nahi|nahi hai|available nahi|khatam|unavailable|sold out|not available", t) is not None
other = re.search(r"rs puram|coimbatore|cbe-rsp|anna nagar|jayanagar|indiranagar|banjara|online", t)
ok = facts and oos and other is not None
print(("OK " if ok else "BAD ") + "sar001=%s cbe_rsp_in_stock=%s says_oos=%s names_store=%s signal=%s" % (
  bool(card), facts, oos, other.group(0) if other else None,
  (d["signal"] or {}).get("outcome")))')
case "$R" in OK*) pass 4 "hinglish hero: ${R#OK }";; *) fail 4 "hinglish hero: ${R#BAD }";; esac

# 5. image chat (royal blue kurta photo) returns MEN-* products
IMG="$ROOT/web/public/samples/blue-kurta.webp"
if [ -f "$IMG" ]; then
  "$PY" - "$IMG" "$SESSION" > "$TMP/c5.json" <<'PY'
import base64, json, sys
b = base64.b64encode(open(sys.argv[1], "rb").read()).decode()
print(json.dumps({"session_id": sys.argv[2] + "-img", "message": "Do you have this in size L?", "store_id": "CHN-TNG",
                  "image_base64": b, "image_mime": "image/webp"}))
PY
  sse c5 /api/chat "$TMP/c5.json"
  R=$(sse_summary "$TMP/c5.sse" | "$PY" -c '
import json,sys; d=json.load(sys.stdin)
skus=[c["sku"] for c in d["cards"]]
ok = any(s.startswith("MEN-") for s in skus)
print(("OK " if ok else "BAD ") + "cards=%s channel=%s" % (skus, (d["signal"] or {}).get("channel")))')
  case "$R" in OK*) pass 5 "image chat: ${R#OK }";; *) fail 5 "image chat: ${R#BAD }";; esac
else
  pass 5 "image chat: SKIPPED (no $IMG)"
fi

# 6. notify-me
R=$(curl -s --max-time 20 -X POST "$BASE/api/notify" -H 'content-type: application/json' \
  -d "{\"session_id\":\"$SESSION\",\"sku\":\"SAR-001\",\"size\":\"FREE\",\"store_id\":\"CHN-TNG\"}")
if echo "$R" | "$PY" -c 'import json,sys; d=json.load(sys.stdin); assert d["waitlist_id"] and d["message"]' 2>/dev/null; then
  pass 6 "notify-me"; else fail 6 "notify-me: $R"; fi

# 7. radar has kpis and series
R=$(curl -s --max-time 40 "$BASE/api/radar?store_id=CHN-TNG" | "$PY" -c '
import json,sys; d=json.load(sys.stdin)
k=d["kpis"]; s=d["series"]
ok = all(x in k for x in ("unmet_value_7d_inr","unmet_units_7d","stockouts_now","signals_today","forecast_gap_units_21d")) and len(s)==98
ok = ok and any(p["actual_units"] is not None for p in s) and any(p["forecast_demand_sensed"] is not None for p in s)
print(("OK " if ok else "BAD ") + "unmet_7d=%s value=%s gaps=%s series=%s" % (k["unmet_units_7d"], k["unmet_value_7d_inr"], len(d["top_gaps"]), len(s)))' 2>&1)
case "$R" in OK*) pass 7 "radar: ${R#OK }";; *) fail 7 "radar: ${R#BAD }";; esac

# 8. plan streams steps and >= 1 proposal
printf '{"store_id":"CHN-TNG","category":"sarees","session_id":"%s"}' "$SESSION" > "$TMP/c8.json"
sse c8 /api/plan "$TMP/c8.json"
sse_summary "$TMP/c8.sse" > "$TMP/c8.sum.json"
R=$("$PY" -c '
import json,sys; d=json.load(open(sys.argv[1]))
ids={s["id"] for s in d["steps"]}
ok = {"forecast","unmet_demand","inventory","transfers","planner"} <= ids and len(d["proposals"])>=1 and (d["done"] or {}).get("plan_id")
print(("OK " if ok else "BAD ") + "steps=%d proposals=%s plan_ms=%s" % (len(d["steps"]),
  [(p["type"], p["sku"], p["quantity"], p.get("from_store_id")) for p in d["proposals"]], (d["done"] or {}).get("latency_ms")))' "$TMP/c8.sum.json")
case "$R" in OK*) pass 8 "plan: ${R#OK }";; *) fail 8 "plan: ${R#BAD }";; esac

# 9. approve returns inventory_changes and notifications_created >= 1
ACTION=$("$PY" -c '
import json,sys; d=json.load(open(sys.argv[1])); ps=d["proposals"]
pick = next((p for p in ps if p["type"]=="transfer" and p["sku"]=="SAR-001"), None) or next((p for p in ps if p["type"]=="transfer"), None) or (ps[0] if ps else None)
print(pick["action_id"] if pick else "")' "$TMP/c8.sum.json" 2>/dev/null)
if [ -n "$ACTION" ]; then
  R=$(curl -s --max-time 30 -X POST "$BASE/api/actions/$ACTION/approve" | "$PY" -c '
import json,sys; d=json.load(sys.stdin)
ok = len(d["inventory_changes"])>=1 and d["notifications_created"]>=1 and d["action"]["status"]=="executed"
print(("OK " if ok else "BAD ") + "%s %s changes=%s notifications=%s" % (d["action"]["type"], d["action"]["sku"],
  [(c["store_id"], c["delta"], c["on_hand_after"]) for c in d["inventory_changes"]], d["notifications_created"]))' 2>&1)
  case "$R" in OK*) pass 9 "approve: ${R#OK }";; *) fail 9 "approve: ${R#BAD }";; esac
else
  fail 9 "approve: no proposal to approve"
fi

# 10. reset
if curl -s --max-time 60 -X POST "$BASE/api/demo/reset" | "$PY" -c 'import json,sys; assert json.load(sys.stdin)["reset_at"]' 2>/dev/null; then
  pass 10 "reset"; else fail 10 "reset"; fi

echo "----"
if [ "$FAILS" -gt 0 ]; then echo "$FAILS check(s) failed"; exit 1; fi
echo "all 10 checks passed"
