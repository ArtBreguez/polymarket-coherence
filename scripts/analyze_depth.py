#!/usr/bin/env python3
"""Depth-aware coherence analysis of Polymarket negRisk (mutually-exclusive)
events.

The mid price and even the top-of-book quote hide the real question: to lock the
guaranteed \$1 payoff of a mutually-exclusive field you must BUY one YES share in
every outcome. What does assembling the whole field actually cost per \$1 of
guaranteed payoff, once you walk the book for a realistic order size?

For each event we simulate buying `size` shares of YES in every child market by
consuming ask liquidity level by level (a marketable buy). The cost to guarantee
\$1 is  Σ_i vwap_buy_i(size)  — if that is < 1 the field is a real (executable)
arbitrage at that size; if > 1 there is no free lunch. We sweep order size and
show how the "arbitrage" that looks present at the mid evaporates with depth and
with field size (number of outcomes).

Reads data/books.json from collect_depth.py. Pure stdlib (+ optional matplotlib).

Usage:
    python scripts/analyze_depth.py --in data/books.json
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict


def _levels(side):
    """Normalize a book side to a sorted list of (price, size) floats."""
    out = []
    for lvl in side or []:
        try:
            out.append((float(lvl["price"]), float(lvl["size"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def vwap_buy(asks, shares):
    """Average price to BUY `shares` by consuming asks cheapest-first.
    Returns (avg_price, filled_shares). If the book is too thin, fills what it
    can and reports the shortfall via filled < shares."""
    asks = sorted(asks, key=lambda x: x[0])  # cheapest ask first
    need = shares
    cost = 0.0
    for price, size in asks:
        if need <= 0:
            break
        take = min(need, size)
        cost += take * price
        need -= take
    filled = shares - need
    return (cost / filled if filled > 0 else float("nan")), filled


def load_events(path):
    books = json.load(open(path))
    events = defaultdict(lambda: {"title": None, "n_markets": 0, "asks": []})
    for _tok, b in books.items():
        eid = b.get("event_id")
        if eid is None:
            continue
        e = events[eid]
        e["title"] = b.get("event_title")
        e["n_markets"] = b.get("n_markets", 0)
        e["asks"].append(_levels(b.get("asks")))
    return events


def field_cost(event, shares):
    """Cost per \$1 guaranteed payoff to buy `shares` YES in every outcome.

    A guaranteed \$1 lock requires filling EVERY outcome of the field. We compare
    the number of legs we can actually fill against the event's declared field
    size (`n_markets`), not just against the books we happened to collect — a
    field with unlisted/empty legs cannot be locked at all, so buying the
    available subset for < \$1 is NOT arbitrage (the winner may be an unfilled
    leg). Returns (cost, legs_filled, field_size, complete: bool)."""
    asks_per_market = event["asks"]
    field_size = event["n_markets"]  # declared number of mutually-exclusive outcomes
    cost = 0.0
    filled_legs = 0
    for asks in asks_per_market:
        avg, filled = vwap_buy(asks, shares)
        if filled >= shares and avg == avg:  # fully filled, not NaN
            cost += avg
            filled_legs += 1
    complete = filled_legs == field_size  # every outcome fillable at this size
    return cost, filled_legs, field_size, complete


def analyze(events, sizes, min_outcomes=3):
    rows = []
    for e in events.values():
        if e["n_markets"] < min_outcomes or len(e["asks"]) < min_outcomes:
            continue
        rec = {"title": e["title"], "n": e["n_markets"], "by_size": {}}
        for s in sizes:
            cost, filled, field_size, complete = field_cost(e, s)
            rec["by_size"][s] = {"cost": cost, "filled_legs": filled,
                                 "field_size": field_size, "complete": complete}
        rows.append(rec)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/books.json")
    ap.add_argument("--sizes", default="1,10,100,1000",
                    help="order sizes in shares to sweep")
    ap.add_argument("--min-outcomes", type=int, default=3)
    ap.add_argument("--fig", default="figures/depth_cost.png")
    args = ap.parse_args()

    sizes = [float(x) for x in args.sizes.split(",")]
    rows = analyze(load_events(args.inp), sizes, args.min_outcomes)
    print(f"negRisk events analyzed (>= {args.min_outcomes} outcomes, with books): {len(rows)}")
    print()
    print("Field-assembly cost per $1 guaranteed payoff (only COMPLETE fields —")
    print("every declared outcome fillable at the given size; incomplete fields")
    print("cannot be locked and are excluded, since the winner may be an empty leg):")
    print(f"{'size':>7} | {'complete fields':>15} | {'median cost':>11} | {'min cost (best arb)':>19}")
    complete_by_size = {}
    for s in sizes:
        full = [r for r in rows if r["by_size"][s]["complete"]]
        costs = [r["by_size"][s]["cost"] for r in full]
        complete_by_size[s] = full
        med = st.median(costs) if costs else float("nan")
        mn = min(costs) if costs else float("nan")
        print(f"{s:7.0f} | {len(full):15d} | {med:11.4f} | {mn:19.4f}")

    print()
    print("Reading: cost < 1.0 == real arbitrage at that size; cost > 1.0 == no free lunch.")
    print("A field only counts if ALL its outcomes are fillable — buying an available")
    print("subset for < $1 is not a lock when the winner may be an unlisted/empty leg.")

    # correlation: at the largest size, does per-$1 cost rise with field size n?
    big = max(sizes)
    full_big = complete_by_size[big]
    if len(full_big) >= 3:
        ns = [r["n"] for r in full_big]
        cs = [r["by_size"][big]["cost"] for r in full_big]
        if st.pstdev(ns) > 0 and st.pstdev(cs) > 0:
            mx, mc = st.mean(ns), st.mean(cs)
            cov = sum((x - mx) * (y - mc) for x, y in zip(ns, cs)) / len(ns)
            cor = cov / (st.pstdev(ns) * st.pstdev(cs))
            print(f"\ncorr(field size n, field cost at size {big:.0f}) = {cor:.3f}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.figure(figsize=(6, 4))
        for r in rows:
            xs = sizes
            ys = [r["by_size"][s]["cost"] if r["by_size"][s]["complete"]
                  else None for s in sizes]
            pts = [(x, y) for x, y in zip(xs, ys) if y is not None]
            if len(pts) >= 2:
                plt.plot([p[0] for p in pts], [p[1] for p in pts], alpha=0.35, color="steelblue")
        plt.axhline(1.0, color="crimson", lw=1, ls="--", label="$1 (fair / no-arb)")
        plt.xscale("log")
        plt.xlabel("Order size per leg (shares, log)")
        plt.ylabel("Cost to lock $1 payoff  (Σ vwap buy)")
        plt.title("Field-assembly cost vs order size")
        plt.legend()
        plt.tight_layout()
        plt.savefig(args.fig, dpi=120)
        print(f"figure -> {args.fig}")
    except ImportError:
        print("(matplotlib not installed — skipped figure)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
