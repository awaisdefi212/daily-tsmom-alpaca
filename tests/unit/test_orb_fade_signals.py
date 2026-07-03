"""ORB failed-breakout fade signal tests."""

import pandas as pd

from src.config import StrategyConfig, SessionConfig, OrbConfig, VwapConfig
from src.session.session_calendar import annotate_sessions, filter_rth
from src.indicators.vwap import compute_vwap
from src.indicators.orb import compute_orb_levels
from src.indicators.trend_day import compute_compression_day
from src.strategy.engines.orb_fade import generate_fade_signals
from tests.fixtures.synthetic import make_bar, rth_minute_timestamps


def _fade_pipeline(df: pd.DataFrame, strategy_cfg: StrategyConfig, orb_minutes=45) -> pd.DataFrame:
    orb = OrbConfig(minutes=orb_minutes, min_width_points=15, max_width_points=200)
    df = annotate_sessions(df, SessionConfig(), orb, strategy_cfg)
    df = filter_rth(df)
    df = compute_vwap(df, VwapConfig(slope_lookback_bars=3))
    df = compute_orb_levels(df, orb)
    if strategy_cfg.fade_compression_only:
        df = compute_compression_day(df, strategy_cfg.max_first_hour_range)
    else:
        df["is_compression_day"] = True
    return generate_fade_signals(df, strategy_cfg)


def test_fade_short_after_failed_upside_break():
    """Upside break then close inside ORB -> short on retest."""
    cfg = StrategyConfig(
        strategy_type="orb_fade",
        fade_compression_only=False,
        require_vwap_slope_flat=False,
        entry_start="10:00",
        entry_cutoff="12:00",
        fade_max_bars=6,
        retest_tolerance_points=5,
    )
    times = rth_minute_timestamps((2024, 4, 1), 120, (9, 30))
    rows = []
    for i, t in enumerate(times):
        if i < 45:
            b = 16000.0
            rows.append(make_bar(t, b, b + 18, b - 2, b + 8, spread=2.0, volume=0.1))
        elif i == 50:
            rows.append(make_bar(t, 16025, 16035, 16020, 16030, spread=2.0, volume=0.2))
        elif i == 51:
            rows.append(make_bar(t, 16015, 16020, 16010, 16012, spread=2.0, volume=0.1))
        elif i == 53:
            rows.append(make_bar(t, 16018, 16022, 16014, 16016, spread=2.0, volume=0.15))
        else:
            rows.append(make_bar(t, 16010, 16015, 16005, 16010, spread=2.0, volume=0.05))
    df = _fade_pipeline(pd.DataFrame(rows), cfg)
    assert (df["signal"] == "short").any()


def test_fade_blocked_on_wide_first_hour():
    """Compression filter blocks signals when first-hour range is wide."""
    cfg = StrategyConfig(
        strategy_type="orb_fade",
        fade_compression_only=True,
        max_first_hour_range=30.0,
        require_vwap_slope_flat=False,
        entry_start="10:00",
        entry_cutoff="12:00",
        fade_max_bars=6,
        retest_tolerance_points=5,
    )
    times = rth_minute_timestamps((2024, 4, 2), 120, (9, 30))
    rows = []
    for i, t in enumerate(times):
        if i < 60:
            b = 17000.0 + (i % 10) * 2
            rows.append(make_bar(t, b, b + 45, b - 5, b + 20, spread=2.0, volume=0.1))
        elif i == 65:
            rows.append(make_bar(t, 17055, 17070, 17050, 17065, spread=2.0, volume=0.2))
        elif i == 66:
            rows.append(make_bar(t, 17040, 17045, 17035, 17038, spread=2.0, volume=0.1))
        elif i == 68:
            rows.append(make_bar(t, 17042, 17048, 17038, 17040, spread=2.0, volume=0.15))
        else:
            rows.append(make_bar(t, 17050, 17055, 17045, 17050, spread=2.0, volume=0.05))
    df = _fade_pipeline(pd.DataFrame(rows), cfg)
    assert (df["signal"].notna()).sum() == 0


def test_fade_long_after_failed_downside_break():
    cfg = StrategyConfig(
        strategy_type="orb_fade",
        fade_compression_only=False,
        require_vwap_slope_flat=False,
        entry_start="10:00",
        entry_cutoff="12:00",
        fade_max_bars=6,
        retest_tolerance_points=5,
    )
    times = rth_minute_timestamps((2024, 4, 3), 120, (9, 30))
    rows = []
    for i, t in enumerate(times):
        if i < 45:
            b = 18000.0
            rows.append(make_bar(t, b, b + 18, b - 2, b + 8, spread=2.0, volume=0.1))
        elif i == 50:
            rows.append(make_bar(t, 17975, 17985, 17970, 17978, spread=2.0, volume=0.2))
        elif i == 51:
            rows.append(make_bar(t, 17990, 17995, 17985, 17992, spread=2.0, volume=0.1))
        elif i == 53:
            rows.append(make_bar(t, 17988, 17992, 17982, 17990, spread=2.0, volume=0.15))
        else:
            rows.append(make_bar(t, 18000, 18005, 17995, 18000, spread=2.0, volume=0.05))
    df = _fade_pipeline(pd.DataFrame(rows), cfg)
    assert (df["signal"] == "long").any()


def test_fade_structure_stop_short():
    from src.strategy.risk import build_trade_plan
    from src.config import RiskConfig

    cfg = RiskConfig(stop_mode="fade_structure", stop_buffer_points=2.0, max_stop_points=40.0)
    plan = build_trade_plan(
        "short",
        15000.0,
        15020.0,
        14980.0,
        40.0,
        15000.0,
        cfg,
        entry_bar_bid_low=14990.0,
        entry_bar_ask_high=15035.0,
    )
    assert plan.stop_price == 15037.0
    assert plan.stop_price > plan.entry_price
