# CodingStandards.md

- Python 3.12, full type hints on public functions; `ruff` (lint+format) must be clean.
- Async-first: IO functions are `async def`; CPU/pandas work stays sync, called via
  `asyncio.to_thread` if it could block > ~100 ms.
- **Never branch on TradingMode outside `core/state.py` and `switch_mode`.** The
  adapter abstraction is the only mode boundary. (Grep check at every milestone:
  `TradingMode.` appearing outside core/, tests/, and app wiring is a defect.)
- Money math: prices/qty as `float` is acceptable in v1 (spot, market orders, precision
  rounded via ccxt helpers) — do NOT introduce Decimal ad hoc; consistency matters more.
- Errors: raise specific exceptions (`OrderTimeout`, `StaleDataError`, defined in one
  `core/errors.py`); catch at module supervisors; never bare `except:`.
- Logging: `logging` stdlib, one logger per module (`logging.getLogger(__name__)`),
  JSON lines format, levels — DEBUG dev detail, INFO fills/jobs, WARNING degradations
  and mode changes, ERROR failures, CRITICAL kill-switch.
- Every DB write goes through store/repo.py functions; every prompt lives in
  ailayer/prompts.py; every schedule interval and threshold comes from config — no
  magic numbers in logic files.
- Tests: new logic lands with its tests in the same milestone; fixtures deterministic.
- Docstrings: one-paragraph module docstring + docstrings on public functions; no
  redundant inline comments.
- Commits: one per Task ID, message `E4.T3: kill-switch watchdog and flatten`.
