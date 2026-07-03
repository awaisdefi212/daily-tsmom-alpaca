"""Noise area boundaries for intraday momentum (Beat the Market)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _session_open_and_prior_close(df: pd.DataFrame) -> pd.DataFrame:
    """Per session: RTH open bid and prior session last bid close."""
    rth = df.loc[df["is_rth"]].sort_values("timestamp")
    if rth.empty:
        return pd.DataFrame(columns=["session_date", "session_open", "prior_close"])

    opens = (
        rth.groupby("session_date", sort=True)
        .first()
        .reset_index()[["session_date", "bid_open"]]
        .rename(columns={"bid_open": "session_open"})
    )
    closes = (
        rth.groupby("session_date", sort=True)
        .last()
        .reset_index()[["session_date", "bid_close"]]
        .rename(columns={"bid_close": "session_close"})
    )
    stats = opens.merge(closes, on="session_date", how="left")
    stats["prior_close"] = stats["session_close"].shift(1)
    return stats[["session_date", "session_open", "prior_close"]]


def compute_noise_area(
    df: pd.DataFrame,
    lookback_days: int = 14,
    volatility_multiplier: float = 1.0,
) -> pd.DataFrame:
    """
    Add noise_upper, noise_lower, noise_sigma using gap-adjusted anchors.

    sigma at time T = mean absolute relative move from session open to T
    over the prior `lookback_days` sessions (no look-ahead).
    """
    out = df.copy()
    session_stats = _session_open_and_prior_close(out)
    if session_stats.empty:
        for col in ("noise_upper", "noise_lower", "noise_sigma", "session_open", "prior_close"):
            out[col] = np.nan
        return out

    out = out.merge(session_stats, on="session_date", how="left")

    open_px = out.groupby("session_date")["session_open"].transform("first")
    mid = out["mid_close"]
    out["_rel_move"] = np.where(open_px > 0, (mid / open_px - 1.0).abs(), np.nan)

    move_hist = (
        out.loc[out["is_rth"]]
        .groupby(["session_date", "et_minute"], sort=False)["_rel_move"]
        .first()
        .reset_index()
    )

    dates = sorted(move_hist["session_date"].unique())
    sigma_lookup: dict[tuple, float] = {}

    for i, day in enumerate(dates):
        prior_days = dates[max(0, i - lookback_days) : i]
        if not prior_days:
            continue
        prior = move_hist[move_hist["session_date"].isin(prior_days)]
        for et_min, grp in prior.groupby("et_minute"):
            sigma_lookup[(day, et_min)] = float(grp["_rel_move"].mean())

    sigmas = []
    for _, row in out.iterrows():
        key = (row["session_date"], row["et_minute"])
        sigmas.append(sigma_lookup.get(key, np.nan))
    out["noise_sigma"] = sigmas

    # Forward-fill sigma within session after first valid value
    out["noise_sigma"] = out.groupby("session_date")["noise_sigma"].ffill()

    upper_anchor = np.fmax(out["session_open"], out["prior_close"].fillna(out["session_open"]))
    lower_anchor = np.fmin(out["session_open"], out["prior_close"].fillna(out["session_open"]))

    vm_sig = volatility_multiplier * out["noise_sigma"]
    out["noise_upper"] = upper_anchor * (1.0 + vm_sig)
    out["noise_lower"] = lower_anchor * (1.0 - vm_sig)

    out.loc[~out["is_rth"], ["noise_upper", "noise_lower", "noise_sigma"]] = np.nan
    return out.drop(columns=["_rel_move"], errors="ignore")
