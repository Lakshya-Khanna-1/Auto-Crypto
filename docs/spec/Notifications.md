# Notifications.md

Telegram bot via `python-telegram-bot`. Token in `.env`, chat_id in config. If
`telegram.enabled: false` or token missing, notifier becomes a no-op logger (never crash).

## Outbound alerts (fixed set — do not add more)
| Event | Level |
|-------|-------|
| Startup / shutdown (mode, open positions count) | info |
| Fill (entry/exit): symbol, side, qty, price, P&L if exit | info |
| Mode change (from→to, source) | warning |
| Kill-switch triggered (reason) + flatten result | ALARM (repeat every 5 min until flatten succeeds) |
| Data feed degraded / recovered | warning |
| Live reconcile mismatch on startup | ALARM |
| Daily AI report | info |

## Inbound commands (only from configured chat_id; others ignored + logged)
| Command | Action |
|---------|--------|
| /status | same payload as GET /api/status, formatted |
| /positions | open positions table |
| /kill | trigger kill-switch immediately (no confirmation — speed matters) |
| /rearm then /confirm within 60 s | re-arm kill-switch |
| /pause /resume | strategy pause toggle |

Mode switching is deliberately NOT available via Telegram (dashboard only).
