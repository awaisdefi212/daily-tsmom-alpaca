"""Synthetic bid/ask bar builders for logical tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
EET = ZoneInfo("Europe/Helsinki")


def et_to_eet_ts(year: int, month: int, day: int, hour: int, minute: int) -> pd.Timestamp:
    dt = datetime(year, month, day, hour, minute, tzinfo=ET)
    return pd.Timestamp(dt.astimezone(EET))


def make_bar(
    ts: pd.Timestamp,
    bid_open: float,
    bid_high: float,
    bid_low: float,
    bid_close: float,
    spread: float = 2.0,
    volume: float = 0.05,
) -> dict:
    return {
        "timestamp": ts,
        "bid_open": bid_open,
        "bid_high": bid_high,
        "bid_low": bid_low,
        "bid_close": bid_close,
        "ask_open": bid_open + spread,
        "ask_high": bid_high + spread,
        "ask_low": bid_low + spread,
        "ask_close": bid_close + spread,
        "volume": volume,
        "mid_close": bid_close + spread / 2,
        "spread": spread,
    }


def rth_minute_timestamps(session_date: tuple[int, int, int], n_minutes: int, start_et: tuple[int, int]) -> list[pd.Timestamp]:
    y, m, d = session_date
    h, mi = start_et
    base = datetime(y, m, d, h, mi, tzinfo=ET)
    return [pd.Timestamp((base + timedelta(minutes=i)).astimezone(EET)) for i in range(n_minutes)]


def build_long_trend_day() -> pd.DataFrame:
    """ORB 30m, long breakout above VWAP, price runs to 3R target."""
    y, m, d = 2024, 1, 16
    times = rth_minute_timestamps((y, m, d), 120, (9, 30))
    rows = []
    base = 15000.0
    spread = 2.0

    for i, ts in enumerate(times):
        if i < 30:
            # ORB window: range ~20 pts
            b = base + (i % 5)
            rows.append(make_bar(ts, b, b + 18, b - 2, b + 8, spread=spread))
        elif i == 35:
            # Breakout long above orb_high (~15018) and vwap
            rows.append(make_bar(ts, 15025, 15035, 15020, 15030, spread=spread, volume=0.2))
        elif i > 35:
            # Trend up to hit 3R target
            lift = 80 + (i - 36) * 5
            b = 15030 + lift
            rows.append(make_bar(ts, b, b + 10, b - 5, b + 5, spread=spread, volume=0.1))
        else:
            b = base + 10
            rows.append(make_bar(ts, b, b + 12, b - 3, b + 5, spread=spread))

    return pd.DataFrame(rows)


def build_false_breakout_below_vwap() -> pd.DataFrame:
    """Breakout above ORB high but ask_close not above VWAP -> no long."""
    y, m, d = 2024, 1, 17
    times = rth_minute_timestamps((y, m, d), 90, (9, 30))
    rows = []
    for i, ts in enumerate(times):
        if i < 5:
            # High-volume spike sets elevated VWAP
            b = 16500.0
            rows.append(make_bar(ts, b, b + 50, b - 5, b + 40, spread=2.0, volume=1.0))
        elif i < 30:
            # Flat ORB at lower prices -> orb_high ~ 16120
            b = 16100.0
            rows.append(make_bar(ts, b, b + 18, b - 2, b + 8, spread=2.0, volume=0.05))
        elif i == 35:
            # Above orb_high (~16120) but below VWAP (~16500 area)
            rows.append(make_bar(ts, 16130, 16145, 16125, 16140, spread=2.0, volume=0.1))
        else:
            b = 16100.0
            rows.append(make_bar(ts, b, b + 10, b - 5, b + 2, spread=2.0, volume=0.05))
    return pd.DataFrame(rows)


def build_whipsaw_day() -> pd.DataFrame:
    """Long breakout then immediate stop."""
    y, m, d = 2024, 1, 18
    times = rth_minute_timestamps((y, m, d), 60, (9, 30))
    rows = []
    for i, ts in enumerate(times):
        if i < 30:
            b = 17000 + (i % 3)
            rows.append(make_bar(ts, b, b + 20, b - 2, b + 10, spread=2.0, volume=0.1))
        elif i == 32:
            rows.append(make_bar(ts, 17025, 17035, 17020, 17030, spread=2.0, volume=0.2))
        elif i == 33:
            # Crash through stop (orb_low ~ 16998)
            rows.append(make_bar(ts, 16980, 16990, 16970, 16975, spread=2.0, volume=0.2))
        else:
            rows.append(make_bar(ts, 17010, 17015, 17005, 17010, spread=2.0))
    return pd.DataFrame(rows)


def build_narrow_orb_day() -> pd.DataFrame:
    """ORB width < min_width -> no trade."""
    y, m, d = 2024, 1, 19
    times = rth_minute_timestamps((y, m, d), 50, (9, 30))
    rows = []
    for i, ts in enumerate(times):
        if i < 30:
            b = 18000.0
            rows.append(make_bar(ts, b, b + 5, b - 1, b + 2, spread=2.0, volume=0.1))
        elif i == 35:
            rows.append(make_bar(ts, 18010, 18020, 18005, 18015, spread=2.0, volume=0.2))
        else:
            rows.append(make_bar(ts, 18000, 18005, 17995, 18000, spread=2.0))
    return pd.DataFrame(rows)


def build_stop_target_same_bar() -> pd.DataFrame:
    """Intrabar hits both stop and target; stop must win."""
    y, m, d = 2024, 1, 22
    times = rth_minute_timestamps((y, m, d), 45, (9, 30))
    rows = []
    for i, ts in enumerate(times):
        if i < 30:
            b = 19000 + (i % 4)
            rows.append(make_bar(ts, b, b + 20, b - 2, b + 8, spread=2.0, volume=0.1))
        elif i == 31:
            rows.append(make_bar(ts, 19025, 19035, 19020, 19030, spread=2.0, volume=0.2))
        elif i == 32:
            # Wide bar: bid_low below stop, bid_high above target
            rows.append(make_bar(ts, 19000, 19200, 18950, 19100, spread=2.0, volume=0.3))
        else:
            rows.append(make_bar(ts, 19010, 19015, 19005, 19010, spread=2.0))
    return pd.DataFrame(rows)


def build_zero_volume_orb_day() -> pd.DataFrame:
    """ORB window has no volume -> no trade."""
    y, m, d = 2024, 1, 23
    times = rth_minute_timestamps((y, m, d), 50, (9, 30))
    rows = []
    for i, ts in enumerate(times):
        vol = 0.0 if i < 30 else 0.1
        b = 20000.0
        rows.append(make_bar(ts, b, b + 25, b - 2, b + 10, spread=2.0, volume=vol))
    return pd.DataFrame(rows)


def write_side_csv(df: pd.DataFrame, path, side: str) -> None:
    out = df.copy()
    out["Time (EET)"] = out["timestamp"].dt.strftime("%Y.%m.%d %H:%M:%S")
    prefix = f"{side}_"
    if side == "bid":
        cols = ["Time (EET)", "bid_open", "bid_high", "bid_low", "bid_close", "volume"]
        names = ["Time (EET)", "Open", "High", "Low", "Close", "Volume "]
    else:
        cols = ["Time (EET)", "ask_open", "ask_high", "ask_low", "ask_close", "volume"]
        names = ["Time (EET)", "Open", "High", "Low", "Close", "Volume "]
    out = out[cols]
    out.columns = names
    out.to_csv(path, index=False)
