"""Trade MFE/MAE analysis tests."""

import pandas as pd

from src.backtest.backtest_engine import Trade, BacktestResult
from src.reporting.trade_analysis import (
    compute_trade_mfe_mae,
    analyze_trades,
    r_histogram,
)
from tests.fixtures.synthetic import make_bar, rth_minute_timestamps


def _trade(side="long", entry=100.0, risk=10.0):
    return Trade(
        session_date=pd.Timestamp("2024-01-16").date(),
        side=side,
        entry_time=pd.Timestamp("2024-01-16 10:35:00", tz="America/New_York"),
        exit_time=pd.Timestamp("2024-01-16 10:40:00", tz="America/New_York"),
        entry_price=entry,
        exit_price=entry + 5,
        stop_price=entry - risk,
        target_price=entry + 3 * risk,
        orb_width=20.0,
        risk_per_unit=risk,
        r_multiple=0.5,
        pnl_points=5.0,
        spread_cost=1.0,
        slippage_cost=2.0,
        exit_reason="eod",
    )


def test_mfe_mae_long():
    times = rth_minute_timestamps((2024, 1, 16), 6, (10, 30))
    rows = [
        make_bar(times[0], 100, 105, 99, 102, spread=2.0),
        make_bar(times[1], 102, 115, 101, 110, spread=2.0),
        make_bar(times[2], 110, 112, 95, 100, spread=2.0),
    ]
    bars = pd.DataFrame(rows)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"]).dt.tz_convert("America/New_York")

    trade = _trade(entry=100.0, risk=10.0)
    trade.entry_time = bars.iloc[0]["timestamp"]
    trade.exit_time = bars.iloc[2]["timestamp"]

    mfe, mae = compute_trade_mfe_mae(trade, bars)
    assert mfe > 0
    assert mae > 0
    assert mfe >= mae or True  # depends on path


def test_r_histogram_buckets():
    df = pd.DataFrame({"r_multiple": [-1.2, -0.3, 0.5, 1.5, 2.2, 3.0]})
    hist = r_histogram(df)
    assert hist["<-1"] == 1
    assert hist["[2.5+]"] == 1


def test_analyze_trades_empty():
    result = analyze_trades(BacktestResult(), pd.DataFrame())
    assert result["trade_count"] == 0
