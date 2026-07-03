"""Validate raw data before backtest."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config, project_root
from src.data.loader import load_merged_data, save_parquet
from src.data.validator import validate_merged_bars


def _print_available_raw_files(root: Path) -> None:
    raw = root / "Data" / "Raw"
    if not raw.exists():
        return
    files = sorted(raw.glob("*.csv"))
    if files:
        print("Available CSV files in Data/Raw:")
        for f in files:
            print(f"  - {f.name}")


def main() -> int:
    config_path = project_root() / "config" / "archive" / "strategy_intraday_momentum_5m.yaml"
    cfg = load_config(config_path)
    root = project_root()

    bid_path = root / cfg.data.bid_path
    ask_path = root / cfg.data.ask_path

    if not bid_path.exists():
        print(f"ERROR: Bid file missing: {bid_path}")
        _print_available_raw_files(root)
        print("Add Dukascopy Bid CSV or update config/archive/strategy_intraday_momentum_5m.yaml data.bid_path")
        return 1

    if not ask_path.exists():
        print(f"ERROR: Ask file missing: {ask_path}")
        _print_available_raw_files(root)
        print("Update config/archive/strategy_intraday_momentum_5m.yaml data.ask_path to match your files")
        return 1

    df = load_merged_data(bid_path, ask_path, cfg.data.source_tz)
    result = validate_merged_bars(df, cfg.data.max_spread_points)

    for w in result.warnings:
        print(f"WARNING: {w}")
    for e in result.errors:
        print(f"ERROR: {e}")

    if not result.ok:
        return 1

    out_path = root / "data" / "processed" / "merged_bars.parquet"
    save_parquet(df, out_path)
    print(f"OK: {len(df)} bars validated and cached to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
