"""Intraday momentum signal tests."""

import pandas as pd

from src.config import StrategyConfig, SessionConfig, OrbConfig, VwapConfig
from src.session.session_calendar import annotate_sessions, filter_rth
from src.indicators.vwap import compute_vwap
from src.indicators.noise_area import compute_noise_area
from src.strategy.engines.intraday_momentum import generate_momentum_signals
from tests.fixtures.synthetic import make_bar, rth_minute_timestamps


def _momentum_pipeline(df: pd.DataFrame, strategy_cfg: StrategyConfig) -> pd.DataFrame:
    orb = OrbConfig(minutes=30)
    df = annotate_sessions(df, SessionConfig(), orb, strategy_cfg)
    df = filter_rth(df)
    df = compute_vwap(df, VwapConfig())
    df = compute_noise_area(df, lookback_days=strategy_cfg.noise_lookback_days)
    return generate_momentum_signals(df, strategy_cfg)


def test_momentum_long_on_strong_up_day():
    """After sigma warmup, strong rally should trigger long at check bar."""
    rows = []
    for day_offset in range(16):
        y, m, d = 2024, 6, 3 + day_offset
        times = rth_minute_timestamps((y, m, d), 390, (9, 30))
        for i, t in enumerate(times):
            b = 16000.0
            if day_offset < 15:
                rows.append(make_bar(t, b, b + 25, b - 3, b + 8, spread=2.0, volume=0.1))
            elif i < 60:
                rows.append(make_bar(t, b, b + 20, b - 2, b + 8, spread=2.0, volume=0.1))
            elif i == 60:
                rows.append(make_bar(t, b + 200, b + 250, b + 190, b + 240, spread=2.0, volume=0.3))
            else:
                rows.append(make_bar(t, b + 200, b + 210, b + 195, b + 205, spread=2.0, volume=0.1))
    cfg = StrategyConfig(
        strategy_type="intraday_momentum",
        entry_start="10:00",
        entry_cutoff="16:00",
        momentum_check_minutes=30,
        noise_lookback_days=14,
    )
    df = _momentum_pipeline(pd.DataFrame(rows), cfg)
    assert (df["signal"] == "long").any()


def test_momentum_no_signal_without_sigma():
    """First sessions without lookback should not signal."""
    cfg = StrategyConfig(
        strategy_type="intraday_momentum",
        entry_start="10:00",
        entry_cutoff="12:00",
        momentum_check_minutes=30,
        noise_lookback_days=14,
    )
    times = rth_minute_timestamps((2024, 7, 1), 120, (9, 30))
    rows = []
    for i, t in enumerate(times):
        b = 17000.0
        if i == 60:
            rows.append(make_bar(t, b + 100, b + 150, b + 90, b + 140, spread=2.0, volume=0.2))
        else:
            rows.append(make_bar(t, b, b + 20, b - 2, b + 8, spread=2.0, volume=0.1))
    df = _momentum_pipeline(pd.DataFrame(rows), cfg)
    assert (df["signal"].notna()).sum() == 0


def test_noise_boundary_stop_long():
    from src.strategy.risk import build_trade_plan
    from src.config import RiskConfig

    cfg = RiskConfig(stop_mode="noise_boundary", stop_buffer_points=0.0)
    plan = build_trade_plan(
        "long",
        15100.0,
        0.0,
        0.0,
        0.0,
        0.0,
        cfg,
        noise_lower=15050.0,
        noise_upper=15080.0,
    )
    assert plan.stop_price == 15050.0
    assert plan.target_price is None
    assert plan.use_boundary_trail
