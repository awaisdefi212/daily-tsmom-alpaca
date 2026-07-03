"""Pullback retest entry signal tests."""

import pandas as pd

from src.config import StrategyConfig, SessionConfig, OrbConfig, VwapConfig
from src.session.session_calendar import annotate_sessions, filter_rth
from src.indicators.vwap import compute_vwap
from src.indicators.orb import compute_orb_levels
from src.strategy.signal_engine import generate_entry_signals
from tests.fixtures.synthetic import make_bar, rth_minute_timestamps


def _pipeline(df: pd.DataFrame, strategy_cfg: StrategyConfig, orb_minutes=45) -> pd.DataFrame:
    orb = OrbConfig(minutes=orb_minutes, min_width_points=15, max_width_points=200)
    df = annotate_sessions(df, SessionConfig(), orb, strategy_cfg)
    df = filter_rth(df)
    df = compute_vwap(df, VwapConfig())
    df = compute_orb_levels(df, orb)
    return generate_entry_signals(df, strategy_cfg)


def test_breakout_close_fires_immediately():
    """breakout_close mode enters on breakout bar."""
    cfg = StrategyConfig(
        entry_mode="breakout_close",
        require_vwap_guard=True,
        min_breakout_volume_mult=0,
    )
    times = rth_minute_timestamps((2024, 2, 5), 90, (9, 30))
    rows = []
    for i, t in enumerate(times):
        if i < 45:
            rows.append(make_bar(t, 17000, 17020, 16995, 17005, spread=2.0, volume=0.1))
        elif i == 50:
            rows.append(make_bar(t, 17025, 17040, 17020, 17035, spread=2.0, volume=0.2))
        else:
            rows.append(make_bar(t, 17010, 17015, 17005, 17010, spread=2.0, volume=0.05))
    df = _pipeline(pd.DataFrame(rows), cfg)
    assert (df["signal"] == "long").any()


def test_pullback_does_not_enter_on_breakout_bar():
    """pullback_retest arms on breakout but waits for retest."""
    cfg = StrategyConfig(
        entry_mode="pullback_retest",
        require_vwap_guard=True,
        min_breakout_volume_mult=0,
        require_vwap_slope=False,
        entry_start="10:00",
        entry_cutoff="12:00",
    )
    times = rth_minute_timestamps((2024, 2, 6), 90, (9, 30))
    rows = []
    for i, t in enumerate(times):
        if i < 45:
            rows.append(make_bar(t, 18000, 18020, 17995, 18005, spread=2.0, volume=0.1))
        elif i == 50:
            # Breakout only — no retest yet
            rows.append(make_bar(t, 18025, 18040, 18022, 18035, spread=2.0, volume=0.2))
        elif i < 60:
            rows.append(make_bar(t, 18010, 18015, 18005, 18010, spread=2.0, volume=0.05))
        else:
            rows.append(make_bar(t, 18010, 18015, 18005, 18010, spread=2.0, volume=0.05))
    df = _pipeline(pd.DataFrame(rows), cfg)
    breakout_bar = df.iloc[50]
    assert breakout_bar["signal"] is None or pd.isna(breakout_bar["signal"])


def test_pullback_enters_on_retest():
    """After breakout arm, retest of orb_high triggers long entry."""
    cfg = StrategyConfig(
        entry_mode="pullback_retest",
        require_vwap_guard=True,
        min_breakout_volume_mult=0,
        require_vwap_slope=False,
        entry_start="10:00",
        entry_cutoff="12:00",
        retest_tolerance_points=5,
    )
    times = rth_minute_timestamps((2024, 2, 7), 100, (9, 30))
    rows = []
    orb_high_approx = 19020.0
    for i, t in enumerate(times):
        if i < 45:
            b = 19000 + (i % 3)
            rows.append(make_bar(t, b, b + 18, b - 2, b + 8, spread=2.0, volume=0.1))
        elif i == 48:
            rows.append(make_bar(t, 19020, 19035, 19018, 19030, spread=2.0, volume=0.2))
        elif i in (49, 50):
            rows.append(make_bar(t, 19028, 19038, 19026, 19034, spread=2.0, volume=0.1))
        elif i == 52:
            rows.append(
                make_bar(
                    t,
                    19028,
                    19032,
                    orb_high_approx - 2,
                    19030,
                    spread=2.0,
                    volume=0.15,
                )
            )
        elif i < 45 or i > 55:
            rows.append(make_bar(t, 19010, 19015, 19005, 19010, spread=2.0, volume=0.05))
    df = _pipeline(pd.DataFrame(rows), cfg)
    assert (df["signal"] == "long").any()


def test_pullback_arm_cancelled_after_two_inside_closes():
    """Arm cancelled when price closes inside ORB for 2 bars."""
    cfg = StrategyConfig(
        entry_mode="pullback_retest",
        require_vwap_guard=False,
        min_breakout_volume_mult=0,
        require_vwap_slope=False,
        entry_start="10:00",
        entry_cutoff="12:00",
        arm_cancel_inside_bars=2,
    )
    times = rth_minute_timestamps((2024, 2, 8), 100, (9, 30))
    rows = []
    for i, t in enumerate(times):
        if i < 45:
            b = 20000
            rows.append(make_bar(t, b, b + 20, b - 2, b + 10, spread=2.0, volume=0.1))
        elif i == 48:
            rows.append(make_bar(t, 20025, 20040, 20020, 20035, spread=2.0, volume=0.2))
        elif i in (50, 51):
            # Two closes back inside ORB (below orb_high ~20020)
            rows.append(make_bar(t, 20010, 20015, 20005, 20012, spread=2.0, volume=0.1))
        elif i == 55:
            rows.append(
                make_bar(t, 20025, 20035, 20018, 20030, spread=2.0, volume=0.15)
            )
        else:
            rows.append(make_bar(t, 20010, 20015, 20005, 20010, spread=2.0, volume=0.05))
    df = _pipeline(pd.DataFrame(rows), cfg)
    assert (df["signal"] == "long").sum() == 0
