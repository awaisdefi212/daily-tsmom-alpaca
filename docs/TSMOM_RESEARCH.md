# Daily Time-Series Momentum — Research Synthesis

## Why pivot from overnight

Overnight EU open v1 failed with **gross -3,774 pts** on NAS100 Dukascopy despite 100% EU spread pass rate. Every year 2016–2025 was negative. This completes the falsification of **all bar-level and session-timing strategies** on this vendor for NQ.

| Strategy family | Gross | Verdict |
|-----------------|-------|---------|
| ORB breakout / tuned / high-RR | negative | CANCEL |
| ORB fade 5m | -191 | CANCEL |
| Noise-area momentum 14d | +1,936 (OOS fail) | CANCEL |
| Gao first30→last30 | -3,748 | CANCEL |
| Overnight EU open 02:00–03:00 ET | -3,774 | CANCEL |

**Pattern:** Mesfin (2026) documents a **0.07–1.50 pt/trade gross ceiling** on 5m MNQ OHLCV — insufficient for 2pt round-trip friction. Session-timing edges (Gao, overnight) failed with **negative gross**, not just cost drag.

## Selected strategy: Daily TSMOM

**Moskowitz, Ooi, Pedersen (2012)** — Time Series Momentum:

- Sign of trailing **12-month** return predicts next **month**
- Positive on **all 58** liquid futures in their sample
- S&P 500 equity index: **3.47%** annual TSMOM return in their table
- ~**12 trades/year** — friction is negligible vs multi-month moves

### Rules (baseline implementation)

| Parameter | Value |
|-----------|-------|
| Lookback | 252 trading days (~12 months) |
| Signal | Long if 12m return > 0, else short |
| Rebalance | First RTH session day of each calendar month |
| Signal timing | Uses **prior trading day's** close (no look-ahead) |
| Exit | Next monthly rebalance |
| Fills | Bid/ask with configurable slippage |

### Why this is "thick edge"

A 10% 12-month move on ES at ~5,000 pts ≈ **500 pts** gross per leg vs **~2 pt** round-trip slip. Orders of magnitude above the Mesfin intraday ceiling.

## Selected instrument: ES (`USA500IDXUSD`)

| Factor | ES | NQ (`USATECHIDXUSD`) |
|--------|----|-----------------------|
| Moskowitz 2012 equity table | **S&P 500 included** | Nasdaq-100 **not** in their 9 equity indexes |
| Muravyev/Kelly overnight papers | **ES futures** | NQ overnight failed on Dukascopy |
| Liquidity / slippage | Deeper book, lower slip | Thinner; all intraday strategies failed |
| Role in this project | **Primary deployment** | **Falsification cross-check** (data already in repo) |

**NQ** remains a secondary test: if daily TSMOM fails gross on NQ but passes on ES, instrument choice is confirmed. If both fail, conclude Dukascopy CFD ≠ CME continuous futures.

## Rejected alternatives

| Candidate | Verdict | Reason |
|-----------|---------|--------|
| Baltussen gamma last-30min | Reject | Same NQ + RTH close as failed Gao |
| Muravyev overnight on ES | Defer | Hourly edge; overnight family dead on NQ CFD |
| OFI / tick microstructure | Infeasible | Needs MBO data |
| Mesfin London/Confluence | Defer | High complexity; still 5m MNQ family |
| Retry intraday on NAS100 | Reject | Exhaustively falsified |

## Validation gates

| Gate | Threshold |
|------|-----------|
| V1 Gross PnL | > 0 |
| V2 Net @ 0.5pt slip | > 0 |
| V3 Net @ 2.0pt slip | > 0 |
| V4 Avg bps/trade | > 30 bps |
| V5 OOS 2024–26 net | > 0 |
| V6 Positive years | >= 50% |
| V7 Lookback stress (9/12/18m) | all gross > 0 |
| V8 Long + short legs | both contribute |

**Verdict:** PASS V1–V5 → KEEP; gross > 0 but slip/OOS fail → VALIDATE; gross ≤ 0 → CANCEL.

## Data requirements

**ES (primary):** User must add Dukascopy CSVs:

- `Data/Raw/USA500IDXUSD_1 Min_Bid_2016.01.01_2026.06.16.csv`
- `Data/Raw/USA500IDXUSD_1 Min_Ask_2016.01.01_2026.06.16.csv`

**NQ (falsification):** Existing NAS100 files in `Data/Raw/`.

## Honest risk

Dukascopy CFD bid/ask is not CME continuous futures. TSMOM is the strongest remaining academic hypothesis, but failure on both instruments would mean **this vendor cannot replicate published futures edges** — not that TSMOM is universally dead.

## References

- Moskowitz, Ooi, Pedersen (2012) — [Time Series Momentum](https://doi.org/10.1016/j.jfineco.2011.11.003)
- Mesfin (2026) — [MNQ OHLCV Falsification](https://arxiv.org/pdf/2605.04004)
- Kelly & Clark, NY Fed SR917 — Overnight Drift
- Muravyev & Bondarenko, JFQA — Market Return Around the Clock
