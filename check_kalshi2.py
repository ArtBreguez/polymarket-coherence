"""Verify the article's two Kalshi claims against the committed snapshot."""
import json

k = json.load(open("/tmp/pcrev/data/kalshi_fed.json"))
mk = k["markets"]
print("markets:", len(mk), "| type:", type(mk).__name__)

items = mk if isinstance(mk, list) else list(mk.values())
first = items[0]
print("keys:", sorted(first.keys()))
print()

matches = json.load(open("/tmp/pcrev/data/event_matches.json"))
fomc = None
for key in ("matches", "events"):
    if key in matches and isinstance(matches[key], list):
        for m in matches[key]:
            blob = json.dumps(m).lower()
            if "fomc" in blob or "fed" in blob:
                fomc = m
                break
if fomc is None:
    fomc = {k2: v for k2, v in matches.items() if not k2.startswith("_")}
print("FOMC match entry:", json.dumps(fomc)[:700])
print()

buckets = fomc.get("buckets") if isinstance(fomc, dict) else None
if isinstance(buckets, dict):
    print("aligned buckets declared:", len(buckets))
    for pm, ks in buckets.items():
        print("  %-28s -> %s" % (str(pm)[:26], ks))

by_ticker = {}
for m in items:
    t = m.get("ticker") or m.get("Ticker")
    by_ticker[t] = m

print()
print("liquidity on the Kalshi side:")
zero = 0
checked = 0
for m in items:
    liq = m.get("liquidity", m.get("open_interest"))
    t = m.get("ticker", "?")
    if liq is not None:
        checked += 1
        if liq == 0:
            zero += 1
print("  markets with a liquidity field: %d | zero liquidity: %d" % (checked, zero))
print("  ALL zero:", checked > 0 and zero == checked)

print()
print("sample of 6 markets (ticker, bid, ask, liquidity):")
for m in items[:6]:
    print("  %-30s bid=%-6s ask=%-6s liq=%s"
          % (str(m.get("ticker"))[:28], m.get("yes_bid"), m.get("yes_ask"),
             m.get("liquidity", m.get("open_interest"))))
