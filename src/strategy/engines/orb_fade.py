"""ORB failed-breakout fade signals on compression days."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import StrategyConfig


def _passes_fade_context(row: pd.Series, strategy_cfg: StrategyConfig) -> bool:
    if not row.get("is_signal_window", False):
        return False
    if not row.get("orb_valid", False):
        return False
    if pd.isna(row.get("orb_high")) or pd.isna(row.get("orb_low")):
        return False
    if pd.isna(row.get("vwap")):
        return False
    if strategy_cfg.fade_compression_only and not row.get("is_compression_day", False):
        return False
    return True


def _passes_fade_entry(row: pd.Series, strategy_cfg: StrategyConfig) -> bool:
    if not row.get("is_entry_window", False):
        return False
    if strategy_cfg.require_vwap_slope_flat:
        if not row.get("vwap_slope_flat", False):
            return False
    return True


def _set_fade_entry_prices(
    out: pd.DataFrame,
    i: int,
    *,
    bid_low: float,
    ask_high: float,
) -> None:
    out.at[i, "entry_bar_bid_low"] = bid_low
    out.at[i, "entry_bar_ask_high"] = ask_high


def generate_fade_signals(df: pd.DataFrame, strategy_cfg: StrategyConfig) -> pd.DataFrame:
    """Fade failed ORB breakouts: short after false upside break, long after false downside."""
    out = df.copy()
    out["signal"] = None
    out["entry_bar_bid_low"] = np.nan
    out["entry_bar_ask_high"] = np.nan

    tol = strategy_cfg.retest_tolerance_points
    max_bars = strategy_cfg.fade_max_bars
    require_inside = strategy_cfg.fade_require_close_inside

    for _, idx in out.groupby("session_date", sort=False).groups.items():
        upside_break = False
        downside_break = False
        break_bar: int | None = None
        false_high = np.nan
        false_low = np.nan
        short_taken = False
        long_taken = False
        fade_short_ready = False
        fade_long_ready = False

        for i in idx:
            row = out.loc[i]
            if not _passes_fade_context(row, strategy_cfg):
                continue

            orb_high = row["orb_high"]
            orb_low = row["orb_low"]
            bars_since = i - break_bar if break_bar is not None else 0

            if upside_break and break_bar is not None:
                false_high = max(false_high, row["ask_high"])
                if bars_since > max_bars:
                    upside_break = False
                    fade_short_ready = False
                    break_bar = None
                elif require_inside and row["bid_close"] < orb_high:
                    fade_short_ready = True
                elif not require_inside:
                    fade_short_ready = True

            if downside_break and break_bar is not None:
                false_low = min(false_low, row["bid_low"])
                if bars_since > max_bars:
                    downside_break = False
                    fade_long_ready = False
                    break_bar = None
                elif require_inside and row["ask_close"] > orb_low:
                    fade_long_ready = True
                elif not require_inside:
                    fade_long_ready = True

            if (
                fade_short_ready
                and not short_taken
                and _passes_fade_entry(row, strategy_cfg)
                and row["ask_high"] >= orb_high - tol
                and row["bid_close"] < orb_high
            ):
                out.at[i, "signal"] = "short"
                _set_fade_entry_prices(
                    out,
                    i,
                    bid_low=row["bid_low"],
                    ask_high=false_high if not np.isnan(false_high) else row["ask_high"],
                )
                short_taken = True
                upside_break = False
                fade_short_ready = False
                break_bar = None

            if (
                fade_long_ready
                and not long_taken
                and _passes_fade_entry(row, strategy_cfg)
                and row["bid_low"] <= orb_low + tol
                and row["ask_close"] > orb_low
            ):
                out.at[i, "signal"] = "long"
                _set_fade_entry_prices(
                    out,
                    i,
                    bid_low=false_low if not np.isnan(false_low) else row["bid_low"],
                    ask_high=row["ask_high"],
                )
                long_taken = True
                downside_break = False
                fade_long_ready = False
                break_bar = None

            if not upside_break and not short_taken and row["ask_high"] > orb_high:
                upside_break = True
                downside_break = False
                break_bar = i
                false_high = row["ask_high"]
                fade_short_ready = False

            if not downside_break and not long_taken and row["bid_low"] < orb_low:
                downside_break = True
                upside_break = False
                break_bar = i
                false_low = row["bid_low"]
                fade_long_ready = False

    if strategy_cfg.max_trades_per_direction == 1:
        for side in ("long", "short"):
            mask = out["signal"] == side
            if not mask.any():
                continue
            dup_rank = out.loc[mask].groupby("session_date").cumcount()
            drop_idx = dup_rank[dup_rank > 0].index
            out.loc[drop_idx, "signal"] = None
            out.loc[drop_idx, "entry_bar_bid_low"] = np.nan
            out.loc[drop_idx, "entry_bar_ask_high"] = np.nan

    return out
