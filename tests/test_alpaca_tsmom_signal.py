"""Unit tests for Alpaca TSMOM live signal logic (no API calls)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd

from src.broker.alpaca_client import AccountSnapshot
from src.broker.alpaca_config import AlpacaSettings
from src.broker.tsmom_live import (
    build_rebalance_plan,
    compute_tsmom_return_from_bars,
    target_from_return,
)


def _daily_bars(n: int, start: float = 100.0, step: float = 0.1) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=n)
    closes = [start + i * step for i in range(n)]
    return pd.DataFrame({"session_date": dates.date, "close": closes})


def test_compute_tsmom_return_positive_trend():
    bars = _daily_bars(260, start=100.0, step=0.5)
    ret = compute_tsmom_return_from_bars(bars, lookback_days=252)
    assert ret is not None
    assert ret > 0


def test_target_from_return_long_only():
    assert target_from_return(0.05, long_only=True) == "long"
    assert target_from_return(-0.01, long_only=True) == "flat"
    assert target_from_return(None, long_only=True) is None


def test_rebalance_day_buy_when_flat_and_positive():
    settings = AlpacaSettings(symbol="SPY", min_history_bars=300)
    bars = _daily_bars(320, start=100.0, step=0.4)
    broker = MagicMock()
    broker.first_trading_day_of_month.return_value = date(2021, 3, 1)

    plan = build_rebalance_plan(
        broker,
        settings,
        as_of_date=date(2021, 3, 1),
        bars=bars,
        account=AccountSnapshot(equity=10_000, buying_power=10_000, cash=10_000),
        position=None,
    )
    assert plan.is_rebalance_day
    assert plan.intended_action == "buy"
    assert plan.order_qty is not None and plan.order_qty > 0


def test_rebalance_day_sell_when_long_and_negative():
    settings = AlpacaSettings(symbol="SPY", min_history_bars=300)
    bars = _daily_bars(320, start=200.0, step=-0.3)
    broker = MagicMock()
    broker.first_trading_day_of_month.return_value = date(2021, 3, 1)

    from src.broker.alpaca_client import PositionSnapshot

    plan = build_rebalance_plan(
        broker,
        settings,
        as_of_date=date(2021, 3, 1),
        bars=bars,
        account=AccountSnapshot(equity=10_000, buying_power=5_000, cash=5_000),
        position=PositionSnapshot(symbol="SPY", qty=10, market_value=5000, current_price=500),
    )
    assert plan.intended_action == "sell"


def test_non_rebalance_day_no_action():
    settings = AlpacaSettings()
    bars = _daily_bars(320)
    broker = MagicMock()
    broker.first_trading_day_of_month.return_value = date(2021, 3, 1)

    plan = build_rebalance_plan(
        broker,
        settings,
        as_of_date=date(2021, 3, 15),
        bars=bars,
        account=AccountSnapshot(equity=10_000, buying_power=10_000, cash=10_000),
        position=None,
    )
    assert plan.intended_action == "none"
    assert not plan.is_rebalance_day
