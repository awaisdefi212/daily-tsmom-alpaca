"""Audit bid/ask spreads across RTH, EU open, and full overnight windows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config, project_root
from src.data.loader import load_merged_data, load_parquet
from src.session.session_calendar import annotate_sessions, _hhmm_to_minutes
from src.session.overnight_calendar import annotate_overnight_windows


def _spread_stats(spread: pd.Series) -> dict:
    if spread.empty:
        return {"count": 0, "median": 0.0, "p90": 0.0, "p99": 0.0, "max": 0.0}
    return {
        "count": int(len(spread)),
        "median": float(spread.median()),
        "p90": float(spread.quantile(0.9)),
        "p99": float(spread.quantile(0.99)),
        "max": float(spread.max()),
    }


def audit_spreads(df: pd.DataFrame, cfg) -> tuple[pd.DataFrame, dict]:
    bars = annotate_sessions(df, cfg.session, cfg.orb, cfg.strategy)
    bars = annotate_overnight_windows(bars, cfg.session, cfg.strategy)

    rth_open = _hhmm_to_minutes(cfg.session.rth_open)
    rth_close = _hhmm_to_minutes(cfg.session.rth_close)
    is_rth = (bars["et_minute"] >= rth_open) & (bars["et_minute"] < rth_close)
    is_overnight = ~is_rth
    is_eu = bars["is_eu_open_window"]

    max_spread = cfg.strategy.max_overnight_spread
    eu_spread = bars.loc[is_eu, "spread"]
    eu_pass_rate = float((eu_spread <= max_spread).mean()) if not eu_spread.empty else 0.0

    rows = [
        {"window": "rth", **_spread_stats(bars.loc[is_rth, "spread"])},
        {"window": "eu_open_02_03", **_spread_stats(eu_spread)},
        {"window": "overnight_all", **_spread_stats(bars.loc[is_overnight, "spread"])},
    ]
    summary = pd.DataFrame(rows)
    gate = {
        "eu_median_spread": float(eu_spread.median()) if not eu_spread.empty else 0.0,
        "eu_pass_rate": eu_pass_rate,
        "median_gate_pass": float(eu_spread.median()) <= 10.0 if not eu_spread.empty else False,
        "pass_rate_gate_pass": eu_pass_rate >= 0.5,
        "proceed": (
            (float(eu_spread.median()) <= 10.0 if not eu_spread.empty else False)
            and eu_pass_rate >= 0.5
        ),
    }
    return summary, gate


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit overnight bid/ask spreads")
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "strategy_overnight_eu_open.yaml"),
    )
    parser.add_argument(
        "--export-csv",
        default=str(ROOT / "data" / "processed" / "validation" / "overnight" / "spread_audit.csv"),
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    root = project_root()
    cache = root / "data" / "processed" / "merged_bars.parquet"
    if cache.exists():
        df = load_parquet(cache)
    else:
        bid = root / cfg.data.bid_path
        ask = root / cfg.data.ask_path
        df = load_merged_data(bid, ask, cfg.data.source_tz)

    summary, gate = audit_spreads(df, cfg)
    print("=== Overnight Spread Audit ===")
    print(summary.to_string(index=False))
    print()
    print(f"EU window median spread: {gate['eu_median_spread']:.2f} pts")
    print(f"EU bars within max_overnight_spread ({cfg.strategy.max_overnight_spread}): {gate['eu_pass_rate']:.1%}")
    print(f"Proceed to backtest: {'YES' if gate['proceed'] else 'CAUTION - wide overnight spreads'}")

    out = Path(args.export_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out, index=False)
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
