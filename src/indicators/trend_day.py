"""Trend-day filter based on first-hour range."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_trend_day(
    df: pd.DataFrame,
    min_first_hour_range: float = 35.0,
    rth_open_minutes: int = 9 * 60 + 30,
    first_hour_end_minutes: int = 10 * 60 + 30,
) -> pd.DataFrame:
    """Add first_hour_range and is_trend_day columns."""
    out = df.copy()
    mask = (out["et_minute"] >= rth_open_minutes) & (out["et_minute"] < first_hour_end_minutes)
    first_hour = out.loc[mask]

    if first_hour.empty:
        out["first_hour_range"] = np.nan
        out["is_trend_day"] = False
        return out

    stats = first_hour.groupby("session_date", sort=False).agg(
        fh_ask_high=("ask_high", "max"),
        fh_bid_low=("bid_low", "min"),
    )
    stats["first_hour_range"] = stats["fh_ask_high"] - stats["fh_bid_low"]
    stats["is_trend_day"] = stats["first_hour_range"] >= min_first_hour_range

    out = out.merge(
        stats[["first_hour_range", "is_trend_day"]],
        on="session_date",
        how="left",
    )
    out["is_trend_day"] = out["is_trend_day"].fillna(False).astype(bool)
    return out


def compute_compression_day(
    df: pd.DataFrame,
    max_first_hour_range: float = 30.0,
    rth_open_minutes: int = 9 * 60 + 30,
    first_hour_end_minutes: int = 10 * 60 + 30,
) -> pd.DataFrame:
    """Add first_hour_range and is_compression_day (narrow first-hour range)."""
    out = compute_trend_day(
        df,
        min_first_hour_range=0.0,
        rth_open_minutes=rth_open_minutes,
        first_hour_end_minutes=first_hour_end_minutes,
    )
    out["is_compression_day"] = out["first_hour_range"] <= max_first_hour_range
    out["is_compression_day"] = out["is_compression_day"].fillna(False).astype(bool)
    return out
