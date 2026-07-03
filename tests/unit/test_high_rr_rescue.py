"""Tests for high-RRR rescue: structure stop, trend-day filter, go/no-go gates."""

import pytest
import pandas as pd

from src.config import RiskConfig, StrategyConfig, SessionConfig, OrbConfig, VwapConfig
from src.strategy.risk import build_trade_plan, StopTooWideError
from src.indicators.trend_day import compute_trend_day
from src.session.session_calendar import annotate_sessions, filter_rth
from src.indicators.vwap import compute_vwap
from src.indicators.orb import compute_orb_levels
from src.strategy.signal_engine import generate_entry_signals
from scripts.go_no_go import evaluate_gates, verdict, GateResult
from tests.fixtures.synthetic import make_bar, rth_minute_timestamps


def test_retest_structure_stop_long_uses_bar_low_and_orb_mid():
    cfg = RiskConfig(
        stop_mode="retest_structure",
        stop_buffer_points=2.0,
        max_stop_points=40.0,
        min_stop_points=12.0,
        target_r_multiple=3.5,
    )
    orb_high, orb_low = 15020.0, 15000.0
    orb_mid = 15010.0
    entry = 15025.0
    plan = build_trade_plan(
        "long",
        entry,
        orb_high,
        orb_low,
        20.0,
        orb_mid,
        cfg,
        entry_bar_bid_low=15012.0,
        entry_bar_ask_high=15028.0,
    )
    # min(15012, 15010) - 2 = 15008; risk = 17
    assert plan.stop_price == 15008.0
    assert plan.stop_price < entry
    assert plan.risk_per_unit == pytest.approx(17.0)


def test_retest_structure_stop_short_uses_bar_high_and_orb_mid():
    cfg = RiskConfig(
        stop_mode="retest_structure",
        stop_buffer_points=2.0,
        max_stop_points=40.0,
        min_stop_points=12.0,
    )
    orb_high, orb_low = 15020.0, 15000.0
    orb_mid = 15010.0
    entry = 14995.0
    plan = build_trade_plan(
        "short",
        entry,
        orb_high,
        orb_low,
        20.0,
        orb_mid,
        cfg,
        entry_bar_bid_low=14992.0,
        entry_bar_ask_high=15008.0,
    )
    # max(15008, 15010) + 2 = 15012; risk = 17
    assert plan.stop_price == 15012.0
    assert plan.stop_price > entry


def test_retest_structure_stop_min_floor():
    cfg = RiskConfig(
        stop_mode="retest_structure",
        stop_buffer_points=2.0,
        max_stop_points=40.0,
        min_stop_points=12.0,
    )
    orb_high, orb_low = 15020.0, 15010.0
    orb_mid = 15015.0
    entry = 15022.0
    plan = build_trade_plan(
        "long",
        entry,
        orb_high,
        orb_low,
        10.0,
        orb_mid,
        cfg,
        entry_bar_bid_low=15020.0,
    )
    # raw risk would be ~5; floored to 12
    assert plan.risk_per_unit == pytest.approx(12.0)
    assert plan.stop_price == entry - 12.0


def test_retest_structure_stop_too_wide_raises():
    cfg = RiskConfig(
        stop_mode="retest_structure",
        stop_buffer_points=2.0,
        max_stop_points=40.0,
        min_stop_points=12.0,
    )
    with pytest.raises(StopTooWideError):
        build_trade_plan(
            "long",
            15100.0,
            15020.0,
            15000.0,
            20.0,
            15010.0,
            cfg,
            entry_bar_bid_low=15000.0,
        )


def _signal_pipeline(df: pd.DataFrame, strategy_cfg: StrategyConfig) -> pd.DataFrame:
    orb = OrbConfig(minutes=45, min_width_points=15, max_width_points=200)
    df = annotate_sessions(df, SessionConfig(), orb, strategy_cfg)
    df = filter_rth(df)
    df = compute_vwap(df, VwapConfig())
    df = compute_orb_levels(df, orb)
    if strategy_cfg.require_trend_day:
        df = compute_trend_day(df, strategy_cfg.min_first_hour_range)
    else:
        df["is_trend_day"] = True
    return generate_entry_signals(df, strategy_cfg)


def test_trend_day_filter_blocks_narrow_first_hour():
    """20pt first-hour range should block signals when require_trend_day=true."""
    cfg = StrategyConfig(
        entry_mode="pullback_retest",
        require_trend_day=True,
        min_first_hour_range=35.0,
        require_vwap_guard=False,
        min_breakout_volume_mult=0,
        require_vwap_slope=False,
        entry_start="10:00",
        entry_cutoff="12:00",
    )
    times = rth_minute_timestamps((2024, 3, 1), 100, (9, 30))
    rows = []
    for i, t in enumerate(times):
        if i < 60:
            # Tight 20pt range in first hour
            b = 16000.0
            rows.append(make_bar(t, b, b + 18, b - 2, b + 8, spread=2.0, volume=0.1))
        elif i == 65:
            rows.append(make_bar(t, 16025, 16040, 16020, 16035, spread=2.0, volume=0.2))
        elif i == 70:
            rows.append(make_bar(t, 16028, 16032, 16018, 16030, spread=2.0, volume=0.15))
        else:
            rows.append(make_bar(t, 16010, 16015, 16005, 16010, spread=2.0, volume=0.05))
    df = _signal_pipeline(pd.DataFrame(rows), cfg)
    assert (df["signal"].notna()).sum() == 0


def test_trend_day_filter_allows_wide_first_hour():
    """50pt first-hour range should allow trend-day signals."""
    cfg = StrategyConfig(
        entry_mode="pullback_retest",
        require_trend_day=True,
        min_first_hour_range=35.0,
        require_vwap_guard=True,
        min_breakout_volume_mult=0,
        require_vwap_slope=False,
        entry_start="10:00",
        entry_cutoff="12:00",
        retest_tolerance_points=5,
    )
    times = rth_minute_timestamps((2024, 3, 2), 100, (9, 30))
    rows = []
    for i, t in enumerate(times):
        if i < 60:
            b = 17000.0 + (i % 10) * 2
            rows.append(make_bar(t, b, b + 45, b - 5, b + 20, spread=2.0, volume=0.1))
        elif i == 65:
            rows.append(make_bar(t, 17055, 17070, 17050, 17065, spread=2.0, volume=0.2))
        elif i in (66, 67):
            rows.append(make_bar(t, 17060, 17068, 17058, 17064, spread=2.0, volume=0.1))
        elif i == 70:
            rows.append(make_bar(t, 17058, 17062, 17048, 17060, spread=2.0, volume=0.15))
        else:
            rows.append(make_bar(t, 17050, 17055, 17045, 17050, spread=2.0, volume=0.05))
    df = _signal_pipeline(pd.DataFrame(rows), cfg)
    assert df["is_trend_day"].any()
    assert (df["signal"] == "long").any()


def test_entry_bar_prices_set_on_signal():
    cfg = StrategyConfig(
        entry_mode="breakout_close",
        require_trend_day=False,
        require_vwap_guard=False,
        min_breakout_volume_mult=0,
        require_vwap_slope=False,
        entry_start="10:00",
        entry_cutoff="12:00",
    )
    times = rth_minute_timestamps((2024, 3, 3), 90, (9, 30))
    rows = []
    for i, t in enumerate(times):
        if i < 30:
            rows.append(make_bar(t, 18000, 18020, 17995, 18005, spread=2.0, volume=0.1))
        elif i == 50:
            rows.append(make_bar(t, 18025, 18040, 18020, 18035, spread=2.0, volume=0.2))
        else:
            rows.append(make_bar(t, 18010, 18015, 18005, 18010, spread=2.0, volume=0.05))
    orb = OrbConfig(minutes=30, min_width_points=15, max_width_points=200)
    df = annotate_sessions(pd.DataFrame(rows), SessionConfig(), orb, cfg)
    df = filter_rth(df)
    df = compute_vwap(df, VwapConfig())
    df = compute_orb_levels(df, orb)
    df["is_trend_day"] = True
    df = generate_entry_signals(df, cfg)
    sig_rows = df[df["signal"].notna()]
    assert not sig_rows.empty
    assert sig_rows["entry_bar_bid_low"].notna().all()
    assert sig_rows["entry_bar_ask_high"].notna().all()


def _make_summary(gross_pnl, net_pnl, trade_count):
    return {
        "net": {"total_pnl": net_pnl, "trade_count": trade_count},
        "gross": {"total_pnl": gross_pnl},
    }


def test_go_no_go_all_pass_verdict():
    summary = _make_summary(500, 100, 200)
    analysis = {"winner_avg_r": 2.5, "avg_mfe_r": 1.5}
    trades = pd.DataFrame(
        {
            "session_date": pd.to_datetime(["2025-01-02", "2024-06-01", "2023-03-01"]),
            "r_multiple": [0.5, 0.2, 0.3],
        }
    )
    trades.loc[0, "r_multiple"] = 0.5
    trades.loc[1, "r_multiple"] = 0.2
    gates = evaluate_gates(summary, summary, analysis, trades)
    assert all(g.passed for g in gates)
    assert verdict(gates).startswith("KEEP -")


def test_go_no_go_cancel_verdict():
    summary = _make_summary(-100, -200, 50)
    analysis = {"winner_avg_r": 0.8, "avg_mfe_r": 0.5}
    trades = pd.DataFrame(
        {
            "session_date": pd.to_datetime(["2025-01-02"]),
            "r_multiple": [-0.5],
        }
    )
    gates = evaluate_gates(summary, summary, analysis, trades)
    assert verdict(gates).startswith("CANCEL")


def test_go_no_go_conditional_keep():
    summary = _make_summary(300, -50, 180)
    analysis = {"winner_avg_r": 2.2, "avg_mfe_r": 1.3}
    trades = pd.DataFrame(
        {
            "session_date": pd.to_datetime(["2025-06-01", "2023-01-01", "2022-06-01"]),
            "r_multiple": [0.2, 0.1, 0.05],
        }
    )
    gates = evaluate_gates(summary, summary, analysis, trades)
    passed = {g.gate_id: g.passed for g in gates}
    assert passed["G1"] and passed["G4"] and passed["G5"] and not passed["G2"]
    assert "conditional" in verdict(gates)
