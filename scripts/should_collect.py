#!/usr/bin/env python3
"""Failover gate: should the CLOUD collector run this tick?

The forward panel is normally collected by the local machine every 15 min. This
GitHub Actions job is a REDUNDANCY for when the local box is down — it must not
double-collect or race the local push when local is healthy.

Rule: the cloud runs ONLY if the newest snapshot already in the panel is older
than STALE_MINUTES (default 25). With local healthy (a push every ~15 min) the
newest row is always fresh, so the cloud gate fails and the job exits silently.
If local has been quiet longer than the threshold, the cloud steps in.

Reads the newest 'ts' across the full panel history (active file + archives) via
panel_io, so it works regardless of rotation. Pure stdlib.

Exit codes:
  0  -> should collect (panel is stale / empty)  -> workflow proceeds
  10 -> fresh, do NOT collect                    -> workflow stops silently
"""
from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel_io  # noqa: E402

STALE_MINUTES = int(os.environ.get("PANEL_STALE_MINUTES", "25"))


def newest_ts() -> dt.datetime | None:
    newest = None
    for r in panel_io.iter_rows():
        ts = r.get("ts")
        if not isinstance(ts, str):
            continue
        try:
            t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if newest is None or t > newest:
            newest = t
    return newest


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc)
    latest = newest_ts()
    if latest is None:
        print("panel empty -> collect")
        return 0
    age_min = (now - latest).total_seconds() / 60
    if age_min >= STALE_MINUTES:
        print(f"newest snapshot {age_min:.0f} min old (>= {STALE_MINUTES}) "
              f"-> local looks down, cloud collects")
        return 0
    print(f"newest snapshot {age_min:.0f} min old (< {STALE_MINUTES}) "
          f"-> local healthy, cloud skips")
    return 10


if __name__ == "__main__":
    raise SystemExit(main())
