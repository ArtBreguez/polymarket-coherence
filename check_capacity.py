"""Does anything survive of the "not worth it" claim once the arithmetic is fixed?

15.8% annualized gross is good, not marginal. So the honest kill-shot has to be
one of:
  (a) the edge is gross of on-chain costs the study does not model
  (b) the window is tiny in absolute terms / capacity-limited
  (c) it is one field out of 38, i.e. not a strategy

Measure (b): how much capital can actually be deployed? The panel records
lock_cost per order size, so the cost curve across sizes shows how fast the edge
decays as you scale in.
"""
import json
from collections import defaultdict

rows = [json.loads(l) for l in open("/tmp/pcrev/data/panel.jsonl") if l.strip()]

TARGET = "Balance of Power: 2026 Midterms"
by_size = defaultdict(list)
for r in rows:
    if r.get("title") == TARGET and r.get("complete") and r.get("lock_cost") is not None:
        by_size[r.get("size")].append(r["lock_cost"])


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


print("cost to lock '%s' by order size:" % TARGET)
print("  size    obs   min cost   median   best gross edge   max capital at best")
for s in sorted(by_size, key=lambda x: (x is None, x)):
    cs = by_size[s]
    mn = min(cs)
    edge = (1.0 - mn) / mn * 100
    # 5 outcomes, s shares each, at ~mn/5 per share average => capital ~= s * mn
    cap = (s or 0) * mn
    print("  %5s  %4d   %.4f    %.4f   %6.2f%%          $%.0f"
          % (s, len(cs), mn, median(cs), edge, cap))

print()
sub_any = [r for r in rows if r.get("complete") and (r.get("lock_cost") or 9) < 1.0]
sizes_sub = defaultdict(int)
for r in sub_any:
    sizes_sub[r.get("size")] += 1
print("sub-$1 observations by size:", dict(sorted(sizes_sub.items(), key=lambda kv: (kv[0] is None, kv[0]))))

print()
print("total events in panel:", len({r['event_id'] for r in rows}))
print("events ever complete:", len({r['event_id'] for r in rows if r.get('complete')}))
print("events ever sub-$1:", len({r['event_id'] for r in sub_any}))
