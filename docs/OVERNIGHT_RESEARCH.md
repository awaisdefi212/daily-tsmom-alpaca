# Overnight EU Open — Research Synthesis

## What failed on NAS100 Dukascopy (2016–2026)

| Strategy | Gross | Net @ 0.5pt | Verdict |
|----------|-------|-------------|---------|
| ORB breakout / tuned / high-RR | negative | negative | CANCEL |
| ORB fade 5m | -191 | -465 | CANCEL |
| Noise-area momentum 14d | +1,936 | +390 | CANCEL (OOS/slip) |
| Gao first30→last30 | **-3,748** | **-6,397** | **CANCEL** |

**Pattern:** All RTH intraday timing strategies on NAS100 CFD fail deployability. Mesfin (2026) documents a **0.07–1.50 pt/trade gross ceiling** on 5m MNQ OHLCV signals — insufficient for 2pt round-trip friction.

Gao failed with **negative gross** — the close-drive / open-drive family does not transfer to this feed.

## What literature still claims has thick edge

### 1. Daily time-series momentum (Moskowitz, Ooi, Pedersen 2012)

- 12-month past return predicts next month across 58 futures; positive on every contract.
- Very thick edge, low turnover (monthly rebalance).
- **Not tested** on this platform; requires multi-day holds and daily bar pipeline.

### 2. European-open overnight drift (Kelly NY Fed SR917; Muravyev & Bondarenko JFQA)

- Peak returns **2:00–3:00 AM ET** when European cash markets open.
- ~1.48 bps/day in peak hour; inventory-reversal mechanism after US close imbalances.
- Muravyev: ~4 hours around EU open account for entire ES futures average return (Sharpe ~1.6 pre-cost).
- **Selected for implementation** — uses 24h data, different clock than failed RTH strategies.

### 3. Baltussen gamma hedging last-30min (JFE 2021)

- Rest-of-day return predicts last 30 minutes (distinct from Gao's first-30min predictor).
- **Deferred** — same NQ instrument and close window as failed Gao.

### 4. Order flow imbalance (Cont-Kukanov-Stoikov 2014)

- Thick at tick horizon (1–60 seconds).
- **Not feasible** — requires MBO/tick data; 1m bid/ask destroys signal.

### 5. Mesfin positive controls (RTH Confluence, London Session B)

- +5.77 to +15.77 pts/trade net on MNQ; requires GMM regime classifiers and London session.
- **Deferred** — high complexity; needs Asia/London session engineering.

## Why overnight EU open (v1)

1. **Never tested** on your data.
2. Uses **full 24h Dukascopy CSV** (not RTH-filtered).
3. **~1 trade/day**, 1-hour hold — thick edge target vs 5m bar noise.
4. Academic mechanism (inventory reversal) distinct from ORB/momentum noise area.

## Strategy variants

**v1 (unconditional):** Long 02:00–03:00 ET every session with spread filter.

**v2 (conditional):** Long only when prior US RTH session return < 0 (Kelly asymmetric reversal). Run only if v1 gross > 0.

## Critical caveats

- Dukascopy NAS100 overnight spreads may be wider than CME ES futures.
- Slippage stress includes **2.0pt** round-trip (Mesfin friction floor).
- Paper results on ES/SPY may not transfer to NAS100 CFD.
- Anomaly may have decayed post-publication.

## If overnight fails

Honest conclusion: **no deployable NAS100 edge** at any tested frequency on this vendor. Next options:

1. Daily TSMOM on NQ (different paradigm)
2. ES (`USA500IDXUSD`) data with simpler rules
3. Stop NAS100 research on this dataset

## References

- Kelly & Clark, NY Fed Staff Report 917 — [Overnight Drift](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf)
- Muravyev & Bondarenko, JFQA — [Market Return Around the Clock](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/market-return-around-the-clock-a-puzzle/089E33AC0B4D3B9A02CBA31EDF6505B3)
- Mesfin (2026) — [MNQ OHLCV Falsification](https://arxiv.org/pdf/2605.04004)
- Moskowitz, Ooi, Pedersen (2012) — [Time Series Momentum](https://doi.org/10.1016/j.jfineco.2011.11.003)
