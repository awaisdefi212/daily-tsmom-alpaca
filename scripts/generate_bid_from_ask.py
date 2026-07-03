"""DEV ONLY: approximate Bid CSV from Ask by subtracting fixed spread.

Use real Dukascopy Bid data for production backtests.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def generate_bid_from_ask(ask_path: Path, bid_path: Path, spread: float = 2.0) -> None:
    df = pd.read_csv(ask_path)
    df.columns = [c.strip() for c in df.columns]
    for col in ("Open", "High", "Low", "Close"):
        df[col] = df[col] - spread
    vol_col = "Volume" if "Volume" in df.columns else "Volume "
    if vol_col not in df.columns:
        df["Volume "] = 0.0
    df.to_csv(bid_path, index=False)
    print(f"Wrote approximate bid file: {bid_path} (spread={spread})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ask_path")
    parser.add_argument("bid_path")
    parser.add_argument("--spread", type=float, default=2.0)
    args = parser.parse_args()
    generate_bid_from_ask(Path(args.ask_path), Path(args.bid_path), args.spread)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
