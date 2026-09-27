"""Check the article's holding period, annualization and T-bill claim.

The article says the capital is locked "eight months" AND that 2.7% over that
period annualizes to "roughly 15%". Those cannot both be true, so at least one
is wrong. Derive the real holding period from the panel's own end_date.
"""
import json
from datetime import datetime

rows = [json.loads(l) for l in open("/tmp/pcrev/data/panel.jsonl") if l.strip()]

# The sub-dollar field the article is about.
sub = [r for r in rows if r.get("complete") and (r.get("lock_cost") or 9) < 1.0]
fields = {}
for r in sub:
    fields.setdefault(r["title"], []).append(r)

print("fields that ever went sub-$1:")
for t, rs in fields.items():
    print("  %-40s obs=%d  min=%.4f" % (t[:38], len(rs), min(x["lock_cost"] for x in rs)))

target = max(fields, key=lambda t: len(fields[t]))
rs = fields[target]
print("\narticle's field:", target)

ends = {r.get("end_date") for r in rs if r.get("end_date")}
print("end_date values:", ends)

ts = sorted(datetime.fromisoformat(r["ts"].replace("Z", "+00:00")) for r in rs)
print("observed window: %s -> %s" % (ts[0].date(), ts[-1].date()))

end = datetime.fromisoformat(sorted(ends)[0].replace("Z", "+00:00"))
hold_days = (end - ts[-1]).days
print("\nresolution date: %s" % end.date())
print("holding period from last sub-$1 obs: %d days (%.2f months)" % (hold_days, hold_days / 30.44))

best = min(r["lock_cost"] for r in rs)
gross = (1.0 - best) / best * 100
print("\nbest lock cost %.4f -> gross edge %.2f%%" % (best, gross))

ann_simple = gross * 365.0 / hold_days
ann_compound = ((1.0 / best) ** (365.0 / hold_days) - 1) * 100
print("annualized (simple):    %.2f%%" % ann_simple)
print("annualized (compound):  %.2f%%" % ann_compound)

print("\n--- the article's two claims ---")
print("article says holding period: 'eight months' -> %d days" % (8 * 30.44))
print("article says annualized:     'roughly 15%'")
ann_if_8mo = gross * 365.0 / (8 * 30.44)
print("2.7%% over EIGHT months would annualize to: %.2f%%  <- not 15%%" % ann_if_8mo)
print()
print("So 'eight months' and '15%' are mutually exclusive.")
print("The repo's 15.05%% implies a holding period of ~%.0f days." % (gross * 365.0 / 15.05))
print()
print("T-bill check: a 2026 US T-bill yields roughly 4%% (order of magnitude).")
print("  %.1f%% annualized is ~%.1fx a T-bill, i.e. BETTER, not 'comparable'." % (ann_simple, ann_simple / 4.0))
