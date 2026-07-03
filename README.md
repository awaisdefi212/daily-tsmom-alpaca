# NAS100 / ES Backtest Platform

Validation-first Python backtest using Dukascopy bid/ask data.

## Strategy status

**KEEP — Daily TSMOM long-only v2** on ES passes all validation gates. Proceed to paper trading.

| Profile | Instrument | Verdict |
|---------|------------|---------|
| `daily_tsmom_es_long_only` | S&P 500 (primary) | **KEEP** — gross +2,523; OOS +1,523 |
| `daily_tsmom_nq_long_only` | NAS100 | **KEEP** — gross +12,231; OOS +6,846 |
| TSMOM v1 long/short | ES / NQ | VALIDATE archived (short leg failed) |
| Overnight / Gao / ORB / momentum | — | CANCEL |

See [docs/STRATEGY_VERDICT.md](docs/STRATEGY_VERDICT.md) and [docs/TSMOM_RESEARCH.md](docs/TSMOM_RESEARCH.md).

## Alpaca paper trading

```powershell
pip install -r requirements.txt
copy .env.example .env
# add APCA_API_KEY_ID / APCA_API_SECRET_KEY
python scripts/run_alpaca_tsmom.py
python scripts/run_alpaca_tsmom.py --execute
```

See [docs/ALPACA_SETUP.md](docs/ALPACA_SETUP.md) (SPY proxy for ES).

Telegram alerts: [docs/TELEGRAM_SETUP.md](docs/TELEGRAM_SETUP.md).

## VPS deploy

Clone from GitHub and schedule monthly runs — [docs/VPS_SETUP.md](docs/VPS_SETUP.md).

## Validation

```powershell
python scripts/validate_tsmom.py --config config/strategy_daily_tsmom_es_long_only.yaml --export-csv data/processed/validation/tsmom_es_long_only
```

## Replay

```powershell
python scripts/run_backtest.py --profile daily_tsmom_es_long_only --analyze --validate
```

## Tests

```bash
python -m pytest tests/ -x --tb=short
```
