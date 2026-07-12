# Dashboard.md

Single-page dashboard served by FastAPI from `tradecore/dashboard/static/`.
Vanilla JS + Chart.js + Tailwind (CDN). One user, LAN/localhost. Auto-refresh via
WebSocket push with 10 s REST polling fallback.

## 1. Layout (single page, top to bottom)

**Header bar (always visible)**
- Mode badge: `PAPER` (blue) / `LIVE` (red, pulsing) / kill-switch `HALTED` (grey) —
  updates instantly via WebSocket.
- Equity, today's P&L (₹/USDT + %, green/red), total P&L since start of current mode.
- Buttons: `Mode Switch`, `KILL SWITCH` (red), `Pause/Resume strategy`.

**Panel 1 — Equity curve**: Chart.js line of `equity_snapshots` for current mode;
range selector 1D/1W/1M/All.

**Panel 2 — Open positions table**
Columns: symbol, side, qty, entry price, current price (live tick), stop price,
unrealized P&L (value + %), opened time, [Close] button per row.
Unrealized P&L recomputed client-side on every ticker WebSocket message.

**Panel 3 — Trade history**: paginated (50/page) closed positions: symbol, entry,
exit, qty, realized P&L, fees, duration, strategy, mode. Filter by mode. CSV export button.

**Panel 4 — Signals & risk log**: last 100 rows of `signals` table incl. rejections
with reasons; kill-switch events highlighted.

**Panel 5 — System status**: data feed freshness per symbol, ws-or-polling indicator,
scheduler last-run times, Ollama reachable (✓/✗), version, uptime.

**Panel 6 — Daily AI report** (collapsible): latest report from AILayer.md; plain text.

## 2. Mode switch UX
Click `Mode Switch` → modal:
- Current mode, target mode radio (paper/live).
- If target = live: shows interlock checklist fetched from `GET /api/mode/preflight`
  (each check ✓/✗ per Configuration.md §3), a text input "type GO-LIVE to confirm",
  and (only if `allow_override: true`) an override checkbox. Confirm button disabled
  until all blocking checks pass and confirmation matches.
- If target = paper: single confirm click.
Result toast + badge update. Errors from the API shown verbatim in the modal.

## 3. REST API contract (all under `/api`, JSON)

| Method & path | Purpose | Response (200) |
|---|---|---|
| GET /status | header data | `{mode, equity, balance, pnl_today, pnl_total, killswitch, paused, uptime_sec}` |
| GET /positions | open positions | `[{id, symbol, side, qty, entry_price, stop_price, current_price, unrealized_pnl, opened_ts}]` |
| POST /positions/{id}/close | manual close | `{fill: {...}}` |
| GET /trades?mode=&page=&page_size= | history | `{items:[...], total}` |
| GET /trades/export.csv?mode= | CSV download | text/csv |
| GET /equity?range=1d\|1w\|1m\|all | curve | `[{ts, equity}]` |
| GET /signals?limit=100 | signal/risk log | `[{ts, symbol, side, risk_decision, risk_reason}]` |
| GET /mode/preflight | live interlock state | `{checks:[{name, ok, detail}], can_go_live}` |
| POST /mode | switch mode | body `{target, confirmation, override}` → `{mode}` or 409 `{error}` |
| POST /killswitch | manual trigger | `{status:"triggered"}` |
| POST /killswitch/rearm | re-arm | body `{confirmation:"RE-ARM"}` → `{status:"armed"}` or 409 |
| POST /strategy/pause, /strategy/resume | toggle strategy_tick | `{paused}` |
| POST /paper/reset | reset paper account | 409 if mode != paper |
| GET /system | panel 5 data | `{feeds:[...], jobs:[...], ollama_ok, version}` |
| GET /report/latest | panel 6 | `{ts, text}` |

Errors: non-200 always `{error: "<human readable>"}`. 409 for blocked actions,
400 for bad input, 500 logged with traceback (traceback never sent to client).

## 4. WebSocket `/ws`
Server pushes JSON events: `{"type": "tick"|"fill"|"mode"|"killswitch"|"equity"|"status", "data": {...}}`.
Client reconnects with backoff; while disconnected, falls back to 10 s polling of /status + /positions.

## 5. Security
Bind 127.0.0.1 by default. If user sets host 0.0.0.0, require `DASHBOARD_PASSWORD`
env var → simple session cookie login page; refuse to start on 0.0.0.0 without it.
No other auth system in v1.
