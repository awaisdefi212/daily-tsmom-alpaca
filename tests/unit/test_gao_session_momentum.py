"""Gao session momentum signal tests."""

import pandas as pd

from src.config import StrategyConfig, SessionConfig, OrbConfig, VwapConfig
from src.session.session_calendar import annotate_sessions, filter_rth
from src.indicators.vwap import compute_vwap
from src.strategy.engines.gao_session_momentum import generate_gao_session_signals
from tests.fixtures.synthetic import make_bar, rth_minute_timestamps


def _gao_pipeline(df: pd.DataFrame, strategy_cfg: StrategyConfig) -> pd.DataFrame:
    orb = OrbConfig(minutes=30)
    df = annotate_sessions(df, SessionConfig(), orb, strategy_cfg)
    df = filter_rth(df)
    df = compute_vwap(df, VwapConfig())
    for col in ("orb_high", "orb_low", "orb_mid", "orb_width"):
        df[col] = 0.0
    return generate_gao_session_signals(df, strategy_cfg)


def _two_day_bars(day2_morning_close: float) -> pd.DataFrame:
    rows = []
    for day in ((2024, 7, 1), (2024, 7, 2)):
        times = rth_minute_timestamps(day, 390, (9, 30))
        for i, t in enumerate(times):
            close = 10000.0
            if day == (2024, 7, 2) and i == 30:
                close = day2_morning_close
            rows.append(make_bar(t, close, close + 5, close - 5, close, spread=2.0))
    return pd.DataFrame(rows)


def test_gao_long_when_morning_return_positive():
    cfg = StrategyConfig(strategy_type="gao_session_momentum", morning_end="10:00", entry_time="15:30")
    df = _gao_pipeline(_two_day_bars(10100.0), cfg)
    day2 = df.loc[df["session_date"] == pd.Timestamp(2024, 7, 2).date()]
    signals = day2.loc[day2["signal"].notna()]
    assert len(signals) == 1
    assert signals.iloc[0]["signal"] == "long"
    assert signals.iloc[0]["et_minute"] == 15 * 60 + 30
    assert float(signals.iloc[0]["morning_return_pts"]) == 100.0


def test_gao_short_when_morning_return_negative():
    cfg = StrategyConfig(strategy_type="gao_session_momentum", morning_end="10:00", entry_time="15:30")
    df = _gao_pipeline(_two_day_bars(9900.0), cfg)
    day2 = df.loc[df["session_date"] == pd.Timestamp(2024, 7, 2).date()]
    signals = day2.loc[day2["signal"].notna()]
    assert len(signals) == 1
    assert signals.iloc[0]["signal"] == "short"


def test_gao_no_signal_when_morning_return_zero():
    cfg = StrategyConfig(strategy_type="gao_session_momentum", morning_end="10:00", entry_time="15:30")
    df = _gao_pipeline(_two_day_bars(10000.0), cfg)
    assert (df["signal"].notna()).sum() == 0


def test_gao_no_signal_on_first_session():
    cfg = StrategyConfig(strategy_type="gao_session_momentum", morning_end="10:00", entry_time="15:30")
    times = rth_minute_timestamps((2024, 7, 1), 390, (9, 30))
    rows = [make_bar(t, 10000, 10005, 9995, 10000, spread=2.0) for t in times]
    df = _gao_pipeline(pd.DataFrame(rows), cfg)
    assert (df["signal"].notna()).sum() == 0


def test_session_hold_plan_has_no_target():
    from src.config import RiskConfig
    from src.strategy.risk import build_trade_plan

    cfg = RiskConfig(stop_mode="session_hold", fixed_stop_points=500)
    plan = build_trade_plan("long", 15000.0, 0.0, 0.0, 0.0, 0.0, cfg)
    assert plan.target_price is None
    assert plan.stop_price == 14500.0
