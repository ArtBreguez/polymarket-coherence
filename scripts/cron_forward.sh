#!/usr/bin/env bash
# Forward-panel cron wrapper: take one snapshot, commit it, push to the repo.
# Runs headless on a schedule. Stays quiet on success (prints a one-line summary
# only when something notable happens) so it is watchdog-friendly.
set -euo pipefail

# Resolve the repo root from this script's own location so it runs both locally
# (/home/ubuntu/polymarket-coherence) and on CI runners (/home/runner/work/...),
# not just on the box where it was first deployed.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# 0) Hard stop: the study's value is spent once the one field that ever opened a
#    sub-$1 window ("Balance of Power: 2026 Midterms") resolves on 2026-11-03.
#    Collect a little past it, then stop — beyond this only long-horizon events
#    remain (2027-2028) that never complete, so extra snapshots add noise, not
#    signal. Past the cutoff this wrapper exits silently; remove/extend the date
#    (or pause the cron) to keep collecting.
COLLECT_UNTIL="2026-11-10"
if [[ "$(date -u +%Y-%m-%d)" > "$COLLECT_UNTIL" ]]; then
  exit 0
fi

# 1) append one snapshot to the panel
OUT="$(python3 scripts/collect_forward.py --size 100 --limit 500 --out data/panel.jsonl 2>&1)"

# 2) commit + push only if the panel actually changed
if git diff --quiet -- data/panel.jsonl; then
  # nothing appended (network hiccup) — stay silent
  exit 0
fi

# 3) roll closed months out of the active file into immutable monthly archives
#    (panel-YYYY-MM.jsonl) so the active file — and each commit's diff — stays
#    bounded as the panel grows. No-op mid-month.
python3 scripts/panel_io.py >/dev/null 2>&1 || true

# 4) keep the panel canonical (drop zombies, normalize schema) then regenerate
#    the dashboard data (incl. cross-market loop.json) and sync the prose numbers
#    in README/FINDINGS from the freshly-written summary.json (single source of
#    truth, so the docs never drift out of date as the panel grows).
python3 scripts/clean_panel.py >/dev/null 2>&1 || true
python3 scripts/generate_site_data.py >/dev/null 2>&1 || true
python3 scripts/sync_panel_numbers.py >/dev/null 2>&1 || true

# stage the active panel, any archives, and the regenerated docs
git add data/panel.jsonl data/panel-*.jsonl docs/data/ README.md FINDINGS.md 2>/dev/null || \
  git add data/panel.jsonl docs/data/ README.md FINDINGS.md
git -c user.name="Arthur Breguez" \
    -c user.email="98524696+ArtBreguez@users.noreply.github.com" \
    commit -q -m "data: forward-panel snapshot $(date -u +%Y-%m-%dT%H:%MZ)"

# push; if it fails (transient), leave the commit for the next run to push
git push -q origin master 2>/dev/null || true

# 5) surface ONLY executable windows (<$1) — the whole point of the panel.
# On a normal run with none found, print nothing (silent = healthy).
if echo "$OUT" | grep -q "LOCK<\$1"; then
  echo "polymarket-coherence: executable window detected"
  echo "$OUT" | grep "LOCK<\$1"
fi
