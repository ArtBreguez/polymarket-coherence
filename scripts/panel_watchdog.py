#!/usr/bin/env python3
"""Dead-man's-switch watchdog for the forward-panel collection.

Silent when healthy, speaks only when something is wrong — designed to run as a
no_agent Hermes cron (non-empty stdout => delivered as an alert; empty => quiet).

Why it watches the REMOTE, not the local file:
    Snapshots are pushed to origin/master by BOTH collectors (the local cron and
    the GitHub Actions failover). Checking the local working copy would miss the
    case "local cron died but the cloud is still pushing fine" — the local file
    would look stale while collection is actually healthy on the remote. So we
    fetch origin and read the newest snapshot timestamp there: that is the true
    output of the whole system, whoever produced it.

Respects the collection cutoff: once we're past COLLECT_UNTIL (+grace), the
collectors stop on purpose, so the watchdog goes silent instead of firing
forever.

Limitation (honest): a LOCAL watchdog cannot alert if the whole box is down —
it's down too. It covers the realistic modes (cloud primary fails, or a
collector script breaks while the box is up). For full box-down coverage, pair a
GitHub Action with an external dead-man's switch (e.g. healthchecks.io) — see the
skill/README note.

Exit code is always 0; the alerting channel is stdout (empty = healthy).
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess

REPO = "/home/ubuntu/polymarket-coherence"
BRANCH = "origin/master"
PANEL = "data/panel.jsonl"

# Alert if no new snapshot in this many minutes (cadence is 15 min; 40 gives ~2
# missed ticks of slack before paging, so a single delayed run won't false-alarm).
STALE_MINUTES = int(os.environ.get("PANEL_WATCHDOG_STALE_MIN", "40"))
# Match the collector's hard stop; go quiet a day after so the intentional end
# of collection is not reported as an outage.
COLLECT_UNTIL = os.environ.get("PANEL_COLLECT_UNTIL", "2026-11-10")
GRACE_DAYS_AFTER_CUTOFF = 1


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def _newest_ts_from(ref_file: str) -> dt.datetime | None:
    """Newest 'ts' in the panel at a given git ref:path (e.g. origin/master:data/panel.jsonl).

    After monthly rotation the active file holds the current month, whose max ts
    is the global max, so reading just the active file is sufficient and cheap.
    """
    code, out = _run(["git", "show", ref_file])
    if code != 0 or not out:
        return None
    newest = None
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # cheap parse: pull the ts value without full json.loads on every line
        i = line.find('"ts"')
        if i == -1:
            continue
        try:
            import json
            ts = json.loads(line).get("ts")
            t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            continue
        if newest is None or t > newest:
            newest = t
    return newest


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc)

    # Past the intentional cutoff (+grace): collection is over by design, stay silent.
    try:
        cutoff = dt.datetime.fromisoformat(COLLECT_UNTIL).replace(tzinfo=dt.timezone.utc)
        if now.date() > (cutoff + dt.timedelta(days=GRACE_DAYS_AFTER_CUTOFF)).date():
            return 0
    except ValueError:
        pass  # malformed cutoff -> keep watching

    # Refresh remote view; tolerate a transient network failure (fall back to
    # whatever origin ref we already have rather than false-alarming).
    _run(["git", "fetch", "--quiet", "origin", "master"], timeout=45)

    newest = _newest_ts_from(f"{BRANCH}:{PANEL}")
    if newest is None:
        # Could not read the remote panel at all — this itself is worth flagging,
        # but only if the local copy is also unreadable/stale (avoid crying wolf
        # on a pure network blip). Fall back to the local working file.
        newest = _newest_ts_from(f"HEAD:{PANEL}")
    if newest is None:
        print("⚠️ polymarket-coherence watchdog: cannot read the panel on origin "
              "OR locally — collection state unknown. Check the repo/network.")
        return 0

    age_min = (now - newest).total_seconds() / 60
    if age_min >= STALE_MINUTES:
        hrs = age_min / 60
        span = f"{age_min:.0f} min" if age_min < 120 else f"{hrs:.1f} h"
        print(
            f"🔴 polymarket-coherence: no new snapshot in {span} "
            f"(newest {newest.isoformat(timespec='minutes')}, threshold {STALE_MINUTES} min).\n"
            f"Both collectors (local cron + GitHub Actions failover) appear stalled. "
            f"Check: local Hermes cron 9dd581af3bdc, and the 'forward-panel (cloud failover)' Action."
        )
    # healthy -> print nothing (silent = OK)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
