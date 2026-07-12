# Configuration.md

## 1. Sources and precedence

1. `config/config.yaml` — all tunable values, committed with safe paper-mode defaults.
2. `.env` — secrets only (API keys, Telegram token). Loaded via `pydantic-settings`.
   Env vars override YAML where names collide.
3. No other config sources. No CLI flags except `--config path`.

Config is loaded once at startup into a frozen pydantic `Settings` object, EXCEPT
`trading.mode`, which is runtime-mutable through the controlled switch in §3.

## 2. config.yaml (complete authoritative template)

```yaml
trading:
  mode: paper                # backtest | paper | live  ← THE switch
  exchange: binance          # any ccxt id; swap requires only this line + keys
  symbols: [BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT]
                             # rule: only top-liquidity pairs; adding a symbol requires
                             # backfill + backtest before it may trade
  timeframe: 1h
  base_currency: USDT

paper:
  starting_balance: 10000    # USDT
  fee_pct: 0.10              # taker fee simulated
  slippage_pct: 0.05         # applied against the trader on every fill

risk:                        # full semantics in RiskManagement.md
  risk_per_trade_pct: 1.0
  max_open_positions: 2
  max_total_exposure_pct: 30
  max_daily_drawdown_pct: 3.0
  max_total_drawdown_pct: 10.0
  max_data_staleness_sec: 300
  max_consecutive_rejections: 3

strategy:
  name: ema_trend            # or ml_lgbm after M9 (MLStrategy.md); one active strategy
  ml_model_path: data/models/lgbm_latest.txt
  ml_threshold: 0.60         # min predicted probability to enter
  ema_fast: 20
  ema_slow: 50
  atr_period: 14
  atr_stop_mult: 2.0

live_guard:                  # interlocks for entering LIVE mode, see §3
  require_paper_trades: 20   # min closed paper trades before live is allowed
  require_paper_days: 14     # min days of paper history
  allow_override: false      # if true, dashboard override checkbox is shown

dashboard:
  host: 127.0.0.1            # LAN exposure is a deliberate manual change
  port: 8080

telegram:
  enabled: true
  chat_id: ""                # set by user; token goes in .env

ollama:
  enabled: true
  host: http://127.0.0.1:11434
  main_model: qwen2.5:7b-instruct-q4_K_M
  fast_model: llama3.2:3b
  embed_model: nomic-embed-text
  request_timeout_sec: 60
```

## 3. Trading-mode switch (paper ↔ live) — CRITICAL FEATURE

### Design
- `core/state.py` holds `current_mode: TradingMode` and a single async function
  `switch_mode(target, confirmation: str | None, override: bool)`.
- Switching binds the corresponding `ExecutionAdapter` on the running app **without
  restart** and persists the new mode to `config.yaml` (so restarts keep the mode).
- **No other code changes with mode.** Strategy, risk, data, dashboard code are identical.

### Switch paths (both call the same `switch_mode`)
1. Edit `trading.mode` in `config.yaml` and restart the service.
2. Dashboard toggle → `POST /api/mode` (see Dashboard.md §3).

### Interlocks for PAPER → LIVE (all enforced server-side in `switch_mode`)
| Check | Behaviour on failure |
|-------|---------------------|
| Valid exchange API keys present and a ccxt `fetch_balance` succeeds | Block, error "live keys invalid" |
| Kill-switch is armed (not currently triggered) | Block |
| Data feed not stale | Block |
| `>= require_paper_trades` closed paper trades AND `>= require_paper_days` days of paper history | Block unless `allow_override: true` AND override checkbox ticked |
| Typed confirmation string equals exactly `GO-LIVE` | Block |

### LIVE → PAPER
Always allowed instantly, no confirmation. Open live positions are NOT auto-closed;
dashboard shows a persistent warning banner "live positions exist while in paper mode"
until they are manually flattened.

### On every switch
Log at WARNING, send Telegram alert, write a row to the `mode_changes` table
(Database.md), push a WebSocket event so the dashboard mode badge updates instantly.

## 4. Environment variables (.env.example — complete list)

```
EXCHANGE_API_KEY=
EXCHANGE_API_SECRET=
TELEGRAM_BOT_TOKEN=
TRADECORE_CONFIG=config/config.yaml   # optional override
```

Live mode must refuse to activate if key/secret are empty. Paper mode must work with
ALL env vars empty (public ccxt endpoints only).
