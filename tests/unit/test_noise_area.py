"""Unit tests for noise area indicator."""

import numpy as np
import pandas as pd
import pytest

from src.config import SessionConfig, OrbConfig, StrategyConfig
from src.session.session_calendar import annotate_sessions, filter_rth
from src.indicators.noise_area import compute_noise_area
from tests.fixtures.synthetic import make_bar, rth_minute_timestamps


def _two_sessions_wide_range_then_trend() -> pd.DataFrame:
    """Build 16 sessions of 5m-style 1m bars for sigma warmup + trend day."""
    rows = []
    base_date = (2024, 5, 1)
    for day_offset in range(16):
        y, m, d = 2024, 5, 1 + day_offset
        times = rth_minute_timestamps((y, m, d), 390, (9, 30))
        for i, t in enumerate(times):
            b = 15000.0 + day_offset * 5
            if i < 60:
                rows.append(make_bar(t, b, b + 30, b - 5, b + 10, spread=2.0, volume=0.1))
            elif day_offset == 15 and i > 120:
                lift = (i - 120) * 8
                rows.append(make_bar(t, b + lift, b + lift + 40, b + lift - 5, b + lift + 30, spread=2.0))
            else:
                rows.append(make_bar(t, b + 5, b + 25, b, b + 10, spread=2.0, volume=0.05))
    return pd.DataFrame(rows)


def test_noise_bounds_widen_through_session():
    df = _two_sessions_wide_range_then_trend()
    cfg = StrategyConfig(entry_start="10:00", entry_cutoff="16:00")
    orb = OrbConfig(minutes=30)
    df = annotate_sessions(df, SessionConfig(), orb, cfg)
    df = filter_rth(df)
    out = compute_noise_area(df, lookback_days=14, volatility_multiplier=1.0)

    last_day = out["session_date"].max()
    day = out[out["session_date"] == last_day].dropna(subset=["noise_sigma"])
    assert not day.empty
    morning = day[day["et_minute"] <= 600]
    afternoon = day[day["et_minute"] >= 720]
    if len(morning) > 0 and len(afternoon) > 0:
        assert afternoon["noise_sigma"].iloc[-1] >= morning["noise_sigma"].iloc[0]


def test_noise_sigma_uses_only_prior_sessions():
    df = _two_sessions_wide_range_then_trend()
    cfg = StrategyConfig()
    orb = OrbConfig(minutes=30)
    df = annotate_sessions(df, SessionConfig(), orb, cfg)
    df = filter_rth(df)
    out = compute_noise_area(df, lookback_days=14, volatility_multiplier=1.0)

    first_day = sorted(out["session_date"].unique())[0]
    first = out[out["session_date"] == first_day]
    assert first["noise_sigma"].isna().all()

    dates = sorted(out["session_date"].unique())
    day15 = out[out["session_date"] == dates[14]]
    assert day15["noise_sigma"].notna().any()


def test_noise_upper_above_lower():
    df = _two_sessions_wide_range_then_trend()
    cfg = StrategyConfig()
    orb = OrbConfig(minutes=30)
    df = annotate_sessions(df, SessionConfig(), orb, cfg)
    df = filter_rth(df)
    out = compute_noise_area(df, lookback_days=14, volatility_multiplier=1.0)
    valid = out.dropna(subset=["noise_upper", "noise_lower"])
    assert (valid["noise_upper"] > valid["noise_lower"]).all()
