"""Reporting module tests."""

from src.backtest.backtest_engine import run_backtest, run_backtest_zero_costs
from src.reporting.reporting import summarize_backtest, format_report, orb_sensitivity


def test_summarize_backtest(long_trend_df, default_config):
    net = run_backtest(long_trend_df, default_config)
    gross = run_backtest_zero_costs(long_trend_df, default_config)
    summary = summarize_backtest(net, gross)
    assert "net" in summary
    assert "gross" in summary
    assert summary["net"]["trade_count"] >= 0


def test_format_report_nonempty(long_trend_df, default_config):
    net = run_backtest(long_trend_df, default_config)
    gross = run_backtest_zero_costs(long_trend_df, default_config)
    text = format_report(summarize_backtest(net, gross))
    assert "Intraday Backtest Report" in text


def test_orb_sensitivity(long_trend_df, default_config):
    sens = orb_sensitivity(long_trend_df, default_config, [15, 30])
    assert len(sens) == 2
    assert "orb_minutes" in sens.columns
