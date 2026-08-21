#!/usr/bin/env python3
"""Generate the compact JSON the GitHub Pages dashboard consumes.

Reads the growing panel (data/panel.jsonl) and the depth snapshot
(data/books.json) and writes small, browser-friendly files to docs/data/ so the
page never has to parse the raw JSONL:

  docs/data/summary.json     headline stats (updated every cron run)
  docs/data/timeseries.json  per-snapshot aggregates for the time chart
  docs/data/events.json      latest per-event lock cost / completeness table

Pure stdlib. Safe to run repeatedly (idempotent overwrite).

Usage:
    python scripts/generate_site_data.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import statistics as st
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hygiene import ZOMBIE_EVENT_IDS as EXCLUDED_EVENT_IDS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(ROOT, "data", "panel.jsonl")
OUTDIR = os.path.join(ROOT, "docs", "data")


def load_panel():
    rows = []
    if not os.path.exists(PANEL):
        return rows
    for line in open(PANEL):
        line = line.strip()
        if line:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("event_id") in EXCLUDED_EVENT_IDS:
                continue  # drop known zombie (expired) markets from the site view
            rows.append(r)
    return rows


def main() -> int:
    os.makedirs(OUTDIR, exist_ok=True)
    rows = load_panel()
    by_ts = defaultdict(list)
    for r in rows:
        by_ts[r["ts"]].append(r)
    snapshots = sorted(by_ts)

    # ---- timeseries: one point per snapshot ----
    timeseries = []
    for ts in snapshots:
        recs = by_ts[ts]
        complete = [r for r in recs if r.get("complete") and r.get("lock_cost") is not None]
        costs = [r["lock_cost"] for r in complete]
        execs = [c for c in costs if c < 1.0]
        timeseries.append({
            "ts": ts,
            "events": len(recs),
            "complete": len(complete),
            "executable": len(execs),
            "min_cost": round(min(costs), 4) if costs else None,
            "median_cost": round(st.median(costs), 4) if costs else None,
        })

    # ---- events: latest snapshot, per-event ----
    events = []
    if snapshots:
        latest = by_ts[snapshots[-1]]
        for r in sorted(latest, key=lambda x: (x.get("lock_cost") is None, x.get("lock_cost") or 9)):
            events.append({
                "title": r.get("title"),
                "n_markets": r.get("n_markets"),
                "fill_ratio": r.get("fill_ratio"),
                "complete": r.get("complete"),
                "lock_cost": r.get("lock_cost"),
            })

    # ---- per-event history for "ever executable" + persistence ----
    ev_hist = defaultdict(list)
    for r in rows:
        ev_hist[r["event_id"]].append(r)
    ever_exec = 0
    all_costs = []
    for recs in ev_hist.values():
        cc = [x["lock_cost"] for x in recs if x.get("complete") and x.get("lock_cost") is not None]
        all_costs.extend(cc)
        if any(c < 1.0 for c in cc):
            ever_exec += 1

    # small/large liquidity structure on the latest snapshot
    small = large = small_complete = large_complete = 0
    small_fill = []
    large_fill = []
    if snapshots:
        for r in by_ts[snapshots[-1]]:
            n = r.get("n_markets") or 0
            fr = r.get("fill_ratio")
            if n <= 20:
                small += 1
                small_complete += 1 if r.get("complete") else 0
                if fr is not None:
                    small_fill.append(fr)
            else:
                large += 1
                large_complete += 1 if r.get("complete") else 0
                if fr is not None:
                    large_fill.append(fr)

    summary = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "snapshots": len(snapshots),
        "first_snapshot": snapshots[0] if snapshots else None,
        "last_snapshot": snapshots[-1] if snapshots else None,
        "distinct_events": len(ev_hist),
        "ever_executable": ever_exec,
        "cost_min": round(min(all_costs), 4) if all_costs else None,
        "cost_median": round(st.median(all_costs), 4) if all_costs else None,
        "cost_max": round(max(all_costs), 4) if all_costs else None,
        "n_cost_obs": len(all_costs),
        "liquidity_structure": {
            "small_n": small, "small_complete_pct": round(100 * small_complete / small) if small else None,
            "small_median_fill_pct": round(100 * st.median(small_fill)) if small_fill else None,
            "large_n": large, "large_complete_pct": round(100 * large_complete / large) if large else None,
            "large_median_fill_pct": round(100 * st.median(large_fill)) if large_fill else None,
        },
    }

    for name, obj in (("summary.json", summary),
                      ("timeseries.json", timeseries),
                      ("events.json", events)):
        with open(os.path.join(OUTDIR, name), "w") as f:
            json.dump(obj, f, indent=2)

    # ---- cross-market LOOP (optional; live network) ----
    try:
        loop_spec = os.path.join(os.path.dirname(__file__), "analyze_loop.py")
        import importlib.util
        spec = importlib.util.spec_from_file_location("analyze_loop", loop_spec)
        alm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(alm)
        matches_path = os.path.join(ROOT, "data", "event_matches.json")
        loop_results = alm.analyze(matches_path)
        loop_obj = {
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "results": loop_results,
        }
        with open(os.path.join(OUTDIR, "loop.json"), "w") as f:
            json.dump(loop_obj, f, indent=2)
        print(f"  cross-market loop.json written ({len(loop_results)} matched events)")
    except Exception as e:  # noqa: BLE001 — network optional; keep site data flowing
        print(f"  (loop.json skipped: {e})")

    print(f"site data written to docs/data/ — {len(snapshots)} snapshots, "
          f"{len(ev_hist)} events, ever_executable={ever_exec}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
