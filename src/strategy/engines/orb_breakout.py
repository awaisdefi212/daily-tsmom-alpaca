"""Archived ORB breakout / pullback retest signal generation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import StrategyConfig


def _passes_quality_filters(
    row: pd.Series,
    side: str,
    strategy_cfg: StrategyConfig,
) -> bool:
    if not row.get("is_entry_window", False):
        return False
    if not row.get("orb_valid", False):
        return False
    if pd.isna(row.get("orb_high")) or pd.isna(row.get("orb_low")):
        return False
    if pd.isna(row.get("vwap")):
        return False
    if strategy_cfg.require_trend_day and not row.get("is_trend_day", False):
        return False

    if side == "long":
        if row["ask_close"] <= row["orb_high"]:
            return False
        if strategy_cfg.require_vwap_guard and row["ask_close"] <= row["vwap"]:
            return False
        if strategy_cfg.min_vwap_distance_orb_frac > 0:
            dist = strategy_cfg.min_vwap_distance_orb_frac * row["orb_width"]
            if row["ask_close"] <= row["vwap"] + dist:
                return False
        if strategy_cfg.require_vwap_slope and not row.get("vwap_slope_up", False):
            return False
    else:
        if row["bid_close"] >= row["orb_low"]:
            return False
        if strategy_cfg.require_vwap_guard and row["bid_close"] >= row["vwap"]:
            return False
        if strategy_cfg.min_vwap_distance_orb_frac > 0:
            dist = strategy_cfg.min_vwap_distance_orb_frac * row["orb_width"]
            if row["bid_close"] >= row["vwap"] - dist:
                return False
        if strategy_cfg.require_vwap_slope and not row.get("vwap_slope_down", False):
            return False

    if strategy_cfg.min_breakout_volume_mult > 0:
        vol_thresh = row["session_vol_median"] * strategy_cfg.min_breakout_volume_mult
        if row["volume"] <= vol_thresh:
            return False

    return True


def _set_entry_bar_prices(out: pd.DataFrame, i: int, row: pd.Series) -> None:
    out.at[i, "entry_bar_bid_low"] = row["bid_low"]
    out.at[i, "entry_bar_ask_high"] = row["ask_high"]


def _generate_breakout_close(out: pd.DataFrame, strategy_cfg: StrategyConfig) -> pd.DataFrame:
    out["signal"] = None
    out["entry_bar_bid_low"] = np.nan
    out["entry_bar_ask_high"] = np.nan

    for i in range(len(out)):
        row = out.iloc[i]
        if _passes_quality_filters(row, "long", strategy_cfg):
            out.iat[i, out.columns.get_loc("signal")] = "long"
            _set_entry_bar_prices(out, i, row)
        elif _passes_quality_filters(row, "short", strategy_cfg):
            out.iat[i, out.columns.get_loc("signal")] = "short"
            _set_entry_bar_prices(out, i, row)

    return _apply_post_filters(out, strategy_cfg)


def _generate_pullback_retest(out: pd.DataFrame, strategy_cfg: StrategyConfig) -> pd.DataFrame:
    out["signal"] = None
    out["entry_bar_bid_low"] = np.nan
    out["entry_bar_ask_high"] = np.nan
    tol = strategy_cfg.retest_tolerance_points
    max_bars = strategy_cfg.retest_max_bars
    cancel_bars = strategy_cfg.arm_cancel_inside_bars

    for _, idx in out.groupby("session_date", sort=False).groups.items():
        armed_long = False
        armed_short = False
        arm_long_at: int | None = None
        arm_short_at: int | None = None
        inside_long = 0
        inside_short = 0
        long_taken = False
        short_taken = False

        for i in idx:
            row = out.loc[i]
            if not row["is_entry_window"]:
                continue

            orb_high = row["orb_high"]
            orb_low = row["orb_low"]
            vwap = row["vwap"]

            if armed_long and not long_taken:
                bars_since = i - arm_long_at if arm_long_at is not None else 0
                if bars_since > max_bars:
                    armed_long = False
                    arm_long_at = None
                    inside_long = 0
                elif row["ask_close"] <= orb_high:
                    inside_long += 1
                    if inside_long >= cancel_bars:
                        armed_long = False
                        arm_long_at = None
                        inside_long = 0
                else:
                    inside_long = 0
                    retest_touch = row["bid_low"] <= orb_high + tol
                    reaccept = row["ask_close"] > orb_high
                    vwap_ok = row["ask_close"] > vwap
                    if retest_touch and reaccept and vwap_ok:
                        out.at[i, "signal"] = "long"
                        _set_entry_bar_prices(out, i, row)
                        long_taken = True
                        armed_long = False
                        arm_long_at = None

            if armed_short and not short_taken:
                bars_since = i - arm_short_at if arm_short_at is not None else 0
                if bars_since > max_bars:
                    armed_short = False
                    arm_short_at = None
                    inside_short = 0
                elif row["bid_close"] >= orb_low:
                    inside_short += 1
                    if inside_short >= cancel_bars:
                        armed_short = False
                        arm_short_at = None
                        inside_short = 0
                else:
                    inside_short = 0
                    retest_touch = row["ask_high"] >= orb_low - tol
                    reaccept = row["bid_close"] < orb_low
                    vwap_ok = row["bid_close"] < vwap
                    if retest_touch and reaccept and vwap_ok:
                        out.at[i, "signal"] = "short"
                        _set_entry_bar_prices(out, i, row)
                        short_taken = True
                        armed_short = False
                        arm_short_at = None

            if not long_taken and not armed_long and _passes_quality_filters(row, "long", strategy_cfg):
                armed_long = True
                arm_long_at = i
                inside_long = 0

            if not short_taken and not armed_short and _passes_quality_filters(row, "short", strategy_cfg):
                armed_short = True
                arm_short_at = i
                inside_short = 0

    return _apply_post_filters(out, strategy_cfg)


def _apply_post_filters(out: pd.DataFrame, strategy_cfg: StrategyConfig) -> pd.DataFrame:
    if strategy_cfg.reject_reentry_next_bar:
        for i in range(len(out) - 1):
            sig = out.iloc[i]["signal"]
            if sig not in ("long", "short"):
                continue
            nxt = i + 1
            if sig == "long" and out.iloc[nxt]["ask_close"] < out.iloc[nxt]["orb_high"]:
                out.iat[nxt, out.columns.get_loc("signal")] = None
            if sig == "short" and out.iloc[nxt]["bid_close"] > out.iloc[nxt]["orb_low"]:
                out.iat[nxt, out.columns.get_loc("signal")] = None

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


def generate_breakout_signals(df: pd.DataFrame, strategy_cfg: StrategyConfig) -> pd.DataFrame:
    out = df.copy()
    if strategy_cfg.entry_mode == "pullback_retest":
        return _generate_pullback_retest(out, strategy_cfg)
    return _generate_breakout_close(out, strategy_cfg)
