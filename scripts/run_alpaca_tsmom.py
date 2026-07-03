"""Run monthly TSMOM rebalance on Alpaca paper account."""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.broker.alpaca_client import AlpacaBroker  # noqa: E402
from src.broker.alpaca_config import AlpacaCredentials, load_alpaca_config  # noqa: E402
from src.broker.telegram_notify import TelegramNotifier  # noqa: E402
from src.broker.tsmom_live import (  # noqa: E402
    append_paper_log,
    build_rebalance_plan,
    execute_plan,
)
from src.config import project_root  # noqa: E402

NY = ZoneInfo("America/New_York")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alpaca paper TSMOM monthly rebalance")
    parser.add_argument(
        "--config",
        default="config/alpaca_tsmom.yaml",
        help="Alpaca TSMOM YAML config",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Submit orders (default is dry-run only)",
    )
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help="Allow live (non-paper) trading when alpaca.paper is false",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Override session date (YYYY-MM-DD), for testing",
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Disable Telegram notifications for this run",
    )
    return parser.parse_args()


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _print_plan(plan) -> None:
    print(f"Session date:     {plan.session_date}")
    print(f"Rebalance day:    {plan.is_rebalance_day}")
    print(f"12m return:       {plan.tsmom_return}")
    print(f"Target exposure:  {plan.target_exposure}")
    print(f"Current qty:      {plan.current_qty}")
    print(f"Action:           {plan.intended_action}")
    print(f"Order qty:        {plan.order_qty}")
    print(f"Reason:           {plan.reason}")


def _order_info(order) -> dict[str, str]:
    if order is None:
        return {}
    return {
        "id": str(getattr(order, "id", "")),
        "status": str(getattr(order, "status", "")),
        "side": str(getattr(order, "side", "")),
        "qty": str(getattr(order, "qty", "")),
        "filled_avg_price": str(getattr(order, "filled_avg_price", "") or ""),
    }


def main() -> int:
    args = parse_args()
    load_dotenv(project_root() / ".env")

    cfg = load_alpaca_config(project_root() / args.config)
    settings = cfg.alpaca
    telegram_enabled = cfg.telegram.enabled and not args.no_telegram
    notifier = TelegramNotifier.from_env(enabled=telegram_enabled)

    try:
        if not settings.paper and not args.allow_live:
            msg = "Refusing live trading. Set alpaca.paper: true or pass --allow-live."
            print(msg, file=sys.stderr)
            notifier.send_error("startup", msg)
            return 1

        as_of = _parse_date(args.date) if args.date else datetime.now(NY).date()
        credentials = AlpacaCredentials.from_env(paper=settings.paper)
        broker = AlpacaBroker(credentials, settings)

        if not broker.is_trading_day(as_of):
            print(f"{as_of} is not an Alpaca trading day — nothing to do.")
            if cfg.telegram.notify_on_no_op:
                notifier.send_non_trading_day(as_of.isoformat())
            return 0

        bars = broker.fetch_daily_bars(settings.symbol, end=as_of)
        account = broker.get_account()
        position = broker.get_position(settings.symbol)

        plan = build_rebalance_plan(
            broker,
            settings,
            as_of_date=as_of,
            bars=bars,
            account=account,
            position=position,
        )

        print(f"Symbol: {settings.symbol} | Equity: ${account.equity:,.2f}")
        _print_plan(plan)

        execute = args.execute
        order = None

        if plan.intended_action != "none" and execute:
            order = execute_plan(broker, settings, plan)
            fill_price = None
            if order is not None and getattr(order, "filled_avg_price", None):
                fill_price = float(order.filled_avg_price)

            last_price = float(bars.iloc[-1]["close"])
            log_path = project_root() / settings.paper_log_path
            append_paper_log(
                log_path,
                plan,
                intended_price=last_price,
                fill_price=fill_price,
                notes=f"order_id={getattr(order, 'id', None)}",
            )
            print(f"\nOrder submitted. Logged to {log_path}")
        elif plan.intended_action != "none":
            print("\nDry run — no orders sent. Pass --execute to trade.")

        should_notify = (
            plan.intended_action != "none"
            or plan.is_rebalance_day
            or cfg.telegram.notify_on_no_op
        )
        if should_notify:
            notifier.send_run_report(
                symbol=settings.symbol,
                paper=settings.paper,
                executed=bool(execute and plan.intended_action != "none"),
                account=account,
                plan=plan,
                order_info=_order_info(order) if order else None,
            )

        return 0
    except Exception as exc:
        tb = traceback.format_exc()
        notifier.send_error("run_alpaca_tsmom", f"{exc}\n{tb}")
        print(tb, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
