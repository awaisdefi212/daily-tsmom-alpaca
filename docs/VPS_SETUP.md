# VPS setup (after cloning from GitHub)

## 1. Clone

```bash
git clone https://github.com/awaisdefi212/daily-tsmom-alpaca.git
cd daily-tsmom-alpaca
```

## 2. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Alpaca credentials (never commit `.env`)

```bash
cp .env.example .env
nano .env
```

Set `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` from your Alpaca paper dashboard.

## 4. Test

```bash
python scripts/test_alpaca_connection.py
python scripts/run_alpaca_tsmom.py
```

## 5. Cron — auto trade on rebalance days

First trading day of each month, ~9:35 AM New York:

```bash
mkdir -p logs
crontab -e
```

```cron
35 9 * * 1-5 cd /path/to/daily-tsmom-alpaca && .venv/bin/python scripts/run_alpaca_tsmom.py --execute >> logs/alpaca.log 2>&1
```

Set VPS timezone to `America/New_York`, or adjust the hour for your zone.

## Notes

- Raw Dukascopy CSVs are **not** in git (too large). Alpaca live trading does not need them.
- Run on **one machine only** (PC or VPS, not both) to avoid duplicate orders.
- Rotate API keys if they were ever shared in chat.
