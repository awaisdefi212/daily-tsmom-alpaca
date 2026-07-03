"""Thin Alpaca data + trading client for TSMOM paper trading."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import GetCalendarRequest, MarketOrderRequest

from src.broker.alpaca_config import AlpacaCredentials, AlpacaSettings

if TYPE_CHECKING:
    from alpaca.trading.models import Order, Position

NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class AccountSnapshot:
    equity: float
    buying_power: float
    cash: float


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    qty: float
    market_value: float
    current_price: float


def _feed_from_settings(settings: AlpacaSettings) -> DataFeed:
    name = settings.data_feed.upper()
    if name == "SIP":
        return DataFeed.SIP
    if name == "IEX":
        return DataFeed.IEX
    raise ValueError(f"Unsupported data_feed '{settings.data_feed}' (use iex or sip)")


class AlpacaBroker:
    def __init__(self, credentials: AlpacaCredentials, settings: AlpacaSettings) -> None:
        self.settings = settings
        self._trading = TradingClient(
            credentials.api_key,
            credentials.secret_key,
            paper=credentials.paper,
        )
        self._data = StockHistoricalDataClient(credentials.api_key, credentials.secret_key)

    def get_account(self) -> AccountSnapshot:
        acct = self._trading.get_account()
        return AccountSnapshot(
            equity=float(acct.equity),
            buying_power=float(acct.buying_power),
            cash=float(acct.cash),
        )

    def get_position(self, symbol: str) -> PositionSnapshot | None:
        try:
            pos: Position = self._trading.get_open_position(symbol)
        except Exception:
            return None
        qty = float(pos.qty)
        if qty == 0:
            return None
        return PositionSnapshot(
            symbol=symbol,
            qty=qty,
            market_value=float(pos.market_value),
            current_price=float(pos.current_price),
        )

    def fetch_daily_bars(
        self,
        symbol: str,
        *,
        end: date | None = None,
        lookback_calendar_days: int = 500,
    ) -> pd.DataFrame:
        end_date = end or datetime.now(NY).date()
        start_date = end_date - timedelta(days=lookback_calendar_days)
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start_date,
            end=end_date,
            feed=_feed_from_settings(self.settings),
        )
        bars = self._data.get_stock_bars(request)
        if bars.df is None or bars.df.empty:
            raise ValueError(f"No daily bars returned for {symbol}")

        df = bars.df.reset_index()
        if "timestamp" not in df.columns:
            raise ValueError("Unexpected Alpaca bar schema: missing timestamp")

        out = pd.DataFrame(
            {
                "session_date": pd.to_datetime(df["timestamp"], utc=True)
                .dt.tz_convert(NY)
                .dt.date,
                "close": df["close"].astype(float),
            }
        )
        return out.sort_values("session_date").drop_duplicates("session_date", keep="last")

    def is_trading_day(self, session_date: date) -> bool:
        cal = self._trading.get_calendar(
            GetCalendarRequest(start=session_date, end=session_date)
        )
        return len(cal) > 0

    def first_trading_day_of_month(self, year: int, month: int) -> date | None:
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        cal = self._trading.get_calendar(GetCalendarRequest(start=start, end=end))
        if not cal:
            return None
        return cal[0].date

    def submit_market_order(self, symbol: str, side: OrderSide, qty: int) -> Order:
        if qty <= 0:
            raise ValueError(f"Order qty must be positive, got {qty}")
        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.DAY,
        )
        return self._trading.submit_order(request)

    def close_position(self, symbol: str) -> Order | None:
        try:
            return self._trading.close_position(symbol)
        except Exception:
            return None
