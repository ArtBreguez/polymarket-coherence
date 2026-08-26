# Findings

*A short, reproducible study of price coherence in Polymarket's mutually-exclusive
(negRisk) events, extended to a cross-market test against Kalshi.*

Snapshot: **2026-08-22** · public data only (Gamma API, CLOB L2 order books,
Kalshi trade-api) · no keys, no wallet · every number below is reproduced by the
scripts in this repo from the committed data.

---

## The question

In a mutually-exclusive event, exactly one outcome resolves YES, so the
outcome prices should sum to 1. When they don't — when Σ(prices) drifts below or
above 1 — it looks like a **coherence violation**, and naively like free money:
buy every outcome for less than \$1 and collect the guaranteed \$1.

**Is that apparent violation real, executable mispricing — or an artifact of how
these markets are quoted and how liquidity is distributed?**

The contribution here is narrow and contrarian: not to discover prediction-market
arbitrage (others have — see *Prior work*), but to show that the **large
multi-outcome "coherence violations" a naive observer sees are governed by
liquidity structure, not mispricing** — and that the only genuine sub-\$1 windows
are rare, marginal (≤0.6% gross), and confined to the *smallest* fields, the
opposite of the naive picture. Demonstrated at three levels of increasing rigor,
including a second, independently-quoted venue.

---

## Part 1 — At the mid, prices already sum to ~1 (top-of-book)

Across **36** negRisk events (**1,757** child markets) in the snapshot:

| Quantity | Median across events |
|---|---|
| Σ P(mid) | **0.998** |
| Σ best-bid | **0.966** |
| Σ best-ask | **1.017** |

The mid-price sum is essentially 1.0 — markets are coherent at the mid. The
bid/ask sums **straddle** 1.0: you cannot buy the whole field for the bid sum
(0.966) because you pay the **ask**, and the ask sum (1.017) is already above \$1.
The gap is a bid/ask **spread band**, and it widens with field size
(corr(field size, band) = **+0.664**).

At top-of-book, 7 of 36 fields *look* buyable below \$0.99 — a mostly-false signal
that Part 2 dismantles (only one of them survives a depth-aware, complete-field
lock).

## Part 2 — Locking a field costs ~\$1, and the only sub-\$1 case is a small dense field (depth-aware)

Top-of-book ignores two things: you can only fill limited size at the best quote,
and **some outcomes have no book at all**. A guaranteed \$1 lock requires filling
*every* declared outcome; if any leg is unfillable, the field cannot be locked —
buying the available subset is not arbitrage, because the winner may be the leg
you couldn't buy.

Walking the **full L2 book** (831 books across 36 events), cost to lock \$1 of
guaranteed payoff by buying every outcome:

| Order size | Complete fields | Median cost | Min cost (best case) |
|---|---|---|---|
| 1 share | 5 | **1.0220** | 0.9940 |
| 100 shares | 5 | **1.0220** | 0.9957 |
| 1000 shares | 5 | 1.0221 | 0.9972 |

The **median** complete field costs well over \$1 to lock, at every size — no free
lunch for the typical field. The **one** exception is exactly the field theory
predicts: "Balance of Power: 2026 Midterms" (5 outcomes, small and dense) locks at
**0.9957** for 100 shares — a marginal **+0.4% gross** window that shrinks as size
grows (0.9972 at 1000) and is *gross* of on-chain execution costs. This is the
same field the Part 3 forward panel flags, so the cross-sectional snapshot and the
prospective panel agree on where — and only where — a genuine window opens.

The reason only 5 fields are lockable at all is the core result:

| Field size | Count | % complete (all outcomes fillable) | Median % of outcomes with a book |
|---|---|---|---|
| small (n ≤ 20) | 9 | **56%** | **100%** |
| large (n > 20) | 27 | **0%** | **50%** |

Completeness **collapses** with field size. Large multi-outcome events (e.g.
"Democratic Presidential Nominee 2028", 128 outcomes) list a **long tail of
illiquid, unpriced outcomes** that cannot be bought. Their "sum of listed prices"
is therefore not an executable portfolio — the apparent violation is a
**liquidity-structure artifact, not mispricing**.

## Part 3 — Executable windows are rare, marginal, and only in small fields (forward panel)

A single snapshot can't tell you whether a fleeting sub-\$1 lock ever *appears*.
A scheduled collector (every 15 min) has built a panel of **<!--panel:snapshots-->528<!--/panel:snapshots-->+ snapshots** over
<!--panel:hours-->~128h<!--/panel:hours--> (and still growing) across <!--panel:distinct_events-->38<!--/panel:distinct_events--> events.

- **<!--panel:complete_events_of-->5 of 38<!--/panel:complete_events_of-->** events were ever complete (lockable) — always the same 5 small,
  dense fields (Fed, midterms, US-Iran). Large fields are **never** lockable.
- **<!--panel:ever_executable_of-->1 of 38<!--/panel:ever_executable_of-->** events ever crossed below \$1 on a **gross** basis: "<!--panel:sub_dollar_field-->Balance of Power: 2026 Midterms<!--/panel:sub_dollar_field-->"
  (5 outcomes) hit a lock cost of **0.994** — a **+0.6%
  gross edge** — and held sub-\$1 across multiple snapshots.
- Lock cost over all <!--panel:n_obs-->2640<!--/panel:n_obs--> complete observations: **min <!--panel:cost_min-->0.994<!--/panel:cost_min-->, median <!--panel:cost_median-->1.021<!--/panel:cost_median-->, max
  <!--panel:cost_max-->1.280<!--/panel:cost_max-->**. <!--panel:sub_dollar_of-->129 of 2640<!--/panel:sub_dollar_of--> (<!--panel:sub_dollar_pct-->4.9%<!--/panel:sub_dollar_pct-->) were sub-\$1, all in that one small dense field.
- **Persistence doesn't rescue it.** That window wasn't a flicker: it stayed
  sub-\$1 for a longest unbroken run of **<!--panel:best_window_run_hours-->~31.2h<!--/panel:best_window_run_hours-->**. But the edge is
  **<!--panel:best_edge_pct-->0.6%<!--/panel:best_edge_pct--> gross**, and the capital stays locked until the field resolves
  (Nov 2026), so annualized it is **<!--panel:best_annualized_pct-->3.02%<!--/panel:best_annualized_pct--> gross-of-costs** — below the
  on-chain gas/conversion drag and the return on a T-bill. A durable window that
  still isn't a free lunch is the sharpest form of the thesis: what kills the
  trade is not fleetingness but **marginality**.

This is the honest, important result — and it *sharpens* rather than weakens the
thesis. The method **does** detect a window when one opens, and the one it found
is exactly where theory predicts: a **small, dense, fully-liquid field**, not a
large one. The window is **marginal (0.6% gross) and gross-of-costs**: on
Polymarket, converting a complete YES set to \$1 incurs on-chain gas and
conversion costs not modeled here (see *Scope & limitations*), which plausibly
erase a 0.6% edge. Large multi-outcome fields — the ones a naive observer flags
as "violated" — **never** produce such a window at all, because they never
complete. So:

- **Large-field "violations": pure liquidity artifact.** Never executable.
- **Small-field windows: real but marginal.** Rare, tiny, gross-of-fees, in the
  few fields dense enough to lock.

The panel confirms prospectively what the snapshots showed: **no large free
lunch — only occasional, sub-1%, small-field, gross-of-cost windows.**

## Part 4 — The same outcome is coherent across two venues (cross-market)

Within one venue prices are coherent almost by construction. The sharper test —
with *real* variance, because two venues quote independently — asks whether the
**same real-world outcome** trades at the same price on **Polymarket and Kalshi**.

Matches are curated and auditable (`data/event_matches.json`), two ways:
**bucket-matched** for discrete categorical events (the FOMC decision, outcome by
outcome) and **name-matched** for team fields (NBA champion, by unique city
substring; ambiguous names are skipped, never guessed). An edge counts as
executable **only** if it (a) survives Kalshi's taker fee `ceil(0.07·p·(1−p))`
**and** (b) sits on real liquidity — a zero-liquidity Kalshi quote is a phantom
top-of-book with an empty order book behind it.

Across **2 matched events / 35 aligned outcomes** (Fed decision · 5 buckets, NBA
champion · 30 teams): **0 executable arbitrage.**

A few NBA outcomes show a gross gap that even survives fees (e.g. NY Knicks
+\$0.01, Philadelphia +\$0.008), but every one sits on a **zero-liquidity Kalshi
quote** — not tradeable. The raw cross-venue gaps are eaten by spread, fees, or
missing depth. **The two venues are coherent.**

---

## Conclusion

The *large* multi-outcome "coherence violations" that a naive observer flags on
Polymarket are **not exploitable mispricing** — they are governed by market
microstructure, shown three ways:

1. **Spread** — at the mid, prices already sum to ~1; the "violation" is the
   bid/ask band, which widens with field size.
2. **Liquidity** — large fields never complete; their long illiquid tail can't be
   bought, so the listed-price sum isn't an executable portfolio.
3. **Cross-venue** — against a second independent order book, matched outcomes are
   coherent once fees and real liquidity are enforced.

The one place a genuine sub-\$1 lock *does* appear is exactly where the
microstructure allows it: a **small, dense, fully-liquid field**, and even there
the edge is **marginal (≤0.6% gross) and confined to one field** (<!--panel:sub_dollar_of-->129 of 2640<!--/panel:sub_dollar_of--> complete observations, all in that single small dense market),
plausibly erased by execution costs. That is the opposite of the naive picture,
in which the *large* fields look most violated.

Bottom line: coherence must be judged on **depth-aware, complete-field,
fee-and-liquidity-aware execution** — not on the sum of listed prices. Judged that
way, the apparent violations vanish, and what remains are tiny, gross-of-cost
windows in the smallest fields.

## Scope & honest limitations

- **Availability, not realized profit.** We measure whether a lock is *available*,
  not whether anyone took it. Depth-aware realized on-chain profit is a different
  question (see *Prior work*).
- **Snapshot + young panel.** Parts 1–2 are a cross-sectional snapshot;
  Part 3's panel is <!--panel:hours-->~128h<!--/panel:hours--> / <!--panel:snapshots-->528<!--/panel:snapshots-->+ snapshots (and still growing). The "rare,
  marginal, small-field-only windows" result is strong over that span, not yet a
  long-horizon duration statistic.
- **Costs modeled only in Part 4.** Parts 1–3 report the raw book-walking fill
  cost. For nearly all fields the lock already costs >\$1, so taker fees / on-chain
  gas only reinforce no-arbitrage. The lone sub-\$1 case (Part 3, 0.6% gross) sits
  *within* the range those unmodeled costs could erase, so it is reported as a
  **gross** window, not realized profit. Part 4 *does* model Kalshi fees.
- **Curated cross-venue matches.** Only unambiguous same-semantics events are
  matched (2 here); automatic semantic matching is deliberately avoided because it
  fabricates false arbitrage.
- **Data hygiene is centralized and tested.** Every pull routes through
  `scripts/hygiene.py` (zombie/expired filtering, price sanity in (0,1), polite
  HTTP), verified by unit tests with no network.

## Prior work

This is a **refinement**, not a first. Arbitrage and coherence on prediction
markets have been studied:

- *Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets* (2025)
- *Executable Arbitrage and Market Efficiency in Prediction Markets* (2026)
- *Semantic Non-Fungibility and Violations of the Law of One Price in Prediction
  Markets* (2026)
- *Settlement Manipulation in Prediction Markets* (2026)

The narrow, reproducible point this repo adds: the coherence "violations" that a
naive observer sees in large multi-outcome fields are a **liquidity-structure and
microstructure artifact**, and the same conclusion holds **cross-venue** once fees
and real liquidity are enforced.

## Reproduce

```bash
python scripts/collect.py        --limit 500 --out data/snapshot.csv
python scripts/analyze.py        --in  data/snapshot.csv        # Part 1
python scripts/collect_depth.py  --limit 500 --out data/books.json
python scripts/analyze_depth.py  --in  data/books.json --sizes 1,10,100,1000  # Part 2
python scripts/analyze_panel.py  --in  data/panel.jsonl         # Part 3
python scripts/analyze_loop.py   --matches data/event_matches.json  # Part 4
python tests/test_core.py        # 23 unit tests, no network
```

Live dashboard: <https://artbreguez.github.io/polymarket-coherence/>
