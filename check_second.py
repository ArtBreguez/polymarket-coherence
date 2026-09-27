"""The second sub-$1 field I left out, and whether it beats the headline one.

The reviewer says 'Fed Decision in September?' annualizes to ~26% because it
resolves much sooner. If true, the field I omitted is economically BETTER than
the one I featured, which turns an omission into cherry-picking.
"""
import json
from datetime import datetime

rows = [json.loads(l) for l in open("/tmp/pcrev/data/panel.jsonl") if l.strip()]
sub = [r for r in rows if r.get("complete") and (r.get("lock_cost") or 9) < 1.0]

for title in sorted({r["title"] for r in sub}):
    rs = [r for r in sub if r["title"] == title]
    best = min(r["lock_cost"] for r in rs)
    end = datetime.fromisoformat(sorted({r["end_date"] for r in rs})[0].replace("Z", "+00:00"))
    tbest = [datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
             for r in rs if r["lock_cost"] == best][0]
    days = (end - tbest).total_seconds() / 86400
    gross = (1 - best) / best * 100
    ann = gross * 365.0 / days
    capital = 100 * best
    profit = 100 * (1 - best)
    print("%s" % title)
    print("   obs sub-$1        %d" % len(rs))
    print("   best lock cost   %.4f  (gross %.2f%%)" % (best, gross))
    print("   deepest print    %s" % tbest.strftime("%Y-%m-%d %H:%M"))
    print("   resolves         %s  -> %.1f days locked" % (end.date(), days))
    print("   annualized gross %.1f%%" % ann)
    print("   capital / profit $%.2f -> $%.2f" % (capital, profit))
    print()

print("A 3-month US T-bill in Sept 2026 yielded roughly 3.9-4.1%.")
print("Both windows annualize far ABOVE that, so 'loses to a T-bill' is wrong")
print("for both, and the omitted field is the better of the two on rate.")
