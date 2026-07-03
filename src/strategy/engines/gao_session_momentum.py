"""Gao et al. (2018) first-30min -> last-30min session momentum signals."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import StrategyConfig
from src.session.session_calendar import _hhmm_to_minutes


def _session_morning_table(df: pd.DataFrame, morning_end_min: int) -> pd.DataFrame:
    """Per session: morning price at morning_end and prior RTH close."""
    rows: list[dict] = []
    for session_date, grp in df.groupby("session_date", sort=True):
        grp = grp.sort_values("et_minute")
        morning = grp.loc[grp["et_minute"] >= morning_end_min]
        if morning.empty:
            continue
        rows.append(
            {
                "session_date": session_date,
                "morning_price": float(morning.iloc[0]["bid_close"]),
                "session_close": float(grp.iloc[-1]["bid_close"]),
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=["session_date", "morning_price", "session_close", "prior_rth_close", "morning_return_pts"]
        )

    sess = pd.DataFrame(rows).sort_values("session_date").reset_index(drop=True)
    sess["prior_rth_close"] = sess["session_close"].shift(1)
    sess["morning_return_pts"] = sess["morning_price"] - sess["prior_rth_close"]
    return sess


def generate_gao_session_signals(df: pd.DataFrame, strategy_cfg: StrategyConfig) -> pd.DataFrame:
    """
    Morning return = bid at morning_end minus prior session RTH close.
    Enter long/short at entry_time bar in direction of morning return; flat if zero.
    """
    out = df.copy()
    out["signal"] = None
    out["morning_return_pts"] = np.nan
    out["prior_rth_close"] = np.nan
    out["morning_price"] = np.nan

    morning_end_min = _hhmm_to_minutes(strategy_cfg.morning_end)
    entry_min = _hhmm_to_minutes(strategy_cfg.entry_time)
    sess = _session_morning_table(out, morning_end_min)
    if sess.empty:
        return out

    stats = sess.set_index("session_date")[
        ["morning_return_pts", "prior_rth_close", "morning_price"]
    ]

    for session_date, idx in out.groupby("session_date", sort=False).groups.items():
        if session_date not in stats.index:
            continue
        row = stats.loc[session_date]
        if pd.isna(row["prior_rth_close"]):
            continue

        ret = float(row["morning_return_pts"])
        out.loc[idx, "morning_return_pts"] = ret
        out.loc[idx, "prior_rth_close"] = float(row["prior_rth_close"])
        out.loc[idx, "morning_price"] = float(row["morning_price"])

        entry_mask = out.loc[idx, "et_minute"] == entry_min
        entry_indices = out.loc[idx].index[entry_mask]
        if len(entry_indices) == 0:
            continue

        entry_i = entry_indices[0]
        if ret > 0:
            out.at[entry_i, "signal"] = "long"
        elif ret < 0:
            out.at[entry_i, "signal"] = "short"

    return out
