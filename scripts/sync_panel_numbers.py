#!/usr/bin/env python3
"""Keep the panel numbers in README.md / FINDINGS.md in sync with the live data.

The forward-panel cron grows data/panel.jsonl every 15 min, so any hard-coded
count in the prose ("183 snapshots", "915 observations", …) drifts out of date
within days. This script makes docs/data/summary.json the single source of truth:
it rewrites only the spans between explicit anchor comments, so it can never
corrupt surrounding prose and is safe to run on every cron tick.

Anchor form (inline):   <!--panel:KEY-->TEXT<!--/panel:KEY-->
The script replaces TEXT with the freshly formatted value for KEY.

Pure stdlib. Idempotent. Exit codes:
  0  files already in sync (nothing written), or --write made them match
  1  --check found drift (nothing written)   [use as a CI/pre-publish gate]
  2  error (missing summary, unknown key, malformed anchor)

Usage:
  python scripts/sync_panel_numbers.py           # rewrite in place
  python scripts/sync_panel_numbers.py --check    # report drift, write nothing
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMMARY = os.path.join(ROOT, "docs", "data", "summary.json")
TARGETS = [os.path.join(ROOT, "README.md"), os.path.join(ROOT, "FINDINGS.md")]

ANCHOR = re.compile(r"(<!--panel:([a-z_]+)-->)(.*?)(<!--/panel:\2-->)", re.DOTALL)


def formatters(s: dict) -> dict[str, str]:
    """Map anchor KEY -> the exact text that belongs between its markers.

    Every value is derived from summary.json; nothing is hand-typed. Keep the
    rendered strings free of Markdown so anchors can sit inside **bold**/prose
    without the sync fighting the surrounding formatting.
    """
    return {
        "snapshots": str(s["snapshots"]),
        "hours": f"~{s['hours_span']}h",
        "distinct_events": str(s["distinct_events"]),
        "complete_events": f"{s['complete_events']}/{s['distinct_events']}",
        "complete_events_of": f"{s['complete_events']} of {s['distinct_events']}",
        "ever_executable": f"{s['ever_executable']}/{s['distinct_events']}",
        "ever_executable_of": f"{s['ever_executable']} of {s['distinct_events']}",
        "n_obs": str(s["n_cost_obs"]),
        "cost_min": f"{s['cost_min']:.3f}",
        "cost_median": f"{s['cost_median']:.3f}",
        "cost_max": f"{s['cost_max']:.3f}",
        "sub_dollar": f"{s['sub_dollar_obs']}/{s['n_cost_obs']}",
        "sub_dollar_of": f"{s['sub_dollar_obs']} of {s['n_cost_obs']}",
        "sub_dollar_pct": f"{s['sub_dollar_pct']}%",
        "sub_dollar_field": str(s["sub_dollar_field"]),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="Report drift and exit 1 if any; write nothing.")
    args = ap.parse_args(argv)

    if not os.path.exists(SUMMARY):
        print(f"error: {SUMMARY} not found — run generate_site_data.py first",
              file=sys.stderr)
        return 2
    s = json.load(open(SUMMARY))
    values = formatters(s)

    drift = False
    unknown: set[str] = set()
    for path in TARGETS:
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()

        def repl(m: re.Match) -> str:
            open_tag, key, cur, close_tag = m.groups()
            if key not in values:
                unknown.add(key)
                return m.group(0)
            return f"{open_tag}{values[key]}{close_tag}"

        new = ANCHOR.sub(repl, text)
        if new != text:
            drift = True
            if args.check:
                # show which keys changed for a useful gate message
                for m in ANCHOR.finditer(text):
                    k = m.group(2)
                    if k in values and m.group(3) != values[k]:
                        print(f"[drift] {os.path.basename(path)} panel:{k}: "
                              f"{m.group(3)!r} -> {values[k]!r}", file=sys.stderr)
            else:
                open(path, "w", encoding="utf-8").write(new)
                print(f"[synced] {os.path.basename(path)}", file=sys.stderr)

    if unknown:
        print(f"error: unknown anchor key(s): {sorted(unknown)}", file=sys.stderr)
        return 2
    if args.check:
        return 1 if drift else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
