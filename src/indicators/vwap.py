"""Session-anchored VWAP from RTH open."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import VwapConfig


def compute_vwap(df: pd.DataFrame, vwap_cfg: VwapConfig | None = None) -> pd.DataFrame:
    """Add vwap, cum_volume, vwap_slope, session_vol_median columns."""
    if vwap_cfg is None:
        vwap_cfg = VwapConfig()

    out = df.copy()
    out["typical_price"] = (out["ask_high"] + out["ask_low"] + out["ask_close"]) / 3.0

    vol_mask = out["volume"] > 0
    out["_pv"] = np.where(vol_mask, out["typical_price"] * out["volume"], 0.0)
    out["_v"] = np.where(vol_mask, out["volume"], 0.0)

    grouped = out.groupby("session_date", sort=False)
    out["cum_volume"] = grouped["_v"].cumsum()
    out["cum_pv"] = grouped["_pv"].cumsum()
    out["vwap"] = np.where(out["cum_volume"] > 0, out["cum_pv"] / out["cum_volume"], np.nan)
    out["vwap"] = grouped["vwap"].ffill()

    lookback = vwap_cfg.slope_lookback_bars
    out["vwap_lag"] = grouped["vwap"].shift(lookback)
    out["vwap_slope_up"] = out["vwap"] > out["vwap_lag"]
    out["vwap_slope_down"] = out["vwap"] < out["vwap_lag"]
    out["vwap_slope_flat"] = (out["vwap"] - out["vwap_lag"]).abs() <= vwap_cfg.slope_flat_points

    out["session_vol_median"] = grouped["volume"].transform("median")

    return out.drop(columns=["_pv", "_v", "vwap_lag"])


def orb_window_has_volume(df: pd.DataFrame) -> bool:
    orb = df.loc[df["is_orb_window"]]
    return bool((orb["volume"] > 0).any())
