"""Daily session calendar for monthly TSMOM rebalance."""

from __future__ import annotations

import pandas as pd

from src.config import StrategyConfig


def annotate_daily_rebalance(df: pd.DataFrame, strategy_cfg: StrategyConfig) -> pd.DataFrame:
    """
    Add monthly rebalance flags and lagged 12m return for TSMOM.

    Signal on rebalance day uses prior trading day's close vs lookback close
  (no look-ahead).
    """
    out = df.copy().sort_values("session_date").reset_index(drop=True)
    lookback = strategy_cfg.tsmom_lookback_days

    if "mid_close" not in out.columns:
        if "close" in out.columns:
            out["mid_close"] = out["close"]
        else:
            out["mid_close"] = (out["bid_close"] + out["ask_close"]) / 2.0

    out["calendar_month"] = pd.to_datetime(out["session_date"]).dt.to_period("M")
    out["is_rebalance_bar"] = ~out["calendar_month"].duplicated()

    prev_close = out["mid_close"].shift(1)
    lag_close = out["mid_close"].shift(lookback + 1)
    out["tsmom_return"] = prev_close / lag_close - 1.0

    out["is_rth"] = True
    out["is_session_end_bar"] = True
    for col in ("orb_high", "orb_low", "orb_mid", "orb_width"):
        out[col] = 0.0
    out["orb_valid"] = True
    return out
