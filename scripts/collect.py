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
import sys
import time
import urllib.parse
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"


def is_expired(end_date, now=None):
    """True if the event's endDate is in the past. Polymarket sometimes keeps
    resolved/expired events flagged closed=false; those 'zombie' markets have
    degenerate prices and must be excluded from a coherence study."""
    if not end_date:
        return False
    try:
        end = dt.datetime.fromisoformat(str(end_date).replace("Z", "+00:00"))
    except ValueError:
        return False
    return end < (now or dt.datetime.now(dt.timezone.utc))


def _get(path: str, params: dict) -> list | dict:
    url = f"{GAMMA}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "polymarket-coherence/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001 — transient network, retry with backoff
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    return []


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def collect(limit: int) -> tuple[list[dict], dict]:
    """Return (rows, manifest). One row per child market of a negRisk event."""
    events = _get("/events", {"closed": "false", "limit": limit,
                              "order": "volume", "ascending": "false"})
    snapshot_ts = dt.datetime.now(dt.timezone.utc).isoformat()
    rows: list[dict] = []
    for e in events:
        if not e.get("negRisk"):
            continue  # negRisk == mutually-exclusive-by-construction; the object of study
        if is_expired(e.get("endDate")):
            continue  # skip zombie markets: past endDate but still closed=false
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
            rows.append({
                "event_id": e.get("id"),
                "event_title": e.get("title"),
                "event_volume": _f(e.get("volume")),
                "event_liquidity": _f(e.get("liquidity")),
                "n_markets": len(markets),
                "market_id": m.get("id"),
                "question": m.get("question"),
                "p_yes_mid": mid,
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
