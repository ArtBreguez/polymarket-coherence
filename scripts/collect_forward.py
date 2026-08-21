#!/usr/bin/env python3
"""Forward panel collector: take one timestamped snapshot of executable coherence
for every Polymarket negRisk (mutually-exclusive) event and APPEND it to a JSONL
time series. Run it on a schedule (e.g. every 15 min) to build a panel that
answers what a single snapshot cannot: *how often and for how long do real,
executable sub-\$1 lock windows actually open?*

Each run appends one JSON line per event with, at a fixed order size:
  - lock_cost: Σ vwap-buy over ALL outcomes (only if the field is complete)
  - complete: whether every declared outcome was fillable
  - fill_ratio: fraction of declared outcomes that had a fillable book
  - n_markets, event volume, and the snapshot timestamp

Public data only (Gamma /events + CLOB /books). No key, no wallet.

Usage:
    python scripts/collect_forward.py --size 100 --limit 500 --out data/panel.jsonl
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hygiene import http_json, gamma_events, live_negrisk_events  # noqa: E402

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
BATCH = 40


def _req(url, data=None):
    """Thin wrapper kept for call-site compatibility; delegates to hygiene."""
    return http_json(url, data=data, timeout=45)


def vwap_buy(asks, shares):
    """Avg price to BUY `shares`, cheapest ask first. Returns (avg, filled)."""
    levels = []
    for lvl in asks or []:
        try:
            levels.append((float(lvl["price"]), float(lvl["size"])))
        except (KeyError, TypeError, ValueError):
            continue
    levels.sort(key=lambda x: x[0])
    need, cost = shares, 0.0
    for price, size in levels:
        if need <= 0:
            break
        take = min(need, size)
        cost += take * price
        need -= take
    filled = shares - need
    return (cost / filled if filled > 0 else float("nan")), filled


def snapshot(size: float, limit: int):
    events = gamma_events(limit=limit)

    # token -> event; collect the YES token per child market.
    # live_negrisk_events applies all shared hygiene: negRisk-only, >=3 outcomes,
    # and zombie/expired exclusion — the single choke point for this pull.
    ev_tokens: dict[str, list[str]] = {}
    ev_meta: dict[str, dict] = {}
    tok_all: list[str] = []
    for e in live_negrisk_events(events, min_outcomes=1):
        eid = str(e.get("id"))
        toks = []
        for m in e.get("markets", []):
            ids = m.get("clobTokenIds")
            if not ids:
                continue
            try:
                toks.append(json.loads(ids)[0])
            except (ValueError, IndexError):
                continue
        if not toks:
            continue
        ev_tokens[eid] = toks
        ev_meta[eid] = {"title": e.get("title"),
                        "n_markets": len(e.get("markets", [])),
                        "volume": e.get("volume"),
                        "end_date": e.get("endDate")}
        tok_all.extend(toks)

    # fetch books in batches
    books: dict[str, list] = {}
    for i in range(0, len(tok_all), BATCH):
        chunk = tok_all[i:i + BATCH]
        resp = _req(f"{CLOB}/books", [{"token_id": t} for t in chunk]) or []
        for b in resp:
            tok = b.get("asset_id") or b.get("token_id")
            if tok:
                books[tok] = b.get("asks", [])
        time.sleep(0.3)

    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    rows = []
    for eid, toks in ev_tokens.items():
        meta = ev_meta[eid]
        n = meta["n_markets"]
        if n < 3:
            continue
        cost = 0.0
        filled_legs = 0
        for t in toks:
            avg, filled = vwap_buy(books.get(t, []), size)
            if filled >= size and avg == avg:
                cost += avg
                filled_legs += 1
        complete = filled_legs == n
        rows.append({
            "ts": ts,
            "event_id": eid,
            "title": meta["title"],
            "n_markets": n,
            "volume": meta["volume"],
            "end_date": meta.get("end_date"),
            "size": size,
            "filled_legs": filled_legs,
            "fill_ratio": round(filled_legs / n, 4) if n else None,
            "complete": complete,
            "lock_cost": round(cost, 6) if complete else None,
        })
    return rows, ts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=float, default=100.0, help="order size per leg (shares)")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--out", default="data/panel.jsonl")
    args = ap.parse_args()

    rows, ts = snapshot(args.size, args.limit)
    with open(args.out, "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    complete = [r for r in rows if r["complete"]]
    arb = [r for r in complete if r["lock_cost"] < 1.0]
    print(f"[{ts}] appended {len(rows)} events -> {args.out} "
          f"(complete: {len(complete)}, executable <$1: {len(arb)})")
    if arb:
        for r in sorted(arb, key=lambda x: x["lock_cost"])[:5]:
            print(f"    LOCK<$1  cost={r['lock_cost']:.4f}  n={r['n_markets']}  {str(r['title'])[:45]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
