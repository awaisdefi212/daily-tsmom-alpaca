"""Backtest edge cases for TSMOM hold-through on unchanged signal."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.backtest.backtest_engine import run_backtest
from src.config import AppConfig, CostsConfig, DataConfig, RiskConfig, SessionConfig, StrategyConfig
from src.session.daily_calendar import annotate_daily_rebalance


def _daily_bar(
    session: date,
    *,
    bid_open: float,
    ask_open: float,
    bid_close: float,
    ask_close: float,
    is_rebalance: bool,
    signal: str | None,
) -> dict:
    return {
        "timestamp": pd.Timestamp(session),
        "session_date": session,
        "bid_open": bid_open,
        "ask_open": ask_open,
        "bid_high": max(bid_open, bid_close) + 1,
        "bid_low": min(bid_open, bid_close) - 1,
        "bid_close": bid_close,
        "ask_high": max(ask_open, ask_close) + 1,
        "ask_low": min(ask_open, ask_close) - 1,
        "ask_close": ask_close,
        "volume": 1.0,
        "mid_close": (bid_close + ask_close) / 2,
        "spread": ask_close - bid_close,
        "is_rebalance_bar": is_rebalance,
        "tsmom_return": 0.05 if signal == "long" else -0.05,
        "signal": signal,
        "is_rth": True,
        "is_session_end_bar": True,
        "et_minute": 16 * 60 - 1,
        "orb_high": 0.0,
        "orb_low": 0.0,
        "orb_mid": 0.0,
        "orb_width": 0.0,
        "orb_valid": True,
    }


def test_monthly_roll_exits_on_bearish_rebalance():
    """Long position exits when rebalance signal is flat (long-only)."""
    bars = pd.DataFrame(
        [
            _daily_bar(date(2024, 1, 2), bid_open=100, ask_open=102, bid_close=100, ask_close=102, is_rebalance=True, signal="long"),
            _daily_bar(date(2024, 2, 1), bid_open=110, ask_open=112, bid_close=110, ask_close=112, is_rebalance=True, signal=None),
        ]
    )
    bars.loc[bars.index[1], "tsmom_return"] = -0.05
    bars.loc[bars.index[1], "signal"] = None
    cfg = AppConfig(
        symbol="TEST",
        data=DataConfig(ask_path="a", bid_path="b"),
        session=SessionConfig(),
        strategy=StrategyConfig(
            strategy_type="daily_tsmom",
            tsmom_long_only=True,
            tsmom_entry_on="open",
        ),
        risk=RiskConfig(stop_mode="monthly_hold", fixed_stop_points=1000, max_stop_points=1000),
        costs=CostsConfig(slippage_points=0.5),
    )
    result = run_backtest(pd.DataFrame(), cfg, prepared_bars=bars)
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "rebalance"
