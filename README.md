# Gold Desk (paper mode)

TradingView alert → Scanner → Setup Analyst + Big Money & World News Radar → Risk rules (code) → Boss → Telegram (A and A+ only).
Plus: the Radar runs every 15 min on its own and texts you breaking gold news (Trump, wars, tariffs, Fed) and a warning 30 min before big US releases.
It NEVER places trades.

## Railway variables
| Name | What |
|---|---|
| ANTHROPIC_API_KEY | from console.anthropic.com (turn on web search there, set a monthly spending limit) |
| WEBHOOK_SECRET | any long password you make up |
| TELEGRAM_BOT_TOKEN | from @BotFather |
| TELEGRAM_CHAT_ID | your PRIVATE chat id (not the public scoreboard) |
| MIN_STOP | minimum stop distance in gold $ (default 20) |
| LOTS_A / LOTS_APLUS | default 4 / 6 |

Add a Railway volume mounted at `/data` so the log survives restarts.

## Links (put your Railway address in front)
- `/stop?key=SECRET` pause the desk · `/start?key=SECRET` restart it
- `/calls?key=SECRET` last 30 alerts with every agent's notes
- `/radar?key=SECRET` run the news radar now
- `/test?key=SECRET&telegram=1` test message to your phone
- `/test?key=SECRET` run a fake alert through the whole desk

## TradingView
Add `GoldDeskFeed.pine` to the XAUUSD 5-minute chart (Pine Editor → paste → Add to chart), put your secret in its settings,
then make ONE alert: Condition "Gold Desk Feed" → "Any alert() function call", Webhook URL = `https://YOUR-APP.up.railway.app/webhook`.
