"""Resample 1-minute bid/ask bars to higher timeframes."""

from __future__ import annotations

import pandas as pd


OHLC_AGG = {
    "bid_open": "first",
    "bid_high": "max",
    "bid_low": "min",
    "bid_close": "last",
    "ask_open": "first",
    "ask_high": "max",
    "ask_low": "min",
    "ask_close": "last",
    "volume": "sum",
}


def resample_bars(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Aggregate 1-min bars to N-minute bars without look-ahead."""
    if minutes <= 1:
        return df.copy()

    required = list(OHLC_AGG.keys())
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns for resample: {missing}")

    out = df.sort_values("timestamp").copy()
    out = out.set_index("timestamp")
    resampled = (
        out.resample(f"{minutes}min", label="left", closed="left")
        .agg(OHLC_AGG)
        .dropna(subset=["bid_close", "ask_close"])
    )
    resampled["mid_close"] = (resampled["bid_close"] + resampled["ask_close"]) / 2.0
    resampled["spread"] = resampled["ask_close"] - resampled["bid_close"]
    return resampled.reset_index()


def resample_daily_rth(df: pd.DataFrame) -> pd.DataFrame:
    """One bar per RTH session using session close OHLC (no look-ahead)."""
    if "session_date" not in df.columns:
        raise ValueError("session_date column required for daily RTH resample")

    required = list(OHLC_AGG.keys())
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns for daily resample: {missing}")

    rows: list[dict] = []
    for session_date, grp in df.groupby("session_date", sort=True):
        grp = grp.sort_values("timestamp")
        first = grp.iloc[0]
        last = grp.iloc[-1]
        row = {
                "timestamp": last["timestamp"],
                "session_date": session_date,
                "bid_open": float(first["bid_open"]),
                "bid_high": float(grp["bid_high"].max()),
                "bid_low": float(grp["bid_low"].min()),
                "bid_close": float(last["bid_close"]),
                "ask_open": float(first["ask_open"]),
                "ask_high": float(grp["ask_high"].max()),
                "ask_low": float(grp["ask_low"].min()),
                "ask_close": float(last["ask_close"]),
                "volume": float(grp["volume"].sum()) if "volume" in grp.columns else 0.0,
            }
        if "et_minute" in grp.columns:
            row["et_minute"] = int(last["et_minute"])
        if "et_timestamp" in grp.columns:
            row["et_timestamp"] = last["et_timestamp"]
        rows.append(row)

    out = pd.DataFrame(rows)
    out["mid_close"] = (out["bid_close"] + out["ask_close"]) / 2.0
    out["spread"] = out["ask_close"] - out["bid_close"]
    return out.reset_index(drop=True)
