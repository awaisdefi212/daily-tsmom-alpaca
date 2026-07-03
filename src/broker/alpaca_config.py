"""Alpaca paper-trading configuration for monthly TSMOM."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class AlpacaSettings(BaseModel):
    symbol: str = "SPY"
    paper: bool = True
    tsmom_lookback_days: int = 252
    tsmom_long_only: bool = True
    position_fraction: float = Field(default=0.95, ge=0.01, le=1.0)
    min_history_bars: int = 300
    paper_log_path: str = "data/paper_trade/alpaca_tsmom_log.csv"
    data_feed: str = "iex"

    @field_validator("data_feed")
    @classmethod
    def normalize_feed(cls, value: str) -> str:
        return value.lower().strip()


class AlpacaTsmomConfig(BaseModel):
    alpaca: AlpacaSettings = Field(default_factory=AlpacaSettings)


def load_alpaca_config(path: str | Path) -> AlpacaTsmomConfig:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return AlpacaTsmomConfig.model_validate(raw)


class AlpacaCredentials(BaseModel):
    api_key: str
    secret_key: str
    paper: bool = True

    @classmethod
    def from_env(cls, *, paper: bool = True) -> AlpacaCredentials:
        api_key = os.getenv("APCA_API_KEY_ID", "").strip()
        secret_key = os.getenv("APCA_API_SECRET_KEY", "").strip()
        if not api_key or not secret_key:
            raise ValueError(
                "Set APCA_API_KEY_ID and APCA_API_SECRET_KEY in the environment or .env file"
            )
        return cls(api_key=api_key, secret_key=secret_key, paper=paper)
