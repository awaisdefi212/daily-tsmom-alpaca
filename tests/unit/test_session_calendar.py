"""Session calendar logical tests."""

import pandas as pd

from src.config import SessionConfig, OrbConfig, StrategyConfig
from src.session.session_calendar import annotate_sessions, filter_rth, _hhmm_to_minutes
from tests.fixtures.synthetic import make_bar, et_to_eet_ts, rth_minute_timestamps


def _annotate(df: pd.DataFrame) -> pd.DataFrame:
    return annotate_sessions(
        df,
        SessionConfig(),
        OrbConfig(minutes=30),
        StrategyConfig(),
    )


def _et_minute(hour: int, minute: int) -> int:
    return hour * 60 + minute


def test_rth_flags_winter_session():
    times = rth_minute_timestamps((2024, 1, 16), 390, (9, 30))
    rows = [make_bar(t, 100, 101, 99, 100) for t in times]
    df = _annotate(pd.DataFrame(rows))
    rth = df.loc[df["is_rth"]]
    assert len(rth) == 390
    assert rth.iloc[0]["et_minute"] == _et_minute(9, 30)
    assert rth.iloc[-1]["et_minute"] == _et_minute(15, 59)


def test_orb_window_thirty_minutes():
    times = rth_minute_timestamps((2024, 1, 16), 60, (9, 30))
    df = _annotate(pd.DataFrame([make_bar(t, 100, 101, 99, 100) for t in times]))
    orb = df.loc[df["is_orb_window"]]
    assert len(orb) == 30
    assert not df.loc[df["et_minute"] == _et_minute(10, 0), "is_orb_window"].iloc[0]


def test_signal_window_starts_after_orb():
    times = rth_minute_timestamps((2024, 1, 16), 90, (9, 30))
    df = _annotate(pd.DataFrame([make_bar(t, 100, 101, 99, 100) for t in times]))
    assert not df.loc[df["et_minute"] == _et_minute(9, 45), "is_signal_window"].iloc[0]
    assert df.loc[df["et_minute"] == _et_minute(10, 0), "is_signal_window"].iloc[0]


def test_session_end_bar_is_last_rth_bar():
    times = rth_minute_timestamps((2024, 1, 16), 390, (9, 30))
    df = _annotate(pd.DataFrame([make_bar(t, 100, 101, 99, 100) for t in times]))
    ends = df.loc[df["is_session_end_bar"]]
    assert len(ends) == 1
    assert ends.iloc[0]["et_minute"] == _et_minute(15, 59)


def test_dst_spring_forward_annotates_without_duplicate_open():
    # US spring forward 2024-03-10: 9:30 ET exists once
    times = rth_minute_timestamps((2024, 3, 11), 120, (9, 30))
    df = _annotate(pd.DataFrame([make_bar(t, 100, 101, 99, 100) for t in times]))
    opens = df.loc[df["et_minute"] == _et_minute(9, 30)]
    assert len(opens) == 1


def test_filter_rth_excludes_premarket():
    pre = et_to_eet_ts(2024, 1, 16, 8, 0)
    rth = et_to_eet_ts(2024, 1, 16, 10, 0)
    df = _annotate(pd.DataFrame([make_bar(pre, 100, 101, 99, 100), make_bar(rth, 100, 101, 99, 100)]))
    out = filter_rth(df)
    assert len(out) == 1
