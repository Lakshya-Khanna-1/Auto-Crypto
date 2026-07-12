# Project Handover

## Current State
- **Completed Milestone**: M2 (Data pipeline - ingestion & storage).
- **Next Milestone**: M3 (Backtester & baseline strategy).
- **Git Branch / Tag**: `main` (We will tag `M2` upon manual verification approval).

## Commands

### Activate Virtual Environment
```powershell
.\.venv\Scripts\Activate.ps1
```

### Run Self-Verification
```powershell
python -m tradecore --selfcheck
```

### Run Automated Tests
```powershell
python -m pytest
```

### Perform Code Style Auditing
```powershell
ruff check .
```

### Run Price Backfill CLI
```powershell
python scripts/backfill.py --symbol BTC/USDT --timeframe 1h --days 730
```

### Run Application (FastAPI Stub + Scheduler Sync)
```powershell
python -m tradecore
```

---

## DB / Logs Layout

- **Database Path**: `data/db/tradecore.sqlite3` (SQLite 3 with WAL journal mode).
- **Parquet Storage**: `data/candles/{exchange}/{symbol_sanitized}/{timeframe}.parquet`
  - Columns: `ts` (int64 ms), `open`, `high`, `low`, `close`, `volume` (float64)
- **Log Directory**: `data/logs/`
  - `tradecore.log` (Rotational application logs, max 10MB, up to 5 backups)
  - `service-out.log` / `service-err.log` (Stdout/Stderr from Windows Service wrapper)
