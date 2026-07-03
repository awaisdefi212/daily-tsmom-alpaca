"""Moskowitz-style daily time-series momentum — monthly rebalance."""

from __future__ import annotations

import pandas as pd

from src.config import StrategyConfig


def generate_daily_tsmom_signals(df: pd.DataFrame, strategy_cfg: StrategyConfig) -> pd.DataFrame:
    """
    Long/short on first RTH day of each month when 12m return is known.

    Uses tsmom_return computed from prior day's close (see daily_calendar).
    """
    out = df.copy()
    out["signal"] = None

    rebalance = out["is_rebalance_bar"] & out["tsmom_return"].notna()
    for idx in out.index[rebalance]:
        ret = float(out.at[idx, "tsmom_return"])
        if ret > 0:
            out.at[idx, "signal"] = "long"
        elif not strategy_cfg.tsmom_long_only:
            out.at[idx, "signal"] = "short"

    return out
