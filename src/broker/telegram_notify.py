"""Telegram notifications for Alpaca TSMOM bot status."""

from __future__ import annotations

import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from src.broker.alpaca_client import AccountSnapshot
from src.broker.tsmom_live import TsmomRebalancePlan


@dataclass(frozen=True)
class TelegramCredentials:
    bot_token: str
    chat_id: str

    @classmethod
    def from_env(cls) -> TelegramCredentials | None:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            return None
        return cls(bot_token=token, chat_id=chat_id)


class TelegramNotifier:
    def __init__(self, credentials: TelegramCredentials | None, *, enabled: bool = True) -> None:
        self._credentials = credentials
        self.enabled = enabled and credentials is not None

    @classmethod
    def from_env(cls, *, enabled: bool = True) -> TelegramNotifier:
        return cls(TelegramCredentials.from_env(), enabled=enabled)

    def send(self, text: str) -> bool:
        if not self.enabled or self._credentials is None:
            return False
        return _post_message(self._credentials, text)

    def send_error(self, context: str, error: str) -> bool:
        body = (
            "<b>TSMOM Bot — ERROR</b>\n"
            f"<b>Context:</b> {html.escape(context)}\n"
            f"<b>Error:</b> {html.escape(error)}"
        )
        return self.send(body)

    def send_non_trading_day(self, session_date: str) -> bool:
        body = (
            "<b>TSMOM Bot — daily check</b>\n"
            f"Date: {html.escape(session_date)}\n"
            "Market: <b>closed</b>\n"
            "Action: none"
        )
        return self.send(body)

    def send_run_report(
        self,
        *,
        symbol: str,
        paper: bool,
        executed: bool,
        account: AccountSnapshot,
        plan: TsmomRebalancePlan,
        order_info: dict[str, Any] | None = None,
    ) -> bool:
        mode = "PAPER" if paper else "LIVE"
        exec_label = "EXECUTED" if executed else "DRY RUN"
        ret = (
            f"{plan.tsmom_return * 100:.2f}%"
            if plan.tsmom_return is not None
            else "n/a"
        )
        lines = [
            f"<b>TSMOM Bot — {exec_label}</b>",
            f"Mode: {mode}",
            f"Date: {plan.session_date}",
            f"Symbol: {html.escape(symbol)}",
            f"Equity: ${account.equity:,.2f}",
            f"Position: {plan.current_qty} shares",
            f"Rebalance day: {'yes' if plan.is_rebalance_day else 'no'}",
            f"12m return: {ret}",
            f"Target: {plan.target_exposure or 'n/a'}",
            f"Action: <b>{html.escape(plan.intended_action)}</b>",
        ]
        if plan.order_qty is not None:
            lines.append(f"Order qty: {plan.order_qty}")
        lines.append(f"Note: {html.escape(plan.reason)}")
        if order_info:
            lines.append("")
            lines.append("<b>Order</b>")
            for key, value in order_info.items():
                lines.append(f"{html.escape(str(key))}: {html.escape(str(value))}")
        return self.send("\n".join(lines))


def _post_message(credentials: TelegramCredentials, text: str) -> bool:
    url = f"https://api.telegram.org/bot{credentials.bot_token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": credentials.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        return bool(body.get("ok"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return False


def send_test_message(credentials: TelegramCredentials) -> bool:
    return _post_message(
        credentials,
        "<b>TSMOM Bot</b>\nTelegram notifications are working.",
    )
