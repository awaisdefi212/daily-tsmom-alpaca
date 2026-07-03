"""Walk-forward grid search for expectancy."""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import AppConfig, load_config, project_root
from src.data.loader import load_parquet
from src.backtest.backtest_engine import run_backtest, prepare_bars
from src.reporting.trade_analysis import analyze_trades


def _slice_by_year(df: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
    years = df["timestamp"].dt.year
    return df.loc[(years >= start) & (years <= end)].copy()


def _eval_config(cfg: AppConfig, df: pd.DataFrame) -> dict:
    prepared = prepare_bars(df, cfg)
    result = run_backtest(df, cfg, prepared_bars=prepared)
    analysis = analyze_trades(result, prepared)
    return {
        "trades": analysis["trade_count"],
        "avg_r": analysis["avg_r"],
        "net_pnl": sum(t.pnl_points for t in result.trades),
        "pct_touched_2_5r": analysis["pct_touched_2_5r"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk-forward expectancy optimization")
    parser.add_argument(
        "--base-config",
        default=str(project_root() / "config" / "strategy_2.5r.yaml"),
    )
    parser.add_argument(
        "--output",
        default=str(project_root() / "data" / "processed" / "optimize_results.csv"),
    )
    parser.add_argument("--min-trades", type=int, default=30)
    args = parser.parse_args()

    base = load_config(args.base_config)
    cache = project_root() / "data" / "processed" / "merged_bars.parquet"
    if not cache.exists():
        print("ERROR: Run validate_data.py first.")
        return 1

    full = load_parquet(cache)
    train = _slice_by_year(full, 2016, 2021)
    val = _slice_by_year(full, 2022, 2024)
    test = _slice_by_year(full, 2025, 2026)

    grid = {
        "orb_minutes": [45, 60],
        "stop_mode": ["orb_midpoint", "opposite_orb_boundary"],
        "min_width": [25, 30],
        "slippage": [0.5, 1.0],
    }

    combos = list(
        itertools.product(
            grid["orb_minutes"],
            grid["stop_mode"],
            grid["min_width"],
            grid["slippage"],
        )
    )
    print(f"Evaluating {len(combos)} configs (train/val/test)...")

    rows = []
    for n, (orb_m, stop_m, min_w, slip) in enumerate(combos, 1):
        cfg = base.model_copy(deep=True)
        cfg.orb.minutes = orb_m
        cfg.orb.min_width_points = min_w
        cfg.risk.stop_mode = stop_m
        cfg.costs.slippage_points = slip

        train_m = _eval_config(cfg, train)
        if train_m["trades"] < args.min_trades:
            print(f"  [{n}/{len(combos)}] skip orb={orb_m} stop={stop_m} width={min_w} slip={slip} (trades={train_m['trades']})")
            continue

        val_m = _eval_config(cfg, val)
        test_m = _eval_config(cfg, test)

        rows.append(
            {
                "orb_minutes": orb_m,
                "stop_mode": stop_m,
                "min_width": min_w,
                "slippage": slip,
                "train_trades": train_m["trades"],
                "train_avg_r": train_m["avg_r"],
                "train_pnl": train_m["net_pnl"],
                "val_avg_r": val_m["avg_r"],
                "val_pnl": val_m["net_pnl"],
                "test_avg_r": test_m["avg_r"],
                "test_pnl": test_m["net_pnl"],
                "test_pct_2_5r": test_m["pct_touched_2_5r"],
            }
        )
        print(
            f"  [{n}/{len(combos)}] orb={orb_m} stop={stop_m} "
            f"val_avg_r={val_m['avg_r']:.3f} test_avg_r={test_m['avg_r']:.3f}"
        )

    if not rows:
        print("No configs passed minimum trade count.")
        return 1

    out = pd.DataFrame(rows).sort_values(["val_avg_r", "test_avg_r"], ascending=False)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    best = out.iloc[0]
    print("\n=== Best config (by validation avg R) ===")
    print(best.to_string())
    print(f"\nFull results: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
