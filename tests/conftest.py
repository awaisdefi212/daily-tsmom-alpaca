"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import AppConfig, load_config
from tests.fixtures.synthetic import (
    build_long_trend_day,
    build_false_breakout_below_vwap,
    build_whipsaw_day,
    build_narrow_orb_day,
    build_stop_target_same_bar,
    write_side_csv,
)


@pytest.fixture
def default_config() -> AppConfig:
    root = Path(__file__).resolve().parent.parent
    return load_config(root / "config" / "archive" / "strategy.yaml")


@pytest.fixture
def long_trend_df():
    return build_long_trend_day()


@pytest.fixture
def false_breakout_df():
    return build_false_breakout_below_vwap()


@pytest.fixture
def whipsaw_df():
    return build_whipsaw_day()


@pytest.fixture
def narrow_orb_df():
    return build_narrow_orb_day()


@pytest.fixture
def stop_target_ambiguous_df():
    return build_stop_target_same_bar()


@pytest.fixture
def fixture_csv_dir(tmp_path):
    df = build_long_trend_day()
    bid = tmp_path / "bid.csv"
    ask = tmp_path / "ask.csv"
    write_side_csv(df, bid, "bid")
    write_side_csv(df, ask, "ask")
    return tmp_path, bid, ask
