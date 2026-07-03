"""Monthly TSMOM signal and rebalance planning for live Alpaca trading."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd

from src.broker.alpaca_client import AccountSnapshot, AlpacaBroker, PositionSnapshot
from src.broker.alpaca_config import AlpacaSettings
from src.config import StrategyConfig
from src.session.daily_calendar import annotate_daily_rebalance
from src.strategy.engines.daily_tsmom import generate_daily_tsmom_signals

IntendedAction = Literal["buy", "sell", "hold", "roll", "none"]
TargetExposure = Literal["long", "flat"]


@dataclass(frozen=True)
class TsmomRebalancePlan:
    session_date: date
    is_rebalance_day: bool
    tsmom_return: float | None
    target_exposure: TargetExposure | None
    intended_action: IntendedAction
    order_qty: int | None
    current_qty: int
    reason: str


def _strategy_cfg(settings: AlpacaSettings) -> StrategyConfig:
    return StrategyConfig(
        strategy_type="daily_tsmom",
        tsmom_lookback_days=settings.tsmom_lookback_days,
        tsmom_long_only=settings.tsmom_long_only,
        tsmom_entry_on="open",
    )


def compute_tsmom_return_from_bars(bars: pd.DataFrame, lookback_days: int) -> float | None:
    """12m return using prior close vs lagged close (matches backtest calendar)."""
    if len(bars) < lookback_days + 2:
        return None
    closes = bars["close"].astype(float)
    prev_close = float(closes.iloc[-1])
    lag_close = float(closes.iloc[-(lookback_days + 1)])
    if lag_close <= 0:
        return None
    return prev_close / lag_close - 1.0


def target_from_return(tsmom_return: float | None, long_only: bool) -> TargetExposure | None:
    if tsmom_return is None:
        return None
    if tsmom_return > 0:
        return "long"
    if long_only:
        return "flat"
    return "flat"


def build_rebalance_plan(
    broker: AlpacaBroker,
    settings: AlpacaSettings,
    *,
    as_of_date: date,
    bars: pd.DataFrame,
    account: AccountSnapshot,
    position: PositionSnapshot | None,
) -> TsmomRebalancePlan:
    symbol = settings.symbol
    current_qty = int(position.qty) if position else 0
    first_day = broker.first_trading_day_of_month(as_of_date.year, as_of_date.month)
    is_rebalance = first_day == as_of_date

    if not is_rebalance:
        return TsmomRebalancePlan(
            session_date=as_of_date,
            is_rebalance_day=False,
            tsmom_return=None,
            target_exposure=None,
            intended_action="none",
            order_qty=None,
            current_qty=current_qty,
            reason="Not the first trading day of the month",
        )

    if len(bars) < settings.min_history_bars:
        return TsmomRebalancePlan(
            session_date=as_of_date,
            is_rebalance_day=True,
            tsmom_return=None,
            target_exposure=None,
            intended_action="none",
            order_qty=None,
            current_qty=current_qty,
            reason=f"Need at least {settings.min_history_bars} daily bars, got {len(bars)}",
        )

    strategy_cfg = _strategy_cfg(settings)
    annotated = annotate_daily_rebalance(bars, strategy_cfg)
    signals = generate_daily_tsmom_signals(annotated, strategy_cfg)

    row = signals[signals["session_date"] == as_of_date]
    if not row.empty:
        tsmom_return = (
            float(row.iloc[0]["tsmom_return"]) if pd.notna(row.iloc[0]["tsmom_return"]) else None
        )
        sig = row.iloc[0]["signal"]
        target: TargetExposure = "long" if sig == "long" else "flat"
    else:
        tsmom_return = compute_tsmom_return_from_bars(bars, settings.tsmom_lookback_days)
        target = target_from_return(tsmom_return, settings.tsmom_long_only)
        if target is None:
            return TsmomRebalancePlan(
                session_date=as_of_date,
                is_rebalance_day=True,
                tsmom_return=None,
                target_exposure=None,
                intended_action="none",
                order_qty=None,
                current_qty=current_qty,
                reason="Insufficient history to compute 12m return",
            )

    last_price = float(bars.iloc[-1]["close"])
    if target == "long" and current_qty <= 0:
        notional = account.equity * settings.position_fraction
        order_qty = max(int(notional / last_price), 0)
        if order_qty <= 0:
            return TsmomRebalancePlan(
                session_date=as_of_date,
                is_rebalance_day=True,
                tsmom_return=tsmom_return,
                target_exposure=target,
                intended_action="none",
                order_qty=None,
                current_qty=current_qty,
                reason="Computed buy qty is zero (check equity and price)",
            )
        return TsmomRebalancePlan(
            session_date=as_of_date,
            is_rebalance_day=True,
            tsmom_return=tsmom_return,
            target_exposure=target,
            intended_action="buy",
            order_qty=order_qty,
            current_qty=current_qty,
            reason=f"12m return {tsmom_return:.4f} > 0 — enter long",
        )

    if target == "flat" and current_qty > 0:
        return TsmomRebalancePlan(
            session_date=as_of_date,
            is_rebalance_day=True,
            tsmom_return=tsmom_return,
            target_exposure=target,
            intended_action="sell",
            order_qty=current_qty,
            current_qty=current_qty,
            reason=f"12m return {tsmom_return:.4f} <= 0 — go flat",
        )

    if target == "long" and current_qty > 0:
        notional = account.equity * settings.position_fraction
        order_qty = max(int(notional / last_price), 0)
        return TsmomRebalancePlan(
            session_date=as_of_date,
            is_rebalance_day=True,
            tsmom_return=tsmom_return,
            target_exposure=target,
            intended_action="roll",
            order_qty=order_qty,
            current_qty=current_qty,
            reason=f"Monthly roll — 12m return {tsmom_return:.4f} > 0",
        )

    return TsmomRebalancePlan(
        session_date=as_of_date,
        is_rebalance_day=True,
        tsmom_return=tsmom_return,
        target_exposure=target,
        intended_action="hold",
        order_qty=None,
        current_qty=current_qty,
        reason=f"Already flat; 12m return {tsmom_return:.4f} <= 0",
    )


def execute_plan(broker: AlpacaBroker, settings: AlpacaSettings, plan: TsmomRebalancePlan):
    from alpaca.trading.enums import OrderSide

    symbol = settings.symbol
    if plan.intended_action == "roll":
        broker.close_position(symbol)
        if plan.order_qty and plan.order_qty > 0:
            return broker.submit_market_order(symbol, OrderSide.BUY, plan.order_qty)
        return None
    if plan.intended_action == "buy" and plan.order_qty:
        return broker.submit_market_order(symbol, OrderSide.BUY, plan.order_qty)
    if plan.intended_action == "sell":
        return broker.close_position(symbol)
    return None


def append_paper_log(
    log_path: Path,
    plan: TsmomRebalancePlan,
    *,
    intended_price: float | None,
    fill_price: float | None,
    notes: str = "",
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "session_date",
                "side",
                "signal_time",
                "intended_entry",
                "fill_entry",
                "spread_at_entry",
                "intended_exit",
                "fill_exit",
                "spread_at_exit",
                "exit_reason",
                "notes",
            ],
        )
        if write_header:
            writer.writeheader()
        side = "long" if plan.target_exposure == "long" else "flat"
        intended = intended_price if intended_price is not None else ""
        fill = fill_price if fill_price is not None else ""
        writer.writerow(
            {
                "session_date": plan.session_date.isoformat(),
                "side": side,
                "signal_time": "09:30:00",
                "intended_entry": intended,
                "fill_entry": fill,
                "spread_at_entry": "",
                "intended_exit": "",
                "fill_exit": "",
                "spread_at_exit": "",
                "exit_reason": plan.intended_action,
                "notes": notes or plan.reason,
            }
        )
