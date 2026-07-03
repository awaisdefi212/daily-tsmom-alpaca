"""Unit tests for daily TSMOM signal timing and resample."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.config import StrategyConfig
from src.data.resample import resample_daily_rth
from src.session.daily_calendar import annotate_daily_rebalance
from src.session.session_calendar import annotate_sessions, filter_rth
from src.strategy.engines.daily_tsmom import generate_daily_tsmom_signals
from tests.fixtures.synthetic import et_to_eet_ts, make_bar

ET = ZoneInfo("America/New_York")


def _rth_day(session: date, close_mid: float) -> pd.DataFrame:
    """Single RTH session as 1m bars with flat close at close_mid."""
    rows = []
    for minute in range(390):
        h = 9 + (30 + minute) // 60
        m = (30 + minute) % 60
        ts = et_to_eet_ts(session.year, session.month, session.day, h, m)
        spread = 2.0
        rows.append(
            make_bar(
                ts,
                close_mid,
                close_mid + spread,
                close_mid - 1,
                close_mid,
                spread=spread,
                volume=0.1,
            )
        )
    return pd.DataFrame(rows)


def _weekdays(n: int, start: date) -> list[date]:
    d = start
    out: list[date] = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _build_daily_series(closes: list[tuple[date, float]]) -> pd.DataFrame:
    from src.config import OrbConfig, SessionConfig

    session_cfg = SessionConfig()
    orb_cfg = OrbConfig()
    strategy_cfg = StrategyConfig(strategy_type="daily_tsmom", tsmom_lookback_days=5)

    parts = [_rth_day(d, px) for d, px in closes]
    df = pd.concat(parts, ignore_index=True)
    df = annotate_sessions(df, session_cfg, orb_cfg, strategy_cfg)
    df = filter_rth(df)
    daily = resample_daily_rth(df)
    return annotate_daily_rebalance(daily, strategy_cfg)


def test_tsmom_return_uses_prior_close_not_same_day():
    """Rebalance-day return uses prior close vs lagged close (no same-day leakage)."""
    strategy_cfg = StrategyConfig(strategy_type="daily_tsmom", tsmom_lookback_days=5)
    days = _weekdays(12, date(2024, 1, 2))
    daily = pd.DataFrame(
        {
            "session_date": days,
            "timestamp": pd.to_datetime(days),
            "bid_close": [10000.0 + i * 10 for i in range(len(days))],
            "ask_close": [10002.0 + i * 10 for i in range(len(days))],
            "bid_open": 10000.0,
            "bid_high": 10010.0,
            "bid_low": 9990.0,
            "ask_open": 10002.0,
            "ask_high": 10012.0,
            "ask_low": 9992.0,
            "volume": 1.0,
        }
    )
    daily = annotate_daily_rebalance(daily, strategy_cfg)
    valid = daily.loc[daily["tsmom_return"].notna()]
    assert not valid.empty
    idx = valid.index[0]
    prev = daily.loc[idx - 1, "mid_close"]
    lag = daily.loc[idx - 6, "mid_close"]
    assert daily.loc[idx, "tsmom_return"] == pytest.approx(prev / lag - 1.0)
    assert daily.loc[idx, "mid_close"] != prev


def test_signal_only_on_rebalance_bars():
    days = _weekdays(40, date(2024, 1, 2))
    closes = [(d, 10000.0 + i * 50.0) for i, d in enumerate(days)]
    daily = _build_daily_series(closes)
    sig = generate_daily_tsmom_signals(
        daily, StrategyConfig(strategy_type="daily_tsmom", tsmom_lookback_days=5)
    )
    signaled = sig.loc[sig["signal"].notna()]
    assert not signaled.empty
    assert (signaled["is_rebalance_bar"]).all()
    assert sig.loc[~sig["is_rebalance_bar"], "signal"].isna().all()


def test_long_only_bearish_rebalance_is_flat():
    """Long-only mode: negative 12m return → no signal (flat)."""
    strategy_cfg = StrategyConfig(
        strategy_type="daily_tsmom",
        tsmom_lookback_days=5,
        tsmom_long_only=True,
    )
    daily = pd.DataFrame(
        {
            "session_date": [date(2024, 2, 1)],
            "is_rebalance_bar": [True],
            "tsmom_return": [-0.05],
        }
    )
    sig = generate_daily_tsmom_signals(daily, strategy_cfg)
    assert sig.iloc[0]["signal"] is None or pd.isna(sig.iloc[0]["signal"])


def test_long_only_bullish_rebalance_is_long():
    days = _weekdays(40, date(2024, 1, 2))
    closes = [(d, 10000.0 + i * 50.0) for i, d in enumerate(days)]
    daily = _build_daily_series(closes)
    sig = generate_daily_tsmom_signals(
        daily,
        StrategyConfig(
            strategy_type="daily_tsmom",
            tsmom_lookback_days=5,
            tsmom_long_only=True,
        ),
    )
    signaled = sig.loc[sig["signal"].notna()]
    assert not signaled.empty
    assert (signaled["signal"] == "long").all()


def test_zero_return_long_only_is_flat():
    strategy_cfg = StrategyConfig(strategy_type="daily_tsmom", tsmom_long_only=True)
    daily = pd.DataFrame(
        {
            "session_date": [date(2024, 2, 1)],
            "is_rebalance_bar": [True],
            "tsmom_return": [0.0],
        }
    )
    sig = generate_daily_tsmom_signals(daily, strategy_cfg)
    assert sig.iloc[0]["signal"] is None or pd.isna(sig.iloc[0]["signal"])


def test_first_rth_day_of_month_is_rebalance():
    """First trading session of each calendar month is flagged rebalance."""
    days = _weekdays(35, date(2024, 1, 2))
    daily = pd.DataFrame(
        {
            "session_date": days,
            "timestamp": pd.to_datetime(days),
            "bid_close": [10000.0] * len(days),
            "ask_close": [10002.0] * len(days),
            "bid_open": 10000.0,
            "bid_high": 10010.0,
            "bid_low": 9990.0,
            "ask_open": 10002.0,
            "ask_high": 10012.0,
            "ask_low": 9992.0,
            "volume": 1.0,
        }
    )
    daily = annotate_daily_rebalance(
        daily, StrategyConfig(strategy_type="daily_tsmom", tsmom_lookback_days=2)
    )
    feb_first = daily[daily["session_date"] == date(2024, 2, 1)]
    assert not feb_first.empty
    assert bool(feb_first.iloc[0]["is_rebalance_bar"])


def test_tsmom_return_ignores_same_day_close():
    """Changing rebalance-day close must not alter tsmom_return (no look-ahead)."""
    strategy_cfg = StrategyConfig(strategy_type="daily_tsmom", tsmom_lookback_days=5)
    days = _weekdays(12, date(2024, 1, 2))
    daily = pd.DataFrame(
        {
            "session_date": days,
            "timestamp": pd.to_datetime(days),
            "bid_close": [10000.0 + i * 10 for i in range(len(days))],
            "ask_close": [10002.0 + i * 10 for i in range(len(days))],
            "bid_open": 10000.0,
            "bid_high": 10010.0,
            "bid_low": 9990.0,
            "ask_open": 10002.0,
            "ask_high": 10012.0,
            "ask_low": 9992.0,
            "volume": 1.0,
        }
    )
    base = annotate_daily_rebalance(daily, strategy_cfg)
    mutated = daily.copy()
    mutated.loc[mutated.index[-1], "bid_close"] = 99999.0
    mutated.loc[mutated.index[-1], "ask_close"] = 100001.0
    alt = annotate_daily_rebalance(mutated, strategy_cfg)
    idx = base.index[-1]
    assert base.loc[idx, "tsmom_return"] == pytest.approx(alt.loc[idx, "tsmom_return"])


def test_resample_daily_one_bar_per_session():
    base = date(2024, 3, 4)
    df = _rth_day(base, 15000.0)
    from src.config import OrbConfig, SessionConfig, StrategyConfig

    session_cfg = SessionConfig()
    orb_cfg = OrbConfig()
    strategy_cfg = StrategyConfig()
    df = annotate_sessions(df, session_cfg, orb_cfg, strategy_cfg)
    df = filter_rth(df)
    daily = resample_daily_rth(df)
    assert len(daily) == 1
    assert daily.iloc[0]["bid_close"] == pytest.approx(15000.0)
