"""Per-trade MFE/MAE and R distribution analysis."""

from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd

from src.backtest.backtest_engine import Trade, BacktestResult
from src.strategy.risk import compute_r_multiple


R_BUCKETS = [
    ("<-1", -np.inf, -1.0),
    ("[-1,-0.5)", -1.0, -0.5),
    ("[-0.5,0)", -0.5, 0.0),
    ("[0,1)", 0.0, 1.0),
    ("[1,2)", 1.0, 2.0),
    ("[2,2.5)", 2.0, 2.5),
    ("[2.5+]", 2.5, np.inf),
]


def _slice_trade_bars(bars: pd.DataFrame, trade: Trade) -> pd.DataFrame:
    entry = pd.Timestamp(trade.entry_time)
    exit_ = pd.Timestamp(trade.exit_time)
    ts = bars["timestamp"]
    if ts.dt.tz is not None:
        if entry.tzinfo is None:
            entry = entry.tz_localize(ts.dt.tz)
        else:
            entry = entry.tz_convert(ts.dt.tz)
        if exit_.tzinfo is None:
            exit_ = exit_.tz_localize(ts.dt.tz)
        else:
            exit_ = exit_.tz_convert(ts.dt.tz)
    mask = (ts >= entry) & (ts <= exit_)
    return bars.loc[mask]


def compute_trade_mfe_mae(trade: Trade, bars: pd.DataFrame) -> tuple[float, float]:
    """Return MFE and MAE in R-multiples using conservative bid/ask sides."""
    risk = trade.risk_per_unit
    if risk <= 0:
        return 0.0, 0.0

    window = _slice_trade_bars(bars, trade)
    if window.empty:
        return 0.0, 0.0

    entry = trade.entry_price
    if trade.side == "long":
        mfe_pts = float(window["bid_high"].max() - entry)
        mae_pts = float(entry - window["bid_low"].min())
    else:
        mfe_pts = float(entry - window["ask_low"].min())
        mae_pts = float(window["ask_high"].max() - entry)

    mfe_r = max(mfe_pts / risk, 0.0)
    mae_r = max(mae_pts / risk, 0.0)
    return mfe_r, mae_r


def enrich_trades_with_excursions(
    trades: list[Trade], bars: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    for t in trades:
        mfe_r, mae_r = compute_trade_mfe_mae(t, bars)
        row = asdict(t)
        row["mfe_r"] = mfe_r
        row["mae_r"] = mae_r
        row["touched_2_5r"] = mfe_r >= 2.5 or t.r_multiple >= 2.5
        rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def r_histogram(trade_df: pd.DataFrame) -> dict[str, int]:
    if trade_df.empty:
        return {label: 0 for label, _, _ in R_BUCKETS}
    counts: dict[str, int] = {}
    for label, lo, hi in R_BUCKETS:
        if np.isinf(lo) and lo < 0:
            counts[label] = int((trade_df["r_multiple"] < hi).sum())
        elif np.isinf(hi):
            counts[label] = int((trade_df["r_multiple"] >= lo).sum())
        else:
            counts[label] = int(((trade_df["r_multiple"] >= lo) & (trade_df["r_multiple"] < hi)).sum())
    return counts


def analyze_trades(result: BacktestResult, bars: pd.DataFrame) -> dict:
    trade_df = enrich_trades_with_excursions(result.trades, bars)
    if trade_df.empty:
        return {
            "trade_count": 0,
            "avg_r": 0.0,
            "winner_avg_r": 0.0,
            "loser_avg_r": 0.0,
            "pct_touched_2_5r": 0.0,
            "r_histogram": r_histogram(trade_df),
            "exit_reason_avg_r": {},
            "avg_mfe_r": 0.0,
            "avg_mae_r": 0.0,
        }

    winners = trade_df[trade_df["r_multiple"] > 0]
    losers = trade_df[trade_df["r_multiple"] <= 0]
    exit_avg = trade_df.groupby("exit_reason")["r_multiple"].mean().to_dict()

    return {
        "trade_count": len(trade_df),
        "avg_r": float(trade_df["r_multiple"].mean()),
        "winner_avg_r": float(winners["r_multiple"].mean()) if not winners.empty else 0.0,
        "loser_avg_r": float(losers["r_multiple"].mean()) if not losers.empty else 0.0,
        "pct_touched_2_5r": float(trade_df["touched_2_5r"].mean()),
        "r_histogram": r_histogram(trade_df),
        "exit_reason_avg_r": {k: float(v) for k, v in exit_avg.items()},
        "avg_mfe_r": float(trade_df["mfe_r"].mean()),
        "avg_mae_r": float(trade_df["mae_r"].mean()),
    }


def format_analysis_report(analysis: dict) -> str:
    lines = [
        "=== Trade Analysis (MFE/MAE) ===",
        f"Trades: {analysis['trade_count']}",
        f"Avg R: {analysis['avg_r']:.2f}",
        f"Winner avg R: {analysis['winner_avg_r']:.2f}",
        f"Loser avg R: {analysis['loser_avg_r']:.2f}",
        f"Avg MFE (R): {analysis['avg_mfe_r']:.2f}",
        f"Avg MAE (R): {analysis['avg_mae_r']:.2f}",
        f"% touched 2.5R before exit: {analysis['pct_touched_2_5r']:.1%}",
        f"R histogram: {analysis['r_histogram']}",
        f"Exit reason avg R: {analysis['exit_reason_avg_r']}",
    ]
    return "\n".join(lines)
