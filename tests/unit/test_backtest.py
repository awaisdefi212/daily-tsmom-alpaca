"""Fill model and backtest invariant tests."""

from src.backtest.fill_model import check_intrabar_exit, apply_slippage
from src.backtest.backtest_engine import run_backtest
from src.config import CostsConfig


def test_stop_before_target_same_bar():
    res = check_intrabar_exit(
        side="long",
        stop=100.0,
        target=200.0,
        bid_high=210.0,
        bid_low=95.0,
        ask_high=212.0,
        ask_low=97.0,
        slippage=0.0,
    )
    assert res is not None
    assert res.reason == "stop"


def test_long_stop_uses_bid_low():
    res = check_intrabar_exit(
        side="long",
        stop=100.0,
        target=200.0,
        bid_high=105.0,
        bid_low=99.0,
        ask_high=107.0,
        ask_low=101.0,
        slippage=0.0,
    )
    assert res.reason == "stop"
    assert res.price == 100.0


def test_slippage_adverse_on_exit():
    px = apply_slippage(100.0, 1.0, adverse=True, side="long", is_entry=False)
    assert px == 99.0


def test_no_overnight_positions(long_trend_df, default_config):
    result = run_backtest(long_trend_df, default_config)
    for t in result.trades:
        assert t.exit_reason in ("stop", "target", "eod")


def test_pnl_identity_whipsaw(whipsaw_df, default_config):
    result = run_backtest(whipsaw_df, default_config)
    for t in result.trades:
        expected = (
            (t.exit_price - t.entry_price)
            if t.side == "long"
            else (t.entry_price - t.exit_price)
        )
        assert abs(t.pnl_points - expected) < 1e-9


def test_cost_monotonicity(long_trend_df, default_config):
    low = run_backtest(long_trend_df, default_config)
    cfg = default_config.model_copy(deep=True)
    cfg.costs.slippage_points = 5.0
    high = run_backtest(long_trend_df, cfg)
    if low.trades and high.trades:
        assert sum(t.slippage_cost for t in high.trades) >= sum(t.slippage_cost for t in low.trades)


def test_stop_target_ambiguous_exits_stop(stop_target_ambiguous_df, default_config):
    result = run_backtest(stop_target_ambiguous_df, default_config)
    assert len(result.trades) >= 1
    assert result.trades[0].exit_reason == "stop"
