"""Data quality validation invariants."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.ok = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def _check_monotonic_time(df: pd.DataFrame, result: ValidationResult) -> None:
    if not df["timestamp"].is_monotonic_increasing:
        result.add_error("Timestamps are not strictly monotonic increasing")
    if df["timestamp"].duplicated().any():
        n = int(df["timestamp"].duplicated().sum())
        result.add_error(f"Found {n} duplicate timestamps")


def _check_ohlc(df: pd.DataFrame, side: str, result: ValidationResult) -> None:
    o, h, l, c = f"{side}_open", f"{side}_high", f"{side}_low", f"{side}_close"
    for col in (o, h, l, c):
        if col not in df.columns:
            result.add_error(f"Missing column {col}")
            return
    bad_low = (df[l] > df[o]) | (df[l] > df[c]) | (df[l] > df[h])
    bad_high = (df[h] < df[o]) | (df[h] < df[c]) | (df[h] < df[l])
    if bad_low.any():
        result.add_error(f"{side}: {int(bad_low.sum())} bars violate low <= open/close/high")
    if bad_high.any():
        result.add_error(f"{side}: {int(bad_high.sum())} bars violate high >= open/close/low")


def _check_spread(df: pd.DataFrame, max_spread: float, result: ValidationResult) -> None:
    if "spread" not in df.columns:
        result.add_error("Missing spread column")
        return
    neg = df["spread"] < 0
    if neg.any():
        result.add_error(f"{int(neg.sum())} bars have negative spread (ask_close < bid_close)")
    wide = df["spread"] > max_spread
    if wide.any():
        result.add_warning(
            f"{int(wide.sum())} bars exceed max_spread ({max_spread} pts); "
            "review data quality"
        )


def _check_volume(df: pd.DataFrame, result: ValidationResult) -> None:
    if "volume" not in df.columns:
        result.add_error("Missing volume column")
        return
    if (df["volume"] < 0).any():
        result.add_error("Negative volume values found")


def validate_merged_bars(df: pd.DataFrame, max_spread: float = 50.0) -> ValidationResult:
    result = ValidationResult(ok=True)
    required = [
        "timestamp",
        "bid_open",
        "bid_high",
        "bid_low",
        "bid_close",
        "ask_open",
        "ask_high",
        "ask_low",
        "ask_close",
        "spread",
        "volume",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        result.add_error(f"Missing required columns: {missing}")
        return result

    if df.empty:
        result.add_error("DataFrame is empty")
        return result

    _check_monotonic_time(df, result)
    _check_ohlc(df, "bid", result)
    _check_ohlc(df, "ask", result)
    _check_spread(df, max_spread, result)
    _check_volume(df, result)

    bad_close = df["ask_close"] < df["bid_close"]
    if bad_close.any():
        result.add_error(f"{int(bad_close.sum())} bars have ask_close < bid_close")

    return result
