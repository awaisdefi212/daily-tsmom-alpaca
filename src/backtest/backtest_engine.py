"""Bar-by-bar backtest engine with scale-out and time-based exits."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import numpy as np

from src.backtest.fill_model import (
    ExitResult,
    apply_slippage,
    check_intrabar_exit,
    session_exit_price,
    session_entry_price,
)
from src.config import AppConfig
from src.session.session_calendar import _hhmm_to_minutes
from src.strategy.risk import (
    TradePlan,
    StopTooWideError,
    build_trade_plan,
    compute_entry_price,
    compute_r_multiple,
    current_r,
    update_trailing_stop,
    update_boundary_trailing_stop,
)


@dataclass
class Trade:
    session_date: object
    side: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    orb_width: float
    risk_per_unit: float
    r_multiple: float
    pnl_points: float
    spread_cost: float
    slippage_cost: float
    exit_reason: str


@dataclass
class _OpenPosition:
    plan: TradePlan
    entry_time: pd.Timestamp
    entry_session: object
    entry_mid: float
    current_stop: float
    best_price: float
    remaining_fraction: float = 1.0
    scaled_out: bool = False
    progress_checked: bool = False
    realized_pnl: float = 0.0


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: pd.DataFrame = field(default_factory=pd.DataFrame)


def prepare_bars(df: pd.DataFrame, config: AppConfig) -> pd.DataFrame:
    from src.session.session_calendar import annotate_sessions, filter_rth
    from src.session.overnight_calendar import annotate_overnight_windows
    from src.indicators.vwap import compute_vwap
    from src.indicators.orb import compute_orb_levels
    from src.indicators.trend_day import compute_trend_day, compute_compression_day
    from src.indicators.noise_area import compute_noise_area
    from src.strategy.signal_engine import generate_entry_signals
    from src.data.resample import resample_bars, resample_daily_rth
    from src.session.daily_calendar import annotate_daily_rebalance

    bars = df
    if config.data.bar_minutes > 1 and config.strategy.strategy_type != "daily_tsmom":
        bars = resample_bars(bars, config.data.bar_minutes)

    stype = config.strategy.strategy_type

    if stype == "daily_tsmom":
        bars = annotate_sessions(bars, config.session, config.orb, config.strategy)
        bars = filter_rth(bars)
        bars = resample_daily_rth(bars)
        bars = annotate_daily_rebalance(bars, config.strategy)
        bars = generate_entry_signals(bars, config.strategy)
        return bars.reset_index(drop=True)

    if stype == "overnight_eu_open":
        bars = annotate_sessions(bars, config.session, config.orb, config.strategy)
        bars = annotate_overnight_windows(bars, config.session, config.strategy)
        bars = bars.loc[bars["is_eu_open_window"]].copy()
        for col in ("orb_high", "orb_low", "orb_mid", "orb_width"):
            bars[col] = 0.0
        bars["orb_valid"] = True
        bars = generate_entry_signals(bars, config.strategy)
        return bars.reset_index(drop=True)

    bars = annotate_sessions(bars, config.session, config.orb, config.strategy)
    bars = filter_rth(bars)
    bars = compute_vwap(bars, config.vwap)

    if stype == "intraday_momentum":
        bars = compute_noise_area(
            bars,
            lookback_days=config.strategy.noise_lookback_days,
            volatility_multiplier=config.strategy.volatility_multiplier,
        )
        for col in ("orb_high", "orb_low", "orb_mid", "orb_width"):
            bars[col] = 0.0
        bars["orb_valid"] = True
    elif stype == "gao_session_momentum":
        for col in ("orb_high", "orb_low", "orb_mid", "orb_width"):
            bars[col] = 0.0
        bars["orb_valid"] = True
        bars["is_trend_day"] = True
        bars["is_compression_day"] = True
    else:
        bars = compute_orb_levels(bars, config.orb)
        if config.strategy.strategy_type == "orb_fade":
            if config.strategy.fade_compression_only:
                bars = compute_compression_day(bars, config.strategy.max_first_hour_range)
            else:
                bars = compute_trend_day(bars, config.strategy.min_first_hour_range)
                bars["is_compression_day"] = True
        elif config.strategy.require_trend_day:
            bars = compute_trend_day(bars, config.strategy.min_first_hour_range)
        else:
            bars["is_trend_day"] = True
            bars["first_hour_range"] = np.nan
            bars["is_compression_day"] = True

    bars = generate_entry_signals(bars, config.strategy)
    return bars.reset_index(drop=True)


def _hhmm_to_minute_optional(value: str | None) -> int | None:
    if value is None:
        return None
    return _hhmm_to_minutes(value)


def _scale_out_hit(
    side: str,
    plan: TradePlan,
    scaled_out: bool,
    bid_high: float,
    bid_low: float,
    ask_high: float,
    ask_low: float,
) -> bool:
    if plan.scale_out_r is None or scaled_out:
        return False
    level = plan.scale_out_r * plan.risk_per_unit
    if side == "long":
        return bid_high >= plan.entry_price + level
    return ask_low <= plan.entry_price - level


def _scale_out_price(side: str, plan: TradePlan, slippage: float) -> float:
    level = plan.scale_out_r * plan.risk_per_unit
    if side == "long":
        raw = plan.entry_price + level
        return apply_slippage(raw, slippage, adverse=True, side="long", is_entry=False)
    raw = plan.entry_price - level
    return apply_slippage(raw, slippage, adverse=True, side="short", is_entry=False)


def run_backtest(
    df: pd.DataFrame,
    config: AppConfig,
    *,
    prepared_bars: pd.DataFrame | None = None,
) -> BacktestResult:
    bars = prepared_bars if prepared_bars is not None else prepare_bars(df, config)
    slippage = config.costs.slippage_points
    trades: list[Trade] = []
    equity_rows: list[dict] = []

    progress_min = _hhmm_to_minute_optional(config.strategy.progress_check_time)
    hard_exit_min = _hhmm_to_minute_optional(config.strategy.hard_exit_time)

    timestamps = bars["timestamp"].values
    session_dates = bars["session_date"].values
    signals = bars["signal"].values
    et_minute = bars["et_minute"].to_numpy(dtype=int)
    ask_close = bars["ask_close"].to_numpy(dtype=float)
    bid_close = bars["bid_close"].to_numpy(dtype=float)
    ask_open = bars.get("ask_open", bars["ask_close"]).to_numpy(dtype=float)
    bid_open = bars.get("bid_open", bars["bid_close"]).to_numpy(dtype=float)
    ask_high = bars["ask_high"].to_numpy(dtype=float)
    bid_low = bars["bid_low"].to_numpy(dtype=float)
    bid_high = bars["bid_high"].to_numpy(dtype=float)
    ask_low = bars["ask_low"].to_numpy(dtype=float)
    orb_high = bars["orb_high"].to_numpy(dtype=float)
    orb_low = bars["orb_low"].to_numpy(dtype=float)
    orb_mid = bars["orb_mid"].to_numpy(dtype=float)
    orb_width = bars["orb_width"].to_numpy(dtype=float)
    is_session_end = bars["is_session_end_bar"].to_numpy(dtype=bool)
    entry_bar_bid_low = bars.get("entry_bar_bid_low", pd.Series(np.nan, index=bars.index)).to_numpy(dtype=float)
    entry_bar_ask_high = bars.get("entry_bar_ask_high", pd.Series(np.nan, index=bars.index)).to_numpy(dtype=float)
    entry_noise_lower = bars.get("entry_noise_lower", pd.Series(np.nan, index=bars.index)).to_numpy(dtype=float)
    entry_noise_upper = bars.get("entry_noise_upper", pd.Series(np.nan, index=bars.index)).to_numpy(dtype=float)
    noise_lower = bars.get("noise_lower", pd.Series(np.nan, index=bars.index)).to_numpy(dtype=float)
    noise_upper = bars.get("noise_upper", pd.Series(np.nan, index=bars.index)).to_numpy(dtype=float)
    vwap = bars.get("vwap", pd.Series(np.nan, index=bars.index)).to_numpy(dtype=float)
    use_vwap_trail = config.strategy.use_vwap_trailing_stop
    boundary_mode = config.risk.stop_mode == "noise_boundary"
    is_daily_tsmom = config.strategy.strategy_type == "daily_tsmom"
    tsmom_use_open = is_daily_tsmom and config.strategy.tsmom_entry_on == "open"

    n = len(bars)
    is_rebalance = (
        bars["is_rebalance_bar"].to_numpy(dtype=bool)
        if is_daily_tsmom and "is_rebalance_bar" in bars.columns
        else np.zeros(n, dtype=bool)
    )

    position: _OpenPosition | None = None

    def _exit_bid_ask(idx: int) -> tuple[float, float]:
        if tsmom_use_open:
            return bid_open[idx], ask_open[idx]
        return bid_close[idx], ask_close[idx]

    for idx in range(n):
        if position is not None:
            side = position.plan.side
            plan = position.plan

            if side == "long":
                position.best_price = max(position.best_price, ask_high[idx])
                mark = bid_close[idx]
            else:
                position.best_price = min(position.best_price, bid_low[idx])
                mark = ask_close[idx]

            position.current_stop = update_trailing_stop(
                plan, side, position.best_price, config.risk, config.costs
            )
            if boundary_mode and plan.use_boundary_trail:
                position.current_stop = update_boundary_trailing_stop(
                    side,
                    position.current_stop,
                    noise_lower[idx],
                    noise_upper[idx],
                    vwap[idx],
                    config.risk.stop_buffer_points,
                    use_vwap_trail,
                )

            exit_res: ExitResult | None = None

            if not position.scaled_out and _scale_out_hit(
                side, plan, position.scaled_out, bid_high[idx], bid_low[idx], ask_high[idx], ask_low[idx]
            ):
                so_price = _scale_out_price(side, plan, slippage)
                leg_pnl = (
                    (so_price - plan.entry_price) * plan.scale_out_pct
                    if side == "long"
                    else (plan.entry_price - so_price) * plan.scale_out_pct
                )
                position.realized_pnl += leg_pnl
                position.remaining_fraction = 1.0 - plan.scale_out_pct
                position.scaled_out = True
                if plan.runner_target_price is not None:
                    plan.target_price = plan.runner_target_price

            active_target = plan.target_price
            exit_res = check_intrabar_exit(
                side=side,
                stop=position.current_stop,
                target=active_target,
                bid_high=bid_high[idx],
                bid_low=bid_low[idx],
                ask_high=ask_high[idx],
                ask_low=ask_low[idx],
                slippage=slippage,
            )

            if exit_res is None and progress_min is not None and et_minute[idx] >= progress_min:
                if not position.progress_checked:
                    position.progress_checked = True
                    r_now = current_r(side, plan.entry_price, mark, plan.risk_per_unit)
                    if r_now < config.strategy.min_progress_r:
                        px = session_exit_price(side, bid_close[idx], ask_close[idx], slippage)
                        exit_res = ExitResult(price=px, reason="progress")

            if exit_res is None and hard_exit_min is not None and et_minute[idx] >= hard_exit_min:
                r_now = current_r(side, plan.entry_price, mark, plan.risk_per_unit)
                if r_now < config.strategy.hard_exit_min_r:
                    px = session_exit_price(side, bid_close[idx], ask_close[idx], slippage)
                    exit_res = ExitResult(price=px, reason="hard_exit")

            if exit_res is None and is_daily_tsmom and is_rebalance[idx]:
                exit_bid, exit_ask = _exit_bid_ask(idx)
                px = session_exit_price(side, exit_bid, exit_ask, slippage)
                exit_res = ExitResult(price=px, reason="rebalance")

            if exit_res is None and is_session_end[idx] and not is_daily_tsmom:
                px = session_exit_price(side, bid_close[idx], ask_close[idx], slippage)
                exit_res = ExitResult(price=px, reason="eod")

            if exit_res is not None:
                leg_pnl = (
                    (exit_res.price - plan.entry_price) * position.remaining_fraction
                    if side == "long"
                    else (plan.entry_price - exit_res.price) * position.remaining_fraction
                )
                total_pnl = position.realized_pnl + leg_pnl
                r_mult = total_pnl / plan.risk_per_unit
                trades.append(
                    Trade(
                        session_date=position.entry_session,
                        side=side,
                        entry_time=position.entry_time,
                        exit_time=timestamps[idx],
                        entry_price=plan.entry_price,
                        exit_price=exit_res.price,
                        stop_price=position.current_stop,
                        target_price=active_target,
                        orb_width=plan.orb_width,
                        risk_per_unit=plan.risk_per_unit,
                        r_multiple=r_mult,
                        pnl_points=total_pnl,
                        spread_cost=abs(position.entry_mid - plan.entry_price),
                        slippage_cost=slippage * 2,
                        exit_reason=exit_res.reason,
                    )
                )
                equity_rows.append({"timestamp": timestamps[idx], "pnl_points": total_pnl})
                position = None
                continue

        sig = signals[idx]
        if position is None and sig in ("long", "short"):
            if tsmom_use_open:
                entry_px = session_entry_price(sig, bid_open[idx], ask_open[idx], slippage)
            else:
                entry_px = compute_entry_price(sig, ask_close[idx], bid_close[idx], slippage)
            bar_bid_low = entry_bar_bid_low[idx] if not np.isnan(entry_bar_bid_low[idx]) else None
            bar_ask_high = entry_bar_ask_high[idx] if not np.isnan(entry_bar_ask_high[idx]) else None
            n_lower = entry_noise_lower[idx] if not np.isnan(entry_noise_lower[idx]) else noise_lower[idx]
            n_upper = entry_noise_upper[idx] if not np.isnan(entry_noise_upper[idx]) else noise_upper[idx]
            nl = None if np.isnan(n_lower) else float(n_lower)
            nu = None if np.isnan(n_upper) else float(n_upper)
            try:
                plan = build_trade_plan(
                    sig,
                    entry_px,
                    orb_high[idx],
                    orb_low[idx],
                    orb_width[idx],
                    orb_mid[idx],
                    config.risk,
                    entry_bar_bid_low=bar_bid_low,
                    entry_bar_ask_high=bar_ask_high,
                    noise_lower=nl,
                    noise_upper=nu,
                )
            except (ValueError, StopTooWideError):
                continue

            position = _OpenPosition(
                plan=plan,
                entry_time=timestamps[idx],
                entry_session=session_dates[idx],
                entry_mid=(ask_close[idx] + bid_close[idx]) / 2.0,
                current_stop=plan.stop_price,
                best_price=entry_px,
            )

    if position is not None and is_daily_tsmom and n > 0:
        idx = n - 1
        side = position.plan.side
        plan = position.plan
        exit_bid, exit_ask = _exit_bid_ask(idx)
        px = session_exit_price(side, exit_bid, exit_ask, slippage)
        leg_pnl = (
            (px - plan.entry_price) * position.remaining_fraction
            if side == "long"
            else (plan.entry_price - px) * position.remaining_fraction
        )
        total_pnl = position.realized_pnl + leg_pnl
        trades.append(
            Trade(
                session_date=position.entry_session,
                side=side,
                entry_time=position.entry_time,
                exit_time=timestamps[idx],
                entry_price=plan.entry_price,
                exit_price=px,
                stop_price=position.current_stop,
                target_price=plan.target_price,
                orb_width=plan.orb_width,
                risk_per_unit=plan.risk_per_unit,
                r_multiple=total_pnl / plan.risk_per_unit,
                pnl_points=total_pnl,
                spread_cost=abs(position.entry_mid - plan.entry_price),
                slippage_cost=slippage * 2,
                exit_reason="data_end",
            )
        )

    if equity_rows:
        eq = pd.DataFrame(equity_rows)
        eq["cumulative_pnl"] = eq["pnl_points"].cumsum()
    else:
        eq = pd.DataFrame(columns=["timestamp", "pnl_points", "cumulative_pnl"])

    return BacktestResult(trades=trades, equity_curve=eq)


def run_backtest_zero_costs(df: pd.DataFrame, config: AppConfig) -> BacktestResult:
    cfg = config.model_copy(deep=True)
    cfg.costs.slippage_points = 0.0
    return run_backtest(df, cfg)
