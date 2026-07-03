"""US RTH session calendar and ORB/signal window flags."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd

from src.config import SessionConfig, OrbConfig, StrategyConfig


def _hhmm_to_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def annotate_sessions(
    df: pd.DataFrame,
    session_cfg: SessionConfig,
    orb_cfg: OrbConfig,
    strategy_cfg: StrategyConfig,
) -> pd.DataFrame:
    out = df.copy()
    et_tz = ZoneInfo(session_cfg.timezone)
    rth_open_min = _hhmm_to_minutes(session_cfg.rth_open)
    rth_close_min = _hhmm_to_minutes(session_cfg.rth_close)
    entry_start_min = _hhmm_to_minutes(strategy_cfg.entry_start)
    entry_cutoff_min = _hhmm_to_minutes(strategy_cfg.entry_cutoff)
    orb_end_min = rth_open_min + orb_cfg.minutes

    if out["timestamp"].dt.tz is None:
        raise ValueError("timestamp column must be timezone-aware")

    et_ts = out["timestamp"].dt.tz_convert(et_tz)
    out["et_timestamp"] = et_ts
    out["et_minute"] = et_ts.dt.hour * 60 + et_ts.dt.minute
    out["session_date"] = et_ts.dt.date

    before_open = out["et_minute"] < rth_open_min
    out.loc[before_open, "session_date"] = (
        et_ts[before_open].dt.normalize() - pd.Timedelta(days=1)
    ).dt.date.values

    is_rth = (out["et_minute"] >= rth_open_min) & (out["et_minute"] < rth_close_min)
    out["is_rth"] = is_rth
    out["is_orb_window"] = is_rth & (out["et_minute"] >= rth_open_min) & (out["et_minute"] < orb_end_min)
    out["is_signal_window"] = (
        is_rth
        & (out["et_minute"] >= orb_end_min)
        & (out["et_minute"] < entry_cutoff_min)
    )
    out["is_entry_window"] = (
        is_rth
        & (out["et_minute"] >= max(orb_end_min, entry_start_min))
        & (out["et_minute"] < entry_cutoff_min)
    )

    out["is_session_end_bar"] = False
    rth = out.loc[is_rth]
    if not rth.empty:
        for _, group in rth.groupby("session_date", sort=False):
            out.loc[group.index[-1], "is_session_end_bar"] = True

    return out


def filter_rth(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[df["is_rth"]].copy().reset_index(drop=True)


def session_dates(df: pd.DataFrame) -> list:
    rth = df.loc[df["is_rth"]]
    return sorted(rth["session_date"].unique())
