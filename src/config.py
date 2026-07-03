"""Strategy configuration loaded from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class DataConfig(BaseModel):
    ask_path: str
    bid_path: str
    source_tz: str = "Europe/Helsinki"
    max_spread_points: float = 50.0
    bar_minutes: int = 1


class SessionConfig(BaseModel):
    timezone: str = "America/New_York"
    rth_open: str = "09:30"
    rth_close: str = "16:00"


class OrbConfig(BaseModel):
    minutes: int = 30
    min_width_points: float = 15.0
    max_width_points: float = 200.0


class VwapConfig(BaseModel):
    anchor: Literal["rth_open"] = "rth_open"
    slope_lookback_bars: int = 15
    slope_flat_points: float = 10.0


class StrategyConfig(BaseModel):
    strategy_type: Literal[
        "orb_breakout",
        "orb_fade",
        "intraday_momentum",
        "gao_session_momentum",
        "overnight_eu_open",
        "daily_tsmom",
    ] = "orb_breakout"
    max_trades_per_direction: int = 1
    entry_mode: Literal["breakout_close", "pullback_retest"] = "breakout_close"
    entry_start: str = "10:00"
    entry_cutoff: str = "15:30"
    require_vwap_guard: bool = True
    entry_on: Literal["close", "next_open"] = "close"
    min_vwap_distance_orb_frac: float = 0.0
    require_vwap_slope: bool = False
    require_vwap_slope_flat: bool = False
    min_breakout_volume_mult: float = 0.0
    reject_reentry_next_bar: bool = False
    retest_max_bars: int = 15
    retest_tolerance_points: float = 3.0
    arm_cancel_inside_bars: int = 2
    require_trend_day: bool = False
    min_first_hour_range: float = 35.0
    fade_max_bars: int = 6
    fade_require_close_inside: bool = True
    fade_compression_only: bool = True
    max_first_hour_range: float = 30.0
    progress_check_time: str | None = None
    min_progress_r: float = 0.5
    hard_exit_time: str | None = None
    hard_exit_min_r: float = 1.5
    momentum_check_minutes: int = 30
    noise_lookback_days: int = 14
    volatility_multiplier: float = 1.0
    use_vwap_trailing_stop: bool = True
    morning_end: str = "10:00"
    entry_time: str = "15:30"
    eu_open_start: str = "02:00"
    eu_open_end: str = "03:00"
    require_prior_rth_down: bool = False
    max_overnight_spread: float = 20.0
    tsmom_lookback_days: int = 252
    tsmom_long_only: bool = False
    tsmom_entry_on: Literal["open", "close"] = "open"


class RiskConfig(BaseModel):
    stop_mode: Literal[
        "opposite_orb_boundary",
        "orb_midpoint",
        "fixed_points",
        "retest_structure",
        "fade_structure",
        "noise_boundary",
        "session_hold",
        "monthly_hold",
    ] = "opposite_orb_boundary"
    stop_buffer_points: float = 2.0
    fixed_stop_points: float = 30.0
    max_stop_points: float = 40.0
    min_stop_points: float = 12.0
    target_r_multiple: float = 3.0
    trail_after_r: float = 1.5
    trail_step_r: float = 0.5
    trail_step_in_r: bool = True
    scale_out_r: float | None = None
    scale_out_pct: float = 0.5
    runner_target_r: float = 4.0


class CostsConfig(BaseModel):
    slippage_points: float = 1.0
    reject_ask_only_backtest: bool = True


class AppConfig(BaseModel):
    symbol: str = "USATECHIDXUSD"
    data: DataConfig
    session: SessionConfig = Field(default_factory=SessionConfig)
    orb: OrbConfig = Field(default_factory=OrbConfig)
    vwap: VwapConfig = Field(default_factory=VwapConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    costs: CostsConfig = Field(default_factory=CostsConfig)


def load_config(path: str | Path) -> AppConfig:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return AppConfig.model_validate(raw)


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent
