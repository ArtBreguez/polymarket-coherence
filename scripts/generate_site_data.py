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
import panel_io  # noqa: E402  full-history reader (active file + monthly archives)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL = os.path.join(ROOT, "data", "panel.jsonl")
OUTDIR = os.path.join(ROOT, "docs", "data")


def load_panel():
    rows = []
    # Read the FULL history: active panel.jsonl plus any rolled-over monthly
    # archives (panel-YYYY-MM.jsonl). panel_io is the single source of truth for
    # where rows live, so rotation never hides data from the dashboard.
    for r in panel_io.iter_rows():
        if r.get("event_id") in EXCLUDED_EVENT_IDS:
            continue  # drop known zombie (expired) markets from the site view
        rows.append(r)
    return rows


def window_stats(rows):
    """Persistence and depth of sub-$1 windows, per the panel records.

    Extracted from main() so it can be unit-tested. Returns the longest unbroken
    sub-$1 run, the deepest print, AND the deepest cost inside that longest run.

    That last value is the point: the longest run and the deepest print are not
    necessarily the same episode. In the committed panel the longest run (31.2h)
    bottoms at 0.994 while the deepest print (0.973) sits in a shorter ~12.7h run
    five days later. Reporting run length beside the global best, with nothing
    tying them together, reads as "the 2.7% edge lasted 31 hours" — which the
    data does not show.
    """
    ev_hist = defaultdict(list)
    for r in rows:
        ev_hist[r["event_id"]].append(r)

    out = {
        "ever_exec": 0,
        "all_costs": [],
        "complete_events": 0,
        "sub_dollar_obs": 0,
        "sub_dollar_titles": set(),
        "best_run_snaps": 0,
        "best_run_snaps_cost": None,
        "best_lock_cost": None,
        "best_lock_end_date": None,
        "best_lock_ts": None,
    }

    for recs in ev_hist.values():
        cc = [x["lock_cost"] for x in recs
              if x.get("complete") and x.get("lock_cost") is not None]
        out["all_costs"].extend(cc)
        if cc:
            out["complete_events"] += 1
        subs = [c for c in cc if c < 1.0]
        out["sub_dollar_obs"] += len(subs)
        if not subs:
            continue
        out["ever_exec"] += 1

        # every field that crossed sub-$1, not just one of them
        for x in recs:
            if (x.get("complete") and x.get("lock_cost") is not None
                    and x["lock_cost"] < 1.0 and x.get("title")):
                out["sub_dollar_titles"].add(x["title"])

        ordered = sorted(recs, key=lambda r: r.get("ts", ""))

        # deepest lock cost across this event's sub-$1 observations
        for x in ordered:
            lc = x.get("lock_cost")
            if x.get("complete") and lc is not None and lc < 1.0:
                if out["best_lock_cost"] is None or lc < out["best_lock_cost"]:
                    out["best_lock_cost"] = lc
                    out["best_lock_end_date"] = x.get("end_date")
                    out["best_lock_ts"] = x.get("ts")

        # longest consecutive sub-$1 run, carrying the best cost inside it
        cur = 0
        cur_min = None
        for x in ordered:
            lc = x.get("lock_cost")
            if x.get("complete") and lc is not None and lc < 1.0:
                cur += 1
                cur_min = lc if cur_min is None else min(cur_min, lc)
                if cur > out["best_run_snaps"]:
                    out["best_run_snaps"] = cur
                    out["best_run_snaps_cost"] = cur_min
            else:
                cur = 0
                cur_min = None

    return out


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
    # All of this lives in window_stats() so it is unit-testable; the two
    # defects it now guards against were reporting bugs, not math bugs.
    ev_hist = defaultdict(list)
    for r in rows:
        ev_hist[r["event_id"]].append(r)
    ws = window_stats(rows)
    ever_exec = ws["ever_exec"]
    all_costs = ws["all_costs"]
    complete_events = ws["complete_events"]
    sub_dollar_obs = ws["sub_dollar_obs"]
    sub_dollar_titles = ws["sub_dollar_titles"]
    best_run_snaps = ws["best_run_snaps"]
    best_run_snaps_cost = ws["best_run_snaps_cost"]
    best_lock_cost = ws["best_lock_cost"]
    best_lock_end_date = ws["best_lock_end_date"]
    best_lock_ts = ws["best_lock_ts"]

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

    # duration span in hours (first→last snapshot), for prose that cites "~Nh"
    hours_span = None
    if len(snapshots) >= 2:
        t0 = dt.datetime.fromisoformat(snapshots[0].replace("Z", "+00:00"))
        t1 = dt.datetime.fromisoformat(snapshots[-1].replace("Z", "+00:00"))
        hours_span = round((t1 - t0).total_seconds() / 3600)

    # Persistence + annualized economics of the deepest window (all derived, no
    # hand-typed numbers). gross_edge_pct = 1 - lock_cost. The capital is locked
    # until the field resolves (end_date), so the honest return is annualized over
    # that horizon — this is what shows a persistent window still isn't a lunch.
    best_run_hours = round(best_run_snaps * 15 / 60, 1) if best_run_snaps else 0
    best_edge_pct = round(100 * (1 - best_lock_cost), 2) if best_lock_cost is not None else None
    best_annualized_pct = None
    if best_lock_cost is not None and best_lock_end_date and best_lock_ts:
        try:
            t_obs = dt.datetime.fromisoformat(best_lock_ts.replace("Z", "+00:00"))
            t_end = dt.datetime.fromisoformat(best_lock_end_date.replace("Z", "+00:00"))
            days_locked = (t_end - t_obs).total_seconds() / 86400
            if days_locked > 0:
                gross = (1.0 - best_lock_cost) / best_lock_cost  # return on cost
                best_annualized_pct = round(100 * gross * (365 / days_locked), 2)
        except (ValueError, AttributeError):
            best_annualized_pct = None

    summary = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "snapshots": len(snapshots),
        "hours_span": hours_span,
        "first_snapshot": snapshots[0] if snapshots else None,
        "last_snapshot": snapshots[-1] if snapshots else None,
        "distinct_events": len(ev_hist),
        "complete_events": complete_events,
        "ever_executable": ever_exec,
        "cost_min": round(min(all_costs), 4) if all_costs else None,
        "cost_median": round(st.median(all_costs), 4) if all_costs else None,
        "cost_max": round(max(all_costs), 4) if all_costs else None,
        "n_cost_obs": len(all_costs),
        "sub_dollar_obs": sub_dollar_obs,
        "sub_dollar_pct": round(100 * sub_dollar_obs / len(all_costs), 1) if all_costs else None,
        "sub_dollar_field": sorted(sub_dollar_titles)[0] if sub_dollar_titles else None,
        "sub_dollar_fields": sorted(sub_dollar_titles),
        "sub_dollar_field_count": len(sub_dollar_titles),
        "best_window_run_snaps": best_run_snaps,
        "best_window_run_hours": best_run_hours,
        "best_run_edge_pct": (round(100 * (1 - best_run_snaps_cost), 2)
                              if best_run_snaps_cost is not None else None),
        "best_edge_pct": best_edge_pct,
        "best_annualized_pct": best_annualized_pct,
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
