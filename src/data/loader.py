"""Load and merge Dukascopy bid/ask CSV files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import AppConfig

TIME_COL = "Time (EET)"
OHLC_COLS = ["Open", "High", "Low", "Close"]
VOLUME_COL = "Volume"


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    if TIME_COL not in df.columns:
        raise ValueError(f"Expected column '{TIME_COL}' in CSV")
    rename = {c: c.lower() for c in OHLC_COLS}
    if VOLUME_COL in df.columns:
        rename[VOLUME_COL] = "volume"
    df = df.rename(columns=rename)
    return df


def _parse_timestamps(series: pd.Series, source_tz: str) -> pd.Series:
    parsed = pd.to_datetime(series, format="%Y.%m.%d %H:%M:%S")
    return parsed.dt.tz_localize(source_tz, ambiguous="infer", nonexistent="shift_forward")


def load_side_csv(path: str | Path, side: str, source_tz: str) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Missing {side} CSV: {path}")

    df = pd.read_csv(path)
    df = _normalize_columns(df)
    df["timestamp"] = _parse_timestamps(df[TIME_COL], source_tz)
    df = df.drop(columns=[TIME_COL])

    prefix = f"{side}_"
    df = df.rename(
        columns={
            "open": f"{prefix}open",
            "high": f"{prefix}high",
            "low": f"{prefix}low",
            "close": f"{prefix}close",
        }
    )
    if "volume" in df.columns:
        df = df.rename(columns={"volume": "volume"})
    else:
        df["volume"] = 0.0

    keep = ["timestamp", f"{prefix}open", f"{prefix}high", f"{prefix}low", f"{prefix}close", "volume"]
    return df[keep].sort_values("timestamp").reset_index(drop=True)


def deduplicate_side_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        raise ValueError("No frames to deduplicate")
    if len(frames) == 1:
        return frames[0]

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("timestamp")
    combined = combined.drop_duplicates(subset=["timestamp"], keep="last")
    return combined.reset_index(drop=True)


def merge_bid_ask(
    bid_df: pd.DataFrame,
    ask_df: pd.DataFrame,
    *,
    volume_from: str = "ask",
) -> pd.DataFrame:
    merged = pd.merge(bid_df, ask_df, on="timestamp", how="inner", suffixes=("_bid", "_ask"))

    vol_bid = merged.get("volume_bid")
    vol_ask = merged.get("volume_ask")
    if volume_from == "ask" and vol_ask is not None:
        merged["volume"] = vol_ask
    elif vol_bid is not None:
        merged["volume"] = vol_bid
    else:
        merged["volume"] = 0.0

    drop_cols = [c for c in merged.columns if c.startswith("volume_")]
    merged = merged.drop(columns=drop_cols)

    merged["mid_close"] = (merged["ask_close"] + merged["bid_close"]) / 2.0
    merged["spread"] = merged["ask_close"] - merged["bid_close"]
    return merged.sort_values("timestamp").reset_index(drop=True)


def load_merged_data(
    bid_path: str | Path,
    ask_paths: str | Path | list[str | Path],
    source_tz: str = "Europe/Helsinki",
) -> pd.DataFrame:
    bid_df = load_side_csv(bid_path, "bid", source_tz)

    if isinstance(ask_paths, (str, Path)):
        ask_paths = [ask_paths]
    ask_frames = [load_side_csv(p, "ask", source_tz) for p in ask_paths]
    ask_df = deduplicate_side_frames(ask_frames)

    return merge_bid_ask(bid_df, ask_df)


def load_backtest_data(cfg: AppConfig, root: Path) -> pd.DataFrame:
    """Load merged bars for backtest; cache is keyed by symbol (never cross-instrument)."""
    bid_path = root / cfg.data.bid_path
    if not bid_path.exists():
        raise FileNotFoundError(f"Missing bid CSV: {bid_path}")

    nq_cache = root / "data" / "processed" / "merged_bars.parquet"
    symbol_cache = root / f"data/processed/merged_bars_{cfg.symbol.lower()}.parquet"

    if cfg.symbol == "USATECHIDXUSD" and nq_cache.exists():
        return load_parquet(nq_cache)
    if symbol_cache.exists():
        return load_parquet(symbol_cache)

    ask_path = root / cfg.data.ask_path
    return load_merged_data(bid_path, ask_path, cfg.data.source_tz)


def save_parquet(df: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def load_parquet(path: str | Path) -> pd.DataFrame:
    return pd.read_parquet(path)
