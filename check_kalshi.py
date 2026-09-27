"""The Kalshi leg: 5 aligned buckets, zero executable arb, zero liquidity on all.

kalshi_fed.json is a dict of 60 entries. Find the FOMC September buckets the
findings align, and check the two claims the article makes about them.
"""
import json

k = json.load(open("/tmp/pcrev/data/kalshi_fed.json"))
print("top-level keys:", list(k.keys())[:8])
probe = k[list(k)[0]]
print("first value type:", type(probe).__name__)
if isinstance(probe, dict):
    print("first value keys:", sorted(probe.keys()))
    print("first value:", json.dumps(probe)[:300])

matches = json.load(open("/tmp/pcrev/data/event_matches.json"))
print("\nevent_matches.json:", json.dumps(matches)[:600])
