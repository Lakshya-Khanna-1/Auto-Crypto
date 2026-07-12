# Database.md

Two stores, both file-based, both under `data/` (gitignored):

## 1. SQLite — application state (`data/db/tradecore.sqlite3`)
Managed with SQLAlchemy Core + Alembic migrations. WAL mode ON. All timestamps UTC ISO-8601.

### Tables (authoritative schema)

**trades** — one row per fill
| column | type | notes |
|--------|------|-------|
| id | INTEGER PK | |
| ts | TEXT | fill time UTC |
| mode | TEXT | paper / live |
| symbol | TEXT | e.g. BTC/USDT |
| side | TEXT | buy / sell |
| qty | REAL | base asset qty |
| price | REAL | fill price incl. slippage |
| fee | REAL | quote currency |
| order_id | TEXT | adapter order id |
| position_id | INTEGER FK→positions | |
| strategy | TEXT | strategy name |

**positions** — one row per position lifecycle
| column | type | notes |
|--------|------|-------|
| id | INTEGER PK | |
| mode, symbol, side | TEXT | |
| qty, entry_price | REAL | |
| stop_price | REAL | ATR stop from risk engine |
| opened_ts, closed_ts | TEXT | closed_ts NULL while open |
| exit_price, realized_pnl, fees_total | REAL | filled at close |
| status | TEXT | open / closed |

**equity_snapshots** — written every 15 min by scheduler + at every fill
| ts, mode | | |
| balance | REAL | cash |
| equity | REAL | cash + mark-to-market of open positions |

**mode_changes** — audit of every mode switch: ts, from_mode, to_mode, source (config/dashboard/telegram), override_used (bool)

**killswitch_events** — ts, reason, details_json, positions_flattened (bool)

**signals** — every strategy signal, approved or not: ts, symbol, side, confidence, risk_decision (approved/rejected), risk_reason

**app_kv** — key TEXT PK, value TEXT. Used for: last processed candle per symbol, daily HWM for drawdown calc, killswitch armed flag.

### Repository layer
All DB access goes through `store/repo.py` typed functions. No raw SQL outside `store/`.

## 2. Parquet — market data (`data/candles/{exchange}/{symbol_sanitized}/{timeframe}.parquet`)
- Columns: ts (int64 ms), open, high, low, close, volume (float64). Sorted, unique ts.
- `store/candles.py` provides: `read(symbol, tf, start, end) -> DataFrame`,
  `append(symbol, tf, df)` (dedupe on ts, atomic write via temp file + replace).
- Symbol sanitization: replace `/` with `-` in paths.
- Retention: keep everything; ~1 year of 1h candles per symbol is < 1 MB.

## 3. Backups
Daily scheduler job zips `data/db/` to `data/backups/db-YYYYMMDD.zip`, keep last 14.
Parquet needs no backup beyond normal (re-downloadable), but include in weekly zip.
