"""Signal generation dispatcher."""

from __future__ import annotations

import pandas as pd

from src.config import StrategyConfig
from src.strategy.engines.orb_breakout import generate_breakout_signals
from src.strategy.engines.orb_fade import generate_fade_signals
from src.strategy.engines.intraday_momentum import generate_momentum_signals
from src.strategy.engines.gao_session_momentum import generate_gao_session_signals
from src.strategy.engines.overnight_eu_open import generate_overnight_eu_signals
from src.strategy.engines.daily_tsmom import generate_daily_tsmom_signals


def generate_entry_signals(df: pd.DataFrame, strategy_cfg: StrategyConfig) -> pd.DataFrame:
    if strategy_cfg.strategy_type == "daily_tsmom":
        return generate_daily_tsmom_signals(df, strategy_cfg)
    if strategy_cfg.strategy_type == "overnight_eu_open":
        return generate_overnight_eu_signals(df, strategy_cfg)
    if strategy_cfg.strategy_type == "gao_session_momentum":
        return generate_gao_session_signals(df, strategy_cfg)
    if strategy_cfg.strategy_type == "intraday_momentum":
        return generate_momentum_signals(df, strategy_cfg)
    if strategy_cfg.strategy_type == "orb_fade":
        return generate_fade_signals(df, strategy_cfg)
    return generate_breakout_signals(df, strategy_cfg)
