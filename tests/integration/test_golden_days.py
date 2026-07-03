"""End-to-end golden day integration tests."""

from src.backtest.backtest_engine import run_backtest
from src.strategy.signal_engine import generate_entry_signals
from src.indicators.orb import compute_orb_levels
from src.indicators.vwap import compute_vwap
from src.session.session_calendar import annotate_sessions, filter_rth


def _pipeline(df, cfg):
    df = annotate_sessions(df, cfg.session, cfg.orb, cfg.strategy)
    df = filter_rth(df)
    df = compute_vwap(df)
    df = compute_orb_levels(df, cfg.orb)
    df = generate_entry_signals(df, cfg.strategy)
    return df


def test_long_trend_day_produces_trade(long_trend_df, default_config):
    bars = _pipeline(long_trend_df, default_config)
    assert (bars["signal"] == "long").any()
    result = run_backtest(long_trend_df, default_config)
    assert len(result.trades) >= 1
    assert result.trades[0].side == "long"


def test_false_breakout_no_trade(false_breakout_df, default_config):
    bars = _pipeline(false_breakout_df, default_config)
    assert bars["signal"].notna().sum() == 0
    result = run_backtest(false_breakout_df, default_config)
    assert len(result.trades) == 0


def test_whipsaw_stopped_out(whipsaw_df, default_config):
    result = run_backtest(whipsaw_df, default_config)
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "stop"
    assert result.trades[0].r_multiple < 0


def test_narrow_orb_no_trade(narrow_orb_df, default_config):
    result = run_backtest(narrow_orb_df, default_config)
    assert len(result.trades) == 0


def test_zero_volume_orb_no_trade(default_config):
    from tests.fixtures.synthetic import build_zero_volume_orb_day

    df = build_zero_volume_orb_day()
    result = run_backtest(df, default_config)
    assert len(result.trades) == 0


def test_csv_roundtrip_pipeline(fixture_csv_dir, default_config):
    from src.data.loader import load_merged_data

    tmp, bid_path, ask_path = fixture_csv_dir
    df = load_merged_data(bid_path, ask_path, "Europe/Helsinki")
    result = run_backtest(df, default_config)
    assert isinstance(result.trades, list)
