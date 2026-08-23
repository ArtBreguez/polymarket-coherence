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
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(ROOT, "data", "panel.jsonl")
BACKUP = os.path.join(ROOT, "data", "panel_raw.jsonl.bak")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hygiene import ZOMBIE_EVENT_IDS as ZOMBIE_IDS  # noqa: E402  single source of truth
import panel_io  # noqa: E402  full-history file set (active + monthly archives)

CANONICAL_KEYS = ["ts", "event_id", "title", "n_markets", "volume", "end_date",
                  "size", "filled_legs", "fill_ratio", "complete", "lock_cost"]


def _read(path):
    rows = []
    if not os.path.exists(path):
        return rows
    for line in open(path):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # drop unparseable lines
    return rows


def main() -> int:
    # Clean across the FULL history so canonicalization (titles, end_date) is
    # consistent whether a row lives in the active file or a rolled archive.
    paths = panel_io.all_paths()
    all_rows = []
    for p in paths:
        for r in _read(p):
            all_rows.append((p, r))

    before = len(all_rows)
    all_rows = [(p, r) for (p, r) in all_rows if r.get("event_id") not in ZOMBIE_IDS]
    dropped = before - len(all_rows)

    # canonical title = the most recent title seen per event_id (rows are in file
    # order, i.e. chronological; archives sort before the active file)
    latest_title, latest_end = {}, {}
    for _p, r in all_rows:
        eid = r.get("event_id")
        latest_title[eid] = r.get("title", latest_title.get(eid))
        if r.get("end_date"):
            latest_end[eid] = r["end_date"]

    # one-time raw backup of the active file (git-ignored), matching prior behavior
    if not os.path.exists(BACKUP) and os.path.exists(PANEL):
        shutil.copy2(PANEL, BACKUP)
        print(f"raw backup -> {BACKUP}")

    # rewrite each file in place, preserving which file each row belongs to
    per_file = {}
    for p, r in all_rows:
        eid = r.get("event_id")
        norm = {k: r.get(k) for k in CANONICAL_KEYS}
        norm["title"] = latest_title.get(eid, r.get("title"))
        norm["end_date"] = r.get("end_date") or latest_end.get(eid)
        per_file.setdefault(p, []).append(norm)

    clean_total = 0
    for p in paths:
        rows = per_file.get(p, [])
        with open(p, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        clean_total += len(rows)

    n_events = len({r["event_id"] for _p, r in all_rows})
    print(f"cleaned panel across {len(paths)} file(s): {before} -> {clean_total} rows "
          f"({dropped} zombie rows dropped), {n_events} distinct events, "
          f"schema normalized to {len(CANONICAL_KEYS)} keys.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
