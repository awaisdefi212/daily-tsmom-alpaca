"""Objective go/no-go gates for the high-RRR rescue profile."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config, project_root, AppConfig
from src.data.loader import load_merged_data, load_parquet
from src.backtest.backtest_engine import run_backtest, prepare_bars
from src.reporting.reporting import summarize_backtest, trades_to_dataframe
from src.reporting.trade_analysis import analyze_trades


@dataclass
class GateResult:
    gate_id: str
    name: str
    passed: bool
    actual: str
    threshold: str


def _year_mask(df: pd.DataFrame, start_year: int, end_year: int) -> pd.Series:
    years = pd.to_datetime(df["session_date"]).dt.year
    return (years >= start_year) & (years <= end_year)


def _avg_r(trades_df: pd.DataFrame, start_year: int | None = None, end_year: int | None = None) -> float:
    if trades_df.empty:
        return 0.0
    df = trades_df
    if start_year is not None and end_year is not None:
        mask = _year_mask(df, start_year, end_year)
        df = df.loc[mask]
    if df.empty:
        return 0.0
    return float(df["r_multiple"].mean())


def evaluate_gates(
    net_summary: dict,
    gross_summary: dict,
    analysis: dict,
    net_trades_df: pd.DataFrame,
) -> list[GateResult]:
    gross_pnl = gross_summary["gross"]["total_pnl"]
    net_pnl = net_summary["net"]["total_pnl"]
    trade_count = net_summary["net"]["trade_count"]
    winner_avg_r = analysis["winner_avg_r"]
    avg_mfe = analysis["avg_mfe_r"]
    test_avg_r = _avg_r(net_trades_df, 2025, 2026)
    val_avg_r = _avg_r(net_trades_df, 2022, 2024)

    return [
        GateResult("G1", "Gross edge (full)", gross_pnl > 0, f"{gross_pnl:.1f}", "> 0"),
        GateResult("G2", "Net viability (full)", net_pnl > 0, f"{net_pnl:.1f}", "> 0"),
        GateResult("G3", "OOS avg R (2025-26)", test_avg_r > 0.15, f"{test_avg_r:.3f}", "> 0.15"),
        GateResult("G4", "Winner avg R", winner_avg_r >= 2.0, f"{winner_avg_r:.2f}", ">= 2.0"),
        GateResult("G5", "Avg MFE", avg_mfe >= 1.2, f"{avg_mfe:.2f}", ">= 1.2"),
        GateResult("G6", "Sample size", trade_count >= 150, f"{trade_count}", ">= 150"),
        GateResult(
            "G7",
            "Not overfit (test vs val)",
            test_avg_r >= val_avg_r - 0.15,
            f"test={test_avg_r:.3f} val={val_avg_r:.3f}",
            "test >= val - 0.15",
        ),
    ]


def verdict(gates: list[GateResult]) -> str:
    passed = {g.gate_id: g.passed for g in gates}
    all_pass = all(passed.values())
    if all_pass:
        return "KEEP - all gates passed; proceed to paper trading"

    g1, g2 = passed["G1"], passed["G2"]
    g4, g5 = passed["G4"], passed["G5"]
    if g1 and g2 and not g4 and not g5:
        return "VALIDATE - gross+net positive (R/MFE gates N/A for boundary stops); run validate_momentum.py"

    if g1 and g4 and g5 and not g2:
        return "KEEP (conditional) - gross edge + RRR shape OK; reduce costs / tighten execution"

    return "CANCEL - edge does not survive on NAS100 1-min Dukascopy data"


def run_evaluation(config_path: Path) -> tuple[list[GateResult], str, dict, dict]:
    root = project_root()
    cfg: AppConfig = load_config(config_path)
    bid_path = root / cfg.data.bid_path
    cache = root / "data" / "processed" / "merged_bars.parquet"

    if cache.exists():
        df = load_parquet(cache)
    else:
        ask_path = root / cfg.data.ask_path
        df = load_merged_data(bid_path, ask_path, cfg.data.source_tz)

    prepared = prepare_bars(df, cfg)
    net = run_backtest(df, cfg, prepared_bars=prepared)
    gross_cfg = cfg.model_copy(deep=True)
    gross_cfg.costs.slippage_points = 0.0
    gross = run_backtest(df, gross_cfg, prepared_bars=prepared)

    net_summary = summarize_backtest(net, gross)
    analysis = analyze_trades(net, prepared)
    net_trades_df = trades_to_dataframe(net.trades)
    gates = evaluate_gates(net_summary, net_summary, analysis, net_trades_df)
    rec = verdict(gates)
    return gates, rec, net_summary, analysis


def format_report(
    gates: list[GateResult],
    recommendation: str,
    summary: dict,
    analysis: dict,
) -> str:
    lines = [
        "=== Go/No-Go Report ===",
        f"Trades: {summary['net']['trade_count']}",
        f"Net PnL: {summary['net']['total_pnl']:.2f}",
        f"Gross PnL: {summary['gross']['total_pnl']:.2f}",
        f"Avg R: {summary['net']['avg_r']:.2f}",
        f"Winner avg R: {analysis['winner_avg_r']:.2f}",
        f"Loser avg R: {analysis['loser_avg_r']:.2f}",
        f"Avg MFE: {analysis['avg_mfe_r']:.2f}",
        "",
        "Gate          Status  Actual              Threshold",
        "------------------------------------------------------",
    ]
    for g in gates:
        status = "PASS" if g.passed else "FAIL"
        lines.append(f"{g.gate_id} {g.name:<22} {status:<6} {g.actual:<19} {g.threshold}")
    lines.append("")
    lines.append(f"RECOMMENDATION: {recommendation}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run go/no-go gates for high_rr profile")
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "archive" / "strategy_intraday_momentum_5m.yaml"),
        help="Path to strategy config YAML",
    )
    args = parser.parse_args()

    gates, rec, summary, analysis = run_evaluation(Path(args.config))
    print(format_report(gates, rec, summary, analysis))
    return 0 if rec.startswith("KEEP") else 1


if __name__ == "__main__":
    raise SystemExit(main())
