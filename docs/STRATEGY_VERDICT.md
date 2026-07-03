# Strategy Verdict Ledger

**Platform status: KEEP — Daily TSMOM long-only v2 passes all gates on ES (deploy) and NQ.**

## Latest: Daily TSMOM long-only v2 — KEEP

### ES (`daily_tsmom_es_long_only`) — primary deployment

| Metric | Result |
|--------|--------|
| Gross PnL | **+2,524 pts** |
| Net @ 0.5pt slip | **+2,474 pts** |
| Net @ 2.0pt slip | **+2,324 pts** |
| OOS 2024–26 | **+1,270 pts** |
| Avg bps/trade | **130.61 bps** |
| Short trades | **0** |

Evidence: [`data/processed/validation/tsmom_es_long_only/`](../data/processed/validation/tsmom_es_long_only/)

### NQ (`daily_tsmom_nq_long_only`) — falsification

| Metric | Result |
|--------|--------|
| Gross PnL | **+11,174 pts** |
| Net @ 0.5pt slip | **+11,124 pts** |
| OOS 2024–26 | **+5,298 pts** |
| Avg bps/trade | **193.76 bps** |

Evidence: [`data/processed/validation/tsmom_nq_long_only/`](../data/processed/validation/tsmom_nq_long_only/)

## Archived: TSMOM long/short v1 — VALIDATE (V8 fail)

Long/short v1 had positive gross but **short leg lost money** on both instruments. Archived to `config/archive/`.

| Version | ES gross | NQ gross | Verdict |
|---------|----------|----------|---------|
| v1 long/short | +1,415 | +7,434 | VALIDATE (V8 fail) |
| **v2 long-only** | **+2,523** | **+12,231** | **KEEP** |

## Cancel ledger (intraday/overnight)

| Strategy | Verdict | Key reason |
|----------|---------|------------|
| ORB breakout / tuned / high-RR | CANCEL | Costs kill edge |
| ORB fade 5m | CANCEL | No gross edge |
| Intraday momentum 14d/90d | CANCEL | OOS -1,778; slip@1.0 -1,156 |
| Gao session momentum | CANCEL | Gross -3,748; OOS -1,151 |
| Overnight EU open v1/v2 | CANCEL | Gross -3,774; OOS -846 |

## Audit (pre–paper trading)

- **Signal look-ahead:** `tsmom_return` uses `shift(1)` / `shift(253)` — prior close only; unit test confirms same-day close does not affect signal.
- **Fill look-ahead:** Fixed — entries/exits at **RTH open** on rebalance day (`tsmom_entry_on: open`), not session close.
- **Data bug fixed:** `run_backtest.py` no longer loads NAS100 cache for ES profiles (`load_backtest_data` keyed by symbol).

## Next step: paper trading

Paper trade ES long-only TSMOM on monthly rebalance (~6 trades/year when bullish). Log actual slippage at rebalance.

```powershell
python scripts/run_backtest.py --profile daily_tsmom_es_long_only --analyze --validate
python scripts/validate_tsmom.py --config config/strategy_daily_tsmom_es_long_only.yaml
```

Research: [docs/TSMOM_RESEARCH.md](TSMOM_RESEARCH.md)

Archived configs: [config/archive/](../config/archive/)
