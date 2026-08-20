#!/usr/bin/env python3
"""Analyze coherence of Polymarket multi-outcome (negRisk) events.

Central question: multi-outcome events are mutually exclusive, so the outcome
probabilities should sum to 1. Naively (at the mid price) apparent violations
look large and frequent. We test whether those violations survive the bid-ask
spread — i.e. whether they are *executable* — and whether their magnitude is a
mechanical function of field size (number of outcomes) rather than genuine
mispricing.

Reads the CSV produced by collect.py. Pure stdlib; writes a summary table and,
if matplotlib is available, one figure. No network, no keys.

Usage:
    python scripts/analyze.py --in data/snapshot.csv
"""
from __future__ import annotations

import argparse
import csv
import statistics as st


def load(path: str) -> dict[str, dict]:
    """Group child markets by event; keep only complete quote triples."""
    events: dict[str, dict] = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            def num(k):
                v = r.get(k)
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None
            bid, ask, mid = num("best_bid"), num("best_ask"), num("p_yes_mid")
            if bid is None or ask is None or mid is None:
                continue
            e = events.setdefault(r["event_id"], {
                "title": r["event_title"],
                "n_markets": int(float(r["n_markets"])) if r["n_markets"] else 0,
                "volume": num("event_volume") or 0.0,
                "bids": [], "asks": [], "mids": [],
            })
            e["bids"].append(bid)
            e["asks"].append(ask)
            e["mids"].append(mid)
    return events


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3 or st.pstdev(xs) == 0 or st.pstdev(ys) == 0:
        return float("nan")
    mx, my = st.mean(xs), st.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)
    return cov / (st.pstdev(xs) * st.pstdev(ys))


def analyze(events: dict[str, dict], min_outcomes: int = 3) -> dict:
    rows = []
    for e in events.values():
        n = len(e["mids"])
        if n < min_outcomes:
            continue
        sig_mid = sum(e["mids"])
        sig_bid = sum(e["bids"])
        sig_ask = sum(e["asks"])
        rows.append({
            "title": e["title"], "n": n, "volume": e["volume"],
            "sum_mid": sig_mid, "sum_bid": sig_bid, "sum_ask": sig_ask,
            "spread_band": sig_ask - sig_bid,
        })

    mids = [r["sum_mid"] for r in rows]
    bids = [r["sum_bid"] for r in rows]
    asks = [r["sum_ask"] for r in rows]
    ns = [r["n"] for r in rows]
    bands = [r["spread_band"] for r in rows]

    # Executable arbitrage: buy the whole field below 1 (Σask<1) or sell above 1 (Σbid>1).
    buy_arb = [r for r in rows if r["sum_ask"] < 0.99]
    sell_arb = [r for r in rows if r["sum_bid"] > 1.01]

    return {
        "n_events": len(rows),
        "median_sum_mid": st.median(mids) if mids else float("nan"),
        "median_sum_bid": st.median(bids) if bids else float("nan"),
        "median_sum_ask": st.median(asks) if asks else float("nan"),
        "corr_fieldsize_spreadband": pearson(ns, bands),
        "executable_buy_arb": len(buy_arb),
        "executable_sell_arb": len(sell_arb),
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/snapshot.csv")
    ap.add_argument("--min-outcomes", type=int, default=3)
    ap.add_argument("--fig", default="figures/coherence_band.png")
    args = ap.parse_args()

    res = analyze(load(args.inp), args.min_outcomes)

    print(f"negRisk events analyzed (>= {args.min_outcomes} outcomes): {res['n_events']}")
    print(f"  median Σ P(mid)  = {res['median_sum_mid']:.3f}   <- coherent at the mid")
    print(f"  median Σ bestBid = {res['median_sum_bid']:.3f}")
    print(f"  median Σ bestAsk = {res['median_sum_ask']:.3f}   <- bid/ask straddle 1.0")
    print(f"  corr(field size, Σask-Σbid spread band) = {res['corr_fieldsize_spreadband']:.3f}")
    print(f"  executably arbitrageable: buy-field Σask<0.99 = {res['executable_buy_arb']}, "
          f"sell-field Σbid>1.01 = {res['executable_sell_arb']}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        ns = [r["n"] for r in res["rows"]]
        band = [r["spread_band"] for r in res["rows"]]
        plt.figure(figsize=(6, 4))
        plt.scatter(ns, band, alpha=0.7)
        plt.xlabel("Field size (number of mutually-exclusive outcomes)")
        plt.ylabel("Spread band  (Σ bestAsk − Σ bestBid)")
        plt.title("Apparent coherence 'violation' scales with field size")
        plt.tight_layout()
        plt.savefig(args.fig, dpi=120)
        print(f"  figure -> {args.fig}")
    except ImportError:
        print("  (matplotlib not installed — skipped figure)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
