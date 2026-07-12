# Architecture.md

## 1. System shape

A **modular monolith**: one Python 3.12 process named `tradecore` containing all trading
logic and serving the dashboard, plus **Ollama** as a separate native Windows service.
Two NSSM-managed Windows services total:

```
┌─────────────────────────── Windows Server ───────────────────────────┐
│                                                                       │
│  NSSM service: tradecore (python -m tradecore)                        │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  FastAPI app (dashboard UI + REST API + WebSocket)              │  │
│  │  ┌───────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────────┐  │  │
│  │  │ datafeed  │→│ strategy │→│ riskengine│→│ execution        │  │  │
│  │  │ (ccxt)    │ │ runner   │ │ (veto/    │ │ (Paper|Live      │  │  │
│  │  │           │ │          │ │  killsw.) │ │  Adapter, ccxt)  │  │  │
│  │  └───────────┘ └──────────┘ └───────────┘ └──────────────────┘  │  │
│  │  ┌───────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────────┐  │  │
│  │  │ store     │ │ scheduler│ │ notifier  │ │ ailayer          │  │  │
│  │  │ SQLite+   │ │ (APSched)│ │ (Telegram)│ │ (Ollama client,  │  │  │
│  │  │ Parquet   │ │          │ │           │ │  advisory only)  │  │  │
│  │  └───────────┘ └──────────┘ └───────────┘ └──────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  NSSM service: ollama (native Windows Ollama)                         │
└───────────────────────────────────────────────────────────────────────┘
```

## 2. Modules

Each module lives in its own package under `tradecore/` (see `FolderStructure.md`).
Modules communicate through **direct Python function calls and an in-process event
bus** (a simple pub/sub built on `asyncio.Queue` — implement in `tradecore/core/events.py`,
~60 lines, this is the only allowed "custom infrastructure").

| Module | Responsibility | Depends on | Spec |
|--------|----------------|------------|------|
| `core` | config loading, event bus, mode state, logging setup | — | Configuration.md |
| `datafeed` | fetch OHLCV via ccxt, WebSocket ticker with REST polling fallback, staleness detection | core | DataPipeline.md |
| `store` | SQLite (state) + Parquet (candles) persistence | core | Database.md |
| `strategy` | strategy base class, baseline EMA trend strategy, signal generation | datafeed, store | TradingEngine.md §3 |
| `riskengine` | position sizing, exposure limits, drawdown watchdog, kill-switch | store, execution | RiskManagement.md |
| `execution` | ExecutionAdapter interface, PaperAdapter, LiveAdapter, order/position tracking | store, datafeed | TradingEngine.md §4–6 |
| `backtest` | vectorbt-based backtester + walk-forward runner | store, strategy | Backtesting.md |
| `dashboard` | FastAPI routes, WebSocket push, static frontend | all read-only + mode/kill controls | Dashboard.md |
| `notifier` | Telegram alerts + inbound commands (/status, /kill) | core | Notifications.md |
| `ailayer` | Ollama client, daily report generation, news summarization | store, datafeed | AILayer.md |
| `scheduler` | APScheduler jobs: candle fetch, strategy tick, risk check, daily report | all | TradingEngine.md §7 |

## 3. Data flow (live/paper tick)

1. `scheduler` fires strategy tick at candle close (1h default).
2. `datafeed` returns latest candles (from Parquet cache, refreshed via ccxt).
3. `strategy` computes signal → emits `SignalEvent(symbol, side, confidence)`.
4. `riskengine.approve(signal)` → returns `ApprovedOrder(qty, stop, ...)` **or rejects**.
   Risk Engine ALWAYS runs; there is no bypass path.
5. `execution.adapter.place(order)` → PaperAdapter simulates fill at live price with
   fee+slippage; LiveAdapter sends via ccxt.
6. Fill event → `store` persists trade → `dashboard` WebSocket push → `notifier` Telegram message.
7. Independently, `riskengine.watchdog` runs every 60 s: checks drawdown, data staleness,
   order-rejection streak → may trigger kill-switch (see RiskManagement.md).

## 4. Mode model

Global mode enum `TradingMode = {BACKTEST, PAPER, LIVE}` held in `core.state`.
Mode determines ONLY which ExecutionAdapter is bound. All other code is mode-agnostic
and must never branch on mode (enforced by code review checklist in CodingStandards.md).
Mode switching rules: `Configuration.md §3`.

## 5. Error-handling philosophy

- Exchange/network errors: retry with exponential backoff (use `tenacity`), max 5 tries,
  then raise → caught by module supervisor → logged + Telegram alert + module marked degraded.
- Degraded `datafeed` for > `max_data_staleness_sec` → kill-switch fires (safety over uptime).
- The process must never crash from a handled trading error; NSSM auto-restart is the
  last resort for unhandled crashes, and on startup the app reconciles state (see TradingEngine.md §8).

## 6. Scalability notes (do NOT implement now)

Module boundaries mirror future services. If ever needed: `datafeed` and `ailayer` are
the first candidates to split out; the event bus interface would be swapped for Redis
pub/sub. Documented here only so future work has a path; the implementation model must
not build any of this.
