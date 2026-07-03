"""Stop, target, trailing stop, and scale-out logic."""

from __future__ import annotations

from dataclasses import dataclass

from src.config import RiskConfig, CostsConfig

import numpy as np


class StopTooWideError(ValueError):
    """Raised when structure stop exceeds max_stop_points — trade should be skipped."""


@dataclass
class TradePlan:
    side: str
    entry_price: float
    stop_price: float
    target_price: float | None
    runner_target_price: float | None
    orb_width: float
    orb_mid: float
    risk_per_unit: float
    scale_out_r: float | None = None
    scale_out_pct: float = 0.5
    use_boundary_trail: bool = False


def compute_entry_price(side: str, ask_close: float, bid_close: float, slippage: float) -> float:
    if side == "long":
        return ask_close + slippage
    return bid_close - slippage


def _resolve_stop(
    side: str,
    entry_price: float,
    orb_high: float,
    orb_low: float,
    orb_mid: float,
    risk_cfg: RiskConfig,
    entry_bar_bid_low: float | None = None,
    entry_bar_ask_high: float | None = None,
    noise_lower: float | None = None,
    noise_upper: float | None = None,
) -> float:
    buffer_pts = risk_cfg.stop_buffer_points
    mode = risk_cfg.stop_mode

    if mode in ("fixed_points", "session_hold", "monthly_hold"):
        if side == "long":
            return entry_price - risk_cfg.fixed_stop_points
        return entry_price + risk_cfg.fixed_stop_points

    if mode == "retest_structure":
        if side == "long":
            bar_low = entry_bar_bid_low if entry_bar_bid_low is not None else orb_mid
            raw_stop = min(bar_low, orb_mid) - buffer_pts
            risk = entry_price - raw_stop
            if risk > risk_cfg.max_stop_points:
                raise StopTooWideError(
                    f"Structure stop risk {risk:.1f} > max {risk_cfg.max_stop_points}"
                )
            if risk < risk_cfg.min_stop_points:
                return entry_price - risk_cfg.min_stop_points
            return raw_stop
        bar_high = entry_bar_ask_high if entry_bar_ask_high is not None else orb_mid
        raw_stop = max(bar_high, orb_mid) + buffer_pts
        risk = raw_stop - entry_price
        if risk > risk_cfg.max_stop_points:
            raise StopTooWideError(
                f"Structure stop risk {risk:.1f} > max {risk_cfg.max_stop_points}"
            )
        if risk < risk_cfg.min_stop_points:
            return entry_price + risk_cfg.min_stop_points
        return raw_stop

    if mode == "fade_structure":
        if side == "long":
            break_low = entry_bar_bid_low if entry_bar_bid_low is not None else orb_low
            raw_stop = min(break_low, orb_low) - buffer_pts
            risk = entry_price - raw_stop
            if risk > risk_cfg.max_stop_points:
                raise StopTooWideError(
                    f"Fade stop risk {risk:.1f} > max {risk_cfg.max_stop_points}"
                )
            if risk < risk_cfg.min_stop_points:
                return entry_price - risk_cfg.min_stop_points
            return raw_stop
        break_high = entry_bar_ask_high if entry_bar_ask_high is not None else orb_high
        raw_stop = max(break_high, orb_high) + buffer_pts
        risk = raw_stop - entry_price
        if risk > risk_cfg.max_stop_points:
            raise StopTooWideError(
                f"Fade stop risk {risk:.1f} > max {risk_cfg.max_stop_points}"
            )
        if risk < risk_cfg.min_stop_points:
            return entry_price + risk_cfg.min_stop_points
        return raw_stop

    if mode == "noise_boundary":
        if side == "long":
            bound = noise_lower if noise_lower is not None else entry_price * 0.99
            return bound - buffer_pts
        bound = noise_upper if noise_upper is not None else entry_price * 1.01
        return bound + buffer_pts

    if mode == "orb_midpoint":
        if side == "long":
            return orb_mid - buffer_pts
        return orb_mid + buffer_pts

    # opposite_orb_boundary
    if side == "long":
        return orb_low - buffer_pts
    return orb_high + buffer_pts


def build_trade_plan(
    side: str,
    entry_price: float,
    orb_high: float,
    orb_low: float,
    orb_width: float,
    orb_mid: float,
    risk_cfg: RiskConfig,
    *,
    entry_bar_bid_low: float | None = None,
    entry_bar_ask_high: float | None = None,
    noise_lower: float | None = None,
    noise_upper: float | None = None,
) -> TradePlan:
    stop = _resolve_stop(
        side,
        entry_price,
        orb_high,
        orb_low,
        orb_mid,
        risk_cfg,
        entry_bar_bid_low=entry_bar_bid_low,
        entry_bar_ask_high=entry_bar_ask_high,
        noise_lower=noise_lower,
        noise_upper=noise_upper,
    )

    boundary_mode = risk_cfg.stop_mode == "noise_boundary"
    session_hold = risk_cfg.stop_mode == "session_hold"

    if side == "long":
        risk = entry_price - stop
        if boundary_mode or session_hold:
            target = None
            runner_target = None
        else:
            target = entry_price + risk_cfg.target_r_multiple * risk
            runner_target = (
                entry_price + risk_cfg.runner_target_r * risk
                if risk_cfg.scale_out_r is not None
                else None
            )
    else:
        risk = stop - entry_price
        if boundary_mode or session_hold:
            target = None
            runner_target = None
        else:
            target = entry_price - risk_cfg.target_r_multiple * risk
            runner_target = (
                entry_price - risk_cfg.runner_target_r * risk
                if risk_cfg.scale_out_r is not None
                else None
            )

    if risk <= 0:
        raise ValueError(f"Non-positive risk for {side} entry={entry_price} stop={stop}")

    return TradePlan(
        side=side,
        entry_price=entry_price,
        stop_price=stop,
        target_price=target,
        runner_target_price=runner_target,
        orb_width=orb_width,
        orb_mid=orb_mid,
        risk_per_unit=risk,
        scale_out_r=risk_cfg.scale_out_r,
        scale_out_pct=risk_cfg.scale_out_pct,
        use_boundary_trail=boundary_mode,
    )


def update_boundary_trailing_stop(
    side: str,
    current_stop: float,
    noise_lower: float,
    noise_upper: float,
    vwap: float,
    buffer_pts: float,
    use_vwap: bool,
) -> float:
    """Ratchet stop at noise boundary (and optionally VWAP) each bar."""
    if side == "long":
        candidate = noise_lower - buffer_pts
        if use_vwap and not np.isnan(vwap):
            candidate = max(candidate, vwap - buffer_pts)
        return max(current_stop, candidate)
    candidate = noise_upper + buffer_pts
    if use_vwap and not np.isnan(vwap):
        candidate = min(candidate, vwap + buffer_pts)
    return min(current_stop, candidate)


def update_trailing_stop(
    plan: TradePlan,
    side: str,
    best_price: float,
    risk_cfg: RiskConfig,
    costs_cfg: CostsConfig,
) -> float:
    """Return updated stop after favorable movement."""
    risk = plan.risk_per_unit
    trail_trigger = risk_cfg.trail_after_r * risk
    if risk_cfg.trail_step_in_r:
        trail_step = risk_cfg.trail_step_r * risk
    else:
        trail_step = risk_cfg.trail_step_r * plan.orb_width
    slippage = costs_cfg.slippage_points
    stop = plan.stop_price

    if side == "long":
        favorable = best_price - plan.entry_price
        if favorable >= trail_trigger:
            breakeven = plan.entry_price + slippage
            trail = best_price - trail_step
            stop = max(stop, breakeven, trail)
    else:
        favorable = plan.entry_price - best_price
        if favorable >= trail_trigger:
            breakeven = plan.entry_price - slippage
            trail = best_price + trail_step
            stop = min(stop, breakeven, trail)

    return stop


def compute_r_multiple(side: str, entry: float, exit_price: float, risk: float) -> float:
    if risk <= 0:
        return 0.0
    if side == "long":
        return (exit_price - entry) / risk
    return (entry - exit_price) / risk


def current_r(side: str, entry: float, mark_price: float, risk: float) -> float:
    return compute_r_multiple(side, entry, mark_price, risk)
