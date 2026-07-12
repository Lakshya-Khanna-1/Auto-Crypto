# TradingEngine.md

## 1. Overview
The trading engine = strategy runner + Risk Engine gate + ExecutionAdapter.
**One code path for paper and live**; only the adapter binding differs (Architecture.md §4).

## 2. Core dataclasses (`execution/adapter.py`)

```
Signal(symbol, side: Long|Flat, confidence: float 0..1, reason: str)
ApprovedOrder(symbol, side, qty, order_type: market, stop_price, signal_id)
Fill(order_id, symbol, side, qty, price, fee, ts)
Position(id, symbol, side, qty, entry_price, stop_price, opened_ts, status)
```

Spot-only, long-only in v1. "Sell" signals mean close the long. No shorting, no
margin, no leverage — the implementation model must not add these.

## 3. Baseline strategy: `ema_trend` (`strategy/ema_trend.py`)

Deterministic EMA crossover with ATR stop. On each closed candle for each symbol:

1. Compute EMA(fast=20), EMA(slow=50), ATR(14) on the candle DataFrame (pandas-ta).
2. **Entry**: no open position AND EMA_fast crossed above EMA_slow on this candle
   → `Signal(symbol, Long, confidence=1.0, reason="ema20>ema50 cross")`.
3. **Exit**: open position AND (EMA_fast crossed below EMA_slow OR close < stop_price)
   → `Signal(symbol, Flat, ...)`. (Stop is also enforced intracandle by the risk
   watchdog using ticker price — see RiskManagement.md §3.)
4. `stop_price = entry_price − atr_stop_mult × ATR` at entry, provided to Risk Engine.

Strategy ABC (`strategy/base.py`): `on_candle(df: DataFrame, position: Position|None) -> Signal|None`.
Strategies are pure functions of data + position; they never touch orders, balances, or mode.

## 4. ExecutionAdapter interface (the paper/live switch point)

```
class ExecutionAdapter(ABC):
    async def place(self, order: ApprovedOrder) -> Fill
    async def flatten(self, symbol: str | None = None) -> list[Fill]   # None = all
    async def get_balance(self) -> Balance
    async def get_open_orders(self) -> list[...]
    async def cancel_all(self) -> None
```

Both adapters share `execution/tracker.py` for position and PnL bookkeeping so
paper and live produce identical DB rows and dashboard views.

## 5. PaperAdapter (`execution/paper.py`)
- Balance starts at `paper.starting_balance`, persisted in `app_kv` so it survives restarts.
- `place`: fill immediately at `feed.last_tick[symbol].price` adjusted **against** the
  trader by `paper.slippage_pct`; fee = notional × `paper.fee_pct`. Refuse fill if
  ticker stale (raises → risk rejection streak counts it).
- Realism rules: no partial fills (fine at BTC/ETH liquidity), fills logged identically
  to live fills with `mode='paper'`.
- Reset: `POST /api/paper/reset` (Dashboard.md) zeroes paper positions and restores
  starting balance — allowed only in paper mode.

## 6. LiveAdapter (`execution/live.py`)
- ccxt authenticated client, `create_order(symbol, 'market', side, qty)`.
- After placing: poll `fetch_order` until closed (max 30 s) → build Fill from actual
  filled qty/price/fee. Timeout → `cancel_order`, raise `OrderTimeout` (counts toward
  rejection streak).
- Quantity rounded DOWN to exchange precision via `exchange.amount_to_precision`;
  check `min_notional` from `exchange.markets` and reject below it.
- On startup in live mode: **reconcile** — `fetch_balance` + `fetch_open_orders`,
  compare with DB open positions; mismatches → Telegram alert + trading paused until
  user resolves via dashboard (do not auto-fix).

## 7. Scheduler jobs (`scheduler/jobs.py`)
| Job | Interval | Action |
|-----|----------|--------|
| candle_sync | 5 min | DataPipeline.md §3 |
| strategy_tick | on the hour +30 s | run all strategies on closed candles → risk → execute |
| risk_watchdog | 60 s | RiskManagement.md §3 |
| equity_snapshot | 15 min | write equity_snapshots row |
| daily_report | 00:15 UTC | AILayer.md report; also DB backup zip |
| ticker_poll | 10 s | only when ws fallback active |

## 8. Crash recovery (startup sequence)
1. Load config → init store → run alembic upgrade.
2. Bind adapter for persisted mode. If mode==live → run reconcile (§6).
3. Load open positions from DB into tracker.
4. Arm kill-switch watchdog BEFORE enabling strategy_tick.
5. Start FastAPI + scheduler. Send Telegram "tradecore started, mode=X, N open positions".
