"""VWAP logical tests."""

import numpy as np
import pandas as pd

from src.config import SessionConfig, OrbConfig, StrategyConfig
from src.indicators.vwap import compute_vwap
from src.session.session_calendar import annotate_sessions
from tests.fixtures.synthetic import make_bar, rth_minute_timestamps


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    df = annotate_sessions(df, SessionConfig(), OrbConfig(), StrategyConfig())
    return compute_vwap(df.loc[df["is_rth"]].copy())


def test_vwap_hand_calculated_five_bars():
    times = rth_minute_timestamps((2024, 1, 16), 5, (9, 30))
    rows = []
    prices = [(100, 102, 99, 101), (101, 103, 100, 102), (102, 104, 101, 103), (103, 105, 102, 104), (104, 106, 103, 105)]
    vols = [0.1, 0.2, 0.0, 0.1, 0.1]
    for t, (o, h, l, c), v in zip(times, prices, vols):
        rows.append(make_bar(t, o, h, l, c, volume=v))
    df = _prep(pd.DataFrame(rows))

    # VWAP uses ask-side typical price: (ask_high + ask_low + ask_close) / 3
    def tp(h, l, c, spread=2.0):
        return ((h + spread) + (l + spread) + (c + spread)) / 3.0

    cum_pv = 0.0
    cum_v = 0.0
    for (o, h, l, c), v in zip(prices, vols):
        if v > 0:
            cum_pv += tp(h, l, c) * v
            cum_v += v
    expected = cum_pv / cum_v
    assert np.isclose(df.iloc[-1]["vwap"], expected, rtol=1e-6)


def test_zero_volume_carries_vwap_forward():
    times = rth_minute_timestamps((2024, 1, 16), 3, (9, 30))
    rows = [
        make_bar(times[0], 100, 101, 99, 100, volume=0.1),
        make_bar(times[1], 100, 101, 99, 100, volume=0.0),
        make_bar(times[2], 110, 111, 109, 110, volume=0.0),
    ]
    df = _prep(pd.DataFrame(rows))
    assert np.isclose(df.iloc[1]["vwap"], df.iloc[0]["vwap"])
    assert np.isclose(df.iloc[2]["vwap"], df.iloc[0]["vwap"])


def test_cum_volume_non_decreasing():
    times = rth_minute_timestamps((2024, 1, 16), 20, (9, 30))
    df = _prep(pd.DataFrame([make_bar(t, 100, 101, 99, 100, volume=0.05) for t in times]))
    assert df["cum_volume"].is_monotonic_increasing


def test_vwap_resets_each_session():
    times1 = rth_minute_timestamps((2024, 1, 16), 5, (9, 30))
    times2 = rth_minute_timestamps((2024, 1, 17), 5, (9, 30))
    rows = [make_bar(t, 100, 101, 99, 100, volume=0.1) for t in times1 + times2]
    full = annotate_sessions(pd.DataFrame(rows), SessionConfig(), OrbConfig(), StrategyConfig())
    df = compute_vwap(full.loc[full["is_rth"]])
    day2_first = df.loc[df["session_date"] == df["session_date"].iloc[-1]].iloc[0]
    expected = ((101 + 2) + (99 + 2) + (100 + 2)) / 3  # ask typical price
    assert np.isclose(day2_first["vwap"], expected, rtol=1e-4)
