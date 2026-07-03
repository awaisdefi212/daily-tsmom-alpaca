"""Tests for overnight EU open strategy."""

import pandas as pd

from src.config import StrategyConfig, SessionConfig, OrbConfig
from src.session.session_calendar import annotate_sessions
from src.session.overnight_calendar import annotate_overnight_windows
from src.strategy.engines.overnight_eu_open import generate_overnight_eu_signals
from tests.fixtures.synthetic import make_bar, rth_minute_timestamps


def _eu_bar(ts, close: float, spread: float = 2.0) -> dict:
    return make_bar(ts, close, close + 5, close - 5, close, spread=spread)


def _build_two_day_with_eu_window() -> pd.DataFrame:
    rows = []
    # Monday RTH — down day (close below open)
    for i, t in enumerate(rth_minute_timestamps((2024, 7, 1), 390, (9, 30))):
        close = 10000.0 - i * 0.1
        rows.append(_eu_bar(t, close))
    # Monday overnight through Tuesday pre-open including EU window
    # Tuesday 02:00-02:59 ET (session_date Monday for before-open bars)
    for hour, minute in [(1, 0), (2, 0), (2, 30), (2, 59)]:
        t = _eu_bar(
            __import__("tests.fixtures.synthetic", fromlist=["et_to_eet_ts"]).et_to_eet_ts(
                2024, 7, 2, hour, minute
            ),
            9950.0,
        )
        rows.append(t)
    return pd.DataFrame(rows)


def _overnight_pipeline(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    orb = OrbConfig()
    df = annotate_sessions(df, SessionConfig(), orb, cfg)
    df = annotate_overnight_windows(df, SessionConfig(), cfg)
    return generate_overnight_eu_signals(df.loc[df["is_eu_open_window"]], cfg)


def test_v1_long_at_eu_entry():
    cfg = StrategyConfig(
        strategy_type="overnight_eu_open",
        eu_open_start="02:00",
        eu_open_end="03:00",
        max_overnight_spread=20.0,
        require_prior_rth_down=False,
    )
    df = _overnight_pipeline(_build_two_day_with_eu_window(), cfg)
    signals = df.loc[df["signal"].notna()]
    assert len(signals) >= 1
    assert signals.iloc[0]["signal"] == "long"
    assert bool(signals.iloc[0]["is_eu_entry_bar"])


def test_v2_skips_when_prior_rth_up():
    cfg = StrategyConfig(
        strategy_type="overnight_eu_open",
        eu_open_start="02:00",
        eu_open_end="03:00",
        require_prior_rth_down=True,
        max_overnight_spread=20.0,
    )
    # Up day Monday RTH
    rows = []
    for i, t in enumerate(rth_minute_timestamps((2024, 7, 1), 390, (9, 30))):
        rows.append(_eu_bar(t, 10000.0 + i * 0.1))
    from tests.fixtures.synthetic import et_to_eet_ts

    for minute in range(0, 60):
        rows.append(_eu_bar(et_to_eet_ts(2024, 7, 2, 2, minute), 10100.0))
    df = _overnight_pipeline(pd.DataFrame(rows), cfg)
    assert (df["signal"].notna()).sum() == 0


def test_skips_wide_spread():
    cfg = StrategyConfig(
        strategy_type="overnight_eu_open",
        eu_open_start="02:00",
        eu_open_end="03:00",
        max_overnight_spread=5.0,
        require_prior_rth_down=False,
    )
    from tests.fixtures.synthetic import et_to_eet_ts

    rows = []
    for i, t in enumerate(rth_minute_timestamps((2024, 7, 1), 390, (9, 30))):
        rows.append(_eu_bar(t, 10000.0))
    rows.append(_eu_bar(et_to_eet_ts(2024, 7, 2, 2, 0), 9950.0, spread=25.0))
    df = _overnight_pipeline(pd.DataFrame(rows), cfg)
    assert (df["signal"].notna()).sum() == 0
