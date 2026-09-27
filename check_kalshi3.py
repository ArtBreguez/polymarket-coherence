"""The five September FOMC buckets: liquidity and executable arbitrage."""
import json

k = json.load(open("/tmp/pcrev/data/kalshi_fed.json"))
mk = k["markets"]
items = list(mk.values()) if isinstance(mk, dict) else mk

matches = json.load(open("/tmp/pcrev/data/event_matches.json"))
entry = None
for v in matches.values():
    if isinstance(v, list):
        for m in v:
            if isinstance(m, dict) and m.get("id") == "fed-sep-2026":
                entry = m
if entry is None:
    for v in matches.values():
        if isinstance(v, dict) and v.get("id") == "fed-sep-2026":
            entry = v

series = entry["kalshi_series"]
datecode = entry["kalshi_date_code"]
buckets = entry["buckets"]
print("series=%s datecode=%s declared buckets=%d" % (series, datecode, len(buckets)))

by_ticker = {m["ticker"]: m for m in items}
print("\nthe five aligned September buckets:")
found = 0
zero_liq = 0
for b in buckets:
    tick = "%s-%s-%s" % (series, datecode, b["kalshi_ticker_suffix"])
    m = by_ticker.get(tick)
    if not m:
        print("  %-12s %-32s NOT IN SNAPSHOT" % (b["label"], tick))
        continue
    found += 1
    liq = float(m["liquidity"])
    if liq == 0.0:
        zero_liq += 1
    print("  %-12s %-32s bid=%.4f ask=%.4f liq=%.4f"
          % (b["label"], tick, float(m["yes_bid"]), float(m["yes_ask"]), liq))

print("\nbuckets found in snapshot: %d of %d" % (found, len(buckets)))
print("with ZERO reported liquidity: %d of %d" % (zero_liq, found))
print("  article claim 'every Kalshi bucket quoted zero reported liquidity':",
      "TRUE" if found and zero_liq == found else "FALSE")

# Article claims 5 aligned buckets. Verify the count the findings use.
print("\narticle claim '5 aligned buckets':", "TRUE" if len(buckets) == 5 else "FALSE (declared %d)" % len(buckets))

# And whether the whole-file liquidity really is uniformly zero.
allliq = [float(m["liquidity"]) for m in items]
print("\nacross all %d Kalshi markets in the snapshot: %d have zero liquidity"
      % (len(allliq), sum(1 for x in allliq if x == 0.0)))
