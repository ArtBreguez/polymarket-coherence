#!/usr/bin/env python3
"""Collect a snapshot of Kalshi mutually-exclusive events with executable
(yes bid / yes ask) prices per outcome. Public data only — no API key.

Kalshi is the second venue for the cross-market Law-of-One-Price study: the same
real-world event (e.g. the September FOMC decision) trades on both Kalshi and
Polymarket, so we can test whether their *executable* prices are coherent.

Endpoint: https://api.elections.kalshi.com/trade-api/v2
  /markets?series_ticker=...   -> markets with yes_bid_dollars / yes_ask_dollars

Usage:
    python scripts/collect_kalshi.py --series KXFEDDECISION --out data/kalshi_fed.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.parse
import urllib.request

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"


def _get(path: str, params: dict) -> dict:
    url = f"{KALSHI}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "polymarket-coherence/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def collect_series(series_ticker: str) -> dict:
    """Return all open markets for a series, keyed by ticker, with yes bid/ask."""
    out = {}
    cursor = None
    while True:
        params = {"limit": 200, "status": "open", "series_ticker": series_ticker}
        if cursor:
            params["cursor"] = cursor
        resp = _get("/markets", params)
        for m in resp.get("markets", []):
            out[m["ticker"]] = {
                "ticker": m.get("ticker"),
                "yes_sub_title": m.get("yes_sub_title"),
                "yes_bid": m.get("yes_bid_dollars"),
                "yes_ask": m.get("yes_ask_dollars"),
                "close_time": m.get("close_time"),
                "liquidity": m.get("liquidity_dollars"),
            }
        cursor = resp.get("cursor")
        if not cursor:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True, help="Kalshi series_ticker, e.g. KXFEDDECISION")
    ap.add_argument("--out", default="data/kalshi.json")
    args = ap.parse_args()

    markets = collect_series(args.series)
    payload = {
        "snapshot_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": f"{KALSHI}/markets?series_ticker={args.series}",
        "series": args.series,
        "markets": markets,
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {len(markets)} Kalshi markets ({args.series}) -> {args.out}")
    for t, m in list(markets.items())[:8]:
        print(f"  {t:34} bid={m['yes_bid']} ask={m['yes_ask']} | {str(m['yes_sub_title'])[:28]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
