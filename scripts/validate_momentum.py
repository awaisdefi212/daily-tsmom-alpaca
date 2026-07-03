"""Advanced validation for intraday momentum strategy."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config, project_root
from src.data.loader import load_merged_data, load_parquet
from src.backtest.backtest_engine import run_backtest, prepare_bars
from src.reporting.reporting import summarize_backtest
from src.reporting.momentum_validation import (
    trades_to_enriched_df,
    annual_breakdown,
    walk_forward_slices,
    slippage_stress,
    lookback_stress,
    bootstrap_mean_bps,
    payoff_stats,
    exit_reason_breakdown,
    evaluate_momentum_gates,
    momentum_verdict,
    format_validation_report,
    evaluate_phase2_gates,
    phase2_verdict,
    format_phase2_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Advanced momentum strategy validation")
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "archive" / "strategy_intraday_momentum_5m.yaml"),
    )
    parser.add_argument(
        "--export-csv",
        default=None,
        help="Directory to write annual/slippage CSV reports",
    )
    parser.add_argument(
        "--phase2",
        action="store_true",
        help="Print Phase 2 gates (OOS + 1.0pt slip) for 90d lookback configs",
    )
    args = parser.parse_args()

    root = project_root()
    cfg = load_config(args.config)
    cache = root / "data" / "processed" / "merged_bars.parquet"

    if cache.exists():
        df = load_parquet(cache)
    else:
        bid_path = root / cfg.data.bid_path
        ask_path = root / cfg.data.ask_path
        df = load_merged_data(bid_path, ask_path, cfg.data.source_tz)

    prepared = prepare_bars(df, cfg)
    net = run_backtest(df, cfg, prepared_bars=prepared)
    gross_cfg = cfg.model_copy(deep=True)
    gross_cfg.costs.slippage_points = 0.0
    gross = run_backtest(df, gross_cfg, prepared_bars=prepared)
    summary = summarize_backtest(net, gross)

    trades_df = trades_to_enriched_df(net)
    annual = annual_breakdown(trades_df)
    wf = walk_forward_slices(trades_df)
    slip = slippage_stress(df, cfg, [0.0, 0.5, 1.0, 1.5], prepared_bars=prepared)
    lb = lookback_stress(df, cfg, [14, 30, 60, 90])
    boot = bootstrap_mean_bps(trades_df)
    payoff = payoff_stats(trades_df)
    exits = exit_reason_breakdown(trades_df)
    gates = evaluate_momentum_gates(summary, summary, trades_df, boot, annual, slip, wf)
    verdict = momentum_verdict(gates)

    report = format_validation_report(
        gates, verdict, annual, wf, slip, lb, boot, payoff, exits
    )
    print(report)

    if args.phase2 or cfg.strategy.noise_lookback_days >= 90:
        p2_gates = evaluate_phase2_gates(wf, slip)
        p2v = phase2_verdict(p2_gates)
        print()
        print(format_phase2_report(p2_gates, p2v, cfg.strategy.noise_lookback_days))

    if args.export_csv:
        out = Path(args.export_csv)
        out.mkdir(parents=True, exist_ok=True)
        annual.to_csv(out / "annual_breakdown.csv", index=False)
        wf.to_csv(out / "walk_forward_slices.csv", index=False)
        slip.to_csv(out / "slippage_stress.csv", index=False)
        lb.to_csv(out / "lookback_stress.csv", index=False)
        if not exits.empty:
            exits.to_csv(out / "exit_breakdown.csv", index=False)
        print(f"\nCSV reports written to {out}")

    return 0 if verdict.startswith(("KEEP", "VALIDATE")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
