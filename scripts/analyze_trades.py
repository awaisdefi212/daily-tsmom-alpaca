"""Analyze trade MFE/MAE and R distribution."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config, project_root
from src.data.loader import load_parquet
from src.backtest.backtest_engine import run_backtest, prepare_bars
from src.reporting.trade_analysis import analyze_trades, format_analysis_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze backtest trades (MFE/MAE)")
    parser.add_argument(
        "--config",
        default=str(project_root() / "config" / "archive" / "strategy_intraday_momentum_5m.yaml"),
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    cache = project_root() / "data" / "processed" / "merged_bars.parquet"
    if not cache.exists():
        print("ERROR: Run validate_data.py first.")
        return 1

    df = load_parquet(cache)
    prepared = prepare_bars(df, cfg)
    result = run_backtest(df, cfg, prepared_bars=prepared)
    analysis = analyze_trades(result, prepared)
    print(format_analysis_report(analysis))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
