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


def load_polymarket_event(title: str, name_source: str = "question") -> dict:
    """Return {name_lower: (bid, ask)} for the negRisk event with this title.
    name_source is 'question' (default) or 'groupItemTitle' for team fields."""
    events = _get(f"{GAMMA}/events?" + urllib.parse.urlencode(
        {"closed": "false", "limit": 500, "order": "volume", "ascending": "false"}))
    for e in events:
        if e.get("title") == title:
            out = {}
            for m in e.get("markets", []):
                key = str(m.get(name_source) or m.get("question", "")).lower()
                out[key] = (_f(m.get("bestBid")), _f(m.get("bestAsk")))
            return out
    return {}


def load_kalshi_series(series: str, by_name: bool = False) -> dict:
    """Return {ticker: (bid, ask, liq)} or, if by_name, {yes_sub_title_lower: (bid, ask, liq)}.
    liq is Kalshi's reported dollar liquidity — 0 means a phantom top-of-book quote
    with no executable depth behind it."""
    out, cursor = {}, None
    while True:
        params = {"limit": 200, "status": "open", "series_ticker": series}
        if cursor:
            params["cursor"] = cursor
        resp = _get(f"{KALSHI}/markets?" + urllib.parse.urlencode(params))
        for m in resp.get("markets", []):
            val = (_f(m.get("yes_bid_dollars")), _f(m.get("yes_ask_dollars")),
                   _f(m.get("liquidity_dollars")) or 0.0)
            key = str(m.get("yes_sub_title") or "").lower() if by_name else m["ticker"]
            out[key] = val
        cursor = resp.get("cursor")
        if not cursor:
            break
    return out


def loop_edge(pb, pa, kb, ka):
    """Pure: given Polymarket (bid,ask) and Kalshi (bid,ask) for the SAME outcome,
    return (edge_gross, edge_net, direction). Net models Kalshi's taker fee on the
    leg bought/sold there. edge_net > 0 == real spread-and-fee-crossing arbitrage."""
    if None in (pb, pa, kb, ka):
        return None, None, None
    # Leg A: buy YES on Kalshi (pay ka + fee), sell on Polymarket (hit pb)
    a = pb - ka - kalshi_fee(ka)
    # Leg B: buy YES on Polymarket (pay pa), sell on Kalshi (hit kb - fee)
    b = kb - kalshi_fee(kb) - pa
    edge_net = max(a, b)
    edge_gross = max(kb - pa, pb - ka)
    direction = "buy_kalshi_sell_poly" if a >= b else "buy_poly_sell_kalshi"
    return round(edge_gross, 4), round(edge_net, 4), direction


def match_bucket(poly: dict, kalshi: dict, bucket: dict, date_code: str):
    """Resolve one explicit bucket's (poly_bid, poly_ask, kalshi_bid, kalshi_ask, kalshi_liq)."""
    pb = pa = None
    needle = bucket["polymarket_contains"].lower()
    for q, (b, a) in poly.items():
        if needle in q:
            pb, pa = b, a
            break
    suffix = f"{date_code}-{bucket['kalshi_ticker_suffix']}"
    kb = ka = None
    kliq = 0.0
    for tkr, (b, a, liq) in kalshi.items():
        if tkr.endswith(suffix):
            kb, ka, kliq = b, a, liq
            break
    return pb, pa, kb, ka, kliq


def _row(label, pb, pa, kb, ka, kliq):
    eg, en, dr = loop_edge(pb, pa, kb, ka)
    # An edge is only executable if BOTH venues have real depth. Kalshi liq==0 is a
    # phantom top-of-book quote (empty order book) — flag it so it never counts as arb.
    executable = bool(en is not None and en > 0 and kliq > 0)
    return {"label": label, "poly_bid": pb, "poly_ask": pa,
            "kalshi_bid": kb, "kalshi_ask": ka, "kalshi_liq": round(kliq, 2),
            "edge_gross": eg, "edge_net": en, "direction": dr,
            "executable": executable}


def analyze_buckets(match):
    poly = load_polymarket_event(match["polymarket_event_title"])
    kalshi = load_kalshi_series(match["kalshi_series"])
    date_code = match["kalshi_date_code"]
    rows = []
    for bucket in match["buckets"]:
        pb, pa, kb, ka, kliq = match_bucket(poly, kalshi, bucket, date_code)
        rows.append(_row(bucket["label"], pb, pa, kb, ka, kliq))
    return rows


def analyze_by_name(match):
    """Match each Kalshi outcome (yes_sub_title = city) to the Polymarket outcome
    whose groupItemTitle contains it (unique-substring). Skips ambiguous names."""
    poly = load_polymarket_event(match["polymarket_event_title"],
                                 match.get("name_source", "groupItemTitle"))
    kalshi = load_kalshi_series(match["kalshi_series"], by_name=True)
    rows = []
    for kname, (kb, ka, kliq) in kalshi.items():
        if not kname:
            continue
        cands = [pn for pn in poly if kname in pn]  # kname (city) inside poly full name
        if len(cands) != 1:
            continue  # skip missing or ambiguous — never guess
        pb, pa = poly[cands[0]]
        rows.append(_row(cands[0].title(), pb, pa, kb, ka, kliq))
    rows.sort(key=lambda r: (r["edge_net"] is None, -(r["edge_net"] or -9)))
    return rows


def analyze(matches_path: str):
    reg = json.load(open(matches_path))
    results = []
    for match in reg["matches"]:
        kind = match.get("kind", "buckets")
        rows = analyze_by_name(match) if kind == "by_name" else analyze_buckets(match)
        results.append({"id": match["id"], "description": match["description"],
                        "kind": kind, "buckets": rows})
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", default="data/event_matches.json")
    args = ap.parse_args()

    for r in analyze(args.matches):
        print(f"\n=== {r['id']}: {r['description']}  [{r['kind']}, {len(r['buckets'])} outcomes] ===")
        print(f"{'outcome':24} {'poly(bid/ask)':>14} {'kalshi(bid/ask)':>14} {'net':>7} {'kliq':>7}")
        best = None
        n_exec = 0
        for b in r["buckets"]:
            pj = f"{b['poly_bid']}/{b['poly_ask']}" if b['poly_bid'] is not None else "—"
            kj = f"{b['kalshi_bid']}/{b['kalshi_ask']}" if b['kalshi_bid'] is not None else "—"
            en = b["edge_net"]
            flag = "  <-- EXECUTABLE ARB" if b["executable"] else ""
            if b["executable"]:
                n_exec += 1
            print(f"{str(b['label'])[:24]:24} {pj:>14} {kj:>14} {str(en):>7} {str(b['kalshi_liq']):>7}{flag}")
            if b["executable"] and (best is None or en > best):
                best = en
        verdict = (f"{n_exec} EXECUTABLE net-of-fee arbitrage(s), best {best}" if n_exec
                   else "no executable arbitrage (edges are phantom top-of-book or fee-negative)")
        print(f"verdict: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
