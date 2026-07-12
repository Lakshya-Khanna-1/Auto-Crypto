# DataPipeline.md

## 1. Responsibilities
- Backfill historical OHLCV, keep candles current, provide latest ticker prices,
  detect staleness. All exchange IO via ccxt only.

## 2. Historical backfill (`scripts/backfill.py`)
CLI: `python scripts/backfill.py --symbol BTC/USDT --timeframe 1h --days 730`
- Loop `exchange.fetch_ohlcv` with `since` pagination (ccxt returns max ~1000 rows/call),
  sleep `exchange.rateLimit` ms between calls, append to Parquet.
- Idempotent: re-running fills gaps only (dedupe on ts).
- Acceptance: 2 years of 1h candles for both default symbols with zero gaps
  (verify: consecutive ts deltas all equal timeframe).

## 3. Live candle updates (scheduler job `candle_sync`, every 5 min)
- For each symbol: fetch last 3 candles via `fetch_ohlcv(limit=3)`, append (dedupe),
  update `app_kv.last_candle_ts.{symbol}`.
- The strategy tick only uses **closed** candles: drop the in-progress candle
  (ts + timeframe > now).

## 4. Ticker prices (for paper fills + dashboard mark-to-market)
- Primary: ccxt.pro WebSocket `watch_ticker` per symbol if `ccxt.pro` available in the
  installed ccxt version; store latest price + received_at in memory (`feed.last_tick`).
- Fallback (and default if ws errors twice in a row): REST `fetch_ticker` polling every
  10 s via scheduler. Switching to fallback logs WARNING once, retries ws hourly.

## 5. Staleness detection
`feed.is_stale = (now - newest(last_tick.received_at)) > risk.max_data_staleness_sec`.
Risk watchdog reads this flag (RiskManagement.md §3). Never trade on stale data.

## 6. Error handling
- All ccxt calls wrapped in `tenacity` retry: 5 attempts, exponential 1→16 s, retry on
  `NetworkError`/`ExchangeNotAvailable`/`RequestTimeout`; do NOT retry on
  `AuthenticationError` or `InsufficientFunds` (raise immediately).
- Exchange-down for >5 min → Telegram alert "datafeed degraded".
