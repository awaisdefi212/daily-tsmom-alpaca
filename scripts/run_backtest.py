"""Run NAS100 intraday backtest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config, project_root
from src.data.loader import load_backtest_data
from src.backtest.backtest_engine import run_backtest, prepare_bars
from src.reporting.reporting import format_report, summarize_backtest, orb_sensitivity
from src.reporting.trade_analysis import analyze_trades, format_analysis_report

PROFILE_MAP = {
    "daily_tsmom_es_long_only": "strategy_daily_tsmom_es_long_only.yaml",
    "daily_tsmom_nq_long_only": "strategy_daily_tsmom_nq_long_only.yaml",
    "daily_tsmom_nq": "archive/strategy_daily_tsmom_nq.yaml",
    "daily_tsmom_es": "archive/strategy_daily_tsmom_es.yaml",
    "overnight_eu_open": "archive/strategy_overnight_eu_open.yaml",
    "overnight_eu_open_v2": "archive/strategy_overnight_eu_open_v2.yaml",
    "gao_session_momentum": "archive/strategy_gao_session_momentum.yaml",
    # Archived profiles (cancelled strategies)
    "intraday_momentum": "archive/strategy_intraday_momentum_5m.yaml",
    "intraday_momentum_90d": "archive/strategy_intraday_momentum_90d.yaml",
    "orb_fade": "archive/strategy_orb_fade_5m.yaml",
    "baseline": "archive/strategy.yaml",
    "2.5r": "archive/strategy_2.5r.yaml",
    "tuned": "archive/strategy_tuned.yaml",
    "high_rr": "archive/strategy_high_rr.yaml",
}

DEFAULT_PROFILE = "daily_tsmom_es_long_only"
DEPRECATED_PROFILES = set(PROFILE_MAP.keys()) - {DEFAULT_PROFILE}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run NAS100 intraday backtest")
    parser.add_argument("--config", default=None)
    parser.add_argument(
        "--profile",
        choices=list(PROFILE_MAP.keys()),
        default=None,
        help=f"Strategy profile (default: {DEFAULT_PROFILE})",
    )
    parser.add_argument(
        "--compare-profiles",
        default=None,
        help="Comma-separated profiles to compare, e.g. baseline,tuned",
    )
    parser.add_argument("--sensitivity", action="store_true")
    parser.add_argument("--compare", action="store_true", help="Run baseline vs 2.5r profile")
    parser.add_argument("--analyze", action="store_true", help="Print MFE/MAE trade analysis")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run advanced validation for supported strategy types",
    )
    args = parser.parse_args()

    if not args.config and not args.profile:
        args.profile = DEFAULT_PROFILE

    root = project_root()

    def _run_one(path: Path, label: str) -> int:
        cfg = load_config(path)
        bid_path = root / cfg.data.bid_path

        if cfg.costs.reject_ask_only_backtest and not bid_path.exists():
            print(f"ERROR: Bid file required: {bid_path}")
            return 1

        df = load_backtest_data(cfg, root)

        prepared = prepare_bars(df, cfg)
        net = run_backtest(df, cfg, prepared_bars=prepared)
        gross_cfg = cfg.model_copy(deep=True)
        gross_cfg.costs.slippage_points = 0.0
        gross = run_backtest(df, gross_cfg, prepared_bars=prepared)
        summary = summarize_backtest(net, gross)

        print(f"\n=== {label} ({path.name}) ===")
        if "archive" in path.parts:
            print("  [ARCHIVED] Cancelled profile - historical replay only")
        print(format_report(summary))
        if args.analyze:
            analysis = analyze_trades(net, prepared)
            print(format_analysis_report(analysis))
            _print_mfe_gates(analysis)
        if args.validate and cfg.strategy.strategy_type == "intraday_momentum":
            _print_momentum_validation(df, cfg, prepared, net, summary)
        if args.validate and cfg.strategy.strategy_type == "gao_session_momentum":
            _print_gao_validation(df, cfg, prepared, net, summary)
        if args.validate and cfg.strategy.strategy_type == "overnight_eu_open":
            _print_overnight_validation(df, cfg, prepared, net, summary)
        if args.validate and cfg.strategy.strategy_type == "daily_tsmom":
            _print_tsmom_validation(df, cfg, prepared, net, summary)
        return 0

    if args.compare_profiles:
        names = [p.strip() for p in args.compare_profiles.split(",")]
        rc = 0
        for name in names:
            if name not in PROFILE_MAP:
                print(f"ERROR: Unknown profile '{name}'. Choose from: {list(PROFILE_MAP)}")
                return 1
            rc |= _run_one(root / "config" / PROFILE_MAP[name], name.capitalize())
        return rc

    if args.compare:
        rc1 = _run_one(root / "config" / PROFILE_MAP["baseline"], "Baseline")
        rc2 = _run_one(root / "config" / PROFILE_MAP["2.5r"], "2.5R Profile")
        return rc1 or rc2

    if args.config:
        config_path = Path(args.config)
        label = config_path.stem
    else:
        config_path = root / "config" / PROFILE_MAP[args.profile]
        label = args.profile

    return _run_one(config_path, label.replace("_", " ").title())


def _print_mfe_gates(analysis: dict) -> None:
    print("\n=== MFE Success Gates ===")
    avg_mfe = analysis["avg_mfe_r"]
    pct_25 = analysis["pct_touched_2_5r"]
    gates = [
        ("Avg MFE > 1.0R", avg_mfe > 1.0, f"{avg_mfe:.2f}"),
        ("% touched 2.5R > 5%", pct_25 > 0.05, f"{pct_25:.1%}"),
    ]
    for label, passed, value in gates:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {label} (actual: {value})")


def _print_momentum_validation(df, cfg, prepared, net, summary) -> None:
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
    )

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
    print()
    print(
        format_validation_report(
            gates, verdict, annual, wf, slip, lb, boot, payoff, exits
        )
    )


def _print_gao_validation(df, cfg, prepared, net, summary) -> None:
    from src.reporting.momentum_validation import (
        trades_to_enriched_df,
        annual_breakdown,
        walk_forward_slices,
        slippage_stress,
        bootstrap_mean_bps,
        payoff_stats,
        exit_reason_breakdown,
        evaluate_gao_gates,
        gao_verdict,
        format_gao_validation_report,
    )

    trades_df = trades_to_enriched_df(net)
    annual = annual_breakdown(trades_df)
    wf = walk_forward_slices(trades_df)
    slip = slippage_stress(df, cfg, [0.0, 0.5, 1.0, 1.5], prepared_bars=prepared)
    boot = bootstrap_mean_bps(trades_df)
    payoff = payoff_stats(trades_df)
    exits = exit_reason_breakdown(trades_df)
    gates = evaluate_gao_gates(summary, summary, trades_df, boot, annual, slip, wf)
    verdict = gao_verdict(gates)
    print()
    print(format_gao_validation_report(gates, verdict, annual, wf, slip, boot, payoff, exits))


def _print_overnight_validation(df, cfg, prepared, net, summary) -> None:
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

    trades_df = trades_to_enriched_df(net)
    annual = annual_breakdown(trades_df)
    wf = walk_forward_slices(trades_df)
    slip = slippage_stress(df, cfg, [0.0, 0.5, 1.0, 1.5, 2.0], prepared_bars=prepared)
    boot = bootstrap_mean_bps(trades_df)
    payoff = payoff_stats(trades_df)
    exits = exit_reason_breakdown(trades_df)
    eu_rate = compute_eu_spread_pass_rate(prepared)
    gates = evaluate_overnight_gates(
        summary, summary, trades_df, boot, annual, slip, wf, eu_rate
    )
    verdict = overnight_verdict(gates)
    print()
    print(
        format_overnight_validation_report(
            gates, verdict, annual, wf, slip, boot, payoff, exits, eu_rate
        )
    )


def _print_tsmom_validation(df, cfg, prepared, net, summary) -> None:
    from src.backtest.backtest_engine import run_backtest
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

    gross_cfg = cfg.model_copy(deep=True)
    gross_cfg.costs.slippage_points = 0.0
    gross_bt = run_backtest(df, gross_cfg, prepared_bars=prepared)
    gross_sum = summarize_backtest(gross_bt, gross_bt)

    trades_df = trades_to_enriched_df(net)
    gross_trades_df = trades_to_enriched_df(gross_bt)
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
        gross_sum,
        trades_df,
        gross_trades_df,
        annual,
        slip,
        wf,
        lb,
        tsmom_long_only=cfg.strategy.tsmom_long_only,
    )
    verdict = tsmom_verdict(gates)
    print()
    print(
        format_tsmom_validation_report(
            gates, verdict, annual, wf, slip, lb, boot, payoff, exits, sides
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
