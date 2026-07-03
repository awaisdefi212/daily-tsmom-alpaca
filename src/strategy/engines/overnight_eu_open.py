"""Kelly/Muravyev European-open overnight drift — long EU window."""

from __future__ import annotations

import pandas as pd

from src.config import StrategyConfig


def generate_overnight_eu_signals(df: pd.DataFrame, strategy_cfg: StrategyConfig) -> pd.DataFrame:
    """
    v1: unconditional long at EU open entry bar.
    v2: long only when require_prior_rth_down and prior_rth_return_pts < 0.
    """
    out = df.copy()
    out["signal"] = None

    for session_date, idx in out.groupby("session_date", sort=False).groups.items():
        entry_mask = out.loc[idx, "is_eu_entry_bar"] & out.loc[idx, "spread_ok"]
        entry_rows = out.loc[idx].index[entry_mask]
        if len(entry_rows) == 0:
            continue

        entry_i = entry_rows[0]
        if strategy_cfg.require_prior_rth_down:
            ret = out.at[entry_i, "prior_rth_return_pts"]
            if pd.isna(ret) or float(ret) >= 0:
                continue

        out.at[entry_i, "signal"] = "long"

    return out
