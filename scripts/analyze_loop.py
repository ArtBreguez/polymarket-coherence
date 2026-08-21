#!/usr/bin/env python3
"""Cross-market Law-of-One-Price (LOOP) analyzer.

The single-venue study showed multi-outcome fields are internally coherent once
you account for spread and liquidity. The sharper question — with real variance,
because two venues quote independently — is *cross-market*: does the SAME
real-world outcome trade at the same price on Polymarket and Kalshi?

For each curated bucket (see data/event_matches.json) we read both venues'
executable quotes:
    Polymarket: bestBid / bestAsk on the YES contract
    Kalshi:     yes_bid / yes_ask
A LOOP violation is EXECUTABLE only if you can buy YES where it's cheap and sell
(or buy NO) where it's dear after crossing both spreads:
    edge = max( kalshi_bid - poly_ask , poly_bid - kalshi_ask )
edge > 0 means a real, spread-crossing arbitrage on that single outcome.

This is deliberately conservative (top-of-book, ignores fees) and reuses the
same executable-price discipline as the rest of the repo.

Usage:
    python scripts/analyze_loop.py --matches data/event_matches.json
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"


def _get(url: str) -> dict | list:
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "polymarket-coherence/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def kalshi_fee(price, contracts=1):
    """Kalshi taker fee: round_up(0.07 * C * p * (1-p)) in dollars.
    Fees turn many raw cross-venue gaps into non-arbitrage — modeling them is the
    whole point of an *executable* coherence study."""
    import math
    if price is None:
        return 0.0
    return math.ceil(0.07 * contracts * price * (1 - price) * 100) / 100


def load_polymarket_event(title: str) -> dict:
    """Return {question_lower: (bid, ask)} for the negRisk event with this title."""
    events = _get(f"{GAMMA}/events?" + urllib.parse.urlencode(
        {"closed": "false", "limit": 500, "order": "volume", "ascending": "false"}))
    for e in events:
        if e.get("title") == title:
            out = {}
            for m in e.get("markets", []):
                q = str(m.get("question", "")).lower()
                out[q] = (_f(m.get("bestBid")), _f(m.get("bestAsk")))
            return out
    return {}


def load_kalshi_series(series: str) -> dict:
    """Return {ticker: (bid, ask)} for all open markets in a Kalshi series."""
    out, cursor = {}, None
    while True:
        params = {"limit": 200, "status": "open", "series_ticker": series}
        if cursor:
            params["cursor"] = cursor
        resp = _get(f"{KALSHI}/markets?" + urllib.parse.urlencode(params))
        for m in resp.get("markets", []):
            out[m["ticker"]] = (_f(m.get("yes_bid_dollars")), _f(m.get("yes_ask_dollars")))
        cursor = resp.get("cursor")
        if not cursor:
            break
    return out


def match_bucket(poly: dict, kalshi: dict, bucket: dict, date_code: str):
    """Resolve one bucket's (poly_bid, poly_ask, kalshi_bid, kalshi_ask)."""
    # Polymarket: first question containing the phrase
    pb = pa = None
    needle = bucket["polymarket_contains"].lower()
    for q, (b, a) in poly.items():
        if needle in q:
            pb, pa = b, a
            break
    # Kalshi: ticker ending in date_code-suffix
    suffix = f"{date_code}-{bucket['kalshi_ticker_suffix']}"
    kb = ka = None
    for tkr, (b, a) in kalshi.items():
        if tkr.endswith(suffix):
            kb, ka = b, a
            break
    return pb, pa, kb, ka


def analyze(matches_path: str):
    reg = json.load(open(matches_path))
    results = []
    for match in reg["matches"]:
        poly = load_polymarket_event(match["polymarket_event_title"])
        kalshi = load_kalshi_series(match["kalshi_series"])
        date_code = match["kalshi_date_code"]
        rows = []
        for bucket in match["buckets"]:
            pb, pa, kb, ka = match_bucket(poly, kalshi, bucket, date_code)
            edge_gross = edge_net = None
            direction = None
            if None not in (pb, pa, kb, ka):
                # Leg A: buy YES on Kalshi (pay ka + fee), sell on Polymarket (hit pb)
                a = pb - ka - kalshi_fee(ka)
                # Leg B: buy YES on Polymarket (pay pa), sell on Kalshi (hit kb - fee)
                b = kb - kalshi_fee(kb) - pa
                edge_net = max(a, b)
                edge_gross = max(kb - pa, pb - ka)
                direction = "buy_kalshi_sell_poly" if a >= b else "buy_poly_sell_kalshi"
            rows.append({
                "label": bucket["label"],
                "poly_bid": pb, "poly_ask": pa,
                "kalshi_bid": kb, "kalshi_ask": ka,
                "mid_gap": (None if None in (pa, pb, ka, kb)
                            else round(((pa + pb) / 2) - ((ka + kb) / 2), 4)),
                "edge_gross": None if edge_gross is None else round(edge_gross, 4),
                "edge_net": None if edge_net is None else round(edge_net, 4),
                "direction": direction,
            })
        results.append({"id": match["id"], "description": match["description"], "buckets": rows})
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", default="data/event_matches.json")
    args = ap.parse_args()

    for r in analyze(args.matches):
        print(f"\n=== {r['id']}: {r['description']} ===")
        print(f"{'bucket':10} {'poly(bid/ask)':>16} {'kalshi(bid/ask)':>16} {'gross':>7} {'net(fee)':>9}")
        best = None
        for b in r["buckets"]:
            pj = f"{b['poly_bid']}/{b['poly_ask']}" if b['poly_bid'] is not None else "—"
            kj = f"{b['kalshi_bid']}/{b['kalshi_ask']}" if b['kalshi_bid'] is not None else "—"
            eg, en = b["edge_gross"], b["edge_net"]
            flag = "  <-- ARB (net>0)" if (en is not None and en > 0) else ""
            print(f"{b['label']:10} {pj:>16} {kj:>16} {str(eg):>7} {str(en):>9}{flag}")
            if en is not None and (best is None or en > best):
                best = en
        verdict = ("REAL net-of-fee cross-market arbitrage" if best and best > 0
                   else "no arbitrage after Kalshi fees")
        print(f"best net edge: {best}  ({verdict})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
