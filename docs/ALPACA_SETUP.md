# Alpaca paper trading — TSMOM long-only

Connect the validated **daily TSMOM ES long-only** strategy to [Alpaca](https://alpaca.markets/) paper trading.

## Instrument mapping

| Backtest | Alpaca paper |
|----------|----------------|
| Dukascopy `USA500IDXUSD` (S&P 500 CFD, points) | **`SPY`** (S&P 500 ETF, USD/share) |

SPY tracks the same broad market; P&amp;L is in dollars per share, not ES points. Use this integration to validate **execution timing, fills, and slippage** — not to match backtest point P&amp;L exactly.

## Setup

1. Create a free [Alpaca paper account](https://app.alpaca.markets/signup).
2. Generate API keys under **Paper Trading → API Keys**.
3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Copy credentials:

```powershell
copy .env.example .env
```

Edit `.env` and set:

```
APCA_API_KEY_ID=...
APCA_API_SECRET_KEY=...
```

Never commit `.env` (it is in `.gitignore`).

## Configuration

`config/alpaca_tsmom.yaml`:

- `symbol`: `SPY` (default)
- `tsmom_lookback_days`: `252` (12 months, matches backtest)
- `tsmom_long_only`: `true`
- `position_fraction`: `0.95` — deploy 95% of equity on long signals
- `data_feed`: `iex` (free); use `sip` if your subscription includes it

## Run

**Dry run** (default — no orders):

```powershell
python scripts/run_alpaca_tsmom.py
```

**Execute on paper** (first trading day of each month only):

```powershell
python scripts/run_alpaca_tsmom.py --execute
```

**Test a specific date:**

```powershell
python scripts/run_alpaca_tsmom.py --date 2026-01-02
```

## Schedule

Run once on each **first US equity trading day of the month**, shortly after the 9:30 ET open (e.g. 9:35 ET):

- Windows: Task Scheduler
- Linux/macOS: cron

Example (9:35 ET on weekdays — script no-ops on non-rebalance days):

```
35 9 * * 1-5 cd /path/to/VWAP+ORB && python scripts/run_alpaca_tsmom.py --execute
```

## Strategy rules (live)

Same as `daily_tsmom_es_long_only` backtest:

1. On the **first trading day** of each calendar month
2. 12-month return (prior close vs 252 trading days ago) **&gt; 0** → **long** (`SPY`)
3. Otherwise → **flat**
4. **Monthly roll**: if still long, close and re-open (matches backtest slippage model)

## Paper trade log

Fills append to `data/paper_trade/alpaca_tsmom_log.csv`. Analyze with:

```powershell
python scripts/analyze_paper_slippage.py --log data/paper_trade/alpaca_tsmom_log.csv
```

## Live trading warning

`alpaca.paper: false` requires `--allow-live`. Do not enable live until paper slippage gates pass.
