# polymarket-coherence

**Do Polymarket's multi-outcome markets really violate coherence — or is it just the spread?**

A small, reproducible study of price coherence in Polymarket's *mutually
exclusive* (negRisk) events. In a mutually-exclusive event the outcome
probabilities must sum to 1. Naive readings at the **mid price** appear to show
frequent, large violations (buy/sell the whole field for less/more than \$1).
This repo tests whether those violations **survive the bid-ask spread** — i.e.
whether they are *executable* — and finds that most do not.

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

### 2. Depth-aware: the "arbitrage" is never executable, and most fields can't be locked at all
The real test of a mutually-exclusive "coherence violation" is whether you can
**buy one YES share in every outcome for less than \$1** and pocket the
guaranteed payoff. Using full L2 books and walking the ask side for realistic
order sizes:

| Order size / leg | Complete fields¹ | Median lock cost | Min lock cost (best case) |
|---|---|---|---|
| 1 share | 5 / 37 | 1.029 | **1.015** |
| 100 shares | 5 / 37 | 1.029 | 1.016 |
| 1,000 shares | 5 / 37 | 1.029 | 1.017 |

¹ *Complete field* = **every** declared outcome is fillable at that size. Only
**5 of 37** events are complete; the other 32 have empty/unlisted legs, so the
field **cannot be locked at all** — buying the available subset for < \$1 is not
arbitrage, because the winner may be one of the empty legs.

**Even in the best complete field, the lock costs 1.015 — above \$1. There is no
executable arbitrage**, and the cost rises with both order size (walking the
book) and field size (corr ≈ +0.47).

> **Interpretation.** Naive reports of widespread "arbitrage" in multi-outcome
> prediction markets are two artifacts stacked: (a) a **mid-price illusion** — at
> executable quotes the field straddles \$1; and (b) **incomplete-field illusion**
> — apparent sub-\$1 fields are missing tradable legs and can't be locked.
> Coherence must be judged on **depth-aware, complete-field** execution, not mid
> prices or a fillable subset.

## Reproduce

```bash
pip install -r requirements.txt          # only matplotlib (optional, for figures)

# Part 1 — top-of-book coherence (mid vs bid/ask)
python scripts/collect.py       --limit 500 --out data/snapshot.csv   # Gamma API, no key
python scripts/analyze.py       --in  data/snapshot.csv

# Part 2 — depth-aware executable coherence (the differentiator)
python scripts/collect_depth.py --limit 500 --out data/books.json     # CLOB L2 books, no key
python scripts/analyze_depth.py --in  data/books.json --sizes 1,10,100,1000
```

`collect*.py` each write a data file plus a `*.manifest.json` recording snapshot
time and source URLs, so a run is fully reproducible from the committed data
alone. The `analyze*.py` scripts are pure stdlib (matplotlib only for the
optional figures) and re-derive every number above.

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
- **Single snapshot per event.** Books are a point-in-time photo; a fleeting
  sub-\$1 window could open and close between snapshots. Establishing how often
  and how long real windows exist needs the forward collector (future work).
- **Scope is coherence, not realized profit.** We measure whether a lock is
  *available*, not whether anyone took it. Depth-aware realized on-chain arbitrage
  profit is measured by the 2026 "Executable Arbitrage" paper (see below); this
  repo is a lightweight, self-contained availability study.

## Prior work (this is a *refinement*, not a first)

Arbitrage and coherence on Polymarket have been studied. This repo does **not**
claim to discover prediction-market arbitrage; its contribution is the narrow,
contrarian, and reproducible point that **naive multi-outcome "coherence
violations" are two stacked artifacts — the mid-price spread band and incomplete
(non-lockable) fields — and vanish under depth-aware, complete-field execution.**

- *Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets* (2025)
- *Executable Arbitrage and Market Efficiency in Prediction Markets* (2026)
- *Semantic Non-Fungibility and Violations of the Law of One Price in Prediction Markets* (2026)

## License

MIT — see [LICENSE](LICENSE).
