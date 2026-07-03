"""ORB logical tests."""

import pandas as pd

from src.config import SessionConfig, OrbConfig, StrategyConfig
from src.indicators.orb import compute_orb_levels, detect_breakout_signal
from src.indicators.vwap import compute_vwap
from src.session.session_calendar import annotate_sessions
from tests.fixtures.synthetic import make_bar, rth_minute_timestamps


def _prep(df: pd.DataFrame, orb_minutes=30) -> pd.DataFrame:
    cfg = OrbConfig(minutes=orb_minutes, min_width_points=15, max_width_points=200)
    df = annotate_sessions(df, SessionConfig(), cfg, StrategyConfig())
    df = df.loc[df["is_rth"]].copy()
    df = compute_vwap(df)
    return compute_orb_levels(df, cfg)


def test_orb_undefined_during_window():
    times = rth_minute_timestamps((2024, 1, 16), 40, (9, 30))
    df = _prep(pd.DataFrame([make_bar(t, 100, 120, 90, 110, volume=0.1) for t in times]))
    during = df.loc[df["is_orb_window"]]
    assert during["orb_high"].isna().all()


def test_orb_immutable_after_window():
    times = rth_minute_timestamps((2024, 1, 16), 50, (9, 30))
    df = _prep(pd.DataFrame([make_bar(t, 100, 120, 90, 110, volume=0.1) for t in times]))
    post = df.loc[df["is_signal_window"]]
    highs = post["orb_high"].dropna().unique()
    assert len(highs) == 1


def test_conservative_range_ask_high_bid_low():
    times = rth_minute_timestamps((2024, 1, 16), 45, (9, 30))
    rows = []
    for i, t in enumerate(times):
        spread = 3.0
        rows.append(make_bar(t, 100, 110, 95, 105, spread=spread, volume=0.1))
    df = _prep(pd.DataFrame(rows))
    post = df.loc[df["is_signal_window"]].iloc[0]
    assert post["orb_high"] >= post["orb_low"]


def test_no_signal_inside_orb_window():
    times = rth_minute_timestamps((2024, 1, 16), 35, (9, 30))
    df = _prep(pd.DataFrame([make_bar(t, 100, 150, 90, 140, volume=0.1) for t in times]))
    row = df.loc[df["is_orb_window"]].iloc[-1]
    assert detect_breakout_signal(row, require_vwap_guard=True) is None


def test_long_signal_requires_strict_vwap_guard():
    row = pd.Series(
        {
            "is_signal_window": True,
            "orb_valid": True,
            "orb_high": 100.0,
            "orb_low": 90.0,
            "ask_close": 101.0,
            "bid_close": 99.0,
            "vwap": 101.0,
        }
    )
    assert detect_breakout_signal(row, require_vwap_guard=True) is None

    row["ask_close"] = 101.01
    assert detect_breakout_signal(row, require_vwap_guard=True) == "long"


def test_narrow_orb_invalid(narrow_orb_df, default_config):
    from src.session.session_calendar import annotate_sessions, filter_rth

    df = annotate_sessions(
        narrow_orb_df, default_config.session, default_config.orb, default_config.strategy
    )
    df = filter_rth(df)
    df = compute_vwap(df)
    df = compute_orb_levels(df, default_config.orb)
    post = df.loc[df["is_signal_window"]]
    assert not post["orb_valid"].any()
