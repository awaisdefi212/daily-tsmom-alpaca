"""Signal and risk logical tests."""

from src.strategy.risk import build_trade_plan, compute_r_multiple, compute_entry_price
from src.config import RiskConfig, StrategyConfig
from src.strategy.signal_engine import generate_entry_signals
from src.indicators.vwap import compute_vwap
from src.indicators.orb import compute_orb_levels
from src.session.session_calendar import annotate_sessions, filter_rth


def _plan(side, entry, orb_high, orb_low, orb_width, orb_mid=None, risk_cfg=None):
    if orb_mid is None:
        orb_mid = (orb_high + orb_low) / 2
    return build_trade_plan(
        side, entry, orb_high, orb_low, orb_width, orb_mid, risk_cfg or RiskConfig()
    )


def test_stop_on_correct_side_long():
    plan = _plan("long", 15030.0, 15020.0, 15000.0, 20.0)
    assert plan.stop_price < plan.entry_price
    assert plan.target_price > plan.entry_price


def test_stop_on_correct_side_short():
    plan = _plan("short", 15000.0, 15020.0, 14980.0, 20.0)
    assert plan.stop_price > plan.entry_price
    assert plan.target_price < plan.entry_price


def test_r_multiple_math():
    plan = _plan("long", 100.0, 110.0, 90.0, 20.0, 100.0, RiskConfig(target_r_multiple=3.0))
    r = compute_r_multiple("long", 100.0, plan.target_price, plan.risk_per_unit)
    assert abs(r - 3.0) < 1e-9


def test_orb_midpoint_tighter_stop():
    cfg = RiskConfig(stop_mode="orb_midpoint", target_r_multiple=2.5)
    boundary = _plan("long", 110.0, 110.0, 90.0, 20.0, 100.0, RiskConfig(stop_mode="opposite_orb_boundary"))
    midpoint = _plan("long", 110.0, 110.0, 90.0, 20.0, 100.0, cfg)
    assert midpoint.risk_per_unit < boundary.risk_per_unit
    assert abs(
        compute_r_multiple("long", 110.0, midpoint.target_price, midpoint.risk_per_unit) - 2.5
    ) < 1e-9


def test_fixed_points_stop():
    cfg = RiskConfig(stop_mode="fixed_points", fixed_stop_points=30.0, target_r_multiple=2.5)
    plan = _plan("long", 100.0, 110.0, 90.0, 20.0, 100.0, cfg)
    assert plan.stop_price == 70.0
    assert plan.risk_per_unit == 30.0


def test_one_trade_per_direction(false_breakout_df, default_config):
    df = annotate_sessions(
        false_breakout_df,
        default_config.session,
        default_config.orb,
        default_config.strategy,
    )
    df = filter_rth(df)
    df = compute_vwap(df)
    df = compute_orb_levels(df, default_config.orb)
    df = generate_entry_signals(df, default_config.strategy)
    longs = df.loc[df["signal"] == "long"]
    assert len(longs) <= default_config.strategy.max_trades_per_direction


def test_no_long_when_breakout_below_vwap(false_breakout_df, default_config):
    df = annotate_sessions(
        false_breakout_df,
        default_config.session,
        default_config.orb,
        default_config.strategy,
    )
    df = filter_rth(df)
    df = compute_vwap(df)
    df = compute_orb_levels(df, default_config.orb)
    df = generate_entry_signals(df, default_config.strategy)
    assert (df["signal"] == "long").sum() == 0


def test_entry_price_includes_slippage():
    px = compute_entry_price("long", 100.0, 98.0, 1.0)
    assert px == 101.0
    px = compute_entry_price("short", 100.0, 98.0, 1.0)
    assert px == 97.0


def test_vwap_slope_filter_rejects(long_trend_df):
    from src.config import load_config
    from pathlib import Path

    cfg = load_config(Path(__file__).resolve().parents[2] / "config" / "archive" / "strategy_2.5r.yaml")
    df = annotate_sessions(long_trend_df, cfg.session, cfg.orb, cfg.strategy)
    df = filter_rth(df)
    df = compute_vwap(df, cfg.vwap)
    df = compute_orb_levels(df, cfg.orb)
    baseline = StrategyConfig(require_vwap_slope=False, min_breakout_volume_mult=0)
    strict = cfg.strategy
    df_base = generate_entry_signals(df, baseline)
    df_strict = generate_entry_signals(df, strict)
    assert (df_strict["signal"].notna().sum()) <= (df_base["signal"].notna().sum())
