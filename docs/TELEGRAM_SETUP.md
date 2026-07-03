# Telegram alerts

Get a message on every cron run so you can monitor the bot without logging into the VPS.

## 1. Create a bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Pick a name and username (must end in `bot`)
4. Copy the **HTTP API token** (looks like `123456789:ABC...`)

## 2. Get your chat ID

1. Open a chat with **your new bot** and tap **Start** (or send any message)
2. On the VPS or your PC:

```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
```

3. Find `"chat":{"id":123456789` in the JSON — that number is your **chat ID**

For a group chat, add the bot to the group, send a message, then run `getUpdates` again and use the group chat id (often negative).

## 3. Add to `.env` on the VPS

```bash
nano ~/daily-tsmom-alpaca/.env
```

Add:

```
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

## 4. Test

```bash
cd ~/daily-tsmom-alpaca
source .venv/bin/activate
python scripts/test_telegram.py
```

You should receive: **"TSMOM Bot — Telegram notifications are working."**

## 5. What you receive

Every weekday when cron runs (~9:35 AM New York):

| Situation | Message |
|-----------|---------|
| Market closed | Short "market closed" ping |
| Trading day, no rebalance | Equity, position, action `none` |
| Rebalance day | 12m return, buy/sell/roll, order details if executed |
| Error | Full error text |

Config in `config/alpaca_tsmom.yaml`:

```yaml
telegram:
  enabled: true
  notify_on_no_op: true   # ping even when no trade
```

Disable for one run: `python scripts/run_alpaca_tsmom.py --no-telegram`

## Troubleshooting

- **No message:** run `python scripts/test_telegram.py` and check token/chat id
- **Bot not responding:** send `/start` to your bot first
- **Wrong chat:** use `getUpdates` after messaging the bot again
