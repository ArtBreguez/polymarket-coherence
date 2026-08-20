#!/usr/bin/env bash
# Forward-panel cron wrapper: take one snapshot, commit it, push to the repo.
# Runs headless on a schedule. Stays quiet on success (prints a one-line summary
# only when something notable happens) so it is watchdog-friendly.
set -euo pipefail

REPO="/home/ubuntu/polymarket-coherence"
cd "$REPO"

# 1) append one snapshot to the panel
OUT="$(python3 scripts/collect_forward.py --size 100 --limit 500 --out data/panel.jsonl 2>&1)"

# 2) commit + push only if the panel actually changed
if git diff --quiet -- data/panel.jsonl; then
  # nothing appended (network hiccup) — stay silent
  exit 0
fi

git add data/panel.jsonl
git -c user.name="Arthur Breguez" \
    -c user.email="98524696+ArtBreguez@users.noreply.github.com" \
    commit -q -m "data: forward-panel snapshot $(date -u +%Y-%m-%dT%H:%MZ)"

# push; if it fails (transient), leave the commit for the next run to push
git push -q origin master 2>/dev/null || true

# 3) surface ONLY executable windows (<$1) — the whole point of the panel.
# On a normal run with none found, print nothing (silent = healthy).
if echo "$OUT" | grep -q "LOCK<\$1"; then
  echo "polymarket-coherence: executable window detected"
  echo "$OUT" | grep "LOCK<\$1"
fi
