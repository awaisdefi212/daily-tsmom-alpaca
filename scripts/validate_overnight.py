"""Validation for overnight EU open strategy."""

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
    bootstrap_mean_bps,
    payoff_stats,
    exit_reason_breakdown,
    compute_eu_spread_pass_rate,
    evaluate_overnight_gates,
    overnight_verdict,
    format_overnight_validation_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Overnight EU open validation")
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "strategy_overnight_eu_open.yaml"),
    )
    parser.add_argument(
        "--export-csv",
        default=None,
        help="Directory to write validation CSV reports",
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
    eu_spread_rate = compute_eu_spread_pass_rate(prepared)

    net = run_backtest(df, cfg, prepared_bars=prepared)
    gross_cfg = cfg.model_copy(deep=True)
    gross_cfg.costs.slippage_points = 0.0
    gross = run_backtest(df, gross_cfg, prepared_bars=prepared)
    summary = summarize_backtest(net, gross)

    trades_df = trades_to_enriched_df(net)
    annual = annual_breakdown(trades_df)
    wf = walk_forward_slices(trades_df)
    slip = slippage_stress(df, cfg, [0.0, 0.5, 1.0, 1.5, 2.0], prepared_bars=prepared)
    boot = bootstrap_mean_bps(trades_df)
    payoff = payoff_stats(trades_df)
    exits = exit_reason_breakdown(trades_df)
    gates = evaluate_overnight_gates(
        summary, summary, trades_df, boot, annual, slip, wf, eu_spread_rate
    )
    verdict = overnight_verdict(gates)

    print(
        format_overnight_validation_report(
            gates, verdict, annual, wf, slip, boot, payoff, exits, eu_spread_rate
        )
    )

    if args.export_csv:
        out = Path(args.export_csv)
        out.mkdir(parents=True, exist_ok=True)
        annual.to_csv(out / "annual_breakdown.csv", index=False)
        wf.to_csv(out / "walk_forward_slices.csv", index=False)
        slip.to_csv(out / "slippage_stress.csv", index=False)
        if not exits.empty:
            exits.to_csv(out / "exit_breakdown.csv", index=False)
        print(f"\nCSV reports written to {out}")

    return 0 if verdict.startswith(("KEEP", "VALIDATE")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
