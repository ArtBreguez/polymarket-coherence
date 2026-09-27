"""Two remaining claims to verify before rewriting.

1. The article says "397 of those 4,820 observations came in under a dollar.
   Every single one in the same field." But check_annualization showed TWO fields
   went sub-$1: Balance of Power (373 obs) and Fed Decision (24 obs). 373+24=397.
   So "every single one in the same field" is FALSE.

2. The article says 4,820 complete observations. With only size=100 in the panel,
   check what 4,820 actually counts and whether "36,632 depth-aware observations"
   in the opening is a fair description of panel.jsonl records.
"""
import json
from collections import defaultdict

rows = [json.loads(l) for l in open("/tmp/pcrev/data/panel.jsonl") if l.strip()]
print("panel.jsonl records:", len(rows))

sizes = defaultdict(int)
for r in rows:
    sizes[r.get("size")] += 1
print("records by size:", dict(sorted(sizes.items(), key=lambda kv: (kv[0] is None, kv[0]))))

comp = [r for r in rows if r.get("complete")]
print("\ncomplete records:", len(comp))
withcost = [r for r in comp if r.get("lock_cost") is not None]
print("complete with a lock_cost:", len(withcost))

sub = [r for r in withcost if r["lock_cost"] < 1.0]
print("sub-$1:", len(sub))

per_field = defaultdict(int)
for r in sub:
    per_field[r["title"]] += 1
print("\nsub-$1 BY FIELD:")
for t, n in sorted(per_field.items(), key=lambda kv: -kv[1]):
    mn = min(r["lock_cost"] for r in sub if r["title"] == t)
    print("  %-42s %3d obs   min %.4f" % (t[:40], n, mn))
print()
print("=> 'every single one in the same field' is", "TRUE" if len(per_field) == 1 else "FALSE")

ts = sorted(r["ts"] for r in rows)
print("\npanel window: %s -> %s" % (ts[0][:10], ts[-1][:10]))
from datetime import datetime
a = datetime.fromisoformat(ts[0].replace("Z", "+00:00"))
b = datetime.fromisoformat(ts[-1].replace("Z", "+00:00"))
print("hours spanned: %.1f" % ((b - a).total_seconds() / 3600))
print("distinct timestamps (snapshots):", len({r["ts"] for r in rows}))
