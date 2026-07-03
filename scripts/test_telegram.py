"""Send a test Telegram message using .env credentials."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.broker.telegram_notify import TelegramCredentials, send_test_message  # noqa: E402


def main() -> int:
    creds = TelegramCredentials.from_env()
    if creds is None:
        print("ERROR: Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        print("See docs/TELEGRAM_SETUP.md")
        return 1

    ok = send_test_message(creds)
    if ok:
        print("OK — check your Telegram chat for the test message.")
        return 0

    print("ERROR: Telegram API call failed. Check token, chat id, and bot /start.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
