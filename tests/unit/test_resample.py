"""Unit tests for bar resampling."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.data.resample import resample_bars
from tests.fixtures.synthetic import make_bar, et_to_eet_ts

ET = ZoneInfo("America/New_York")


def _five_1min_bars(start: datetime) -> pd.DataFrame:
    rows = []
    for i in range(5):
        ts = et_to_eet_ts(start.year, start.month, start.day, start.hour, start.minute + i)
        b = 15000.0 + i
        rows.append(make_bar(ts, b, b + 10, b - 5, b + 2, spread=2.0, volume=0.1))
    return pd.DataFrame(rows)


def test_resample_5m_ohlc_invariants():
    start = datetime(2024, 3, 4, 9, 30, tzinfo=ET)
    df = _five_1min_bars(start)
    out = resample_bars(df, 5)
    assert len(out) == 1
    assert out.iloc[0]["bid_high"] == pytest.approx(15004.0 + 10)
    assert out.iloc[0]["bid_low"] == pytest.approx(15000.0 - 5)
    assert out.iloc[0]["bid_open"] == pytest.approx(15000.0)
    assert out.iloc[0]["bid_close"] == pytest.approx(15004.0 + 2)
    assert out.iloc[0]["volume"] == pytest.approx(0.5)


def test_resample_preserves_monotonic_time():
    start = datetime(2024, 3, 4, 9, 30, tzinfo=ET)
    rows = []
    for block in range(3):
        base = start + timedelta(minutes=block * 5)
        rows.extend(_five_1min_bars(base).to_dict("records"))
    df = pd.DataFrame(rows)
    out = resample_bars(df, 5)
    assert out["timestamp"].is_monotonic_increasing
    assert len(out) == 3


def test_resample_spread_sanity():
    start = datetime(2024, 3, 4, 9, 30, tzinfo=ET)
    df = _five_1min_bars(start)
    out = resample_bars(df, 5)
    assert (out["spread"] >= 0).all()
    assert (out["ask_high"] >= out["bid_high"]).all()
    assert (out["ask_low"] >= out["bid_low"]).all()


def test_resample_minutes_one_is_noop():
    start = datetime(2024, 3, 4, 9, 30, tzinfo=ET)
    df = _five_1min_bars(start)
    out = resample_bars(df, 1)
    assert len(out) == len(df)


def test_resample_daily_rth_one_bar_per_session():
    from datetime import date

    from src.config import OrbConfig, SessionConfig, StrategyConfig
    from src.data.resample import resample_daily_rth
    from src.session.session_calendar import annotate_sessions, filter_rth
    from tests.unit.test_daily_tsmom import _rth_day

    base = date(2024, 3, 4)
    df = _rth_day(base, 15000.0)
    session_cfg = SessionConfig()
    orb_cfg = OrbConfig()
    strategy_cfg = StrategyConfig()
    df = annotate_sessions(df, session_cfg, orb_cfg, strategy_cfg)
    df = filter_rth(df)
    daily = resample_daily_rth(df)
    assert len(daily) == 1
    assert daily.iloc[0]["bid_close"] == pytest.approx(15000.0)
