#!/usr/bin/env python3
"""Collect full L2 order books for every child market of Polymarket negRisk
(mutually-exclusive) events.

This is what lets the study go beyond top-of-book: with full depth we can ask
how much it *actually* costs to assemble the whole field and lock the \$1 payoff
for a given order size — the depth-aware executable-coherence question.

Two-stage, public data only (no key, no wallet):
  1. Gamma /events  -> negRisk events + their child markets' clobTokenIds.
  2. CLOB  /books    -> batched L2 books (bids/asks with price+size) per token.

Writes:
  data/books.json      raw L2 books keyed by token_id (+ event metadata)
  data/books.manifest.json  snapshot time, counts, source

Usage:
    python scripts/collect_depth.py --limit 500 --out data/books.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
import urllib.parse
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
BATCH = 40  # tokens per /books POST — polite and well within limits


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


def _get(url: str):
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "polymarket-coherence/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))


def _post(url: str, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "polymarket-coherence/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read())
        except Exception:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))


def collect(limit: int):
    events = _get(f"{GAMMA}/events?" + urllib.parse.urlencode(
        {"closed": "false", "limit": limit, "order": "volume", "ascending": "false"}))

    # token_id -> {event_id, event_title, n_markets, question, volume}
    meta: dict[str, dict] = {}
    tokens: list[str] = []
    for e in events:
        if not e.get("negRisk"):
            continue
        if is_expired(e.get("endDate")):
            continue  # skip zombie markets: past endDate but still closed=false
        markets = e.get("markets", [])
        n = len(markets)
        for m in markets:
            ids = m.get("clobTokenIds")
            if not ids:
                continue
            try:
                yes_token = json.loads(ids)[0]  # [0] == YES leg
            except (ValueError, IndexError):
                continue
            meta[yes_token] = {
                "event_id": e.get("id"),
                "event_title": e.get("title"),
                "n_markets": n,
                "question": m.get("question"),
                "event_volume": e.get("volume"),
            }
            tokens.append(yes_token)

    books: dict[str, dict] = {}
    for i in range(0, len(tokens), BATCH):
        chunk = tokens[i:i + BATCH]
        resp = _post(f"{CLOB}/books", [{"token_id": t} for t in chunk])
        for book in resp or []:
            tok = book.get("asset_id") or book.get("token_id")
            if tok:
                books[tok] = {"bids": book.get("bids", []),
                              "asks": book.get("asks", []),
                              **meta.get(tok, {})}
        print(f"  fetched books {i + len(chunk)}/{len(tokens)}", flush=True)
        time.sleep(0.3)  # be gentle

    manifest = {
        "snapshot_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_events": f"{GAMMA}/events?closed=false&order=volume",
        "source_books": f"{CLOB}/books (batched POST)",
        "events_scanned": len(events),
        "tokens_requested": len(tokens),
        "books_returned": len(books),
    }
    return books, manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--out", default="data/books.json")
    args = ap.parse_args()

    books, manifest = collect(args.limit)
    with open(args.out, "w") as f:
        json.dump(books, f)
    mpath = args.out.rsplit(".", 1)[0] + ".manifest.json"
    with open(mpath, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote {len(books)} L2 books -> {args.out}")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
