"""Figures 3 and 4, because X Articles support neither code blocks nor tables.

The draft carried its data as monospace blocks. In the Article editor those
collapse into unreadable prose, so each becomes an image.

Both figures derive their numbers from the committed snapshot and assert against
the published findings. Figure 4 reproduces the depth-aware completeness table,
including the filter at scripts/analyze_depth.py:97 that an event needs at least
as many collected ask books as declared outcomes to enter the table at all.
Missing that filter yields 11 small fields at 45% rather than the published 9
at 56%, because events whose legs were never collected get scored as incomplete
instead of being excluded as unmeasured.
"""
import csv
import json
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DARK = "#0d1117"
plt.rcParams.update({
    "figure.facecolor": DARK, "axes.facecolor": DARK,
    "text.color": "#e6edf3", "axes.labelcolor": "#e6edf3",
    "xtick.color": "#8b949e", "ytick.color": "#8b949e",
    "axes.edgecolor": "#30363d", "font.size": 11,
})


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


# ------------------------------------------------------------------ figure 3
# Top-of-book sums: the "violation" is one side of the spread.
rows = list(csv.DictReader(open("/tmp/pcrev/data/snapshot.csv")))
by_event = defaultdict(lambda: {"mid": 0.0, "bid": 0.0, "ask": 0.0, "n": 0})
for r in rows:
    try:
        mid, bid, ask = float(r["p_yes_mid"]), float(r["best_bid"]), float(r["best_ask"])
    except (ValueError, KeyError):
        continue
    if r.get("p_yes_mid_valid", "").strip().lower() not in ("true", "1", ""):
        continue
    e = by_event[r["event_id"]]
    e["mid"] += mid
    e["bid"] += bid
    e["ask"] += ask
    e["n"] += 1

sums = [v for v in by_event.values() if v["n"] >= 3]
m_mid = median([v["mid"] for v in sums])
m_bid = median([v["bid"] for v in sums])
m_ask = median([v["ask"] for v in sums])
print("events summed: %d" % len(sums))
print("median sums   mid %.3f   bid %.3f   ask %.3f" % (m_mid, m_bid, m_ask))

pub = {"mid": 0.998, "bid": 0.966, "ask": 1.017}
got = {"mid": m_mid, "bid": m_bid, "ask": m_ask}
bad = [k for k in pub if abs(pub[k] - got[k]) > 0.004]
for k in ("mid", "bid", "ask"):
    print(("  OK   " if k not in bad else "  FAIL ")
          + "%s published %.3f  derived %.3f" % (k, pub[k], got[k]))
if bad:
    raise SystemExit("top-of-book sums do not match the findings: %s" % bad)

fig, ax = plt.subplots(figsize=(10, 4.6))
labels = ["sum of best BIDS\n(where you sell)", "sum of MID prices\n(the fair read)",
          "sum of best ASKS\n(where you buy)"]
vals = [m_bid, m_mid, m_ask]
colors = ["#3fb950", "#8b949e", "#f85149"]
bars = ax.barh(labels, vals, color=colors, height=0.55)
ax.axvline(1.0, color="#e6edf3", lw=2, ls="--", zorder=5)
ax.text(1.0015, -0.44, "coherent = 1.00", color="#e6edf3", fontsize=10, ha="left")
for b, v in zip(bars, vals):
    ax.text(v + 0.002, b.get_y() + b.get_height() / 2, "%.3f" % v,
            va="center", fontsize=12.5, color="#e6edf3", fontweight="bold")
ax.set_xlim(0.94, 1.045)
ax.set_xlabel("sum of outcome probabilities across a mutually exclusive field")
ax.set_title("The apparent violation is one side of the spread, not a mispricing",
             color="#e6edf3", fontsize=13, pad=14, loc="left")
ax.spines[["top", "right"]].set_visible(False)
fig.text(0.99, 0.005, "polymarket-coherence  ·  @HiddenTerps", color="#484f58",
         fontsize=8.5, ha="right")
fig.tight_layout()
fig.savefig("/tmp/pcrev/out/fig3_spread.png", dpi=170, facecolor=DARK)
print("wrote fig3_spread.png")

# ------------------------------------------------------------------ figure 4
# Completeness by field size, from the depth-aware snapshot (books.json).
books = json.load(open("/tmp/pcrev/data/books.json"))
ev = defaultdict(lambda: {"declared": 0, "with_book": 0, "fillable": 0, "title": ""})
for tok, b in books.items():
    e = ev[b["event_id"]]
    e["declared"] = b.get("n_markets") or 0
    e["title"] = b.get("event_title", "")
    e["with_book"] += 1
    if b.get("asks"):
        e["fillable"] += 1

# See module docstring: both conditions are load-bearing.
evs = {k: v for k, v in ev.items() if v["declared"] >= 3 and v["fillable"] >= 3}
print("\ndepth-aware events analyzed: %d" % len(evs))

stats = {}
for label, keep in (("small", lambda n: n <= 20), ("large", lambda n: n > 20)):
    g = [v for v in evs.values() if keep(v["declared"])]
    complete = [v for v in g if v["fillable"] >= v["declared"]]
    ratios = [100.0 * v["with_book"] / v["declared"] for v in g]
    stats[label] = {"n": len(g), "complete": 100.0 * len(complete) / len(g),
                    "fill": median(ratios)}
    print("%s  events=%2d  complete=%3.0f%%  median with a book=%3.0f%%"
          % (label, stats[label]["n"], stats[label]["complete"], stats[label]["fill"]))

checks = {
    "36 events analyzed": len(evs) == 36,
    "9 small events": stats["small"]["n"] == 9,
    "27 large events": stats["large"]["n"] == 27,
    "small 56% complete": abs(stats["small"]["complete"] - 56) < 1.5,
    "large 0% complete": stats["large"]["complete"] == 0.0,
    "small 100% with a book": abs(stats["small"]["fill"] - 100) < 0.6,
    "large 50% with a book": abs(stats["large"]["fill"] - 50) < 1.5,
}
bad = [k for k, v in checks.items() if not v]
for k, v in checks.items():
    print(("  OK   " if v else "  FAIL ") + k)
if bad:
    raise SystemExit("completeness figures do not match the findings: %s" % bad)

fig, ax = plt.subplots(figsize=(10, 4.8))
groups = ["small fields\n20 outcomes or fewer\n(%d events)" % stats["small"]["n"],
          "large fields\nmore than 20 outcomes\n(%d events)" % stats["large"]["n"]]
x = range(len(groups))
w = 0.36
comp = [stats["small"]["complete"], stats["large"]["complete"]]
fill = [stats["small"]["fill"], stats["large"]["fill"]]
b1 = ax.bar([i - w / 2 for i in x], comp, w,
            label="ever lockable (every leg fillable)", color="#58a6ff")
b2 = ax.bar([i + w / 2 for i in x], fill, w,
            label="median share of outcomes with any order book", color="#8957e5")
for bars in (b1, b2):
    for b in bars:
        h = b.get_height()
        ax.text(b.get_x() + b.get_width() / 2, h + 1.8, "%.0f%%" % h,
                ha="center", fontsize=12, color="#e6edf3", fontweight="bold")
ax.annotate("never lockable,\nnot once", xy=(1 - w / 2, 1.5), xytext=(1 - w / 2 - 0.015, 33),
            color="#f85149", fontsize=10.5, ha="center", linespacing=1.4,
            arrowprops=dict(arrowstyle="->", color="#f85149", lw=1.4))
ax.set_xticks(list(x))
ax.set_xticklabels(groups)
ax.set_ylim(0, 132)
ax.set_ylabel("percent")
ax.set_title("The fields with the biggest apparent violations can never be locked at all",
             color="#e6edf3", fontsize=13, pad=14, loc="left")
ax.legend(frameon=False, loc="upper left", fontsize=9.5, labelcolor="#8b949e",
          bbox_to_anchor=(0.0, 1.0))
ax.spines[["top", "right"]].set_visible(False)
fig.text(0.99, 0.005, "polymarket-coherence  ·  @HiddenTerps", color="#484f58",
         fontsize=8.5, ha="right")
fig.tight_layout()
fig.savefig("/tmp/pcrev/out/fig4_completeness.png", dpi=170, facecolor=DARK)
print("wrote fig4_completeness.png")
