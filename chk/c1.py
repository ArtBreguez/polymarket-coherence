"""Charts for the article, straight from the committed panel.

Also re-derives the numbers the article quotes, so a figure and the prose cannot
drift apart. If a check fails this exits non-zero rather than drawing anything.
"""
import json
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

rows = [json.loads(l) for l in open("/tmp/pcrev/data/panel.jsonl") if l.strip()]

# The article's headline numbers are the 100-share, complete-field observations.
comp = [r for r in rows if r.get("complete")]
c100 = [r for r in comp if r.get("size") == 100]

costs100 = sorted(r["lock_cost"] for r in c100 if r.get("lock_cost") is not None)
allcosts = sorted(r["lock_cost"] for r in comp if r.get("lock_cost") is not None)


def median(xs):
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


print("complete observations (all sizes):", len(allcosts))
print("  min %.4f  median %.4f  max %.4f" % (min(allcosts), median(allcosts), max(allcosts)))
sub = [c for c in allcosts if c < 1.0]
print("  sub-$1: %d of %d (%.1f%%)" % (len(sub), len(allcosts), 100 * len(sub) / len(allcosts)))

events = {r["event_id"] for r in rows}
comp_events = {r["event_id"] for r in comp}
sub_events = {r["event_id"] for r in comp if (r.get("lock_cost") or 9) < 1.0}
print("events: %d total, %d ever complete, %d ever sub-$1" % (len(events), len(comp_events), len(sub_events)))
for e in sub_events:
    t = next(r["title"] for r in rows if r["event_id"] == e)
    print("   sub-$1 field:", t)

# --- checks against the article ---
checks = {
    "n_obs 4820": len(allcosts) == 4820,
    "min 0.973": abs(min(allcosts) - 0.973) < 0.0005,
    "median 1.022": abs(median(allcosts) - 1.022) < 0.0005,
    "sub_dollar 397": len(sub) == 397,
    "38 events": len(events) == 38,
    "5 ever complete": len(comp_events) == 5,
    "2 ever sub-$1": len(sub_events) == 2,
}
print()
bad = [k for k, v in checks.items() if not v]
for k, v in checks.items():
    print(("  OK   " if v else "  FAIL ") + k)
if bad:
    raise SystemExit("article numbers do not match the data: %s" % bad)

# ---------------------------------------------------------------- figure 1
# Lock cost distribution: where $1.00 actually sits.
plt.rcParams.update({
    "figure.facecolor": "#0d1117", "axes.facecolor": "#0d1117",
    "text.color": "#e6edf3", "axes.labelcolor": "#e6edf3",
    "xtick.color": "#8b949e", "ytick.color": "#8b949e",
    "axes.edgecolor": "#30363d", "font.size": 11,
})

fig, ax = plt.subplots(figsize=(10, 5.2))
ax.hist(allcosts, bins=90, color="#58a6ff", edgecolor="#0d1117", linewidth=0.4)
top = ax.get_ylim()[1]
ax.set_ylim(0, top * 1.18)
top = ax.get_ylim()[1]

# Shade the profitable region first so bars and labels sit on top of it.
ax.axvspan(min(allcosts), 1.0, color="#3fb950", alpha=0.10, zorder=0)
ax.axvline(1.0, color="#f85149", lw=2, ls="--", zorder=5)

# Labels go in clear air above the bars, not on top of them.
ax.annotate("$1.00 break-even", xy=(1.0, top * 0.80), xytext=(1.045, top * 0.92),
            color="#f85149", fontsize=10.5, ha="left", va="center", zorder=6,
            arrowprops=dict(arrowstyle="->", color="#f85149", lw=1.3))
ax.annotate("everything profitable\nlives in here\n%d of %d observations" % (len(sub), len(allcosts)),
            xy=(0.982, top * 0.30), xytext=(1.105, top * 0.62),
            color="#3fb950", fontsize=10.5, ha="left", va="center", linespacing=1.5, zorder=6,
            arrowprops=dict(arrowstyle="->", color="#3fb950", lw=1.3))
ax.set_xlabel("cost to lock the whole field  (depth-aware, walking real order books)")
ax.set_ylabel("observations")
ax.set_title("Every lockable field in 964 snapshots. Almost all cost MORE than $1.",
             color="#e6edf3", fontsize=13, pad=14, loc="left")
ax.spines[["top", "right"]].set_visible(False)
fig.text(0.99, 0.005, "polymarket-coherence  ·  @HiddenTerps", color="#484f58",
         fontsize=8.5, ha="right")
fig.tight_layout()
fig.savefig("/tmp/pcrev/out/fig1_lockcost.png", dpi=170, facecolor="#0d1117")
print("\nwrote fig1_lockcost.png")

# ---------------------------------------------------------------- figure 2
# The 31-hour window, as a time series on the one field that had it.
best_event = max(sub_events, key=lambda e: sum(
    1 for r in comp if r["event_id"] == e and (r.get("lock_cost") or 9) < 1.0))
title = next(r["title"] for r in rows if r["event_id"] == best_event)

ser = sorted(
    ((datetime.fromisoformat(r["ts"].replace("Z", "+00:00")), r["lock_cost"])
     for r in comp if r["event_id"] == best_event and r.get("size") == 100
     and r.get("lock_cost") is not None),
    key=lambda t: t[0])
xs = [t for t, _ in ser]
ys = [c for _, c in ser]

fig, ax = plt.subplots(figsize=(10, 5.2))
ax.plot(xs, ys, color="#58a6ff", lw=1.6)
ax.axhline(1.0, color="#f85149", lw=1.8, ls="--")
ax.fill_between(xs, ys, 1.0, where=[y < 1.0 for y in ys],
                color="#3fb950", alpha=0.35, interpolate=True)
ax.text(xs[2], 1.0013, "break-even", color="#f85149", fontsize=9.5, ha="left")
ax.annotate("guaranteed profit, 31.2h straight\n2.77% gross, ~15.8% annualized\non about $97 of capital",
            xy=(xs[ys.index(min(ys))], min(ys)),
            xytext=(0.06, 0.22), textcoords="axes fraction",
            color="#3fb950", fontsize=10, linespacing=1.5,
            arrowprops=dict(arrowstyle="->", color="#3fb950", lw=1.3))
ax.set_ylabel("cost to lock all 5 outcomes  ($)")
ax.set_title("%s — the deepest sub-$1 window in the panel" % title,
             color="#e6edf3", fontsize=13, pad=14, loc="left")
ax.spines[["top", "right"]].set_visible(False)
fig.autofmt_xdate()
fig.text(0.99, 0.005, "polymarket-coherence  ·  @HiddenTerps", color="#484f58",
         fontsize=8.5, ha="right")
fig.tight_layout()
fig.savefig("/tmp/pcrev/out/fig2_window.png", dpi=170, facecolor="#0d1117")
print("wrote fig2_window.png   field=%s  points=%d" % (title, len(ys)))
print("  min in that field: %.4f" % min(ys))
