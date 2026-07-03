"""Tests for Telegram notification formatting and delivery."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from src.broker.alpaca_client import AccountSnapshot
from src.broker.telegram_notify import TelegramCredentials, TelegramNotifier, _post_message
from src.broker.tsmom_live import TsmomRebalancePlan


def test_notifier_disabled_without_credentials():
    notifier = TelegramNotifier(None, enabled=True)
    assert notifier.send("hello") is False


@patch("src.broker.telegram_notify.urllib.request.urlopen")
def test_post_message_success(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"ok": true}'
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    creds = TelegramCredentials(bot_token="token", chat_id="123")
    assert _post_message(creds, "test") is True


def test_run_report_includes_action():
    notifier = TelegramNotifier(None, enabled=False)
    plan = TsmomRebalancePlan(
        session_date=date(2026, 6, 1),
        is_rebalance_day=True,
        tsmom_return=0.12,
        target_exposure="long",
        intended_action="buy",
        order_qty=100,
        current_qty=0,
        reason="test",
    )
    account = AccountSnapshot(equity=100_000, buying_power=400_000, cash=100_000)
    assert notifier.send_run_report(
        symbol="SPY",
        paper=True,
        executed=False,
        account=account,
        plan=plan,
    ) is False
