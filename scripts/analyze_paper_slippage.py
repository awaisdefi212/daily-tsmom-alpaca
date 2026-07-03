"""Analyze paper-trade slippage logs for Phase 1 gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REQUIRED_COLS = [
    "session_date",
    "side",
    "intended_entry",
    "fill_entry",
    "intended_exit",
    "fill_exit",
]

MIN_SESSIONS = 20
MAX_ROUND_TRIP_SLIP = 1.0


def load_log(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    return df


def compute_slippage(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["entry_slip"] = (out["fill_entry"] - out["intended_entry"]).abs()
    out["exit_slip"] = (out["fill_exit"] - out["intended_exit"]).abs()
    out["round_trip_slip"] = out["entry_slip"] + out["exit_slip"]
    return out


def evaluate_phase1(df: pd.DataFrame) -> dict:
    enriched = compute_slippage(df)
    sessions = enriched["session_date"].nunique()
    avg_rt = float(enriched["round_trip_slip"].mean()) if not enriched.empty else 0.0
    avg_entry = float(enriched["entry_slip"].mean()) if not enriched.empty else 0.0
    avg_exit = float(enriched["exit_slip"].mean()) if not enriched.empty else 0.0
    passed = sessions >= MIN_SESSIONS and avg_rt <= MAX_ROUND_TRIP_SLIP
    return {
        "sessions": sessions,
        "trades": len(enriched),
        "avg_entry_slip": avg_entry,
        "avg_exit_slip": avg_exit,
        "avg_round_trip_slip": avg_rt,
        "max_round_trip_slip": float(enriched["round_trip_slip"].max()) if not enriched.empty else 0.0,
        "passed": passed,
    }


def format_report(result: dict) -> str:
    status = "PASS" if result["passed"] else "FAIL"
    lines = [
        "=== Phase 1 Paper Slippage Gate ===",
        f"Sessions logged: {result['sessions']} (need >= {MIN_SESSIONS})",
        f"Trades logged: {result['trades']}",
        f"Avg entry slip: {result['avg_entry_slip']:.2f} pts",
        f"Avg exit slip: {result['avg_exit_slip']:.2f} pts",
        f"Avg round-trip slip: {result['avg_round_trip_slip']:.2f} pts (need <= {MAX_ROUND_TRIP_SLIP})",
        f"Max round-trip slip: {result['max_round_trip_slip']:.2f} pts",
        "",
        f"VERDICT: {status}",
    ]
    if not result["passed"]:
        lines.append(
            "Action: edge may not survive at your broker — do not proceed to live trading."
        )
    else:
        lines.append("Action: proceed to Phase 2 (90-day lookback validation).")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1 paper slippage analysis")
    parser.add_argument(
        "--log",
        default=str(ROOT / "data" / "paper_trade" / "paper_trade_log.csv"),
        help="Path to paper trade CSV log",
    )
    args = parser.parse_args()
    path = Path(args.log)
    if not path.exists():
        print(f"ERROR: Log not found: {path}")
        print(f"Copy template: data/paper_trade/paper_trade_log_template.csv")
        print("Paper trade 20 RTH sessions, then run this script again.")
        return 1

    df = load_log(path)
    if df.empty or len(df) == 1 and "example" in str(df.get("notes", pd.Series([""])).iloc[0]).lower():
        print("ERROR: Log is empty or still contains only the example row.")
        return 1

    result = evaluate_phase1(df)
    print(format_report(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
