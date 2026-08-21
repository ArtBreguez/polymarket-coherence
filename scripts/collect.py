#!/usr/bin/env python3
"""Collect a snapshot of Polymarket multi-outcome (negRisk) events with
executable (best bid / best ask) prices for every child market.

Public data only — no API key, no wallet. Uses the Gamma API. The output is a
single tidy CSV (one row per child market) plus a JSON manifest recording the
snapshot time and query, so any run is fully reproducible from the CSV alone.

Usage:
    python scripts/collect.py --limit 500 --out data/snapshot.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hygiene import to_float as _f, clean_price, http_json, live_negrisk_events  # noqa: E402

GAMMA = "https://gamma-api.polymarket.com"


def _get(path: str, params: dict) -> list | dict:
    import urllib.parse
    return http_json(f"{GAMMA}{path}?" + urllib.parse.urlencode(params))


def collect(limit: int) -> tuple[list[dict], dict]:
    """Return (rows, manifest). One row per child market of a negRisk event."""
    events = _get("/events", {"closed": "false", "limit": limit,
                              "order": "volume", "ascending": "false"})
    snapshot_ts = dt.datetime.now(dt.timezone.utc).isoformat()
    rows: list[dict] = []
    for e in live_negrisk_events(events, min_outcomes=1):
        markets = e.get("markets", [])
        for m in markets:
            best_bid = _f(m.get("bestBid"))
            best_ask = _f(m.get("bestAsk"))
            op = m.get("outcomePrices")
            mid = None
            if op:
                try:
                    mid = float(json.loads(op)[0])  # P(Yes)
                except (ValueError, IndexError, TypeError):
                    mid = None
            # Price sanity: a probability must live in (0,1). A mid of exactly 0/1
            # (or out of range) is a degenerate/resolved/placeholder leg. We keep
            # the raw value for transparency but flag it so downstream analysis can
            # exclude it instead of silently averaging corruption into a result.
            mid_ok = clean_price(mid) is not None
            rows.append({
                "event_id": e.get("id"),
                "event_title": e.get("title"),
                "event_volume": _f(e.get("volume")),
                "event_liquidity": _f(e.get("liquidity")),
                "n_markets": len(markets),
                "market_id": m.get("id"),
                "question": m.get("question"),
                "p_yes_mid": mid,
                "p_yes_mid_valid": mid_ok,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "end_date": e.get("endDate"),
            })
    manifest = {
        "snapshot_utc": snapshot_ts,
        "source": f"{GAMMA}/events?closed=false&order=volume",
        "events_scanned": len(events),
        "negRisk_child_markets": len(rows),
        "note": "Public Gamma API snapshot. p_yes_mid is outcomePrices[0]; "
                "best_bid/best_ask are the executable top-of-book quotes.",
    }
    return rows, manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500,
                    help="max events to scan (Gamma pages by volume desc)")
    ap.add_argument("--out", default="data/snapshot.csv")
    args = ap.parse_args()

    rows, manifest = collect(args.limit)
    if not rows:
        print("No negRisk child markets collected — aborting.", file=sys.stderr)
        return 1

    fields = list(rows[0].keys())
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    manifest_path = args.out.rsplit(".", 1)[0] + ".manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Wrote {len(rows)} rows → {args.out}")
    print(f"Manifest → {manifest_path}")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
