"""Backtest metrics and cost breakdown."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from src.backtest.backtest_engine import BacktestResult, Trade


def trades_to_dataframe(trades: list[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame([asdict(t) for t in trades])


def summarize_backtest(net: BacktestResult, gross: BacktestResult) -> dict:
    net_df = trades_to_dataframe(net.trades)
    gross_df = trades_to_dataframe(gross.trades)

    def _stats(df: pd.DataFrame) -> dict:
        if df.empty:
            return {
                "trade_count": 0,
                "win_rate": 0.0,
                "avg_r": 0.0,
                "median_r": 0.0,
                "p95_r": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0,
                "max_drawdown": 0.0,
            }
        wins = df[df["pnl_points"] > 0]
        losses = df[df["pnl_points"] <= 0]
        gross_profit = wins["pnl_points"].sum() if not wins.empty else 0.0
        gross_loss = abs(losses["pnl_points"].sum()) if not losses.empty else 0.0
        eq = df["pnl_points"].cumsum()
        peak = eq.cummax()
        dd = (eq - peak).min()
        return {
            "trade_count": len(df),
            "win_rate": len(wins) / len(df),
            "avg_r": float(df["r_multiple"].mean()),
            "median_r": float(df["r_multiple"].median()),
            "p95_r": float(df["r_multiple"].quantile(0.95)),
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
            "total_pnl": float(df["pnl_points"].sum()),
            "max_drawdown": float(dd),
        }

    net_stats = _stats(net_df)
    gross_stats = _stats(gross_df)

    spread_drag = gross_stats["total_pnl"] - net_stats["total_pnl"]

    return {
        "net": net_stats,
        "gross": gross_stats,
        "cost_drag_points": spread_drag,
        "exit_reason_counts": net_df["exit_reason"].value_counts().to_dict() if not net_df.empty else {},
    }


def format_report(summary: dict) -> str:
    lines = [
        "=== Intraday Backtest Report ===",
        f"Trades: {summary['net']['trade_count']}",
        f"Net PnL (points): {summary['net']['total_pnl']:.2f}",
        f"Gross PnL (zero slippage): {summary['gross']['total_pnl']:.2f}",
        f"Cost drag (points): {summary['cost_drag_points']:.2f}",
        f"Win rate: {summary['net']['win_rate']:.1%}",
        f"Avg R: {summary['net']['avg_r']:.2f}",
        f"Median R: {summary['net']['median_r']:.2f}",
        f"95th pct R: {summary['net']['p95_r']:.2f}",
        f"Profit factor: {summary['net']['profit_factor']:.2f}",
        f"Max drawdown (points): {summary['net']['max_drawdown']:.2f}",
        f"Exit reasons: {summary['exit_reason_counts']}",
    ]
    return "\n".join(lines)


def orb_sensitivity(df: pd.DataFrame, config, orb_minutes_list: list[int]) -> pd.DataFrame:
    from src.config import AppConfig
    from src.backtest.backtest_engine import run_backtest

    rows = []
    for mins in orb_minutes_list:
        cfg: AppConfig = config.model_copy(deep=True)
        cfg.orb.minutes = mins
        result = run_backtest(df, cfg)
        summary = summarize_backtest(result, result)
        rows.append(
            {
                "orb_minutes": mins,
                "trades": summary["net"]["trade_count"],
                "net_pnl": summary["net"]["total_pnl"],
                "avg_r": summary["net"]["avg_r"],
            }
        )
    return pd.DataFrame(rows)
