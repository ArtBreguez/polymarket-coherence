#!/usr/bin/env python3
"""Cross-market Law-of-One-Price (LOOP) analyzer — frozen / reproducible.

The single-venue study showed multi-outcome fields are internally coherent once
you account for spread and liquidity. The sharper question — with real variance,
because two venues quote independently — is *cross-market*: does the SAME
real-world outcome trade at the same price on Polymarket and Kalshi?

This reads BOTH venues from committed snapshots (no network), so every number is
reproducible from the data in this repo, exactly like Parts 1–3:
    Polymarket: data/snapshot.csv          (bestBid / bestAsk on the YES contract)
    Kalshi:     data/kalshi_fed.json       (yes_bid / yes_ask + reported liquidity)

A LOOP violation is EXECUTABLE only if you can buy YES where it's cheap and sell
where it's dear after crossing both spreads AND paying Kalshi's taker fee, on a
quote that has real liquidity behind it (Kalshi liquidity == 0 is a phantom
top-of-book with an empty order book).

Scope note: the cross-venue leg is the FOMC September-2026 decision, the one event
for which both venues were captured in the frozen snapshot. (An earlier NBA-champion
leg relied on a live Kalshi pull that was never committed, so it is not reproducible
and has been dropped rather than shipped un-reproducible.)

Usage:
    python scripts/analyze_loop.py --matches data/event_matches.json
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hygiene import to_float as _f  # noqa: E402


def kalshi_fee(price, contracts=1):
    """Kalshi taker fee: round_up(0.07 * C * p * (1-p)) in dollars.
    Fees turn many raw cross-venue gaps into non-arbitrage — modeling them is the
    whole point of an *executable* coherence study."""
    if price is None:
        return 0.0
    return math.ceil(0.07 * contracts * price * (1 - price) * 100) / 100


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


def load_polymarket_event(title: str, snapshot_path: str) -> dict:
    """Return {question_lower: (bid, ask)} for the negRisk event with this title,
    read from the committed Polymarket snapshot CSV."""
    out: dict = {}
    with open(snapshot_path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("event_title") == title:
                key = str(r.get("question", "")).lower()
                out[key] = (_f(r.get("best_bid")), _f(r.get("best_ask")))
    return out


def load_kalshi_markets(kalshi_path: str) -> dict:
    """Return {ticker: (bid, ask, liq)} from the committed Kalshi snapshot JSON.
    liq is Kalshi's reported dollar liquidity — 0 means a phantom top-of-book quote
    with no executable depth behind it."""
    out: dict = {}
    d = json.load(open(kalshi_path))
    for tkr, m in d.get("markets", {}).items():
        out[tkr] = (_f(m.get("yes_bid")), _f(m.get("yes_ask")), _f(m.get("liquidity")) or 0.0)
    return out


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
    poly = load_polymarket_event(match["polymarket_event_title"], match["polymarket_snapshot"])
    kalshi = load_kalshi_markets(match["kalshi_snapshot"])
    date_code = match["kalshi_date_code"]
    rows = []
    for bucket in match["buckets"]:
        pb, pa, kb, ka, kliq = match_bucket(poly, kalshi, bucket, date_code)
        rows.append(_row(bucket["label"], pb, pa, kb, ka, kliq))
    return rows


def analyze(matches_path: str):
    reg = json.load(open(matches_path))
    results = []
    for match in reg["matches"]:
        # Only frozen, reproducible matches are analyzed. A match without a
        # committed Kalshi snapshot cannot be reproduced and is skipped.
        if not match.get("kalshi_snapshot") or not match.get("polymarket_snapshot"):
            continue
        rows = analyze_buckets(match)
        results.append({"id": match["id"], "description": match["description"],
                        "kind": match.get("kind", "buckets"), "buckets": rows})
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", default="data/event_matches.json")
    args = ap.parse_args()

    for r in analyze(args.matches):
        print(f"\n=== {r['id']}: {r['description']}  [{r['kind']}, {len(r['buckets'])} outcomes] ===")
        print(f"{'outcome':24} {'poly(bid/ask)':>14} {'kalshi(bid/ask)':>16} {'gross':>7} {'net':>7} {'kliq':>7}")
        best = None
        n_exec = 0
        for b in r["buckets"]:
            pj = f"{b['poly_bid']}/{b['poly_ask']}" if b['poly_bid'] is not None else "—"
            kj = f"{b['kalshi_bid']}/{b['kalshi_ask']}" if b['kalshi_bid'] is not None else "—"
            flag = "  <-- EXECUTABLE ARB" if b["executable"] else ""
            if b["executable"]:
                n_exec += 1
            print(f"{str(b['label'])[:24]:24} {pj:>14} {kj:>16} "
                  f"{str(b['edge_gross']):>7} {str(b['edge_net']):>7} {str(b['kalshi_liq']):>7}{flag}")
            if b["executable"] and (best is None or b["edge_net"] > best):
                best = b["edge_net"]
        verdict = (f"{n_exec} EXECUTABLE net-of-fee arbitrage(s), best {best}" if n_exec
                   else "no executable arbitrage (edges are phantom top-of-book or fee-negative)")
        print(f"verdict: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
