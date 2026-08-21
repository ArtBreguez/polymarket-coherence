#!/usr/bin/env python3
"""Clean and canonicalize the forward panel.

The raw panel.jsonl is an honest append-only collection log, but it accumulated
three hygiene issues over its first day:
  1. Zombie markets (expired but still closed=false) captured before the endDate
     filter existed — event_ids in ZOMBIE_IDS.
  2. Schema drift — early rows lack the `end_date` field added later.
  3. One event whose title Polymarket renamed mid-run (same event_id).

This script rewrites data/panel.jsonl in place as a canonical, clean series:
  - drops zombie event_ids,
  - backfills a stable `end_date` key on every row (None where unknown),
  - canonicalizes each event_id to its most recent title,
  - preserves every valid observation and their timestamps.

The pre-clean file is backed up to data/panel_raw.jsonl.bak (git-ignored) so the
unedited record survives. Idempotent: running twice is a no-op.

Usage:
    python scripts/clean_panel.py
"""
from __future__ import annotations

import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(ROOT, "data", "panel.jsonl")
BACKUP = os.path.join(ROOT, "data", "panel_raw.jsonl.bak")

# Expired-but-still-open markets collected before the endDate filter landed.
ZOMBIE_IDS = {
    "831375",  # Next Prime Minister of Ethiopia? (endDate 2026-06-01)
    "411239",  # Elon Musk # tweets August 14 - August 21, 2026?
}

CANONICAL_KEYS = ["ts", "event_id", "title", "n_markets", "volume", "end_date",
                  "size", "filled_legs", "fill_ratio", "complete", "lock_cost"]


def main() -> int:
    rows = []
    for line in open(PANEL):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # drop unparseable lines

    before = len(rows)
    rows = [r for r in rows if r.get("event_id") not in ZOMBIE_IDS]
    dropped = before - len(rows)

    # canonical title = the most recent title seen per event_id (rows are in file
    # order, i.e. chronological)
    latest_title, latest_end = {}, {}
    for r in rows:
        eid = r.get("event_id")
        latest_title[eid] = r.get("title", latest_title.get(eid))
        if r.get("end_date"):
            latest_end[eid] = r["end_date"]

    clean = []
    for r in rows:
        eid = r.get("event_id")
        norm = {k: r.get(k) for k in CANONICAL_KEYS}
        norm["title"] = latest_title.get(eid, r.get("title"))
        norm["end_date"] = r.get("end_date") or latest_end.get(eid)
        clean.append(norm)

    if not os.path.exists(BACKUP):
        shutil.copy2(PANEL, BACKUP)
        print(f"raw backup -> {BACKUP}")

    with open(PANEL, "w") as f:
        for r in clean:
            f.write(json.dumps(r) + "\n")

    n_events = len({r["event_id"] for r in clean})
    print(f"cleaned panel: {before} -> {len(clean)} rows "
          f"({dropped} zombie rows dropped), {n_events} distinct events, "
          f"schema normalized to {len(CANONICAL_KEYS)} keys.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
