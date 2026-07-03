"""Intraday momentum signals using noise area boundaries."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import StrategyConfig
from src.session.session_calendar import _hhmm_to_minutes


def _is_momentum_check(et_minute: int, check_interval: int, entry_start: str, entry_cutoff: str) -> bool:
    start = _hhmm_to_minutes(entry_start)
    cutoff = _hhmm_to_minutes(entry_cutoff)
    if et_minute < start or et_minute >= cutoff:
        return False
    return et_minute % check_interval == 0


def generate_momentum_signals(df: pd.DataFrame, strategy_cfg: StrategyConfig) -> pd.DataFrame:
    """Enter long above noise_upper or short below noise_lower at check intervals."""
    out = df.copy()
    out["signal"] = None
    out["entry_noise_lower"] = np.nan
    out["entry_noise_upper"] = np.nan

    interval = strategy_cfg.momentum_check_minutes

    for _, idx in out.groupby("session_date", sort=False).groups.items():
        traded = False
        for i in idx:
            row = out.loc[i]
            if traded:
                continue
            if not _is_momentum_check(
                int(row["et_minute"]),
                interval,
                strategy_cfg.entry_start,
                strategy_cfg.entry_cutoff,
            ):
                continue
            if pd.isna(row.get("noise_upper")) or pd.isna(row.get("noise_lower")):
                continue

            upper = row["noise_upper"]
            lower = row["noise_lower"]

            if row["ask_close"] > upper:
                out.at[i, "signal"] = "long"
                out.at[i, "entry_noise_lower"] = lower
                out.at[i, "entry_noise_upper"] = upper
                traded = True
            elif row["bid_close"] < lower:
                out.at[i, "signal"] = "short"
                out.at[i, "entry_noise_lower"] = lower
                out.at[i, "entry_noise_upper"] = upper
                traded = True

    return out
