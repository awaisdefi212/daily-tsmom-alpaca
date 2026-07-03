"""Quick Alpaca paper connection check (no orders)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.broker.alpaca_client import AlpacaBroker  # noqa: E402
from src.broker.alpaca_config import AlpacaCredentials, load_alpaca_config  # noqa: E402
from src.broker.tsmom_live import build_rebalance_plan  # noqa: E402


def main() -> int:
    cfg = load_alpaca_config(ROOT / "config/alpaca_tsmom.yaml")
    creds = AlpacaCredentials.from_env(paper=cfg.alpaca.paper)
    broker = AlpacaBroker(creds, cfg.alpaca)

    acct = broker.get_account()
    pos = broker.get_position(cfg.alpaca.symbol)
    bars = broker.fetch_daily_bars(cfg.alpaca.symbol)

    print("CONNECTED OK — Alpaca paper")
    print(f"  Equity:       ${acct.equity:,.2f}")
    print(f"  Buying power: ${acct.buying_power:,.2f}")
    print(f"  Cash:         ${acct.cash:,.2f}")
    print(f"  {cfg.alpaca.symbol} position: {int(pos.qty) if pos else 0} shares")
    print(f"  Daily bars:   {len(bars)} through {bars.iloc[-1]['session_date']}")

    plan = build_rebalance_plan(
        broker,
        cfg.alpaca,
        as_of_date=date(2026, 6, 1),
        bars=bars,
        account=acct,
        position=pos,
    )
    print(f"  Jun 1 plan:   action={plan.intended_action}, 12m return={plan.tsmom_return}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
