# polymarket-coherence

**Do Polymarket's multi-outcome markets really violate coherence — or is it just the spread?**

A small, reproducible study of price coherence in Polymarket's *mutually
exclusive* (negRisk) events. In a mutually-exclusive event the outcome
probabilities must sum to 1. Naive readings at the **mid price** appear to show
frequent, large violations (buy/sell the whole field for less/more than \$1).
This repo tests whether those violations **survive the bid-ask spread** — i.e.
whether they are *executable* — and finds that most do not.

## TL;DR finding (snapshot of 37 negRisk events, ≥3 outcomes)

| Quantity | Median |
|---|---|
| Σ P(outcome) at **mid** | **1.000** — coherent |
| Σ **best bid** | 0.972 |
| Σ **best ask** | 1.026 |

The mid prices are coherent; the apparent "violation" is the **bid-ask spread
band** straddling 1.0. And the band's width is mechanical: it grows with the
number of outcomes, because each additional market contributes another
half-spread — **corr(field size, Σask−Σbid) = 0.65**. After accounting for the
spread, only **6/37** events are executably buyable-below-\$1 and **4/37**
sellable-above-\$1; the rest is not exploitable.

> **Interpretation.** Reports of widespread "arbitrage" in multi-outcome
> prediction markets are, in large part, a **mid-price artifact**. Coherence
> should be judged on executable (bid/ask) prices, and apparent violation
> magnitude must be normalized by field size before it means anything.

## Reproduce

```bash
pip install -r requirements.txt          # only matplotlib (optional, for the figure)
python scripts/collect.py --limit 500 --out data/snapshot.csv   # public Gamma API, no key
python scripts/analyze.py --in data/snapshot.csv
```

`collect.py` writes a tidy one-row-per-market CSV plus a `*.manifest.json`
recording the snapshot time and source URL, so a run is fully reproducible from
the committed CSV alone. `analyze.py` is pure stdlib (matplotlib only for the
optional figure) and re-derives every number above.

## Data

- **Source:** Polymarket **Gamma API** (`/events`, public, no authentication).
- **Scope:** open events flagged `negRisk` (mutually-exclusive by construction),
  with each child market's `bestBid`, `bestAsk`, and mid `outcomePrices[0]`.
- **No credentials, no wallet, no private data.** Everything here runs from
  public market data.

## Honest limitations

- **Snapshot, not panel.** The Gamma API does not reliably serve historical
  price series for resolved markets (verified: even the \$1.5B Trump-2024 market
  returns an empty `prices-history`). This study is therefore a **cross-sectional
  snapshot**; a time-series version would need a live collector running forward.
- **Top-of-book only.** `bestBid`/`bestAsk` ignore depth. A truly executable
  arbitrage estimate needs L2 depth (you cannot fill the whole field at the top
  quote). Depth-aware executable arbitrage on negRisk markets is exactly what
  Beiglböck et al. (*Executable Arbitrage and Market Efficiency in Prediction
  Markets*, 2026) measure; this repo is a lightweight, spread-level complement,
  not a replacement.
- **Outlier-driven correlation.** The field-size/​spread relationship is partly
  driven by a few very large, illiquid fields (e.g. an 81-outcome award market).
  See `analyze.py` for the per-market–normalized view.

## Prior work (this is a *refinement*, not a first)

Arbitrage and coherence on Polymarket have been studied. This repo does **not**
claim to discover prediction-market arbitrage; it makes the narrow, contrarian
point that **spread and field size explain most naive coherence violations**.

- *Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets* (2025)
- *Executable Arbitrage and Market Efficiency in Prediction Markets* (2026)
- *Semantic Non-Fungibility and Violations of the Law of One Price in Prediction Markets* (2026)

## License

MIT — see [LICENSE](LICENSE).
