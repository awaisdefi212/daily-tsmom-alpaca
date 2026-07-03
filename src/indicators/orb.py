"""Opening Range Breakout levels (conservative bid/ask range)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import OrbConfig


def compute_orb_levels(df: pd.DataFrame, orb_cfg: OrbConfig) -> pd.DataFrame:
    """Add orb_high, orb_low, orb_mid, orb_width (NaN until ORB window closes)."""
    out = df.copy()
    orb_slice = out.loc[out["is_orb_window"]]
    if orb_slice.empty:
        for col in ("orb_high", "orb_low", "orb_mid", "orb_width"):
            out[col] = np.nan
        out["orb_valid"] = False
        return out

    grouped = orb_slice.groupby("session_date", sort=False)
    orb_stats = grouped.agg(
        orb_high=("ask_high", "max"),
        orb_low=("bid_low", "min"),
        has_volume=("volume", lambda s: (s > 0).any()),
    )
    orb_stats["orb_mid"] = (orb_stats["orb_high"] + orb_stats["orb_low"]) / 2.0
    orb_stats["orb_width"] = orb_stats["orb_high"] - orb_stats["orb_low"]
    orb_stats["orb_valid"] = (
        (orb_stats["orb_width"] >= orb_cfg.min_width_points)
        & (orb_stats["orb_width"] <= orb_cfg.max_width_points)
        & orb_stats["has_volume"]
    )

    out = out.merge(
        orb_stats[["orb_high", "orb_low", "orb_mid", "orb_width", "orb_valid"]],
        on="session_date",
        how="left",
    )
    post_orb_mask = out["is_rth"] & ~out["is_orb_window"]
    for col in ("orb_high", "orb_low", "orb_mid", "orb_width", "orb_valid"):
        out[col] = np.where(post_orb_mask, out[col], np.nan if col != "orb_valid" else False)

    return out


def detect_breakout_signal(row: pd.Series, require_vwap_guard: bool) -> str | None:
    """Return 'long', 'short', or None for a single post-ORB bar."""
    if not row.get("is_signal_window", False):
        return None
    if not row.get("orb_valid", False):
        return None
    if pd.isna(row.get("orb_high")) or pd.isna(row.get("orb_low")):
        return None

    vwap = row.get("vwap")
    if pd.isna(vwap):
        return None

    if row["ask_close"] > row["orb_high"]:
        if not require_vwap_guard or row["ask_close"] > vwap:
            return "long"
    if row["bid_close"] < row["orb_low"]:
        if not require_vwap_guard or row["bid_close"] < vwap:
            return "short"
    return None
