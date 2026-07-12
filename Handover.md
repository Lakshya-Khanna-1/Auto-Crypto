# Project Handover

## Current State
- **Completed Milestone**: M1 (Skeleton & core setup).
- **Next Milestone**: M2 (Data pipeline - ingestion & storage).
- **Git Branch / Tag**: `main` (We will tag `M1` upon manual verification approval).

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

### Run Application (FastAPI Stub)
```powershell
python -m tradecore
```

---

## DB / Logs Layout

- **Database Path**: `data/db/tradecore.sqlite3` (SQLite 3 with WAL journal mode).
- **Log Directory**: `data/logs/`
  - `tradecore.log` (Rotational application logs, max 10MB, up to 5 backups)
  - `service-out.log` / `service-err.log` (Stdout/Stderr from Windows Service wrapper)
