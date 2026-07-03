"""Data loader and validator logical tests."""

import pandas as pd
import pytest

from src.data.loader import (
    load_side_csv,
    merge_bid_ask,
    deduplicate_side_frames,
    load_merged_data,
)
from src.data.validator import validate_merged_bars
from tests.fixtures.synthetic import make_bar, et_to_eet_ts, write_side_csv, build_long_trend_day


def test_normalize_trailing_volume_header(fixture_csv_dir):
    tmp, bid_path, ask_path = fixture_csv_dir
    df = load_side_csv(ask_path, "ask", "Europe/Helsinki")
    assert "ask_close" in df.columns
    assert "volume" in df.columns


def test_merge_bid_ask_spread(fixture_csv_dir):
    tmp, bid_path, ask_path = fixture_csv_dir
    bid = load_side_csv(bid_path, "bid", "Europe/Helsinki")
    ask = load_side_csv(ask_path, "ask", "Europe/Helsinki")
    merged = merge_bid_ask(bid, ask)
    assert (merged["spread"] >= 0).all()
    assert merged["ask_close"].ge(merged["bid_close"]).all()


def test_deduplicate_keeps_latest():
    ts = et_to_eet_ts(2024, 1, 15, 10, 0)
    a = pd.DataFrame([make_bar(ts, 100, 101, 99, 100)])
    b = pd.DataFrame([make_bar(ts, 200, 201, 199, 200)])
    out = deduplicate_side_frames([a, b])
    assert out.iloc[0]["bid_close"] == 200


def test_monotonic_validation():
    ts1 = et_to_eet_ts(2024, 1, 15, 10, 0)
    ts2 = et_to_eet_ts(2024, 1, 15, 10, 1)
    df = pd.DataFrame([make_bar(ts2, 100, 101, 99, 100), make_bar(ts1, 100, 101, 99, 100)])
    result = validate_merged_bars(df)
    assert not result.ok


def test_ohlc_integrity_validation():
    ts = et_to_eet_ts(2024, 1, 15, 10, 0)
    row = make_bar(ts, 100, 99, 101, 100)  # invalid: low > high
    result = validate_merged_bars(pd.DataFrame([row]))
    assert not result.ok


def test_negative_spread_fails():
    ts = et_to_eet_ts(2024, 1, 15, 10, 0)
    row = make_bar(ts, 100, 101, 99, 100, spread=-1)
    result = validate_merged_bars(pd.DataFrame([row]))
    assert not result.ok


def test_valid_merged_passes(long_trend_df):
    result = validate_merged_bars(long_trend_df)
    assert result.ok, result.errors


def test_load_merged_from_csv(fixture_csv_dir):
    tmp, bid_path, ask_path = fixture_csv_dir
    df = load_merged_data(bid_path, ask_path, "Europe/Helsinki")
    assert len(df) > 0
    assert "spread" in df.columns
