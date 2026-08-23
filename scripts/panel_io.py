#!/usr/bin/env python3
"""Shared panel I/O: the active append file plus rolled-over monthly archives.

Why this exists
    The forward-panel cron appends one line per event every 15 min and commits
    the file each time. A single ever-growing ``panel.jsonl`` makes every commit
    re-store the whole file, so the git repo grows ~O(N^2). Monthly rotation
    fixes that: once a calendar month closes, its rows are split into an
    immutable ``panel-YYYY-MM.jsonl`` that never changes again (git stores it
    once), and the active ``panel.jsonl`` only ever holds the current month, so
    each commit's diff stays bounded.

    Analysis must still see the FULL history, so every reader loads the active
    file *and* all archives via ``iter_rows()`` / ``all_paths()``. This module is
    the single source of truth for where panel rows live.

Pure stdlib. Idempotent rotation.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
from collections import defaultdict

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
ACTIVE = os.path.join(DATA_DIR, "panel.jsonl")
ARCHIVE_GLOB = os.path.join(DATA_DIR, "panel-*.jsonl")


def _month_of(row: dict) -> str | None:
    """Return the 'YYYY-MM' bucket for a row's timestamp, or None if unusable."""
    ts = row.get("ts")
    if not isinstance(ts, str) or len(ts) < 7:
        return None
    ym = ts[:7]
    # cheap sanity check: 'YYYY-MM'
    if len(ym) == 7 and ym[4] == "-" and ym[:4].isdigit() and ym[5:].isdigit():
        return ym
    return None


def archive_paths() -> list[str]:
    """All monthly archive files, chronologically sorted (name sorts by date)."""
    return sorted(glob.glob(ARCHIVE_GLOB))


def all_paths() -> list[str]:
    """Every file holding panel rows: archives first, then the active file."""
    paths = archive_paths()
    if os.path.exists(ACTIVE):
        paths.append(ACTIVE)
    return paths


def iter_rows(paths: list[str] | None = None):
    """Yield parsed rows across the full history (archives + active), in order.

    Unparseable lines are skipped so a partial final write can't abort a read.
    """
    for path in (paths if paths is not None else all_paths()):
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            continue


def _read_rows(path: str) -> list[dict]:
    rows: list[dict] = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def rotate(now: dt.datetime | None = None) -> dict:
    """Split closed-month rows out of the active file into monthly archives.

    A "closed" month is any month earlier than ``now``'s month. Current-month
    rows stay in the active file (still being appended to). Rows already in an
    archive are left untouched. Idempotent: with nothing to roll over it is a
    no-op and touches no files (so the cron's `git diff` stays empty).

    Returns a summary dict: {"rotated_months": [...], "moved_rows": N,
    "kept_rows": M}.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    current_ym = f"{now.year:04d}-{now.month:02d}"

    rows = _read_rows(ACTIVE)
    if not rows:
        return {"rotated_months": [], "moved_rows": 0, "kept_rows": 0}

    keep: list[dict] = []
    closed: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        ym = _month_of(r)
        # Unknown/undated rows are conservative-kept in the active file rather
        # than misfiled into an archive.
        if ym is None or ym >= current_ym:
            keep.append(r)
        else:
            closed[ym].append(r)

    if not closed:
        return {"rotated_months": [], "moved_rows": 0, "kept_rows": len(keep)}

    # Append each closed month's rows to its archive (create or extend), then
    # rewrite the active file with only the kept rows.
    for ym, month_rows in sorted(closed.items()):
        arch = os.path.join(DATA_DIR, f"panel-{ym}.jsonl")
        with open(arch, "a") as f:
            for r in month_rows:
                f.write(json.dumps(r) + "\n")

    with open(ACTIVE, "w") as f:
        for r in keep:
            f.write(json.dumps(r) + "\n")

    return {
        "rotated_months": sorted(closed),
        "moved_rows": sum(len(v) for v in closed.values()),
        "kept_rows": len(keep),
    }


if __name__ == "__main__":
    summary = rotate()
    if summary["moved_rows"]:
        print(
            f"rotated {summary['moved_rows']} rows into "
            f"{summary['rotated_months']}; {summary['kept_rows']} kept in active"
        )
