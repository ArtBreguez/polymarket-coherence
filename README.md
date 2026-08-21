# polymarket-coherence

**Do Polymarket's multi-outcome markets really violate coherence — or is it just the spread?**

📊 **Live dashboard:** https://artbreguez.github.io/polymarket-coherence/ — auto-updates
every 15 min from a scheduled collector.

![tests](https://github.com/ArtBreguez/polymarket-coherence/actions/workflows/tests.yml/badge.svg)

A small, reproducible study of price coherence in Polymarket's *mutually
exclusive* (negRisk) events. In a mutually-exclusive event the outcome
probabilities must sum to 1. Naive readings at the **mid price** appear to show
frequent, large violations (buy/sell the whole field for less/more than \$1).
This repo tests whether those violations **survive the bid-ask spread and order-book
depth** — i.e. whether they are *executable* — and finds they are governed by
liquidity structure, not mispricing.

## TL;DR findings

### 1. Top-of-book: mid prices are coherent; the "violation" is the spread
Snapshot of 37 negRisk events (≥3 outcomes):

| Quantity | Median |
|---|---|
| Σ P(outcome) at **mid** | **1.000** — coherent |
| Σ **best bid** | 0.972 |
| Σ **best ask** | 1.026 |

The mid prices sum to 1; the apparent violation is the **bid-ask spread band**
straddling 1.0.

### 2. Depth-aware: apparent "violations" are a liquidity-structure artifact
The real test of a mutually-exclusive "coherence violation" is whether you can
**buy one YES share in every outcome for less than \$1** and pocket the
guaranteed payoff. That requires *every* outcome to be fillable. Walking full L2
books shows completeness is governed by field size:

| Field size | Events | Complete¹ | Median outcomes with a book |
|---|---|---|---|
| small (≤20 outcomes) | 9 | **56%** | **100%** |
| large (>20 outcomes) | 28 | **0%** | **47%** |

¹ *Complete* = every declared outcome is fillable, so the field can actually be
locked.

Small, dense fields are complete and **not arbitrageable** — locking \$1 costs
**1.015–1.029** (above \$1) across order sizes of 1–1,000 shares, and rises with
both order size (walking the book) and field size (corr ≈ +0.47). Large fields
are **never complete**: a median of ~half their outcomes have no book at all, so
the "sum of listed prices" is not a portfolio you can buy. Of the missing legs,
**836 are real named candidates with no liquidity** vs only 114 structural
placeholders — this is a genuine long-tail illiquidity effect, not a listing
artifact.

> **Interpretation.** Naive multi-outcome "coherence violations" on Polymarket
> are **not mispricing** and **not free money**. They are governed by liquidity
> structure: (a) at the mid, prices already sum to ~1; (b) small dense fields are
> coherent and cost >\$1 to lock after spread; (c) large fields only *appear*
> violated because a long tail of illiquid, unpriced outcomes cannot be bought,
> so their listed-price sum is not an executable portfolio. Coherence must be
> judged on **depth-aware, complete-field** execution.

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

## Part 3 — does an executable window ever open? (forward panel)

A single snapshot cannot tell you whether a fleeting sub-\$1 lock ever appears.
`collect_forward.py` appends one timestamped observation per event to
`data/panel.jsonl`; run it on a schedule (e.g. every 15 min) to build a panel.
`analyze_panel.py` then reports, per event: how many snapshots were complete
(lockable), the min/median lock cost over time, the fraction of snapshots that
were executable (< \$1), and the **longest run of consecutive executable
snapshots** — a proxy for how long a window persists.

Seed panel (2 back-to-back snapshots, order size 100): **5/39 events complete,
0 ever executable**, lock cost stable across snapshots (min 1.016, median 1.029).
The committed `panel.jsonl` is a seed; the scheduled collector grows it into a
real time series.

## Data

- **Source:** Polymarket **Gamma API** (`/events`) and **CLOB API** (`/books`) —
  both public, no authentication.
- **Scope:** open events flagged `negRisk` (mutually-exclusive by construction).
  Part 1 uses each child market's `bestBid`, `bestAsk`, mid `outcomePrices[0]`;
  Part 2 uses the full L2 order book (all price/size levels) per outcome.
- **No credentials, no wallet, no private data.** Everything runs from public
  market data.

## Honest limitations

- **Snapshot, not panel.** The Gamma API does not reliably serve historical
  price series for resolved markets (verified: even the \$1.5B Trump-2024 market
  returns an empty `prices-history`). This study is a **cross-sectional
  snapshot**; a time-series version would need a live collector running forward.
- **Fees & gas not modeled.** The lock cost is the raw fill cost of walking the
  book. Polymarket makers are fee-exempt but takers and on-chain conversion pay
  costs, which only make the (already > \$1) lock *more* expensive — so the
  no-arbitrage conclusion is conservative.
- **Panel is young.** Window-persistence needs many snapshots; the committed
  `panel.jsonl` is a seed. The scheduled `collect_forward.py` grows it into a
  real time series (see Part 3). Until it does, "0 executable windows" is a
  strong snapshot result, not yet a duration statistic.
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
contrarian, and reproducible point that **naive multi-outcome "coherence
violations" are governed by liquidity structure, not mispricing** — the mid
prices already sum to ~1, small dense fields cost >\$1 to lock after spread, and
large fields only *appear* violated because a long tail of illiquid, unpriced
outcomes cannot be bought.

- *Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets* (2025)
- *Executable Arbitrage and Market Efficiency in Prediction Markets* (2026)
- *Semantic Non-Fungibility and Violations of the Law of One Price in Prediction Markets* (2026)

## License

MIT — see [LICENSE](LICENSE).
