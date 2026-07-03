"""50/50 NQ + ES intraday momentum portfolio validation (Phase 3)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config, project_root
from src.data.loader import load_merged_data, load_parquet
from src.backtest.backtest_engine import run_backtest, prepare_bars
from src.reporting.reporting import summarize_backtest, trades_to_dataframe
from src.reporting.momentum_validation import (
    trades_to_enriched_df,
    walk_forward_slices,
    slippage_stress,
    evaluate_phase2_gates,
    phase2_verdict,
    format_phase2_report,
)


def _load_df(cfg, root: Path):
    cache = root / "data" / "processed" / "merged_bars.parquet"
    bid_path = root / cfg.data.bid_path
    if cfg.symbol == "USA500IDXUSD":
        es_cache = root / "data" / "processed" / "merged_bars_es.parquet"
        if es_cache.exists():
            return load_parquet(es_cache)
        if not bid_path.exists():
            return None
        ask_path = root / cfg.data.ask_path
        return load_merged_data(bid_path, ask_path, cfg.data.source_tz)
    if cache.exists():
        return load_parquet(cache)
    ask_path = root / cfg.data.ask_path
    return load_merged_data(bid_path, ask_path, cfg.data.source_tz)


def run_portfolio_validation(
    nq_config: Path,
    es_config: Path,
    weight_nq: float = 0.5,
) -> dict:
    root = project_root()
    nq_cfg = load_config(nq_config)
    es_cfg = load_config(es_config)

    es_bid = root / es_cfg.data.bid_path
    if not es_bid.exists():
        return {"status": "skipped", "reason": f"ES bid file missing: {es_bid}"}

    nq_df = _load_df(nq_cfg, root)
    es_df = _load_df(es_cfg, root)
    if nq_df is None or es_df is None:
        return {"status": "skipped", "reason": "Could not load NQ or ES data"}

    nq_prep = prepare_bars(nq_df, nq_cfg)
    es_prep = prepare_bars(es_df, es_cfg)
    nq_net = run_backtest(nq_df, nq_cfg, prepared_bars=nq_prep)
    es_net = run_backtest(es_df, es_cfg, prepared_bars=es_prep)

    nq_tdf = trades_to_enriched_df(nq_net)
    es_tdf = trades_to_enriched_df(es_net)
    nq_tdf["weighted_pnl"] = nq_tdf["pnl_points"] * weight_nq
    es_tdf["weighted_pnl"] = es_tdf["pnl_points"] * (1.0 - weight_nq)

    combined = pd.concat([nq_tdf, es_tdf], ignore_index=True)
    combined["pnl_points"] = combined["weighted_pnl"]
    combined_pnl = float(combined["weighted_pnl"].sum())

    nq_summary = summarize_backtest(nq_net, nq_net)
    es_summary = summarize_backtest(es_net, es_net)

    slip_nq = slippage_stress(nq_df, nq_cfg, [0.5, 1.0], prepared_bars=nq_prep)
    slip_es = slippage_stress(es_df, es_cfg, [0.5, 1.0], prepared_bars=es_prep)

    combined_wf = walk_forward_slices(combined)

    return {
        "status": "ok",
        "nq_net": nq_summary["net"]["total_pnl"],
        "es_net": es_summary["net"]["total_pnl"],
        "combined_net": combined_pnl,
        "nq_trades": nq_summary["net"]["trade_count"],
        "es_trades": es_summary["net"]["trade_count"],
        "combined_wf": combined_wf,
        "slip_nq": slip_nq,
        "slip_es": slip_es,
    }


def format_portfolio_report(result: dict) -> str:
    if result["status"] == "skipped":
        return (
            "=== Phase 3 Portfolio Validation ===\n"
            f"SKIPPED: {result['reason']}\n"
            "Add Dukascopy USA500IDXUSD bid/ask CSVs to Data/Raw/ and re-run."
        )

    import pandas as pd

    lines = [
        "=== Phase 3 Portfolio Validation (50% NQ + 50% ES) ===",
        f"NQ net @ 0.5pt: {result['nq_net']:+.1f} ({result['nq_trades']} trades)",
        f"ES net @ 0.5pt: {result['es_net']:+.1f} ({result['es_trades']} trades)",
        f"Combined weighted net: {result['combined_net']:+.1f}",
        "",
        "--- Combined walk-forward ---",
    ]
    for _, row in result["combined_wf"].iterrows():
        lines.append(
            f"  {row['slice']}: {int(row['trades'])} trades, net {row['net_pnl']:+.1f} pts"
        )
    lines.extend(["", "--- Slippage stress (per leg) ---"])
    for label, slip_df in [("NQ", result["slip_nq"]), ("ES", result["slip_es"])]:
        for _, row in slip_df.iterrows():
            lines.append(
                f"  {label} slip {row['slippage_pts']:.1f}pt: net {row['net_pnl']:+.1f}"
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3 NQ+ES portfolio validation")
    parser.add_argument(
        "--nq-config",
        default=str(ROOT / "config" / "archive" / "strategy_intraday_momentum_90d.yaml"),
    )
    parser.add_argument(
        "--es-config",
        default=str(ROOT / "config" / "archive" / "strategy_intraday_momentum_es.yaml"),
    )
    args = parser.parse_args()

    result = run_portfolio_validation(Path(args.nq_config), Path(args.es_config))
    print(format_portfolio_report(result))
    return 0 if result["status"] in ("ok", "skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
