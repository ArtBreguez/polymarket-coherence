#!/usr/bin/env python3
"""Panel analyzer: read the forward time series (panel.jsonl) and quantify how
often and for how long executable sub-\$1 lock windows actually open in
Polymarket negRisk events — the question a single snapshot cannot answer.

For each event across all snapshots it reports:
  - snapshots seen, and how many had a COMPLETE (lockable) field
  - min / median lock cost over complete snapshots
  - executable_rate: fraction of complete snapshots with lock_cost < 1.0
  - longest run of consecutive complete snapshots with lock_cost < 1.0
    (a proxy for window persistence, in snapshot units)

Then it prints panel-level summaries: how many events EVER showed an executable
window, and the distribution of lock cost over all complete observations.

Pure stdlib. Reads data/panel.jsonl (one JSON object per line).

Usage:
    python scripts/analyze_panel.py --in data/panel.jsonl
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict


def load(path):
    snaps = defaultdict(list)  # event_id -> list of records (in file order)
    all_ts = set()
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        snaps[r["event_id"]].append(r)
        all_ts.add(r["ts"])
    return snaps, sorted(all_ts)


def longest_executable_run(records):
    """Longest run of consecutive snapshots that are complete AND lock_cost<1."""
    best = cur = 0
    for r in sorted(records, key=lambda x: x["ts"]):
        if r["complete"] and r["lock_cost"] is not None and r["lock_cost"] < 1.0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/panel.jsonl")
    ap.add_argument("--threshold", type=float, default=1.0,
                    help="lock cost below which a field is an executable arbitrage")
    args = ap.parse_args()

    snaps, all_ts = load(args.inp)
    n_snapshots = len(all_ts)
    print(f"panel: {n_snapshots} snapshots, {len(snaps)} distinct events")
    if n_snapshots >= 2:
        print(f"       span {all_ts[0]}  ->  {all_ts[-1]}")
    print()

    per_event = []
    all_complete_costs = []
    ever_executable = 0
    for eid, recs in snaps.items():
        complete = [r for r in recs if r["complete"] and r["lock_cost"] is not None]
        costs = [r["lock_cost"] for r in complete]
        all_complete_costs.extend(costs)
        execs = [c for c in costs if c < args.threshold]
        if execs:
            ever_executable += 1
        per_event.append({
            "title": recs[0]["title"],
            "n": recs[0]["n_markets"],
            "seen": len(recs),
            "complete": len(complete),
            "min_cost": min(costs) if costs else None,
            "median_cost": st.median(costs) if costs else None,
            "exec_rate": (len(execs) / len(complete)) if complete else 0.0,
            "longest_run": longest_executable_run(recs),
        })

    print("Per-event (events that were complete at least once), by min lock cost:")
    print(f"{'n':>4} {'seen':>4} {'compl':>5} {'min':>7} {'med':>7} {'exec%':>6} {'run':>4}  title")
    shown = [e for e in per_event if e["complete"] > 0]
    for e in sorted(shown, key=lambda x: (x["min_cost"] if x["min_cost"] is not None else 9)):
        print(f"{e['n']:4} {e['seen']:4} {e['complete']:5} "
              f"{e['min_cost']:7.4f} {e['median_cost']:7.4f} "
              f"{100*e['exec_rate']:5.0f}% {e['longest_run']:4}  {str(e['title'])[:40]}")

    print()
    print("=== Panel summary ===")
    print(f"events complete >=1 snapshot : {len(shown)} / {len(snaps)}")
    print(f"events EVER executable (<{args.threshold:g}) : {ever_executable} / {len(snaps)}")
    if all_complete_costs:
        print(f"lock cost over all complete observations: "
              f"min={min(all_complete_costs):.4f} "
              f"median={st.median(all_complete_costs):.4f} "
              f"max={max(all_complete_costs):.4f}  (n={len(all_complete_costs)})")
    if n_snapshots < 3:
        print("\nNOTE: window-persistence (longest_run) is only meaningful with more")
        print("snapshots. Run collect_forward.py on a schedule to grow the panel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
