"""Overnight session windows and prior RTH return for EU-open strategies."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import SessionConfig, StrategyConfig
from src.session.session_calendar import _hhmm_to_minutes


def _rth_session_returns(df: pd.DataFrame, session_cfg: SessionConfig) -> pd.DataFrame:
    """Per session_date: RTH open/close bid and return from prior RTH close to session close."""
    rth_open_min = _hhmm_to_minutes(session_cfg.rth_open)
    rth_close_min = _hhmm_to_minutes(session_cfg.rth_close)
    rth = df.loc[df["is_rth"]].sort_values(["session_date", "et_minute"])
    rows: list[dict] = []
    for session_date, grp in rth.groupby("session_date", sort=True):
        if grp.empty:
            continue
        rows.append(
            {
                "session_date": session_date,
                "rth_open_price": float(grp.iloc[0]["bid_close"]),
                "rth_close_price": float(grp.iloc[-1]["bid_close"]),
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=["session_date", "rth_open_price", "rth_close_price", "prior_rth_close", "prior_rth_return_pts"]
        )
    sess = pd.DataFrame(rows).sort_values("session_date").reset_index(drop=True)
    sess["prior_rth_close"] = sess["rth_close_price"].shift(1)
    sess["prior_rth_return_pts"] = sess["rth_close_price"] - sess["prior_rth_close"]
    return sess


def annotate_overnight_windows(
    df: pd.DataFrame,
    session_cfg: SessionConfig,
    strategy_cfg: StrategyConfig,
) -> pd.DataFrame:
    """
    Add EU open window flags and prior RTH return on full 24h annotated bars.
    session_date for overnight bars before 09:30 ET links to the prior US session day.
    """
    out = df.copy()
    eu_start = _hhmm_to_minutes(strategy_cfg.eu_open_start)
    eu_end = _hhmm_to_minutes(strategy_cfg.eu_open_end)
    rth_open_min = _hhmm_to_minutes(session_cfg.rth_open)
    rth_close_min = _hhmm_to_minutes(session_cfg.rth_close)

    out["is_rth"] = (out["et_minute"] >= rth_open_min) & (out["et_minute"] < rth_close_min)
    out["is_overnight"] = ~out["is_rth"]
    out["is_eu_open_window"] = (out["et_minute"] >= eu_start) & (out["et_minute"] < eu_end)
    out["is_eu_entry_bar"] = out["et_minute"] == eu_start
    out["is_eu_window_end_bar"] = False
    out["is_session_end_bar"] = False

    eu = out.loc[out["is_eu_open_window"]]
    if not eu.empty:
        for _, grp in eu.groupby("session_date", sort=False):
            out.loc[grp.index[-1], "is_eu_window_end_bar"] = True
            out.loc[grp.index[-1], "is_session_end_bar"] = True

    rth_stats = _rth_session_returns(out, session_cfg)
    if rth_stats.empty:
        out["prior_rth_return_pts"] = np.nan
        out["spread_ok"] = out["spread"] <= strategy_cfg.max_overnight_spread
        return out

    stats = rth_stats.set_index("session_date")["prior_rth_return_pts"]
    out["prior_rth_return_pts"] = out["session_date"].map(stats)
    if "spread" not in out.columns:
        out["spread"] = out["ask_close"] - out["bid_close"]
    out["spread_ok"] = out["spread"] <= strategy_cfg.max_overnight_spread
    return out
