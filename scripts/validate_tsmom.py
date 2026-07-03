"""Validation for daily time-series momentum strategy."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config, project_root
from src.data.loader import load_backtest_data
from src.backtest.backtest_engine import run_backtest, prepare_bars
from src.reporting.reporting import summarize_backtest
from src.reporting.momentum_validation import (
    trades_to_enriched_df,
    annual_breakdown,
    walk_forward_slices,
    slippage_stress,
    tsmom_lookback_stress,
    bootstrap_mean_bps,
    payoff_stats,
    exit_reason_breakdown,
    side_gross_pnl,
    evaluate_tsmom_gates,
    tsmom_verdict,
    format_tsmom_validation_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily TSMOM validation")
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "strategy_daily_tsmom_nq.yaml"),
    )
    parser.add_argument(
        "--export-csv",
        default=None,
        help="Directory to write validation CSV reports",
    )
    args = parser.parse_args()

    root = project_root()
    cfg = load_config(args.config)
    try:
        df = load_backtest_data(cfg, root)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1

    prepared = prepare_bars(df, cfg)

    net = run_backtest(df, cfg, prepared_bars=prepared)
    gross_cfg = cfg.model_copy(deep=True)
    gross_cfg.costs.slippage_points = 0.0
    gross = run_backtest(df, gross_cfg, prepared_bars=prepared)
    summary = summarize_backtest(net, gross)
    gross_summary = summarize_backtest(gross, gross)

    trades_df = trades_to_enriched_df(net)
    gross_trades_df = trades_to_enriched_df(gross)
    annual = annual_breakdown(trades_df)
    wf = walk_forward_slices(trades_df)
    slip = slippage_stress(df, cfg, [0.0, 0.5, 1.0, 1.5, 2.0], prepared_bars=prepared)
    lb = tsmom_lookback_stress(df, cfg, [189, 252, 378])
    boot = bootstrap_mean_bps(trades_df)
    payoff = payoff_stats(trades_df)
    exits = exit_reason_breakdown(trades_df)
    sides = side_gross_pnl(gross_trades_df)
    gates = evaluate_tsmom_gates(
        summary,
        gross_summary,
        trades_df,
        gross_trades_df,
        annual,
        slip,
        wf,
        lb,
        tsmom_long_only=cfg.strategy.tsmom_long_only,
    )
    verdict = tsmom_verdict(gates)

    print(
        format_tsmom_validation_report(
            gates, verdict, annual, wf, slip, lb, boot, payoff, exits, sides
        )
    )

    if args.export_csv:
        out_dir = Path(args.export_csv)
        out_dir.mkdir(parents=True, exist_ok=True)
        annual.to_csv(out_dir / "annual_breakdown.csv", index=False)
        wf.to_csv(out_dir / "walk_forward_slices.csv", index=False)
        slip.to_csv(out_dir / "slippage_stress.csv", index=False)
        lb.to_csv(out_dir / "lookback_stress.csv", index=False)
        if not exits.empty:
            exits.to_csv(out_dir / "exit_breakdown.csv", index=False)
        print(f"\nExported CSV reports to {out_dir}")

    return 0 if verdict.startswith("KEEP") or verdict.startswith("VALIDATE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
