# polymarket-coherence

**Do Polymarket's multi-outcome markets really violate coherence — or is it just the spread?**

📊 **Live dashboard:** https://artbreguez.github.io/polymarket-coherence/ — auto-updates
every 15 min from a scheduled collector.

![tests](https://github.com/ArtBreguez/polymarket-coherence/actions/workflows/tests.yml/badge.svg)

📄 **Read the write-up: [FINDINGS.md](FINDINGS.md)** — question, method, results,
limitations, prior work (the short-paper version of this repo).

A small, reproducible study of price coherence in Polymarket's *mutually
exclusive* (negRisk) events. In a mutually-exclusive event the outcome
probabilities must sum to 1. Naive readings at the **mid price** appear to show
frequent, large violations (buy/sell the whole field for less/more than \$1).
This repo tests whether those violations **survive the bid-ask spread and order-book
depth** — i.e. whether they are *executable* — and finds the large ones are a
liquidity-structure artifact, while genuine sub-\$1 windows are rare, marginal
(≤0.6% gross), and confined to the smallest fields.

## TL;DR findings

### 1. Top-of-book: mid prices are coherent; the "violation" is the spread
Snapshot of 36 negRisk events (≥3 outcomes, 1,757 child markets):

| Quantity | Median |
|---|---|
| Σ P(outcome) at **mid** | **0.998** — coherent |
| Σ **best bid** | 0.966 |
| Σ **best ask** | 1.017 |

The mid prices sum to ~1; the apparent violation is the **bid-ask spread band**
straddling 1.0, which widens with field size (corr ≈ **+0.66**).

### 2. Depth-aware: apparent "violations" are a liquidity-structure artifact
The real test of a mutually-exclusive "coherence violation" is whether you can
**buy one YES share in every outcome for less than \$1** and pocket the
guaranteed payoff. That requires *every* outcome to be fillable. Walking full L2
books shows completeness is governed by field size:

| Field size | Events | Complete¹ | Median outcomes with a book |
|---|---|---|---|
| small (≤20 outcomes) | 9 | **56%** | **100%** |
| large (>20 outcomes) | 27 | **0%** | **50%** |

¹ *Complete* = every declared outcome is fillable, so the field can actually be
locked.

Small, dense fields are complete; the **median** complete field still costs more
than \$1 to lock — a median of **1.022** across order sizes of 1–1,000 shares,
rising with both order size (walking the book) and field size (corr ≈ **+0.37**).
The lone sub-\$1 case is a small dense field — "Balance of Power: 2026 Midterms"
locks at **0.9957** (100 shares), a marginal **+0.4% gross** window that shrinks
with size and is gross of on-chain costs. Large fields are **never complete**: a
median of ~half their outcomes have no book at all, so the "sum of listed prices"
is not a portfolio you can buy — a genuine long-tail illiquidity effect, not a
listing artifact.

> **Interpretation.** The *large* multi-outcome "coherence violations" a naive
> observer flags on Polymarket are **not mispricing** and **not free money**.
> They are governed by liquidity structure: (a) at the mid, prices already sum to
> ~1; (b) small dense fields are near-coherent and typically cost >\$1 to lock
> after spread; (c) large fields only *appear* violated because a long tail of
> illiquid, unpriced outcomes cannot be bought, so their listed-price sum is not
> an executable portfolio. The forward panel (below) finds the *only* genuine
> sub-\$1 windows are rare, marginal (≤0.6% gross), and confined to small fields —
> the opposite of the naive picture. Coherence must be judged on **depth-aware,
> complete-field** execution.

### 3. Cross-market (Law of One Price): Polymarket vs Kalshi
Within one venue, prices are internally coherent by construction. The sharper
test — with *real* variance, because two venues quote independently — is whether
the **same real-world outcome** trades at the same price on **Polymarket and
Kalshi**. We curate explicit event matches (`data/event_matches.json`) two ways:
**bucket-matched** (discrete categorical events like the FOMC decision, mapped
outcome-by-outcome) and **name-matched** (team fields like the NBA champion,
matched by unique city substring; ambiguous names such as two Madrid clubs are
skipped, never guessed). Automatic semantic matching is error-prone and produces
fake arbitrage, so every match is declared and auditable.

An edge counts as executable arbitrage only if it (a) survives **Kalshi's taker
fee** `ceil(0.07·p·(1−p))` **and** (b) sits on **real liquidity** — a
zero-liquidity Kalshi quote is a phantom top-of-book with an empty order book
behind it, so a "gap" there is not tradeable.

Live example — September FOMC decision, aligned bucket by bucket:

| Bucket | Polymarket (bid/ask) | Kalshi (bid/ask) | Gross edge | Net of fee |
|---|---|---|---|---|
| maintain | 0.67 / 0.68 | 0.65 / 0.66 | +0.01 | **−0.01** |
| hike 25bp | 0.31 / 0.32 | 0.32 / 0.33 | 0.00 | **−0.02** |
| cut 25bp | 0.011 / 0.012 | 0.00 / 0.01 | +0.001 | **−0.009** |

Across the matched events (Fed decision · 5 buckets, NBA champion · 30 teams =
**35 aligned outcomes**): **0 executable arbitrage.** A few NBA teams show a
gross gap that even survives fees (e.g. NY Knicks +$0.01), but every one sits on
a **zero-liquidity Kalshi quote** — phantom top-of-book, not tradeable. The two
venues are coherent.

> **Interpretation.** The same-outcome, cross-venue result mirrors the
> single-venue one: apparent coherence violations are a **spread-, fee- and
> liquidity artifact**, not exploitable mispricing — now shown against a second,
> independently-quoted order book, a much stronger test than internal coherence
> alone. The method *does* flag a real window whenever one opens (net edge > 0 on
> real liquidity); in this snapshot none does.

## Reproduce

```bash
pip install -r requirements.txt          # only matplotlib (optional, for figures)

# Part 1 — top-of-book coherence (mid vs bid/ask)
python scripts/collect.py       --limit 500 --out data/snapshot.csv   # Gamma API, no key
python scripts/analyze.py       --in  data/snapshot.csv

# Part 2 — depth-aware executable coherence (the differentiator)
python scripts/collect_depth.py --limit 500 --out data/books.json     # CLOB L2 books, no key
python scripts/analyze_depth.py --in  data/books.json --sizes 1,10,100,1000

# Part 3 — forward panel: run on a schedule, then analyze window persistence
python scripts/collect_forward.py --size 100 --out data/panel.jsonl    # append one snapshot
python scripts/analyze_panel.py   --in  data/panel.jsonl               # windows over time

# Part 4 — cross-market Law of One Price (Polymarket vs Kalshi)
python scripts/collect_kalshi.py --series KXFEDDECISION --out data/kalshi_fed.json  # Kalshi, no key
python scripts/analyze_loop.py   --matches data/event_matches.json     # net-of-fee cross-venue edge

# Tests (no network)
python tests/test_core.py
```

`collect*.py` each write a data file plus a `*.manifest.json` recording snapshot
time and source URLs, so a run is fully reproducible from the committed data
alone. The `analyze*.py` scripts are pure stdlib (matplotlib only for the
optional figures) and re-derive every number above.

### Data hygiene (`scripts/hygiene.py`)
Every external pull — Polymarket Gamma, Polymarket CLOB, Kalshi — routes through
one shared hygiene module instead of re-implementing (and drifting) the rules per
collector. It is the single choke point that guarantees:

- **Zombie filtering** — events whose `endDate` is in the past are dropped even
  when the venue still flags them `closed=false` (resolved/expired markets have
  degenerate prices and evaporating liquidity), plus a curated `ZOMBIE_EVENT_IDS`
  set for events captured before the filter existed.
- **`live_negrisk_events()`** — the one function every Polymarket pull calls:
  negRisk-only, minimum field size, zombie-free.
- **Price sanity** — `clean_price()` accepts a probability quote only in the open
  interval (0, 1); exactly 0/1, negative, >1 or NaN is degenerate and flagged
  (`p_yes_mid_valid`) rather than silently averaged into a result.
- **Polite HTTP** — retry with backoff and a real `User-Agent` (Gamma 403s
  without one).

All of it is pure/stdlib and unit-tested with no network (`tests/test_core.py`),
so the cleaning rules themselves are verified, not just trusted.

## Part 3 — does an executable window ever open? (forward panel)

A single snapshot cannot tell you whether a fleeting sub-\$1 lock ever appears.
`collect_forward.py` appends one timestamped observation per event to
`data/panel.jsonl`; run it on a schedule (e.g. every 15 min) to build a panel.
`analyze_panel.py` then reports, per event: how many snapshots were complete
(lockable), the min/median lock cost over time, the fraction of snapshots that
were executable (< \$1), and the **longest run of consecutive executable
snapshots** — a proxy for how long a window persists.

Panel to date (**<!--panel:snapshots-->721<!--/panel:snapshots-->+ snapshots**
over <!--panel:hours-->~176h<!--/panel:hours--> and still growing, order size
100): **<!--panel:complete_events-->5/38<!--/panel:complete_events--> events
complete** (the same small dense fields every time; large fields never lock).
**<!--panel:ever_executable-->1/38<!--/panel:ever_executable--> ever crossed
below \$1 on a gross basis** — "<!--panel:sub_dollar_field-->Balance of Power: 2026 Midterms<!--/panel:sub_dollar_field-->"
hit **0.994** (+0.6% gross edge) and held sub-\$1 across multiple snapshots. Lock
cost over all <!--panel:n_obs-->3605<!--/panel:n_obs--> complete observations:
**min <!--panel:cost_min-->0.973<!--/panel:cost_min-->, median
<!--panel:cost_median-->1.022<!--/panel:cost_median-->, max
<!--panel:cost_max-->1.280<!--/panel:cost_max-->**;
**<!--panel:sub_dollar-->165/3605<!--/panel:sub_dollar-->
(<!--panel:sub_dollar_pct-->4.6%<!--/panel:sub_dollar_pct-->)** were sub-\$1 — all
in that one small dense field, and all *gross* of on-chain execution costs that
plausibly erase a ~0.6% edge. Large multi-outcome fields — the ones that *look*
most violated — never produce a window at all. The scheduled collector keeps
growing the series.

## Data

- **Source:** Polymarket **Gamma API** (`/events`) and **CLOB API** (`/books`) —
  both public, no authentication.
- **Scope:** open events flagged `negRisk` (mutually-exclusive by construction).
  Part 1 uses each child market's `bestBid`, `bestAsk`, mid `outcomePrices[0]`;
  Part 2 uses the full L2 order book (all price/size levels) per outcome.
- **No credentials, no wallet, no private data.** Everything runs from public
  market data.

## Honest limitations

- **Parts 1–2 are cross-sectional; Part 3 is a young panel.** The Gamma API does
  not reliably serve historical price series for resolved markets (verified: even
  the \$1.5B Trump-2024 market returns an empty `prices-history`), so Parts 1–2
  are a single snapshot. Part 3's forward collector has built
  <!--panel:hours-->~176h<!--/panel:hours--> /
  <!--panel:snapshots-->721<!--/panel:snapshots-->+ snapshots so far (and still
  growing) — the "rare, marginal, small-field-only
  windows" result is strong over that span, but not yet a long-horizon duration
  statistic.
- **Fees & gas not modeled in Parts 1–3.** The lock cost is the raw fill cost of
  walking the book. Polymarket makers are fee-exempt but takers and on-chain
  conversion pay costs. For the vast majority of fields the lock already costs
  > \$1, so these costs only reinforce no-arbitrage. The one exception — the
  small-field 0.6%-gross window in Part 3 — is *within* the range these unmodeled
  costs could plausibly erase, so we report it as a **gross** window, not a
  realized profit. Part 4 *does* model Kalshi's taker fee explicitly.
- **Zombie markets are filtered.** Polymarket occasionally keeps an event flagged
  `closed=false` past its `endDate` (e.g. a resolved weekly market). These have
  degenerate prices and evaporating liquidity, so all collectors now drop any
  event whose `endDate` is in the past, and the site generator excludes two such
  events that were captured before that filter existed. The raw `panel.jsonl` is
  kept intact as the unedited collection record; the filtering happens at the
  analysis/site layer.
- **Scope is coherence, not realized profit.** We measure whether a lock is
  *available*, not whether anyone took it. Depth-aware realized on-chain arbitrage
  profit is measured by the 2026 "Executable Arbitrage" paper (see below); this
  repo is a lightweight, self-contained availability study.

## Prior work (this is a *refinement*, not a first)

Arbitrage and coherence on Polymarket have been studied. This repo does **not**
claim to discover prediction-market arbitrage; its contribution is the narrow,
contrarian, and reproducible point that **the large multi-outcome "coherence
violations" a naive observer sees are a liquidity-structure artifact, not
mispricing** — the mid prices already sum to ~1, small dense fields typically
cost >\$1 to lock after spread (genuine sub-\$1 windows are rare, ≤0.6% gross, and
only in the smallest fields), and large fields only *appear* violated because a
long tail of illiquid, unpriced outcomes cannot be bought.

- *Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets* (2025)
- *Executable Arbitrage and Market Efficiency in Prediction Markets* (2026)
- *Semantic Non-Fungibility and Violations of the Law of One Price in Prediction Markets* (2026)

## License

MIT — see [LICENSE](LICENSE).
