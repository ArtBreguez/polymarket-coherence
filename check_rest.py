"""The claims I have NOT yet verified myself.

Everything checked so far came from panel.jsonl. These four come from other
sources and are still taken on trust from the README:

  1. correlation ~ +0.66 between spread band width and field size
  2. 31.2 hours unbroken sub-$1 run
  3. Kalshi: 5 aligned buckets, zero executable arbitrage, zero liquidity on EVERY bucket
  4. 1,757 child markets / 36 events in the snapshot
"""
import csv
import json
from datetime import datetime
from collections import defaultdict

# ---------------------------------------------------------------- 1 + 4
rows = list(csv.DictReader(open("/tmp/pcrev/data/snapshot.csv")))
print("snapshot.csv rows (child markets):", len(rows))
ev = defaultdict(lambda: {"mid": 0.0, "bid": 0.0, "ask": 0.0, "n": 0})
for r in rows:
    try:
        mid, bid, ask = float(r["p_yes_mid"]), float(r["best_bid"]), float(r["best_ask"])
    except (ValueError, KeyError):
        continue
    e = ev[r["event_id"]]
    e["mid"] += mid
    e["bid"] += bid
    e["ask"] += ask
    e["n"] += 1

evs = {k: v for k, v in ev.items() if v["n"] >= 3}
print("events with >=3 outcomes:", len(evs))
print("child markets in those events:", sum(v["n"] for v in evs.values()))

# spread band width vs field size
ns = [v["n"] for v in evs.values()]
bands = [v["ask"] - v["bid"] for v in evs.values()]
mn, mb = sum(ns) / len(ns), sum(bands) / len(bands)
cov = sum((a - mn) * (b - mb) for a, b in zip(ns, bands)) / len(ns)
sx = (sum((a - mn) ** 2 for a in ns) / len(ns)) ** 0.5
sy = (sum((b - mb) ** 2 for b in bands) / len(bands)) ** 0.5
corr = cov / (sx * sy)
print("\ncorr(field size, ask-bid band) = %+.3f   [article says ~+0.66]" % corr)
print("  match:", abs(corr - 0.66) < 0.05)

# ---------------------------------------------------------------- 2
panel = [json.loads(l) for l in open("/tmp/pcrev/data/panel.jsonl") if l.strip()]
TARGET = "Balance of Power: 2026 Midterms"
ser = sorted(
    (datetime.fromisoformat(r["ts"].replace("Z", "+00:00")), r["lock_cost"])
    for r in panel
    if r.get("title") == TARGET and r.get("complete") and r.get("lock_cost") is not None)

best_run = cur_start = cur_end = None
run_start = None
for t, c in ser:
    if c < 1.0:
        if run_start is None:
            run_start = t
        cur_end = t
    else:
        if run_start is not None:
            dur = (cur_end - run_start).total_seconds() / 3600
            if best_run is None or dur > best_run:
                best_run, cur_start = dur, run_start
            run_start = None
if run_start is not None:
    dur = (cur_end - run_start).total_seconds() / 3600
    if best_run is None or dur > best_run:
        best_run = dur

print("\nlongest unbroken sub-$1 run: %.1f h   [article says 31.2 h]" % best_run)
print("  match:", abs(best_run - 31.2) < 0.6)

# ---------------------------------------------------------------- 3
k = json.load(open("/tmp/pcrev/data/kalshi_fed.json"))
print("\nkalshi_fed.json type:", type(k).__name__)
items = k if isinstance(k, list) else k.get("markets") or list(k.values())
print("entries:", len(items) if hasattr(items, "__len__") else "?")
if isinstance(items, list) and items and isinstance(items[0], dict):
    print("keys of first:", sorted(items[0].keys())[:14])
    liq = []
    for m in items:
        for key in ("liquidity", "open_interest", "volume"):
            if key in m:
                liq.append((m.get("ticker") or m.get("title", "?"), key, m[key]))
                break
    for t, key, v in liq[:10]:
        print("  %-34s %s=%s" % (str(t)[:32], key, v))
    print("\nall zero liquidity:", all(v == 0 for _, _, v in liq) if liq else "no liquidity field")
