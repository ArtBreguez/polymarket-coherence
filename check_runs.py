"""Is the 31.2h run the same episode as the 0.973 print?

The reviewer says no: the 31.25h unbroken sub-$1 run is Aug 21-23 and bottomed at
0.9940 (0.6% edge), while the 0.973 print is Aug 27 inside a separate ~13h run.
If true, the article welds a deep edge to a long duration that did not contain
it. That is the worst kind of error: both numbers are real and the sentence
joining them is false.
"""
import json
from datetime import datetime

rows = [json.loads(l) for l in open("/tmp/pcrev/data/panel.jsonl") if l.strip()]
TARGET = "Balance of Power: 2026 Midterms"
ser = sorted(
    (datetime.fromisoformat(r["ts"].replace("Z", "+00:00")), r["lock_cost"])
    for r in rows
    if r.get("title") == TARGET and r.get("complete") and r.get("lock_cost") is not None)
print("observations: %d  from %s to %s" % (len(ser), ser[0][0].date(), ser[-1][0].date()))


def runs(threshold):
    out = []
    start = None
    prev = None
    for t, c in ser:
        if c < threshold:
            if start is None:
                start = t
            prev = t
        else:
            if start is not None:
                out.append((start, prev))
                start = None
    if start is not None:
        out.append((start, prev))
    return out


for th in (1.0, 0.99, 0.98):
    rs = runs(th)
    print("\n--- threshold < %.2f : %d separate runs" % (th, len(rs)))
    for a, b in sorted(rs, key=lambda p: -(p[1] - p[0]).total_seconds())[:6]:
        dur = (b - a).total_seconds() / 3600
        seg = [c for t, c in ser if a <= t <= b]
        print("  %s -> %s  %5.2f h  n=%3d  min=%.4f"
              % (a.strftime("%m-%d %H:%M"), b.strftime("%m-%d %H:%M"), dur, len(seg), min(seg)))

# Which run contains the global minimum?
gmin = min(c for _, c in ser)
tmin = [t for t, c in ser if c == gmin][0]
print("\nglobal min %.4f at %s" % (gmin, tmin.strftime("%Y-%m-%d %H:%M")))
for a, b in runs(1.0):
    if a <= tmin <= b:
        dur = (b - a).total_seconds() / 3600
        seg = [c for t, c in ser if a <= t <= b]
        print("  -> sits in the run %s -> %s (%.2f h, min %.4f)"
              % (a.strftime("%m-%d %H:%M"), b.strftime("%m-%d %H:%M"), dur, min(seg)))

longest = max(runs(1.0), key=lambda p: (p[1] - p[0]).total_seconds())
seg = [c for t, c in ser if longest[0] <= t <= longest[1]]
print("\nLONGEST run: %s -> %s  %.2f h  min=%.4f  <- the 31h run's best edge is %.2f%%"
      % (longest[0].strftime("%m-%d %H:%M"), longest[1].strftime("%m-%d %H:%M"),
         (longest[1] - longest[0]).total_seconds() / 3600, min(seg),
         (1 - min(seg)) / min(seg) * 100))

total = sum((b - a).total_seconds() for a, b in runs(1.0)) / 3600
allsub = [c for _, c in ser if c < 1.0]
print("\ntotal sub-$1 time: %.1f h across %d runs; mean cost while sub-$1 %.4f"
      % (total, len(runs(1.0)), sum(allsub) / len(allsub)))
