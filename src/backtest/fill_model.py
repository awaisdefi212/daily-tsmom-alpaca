"""Pessimistic bid/ask fill model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExitResult:
    price: float
    reason: str


def apply_slippage(price: float, slippage: float, adverse: bool, side: str, is_entry: bool) -> float:
    """Adverse slippage moves fill against the trader."""
    if is_entry:
        if side == "long":
            return price + slippage
        return price - slippage
    if side == "long":
        return price - slippage
    return price + slippage


def check_intrabar_exit(
    side: str,
    stop: float,
    target: float | None,
    bid_high: float,
    bid_low: float,
    ask_high: float,
    ask_low: float,
    slippage: float,
) -> ExitResult | None:
    """
    Pessimistic intrabar resolution: stop checked before target.
    Long exits on bid; short exits on ask.
    """
    if side == "long":
        stop_hit = bid_low <= stop
        target_hit = target is not None and bid_high >= target
        if stop_hit:
            return ExitResult(
                price=apply_slippage(stop, slippage, adverse=True, side="long", is_entry=False),
                reason="stop",
            )
        if target_hit:
            return ExitResult(
                price=apply_slippage(target, slippage, adverse=True, side="long", is_entry=False),
                reason="target",
            )
    else:
        stop_hit = ask_high >= stop
        target_hit = target is not None and ask_low <= target
        if stop_hit:
            return ExitResult(
                price=apply_slippage(stop, slippage, adverse=True, side="short", is_entry=False),
                reason="stop",
            )
        if target_hit:
            return ExitResult(
                price=apply_slippage(target, slippage, adverse=True, side="short", is_entry=False),
                reason="target",
            )
    return None


def session_exit_price(side: str, bid_close: float, ask_close: float, slippage: float) -> float:
    if side == "long":
        return apply_slippage(bid_close, slippage, adverse=True, side="long", is_entry=False)
    return apply_slippage(ask_close, slippage, adverse=True, side="short", is_entry=False)


def session_entry_price(side: str, bid: float, ask: float, slippage: float) -> float:
    return apply_slippage(ask if side == "long" else bid, slippage, adverse=True, side=side, is_entry=True)
