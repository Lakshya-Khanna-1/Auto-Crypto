# TestingPlan.md

## 1. Test layers
- **Unit** (`tests/unit/`): pure logic — sizing, strategy signals on synthetic candle
  fixtures, config validation, staleness math, Parquet dedupe. No network. Target ≥ 80%
  coverage on riskengine/, strategy/, execution/tracker.py.
- **Integration** (`tests/integration/`): full app in PAPER mode with a `FakeFeed`
  (deterministic candle/tick source) — assert: signal → risk approval → paper fill →
  DB rows → /api/status reflects P&L; kill-switch flatten end-to-end; mode-switch
  interlocks (live blocked without keys); crash-recovery (restart app, positions reload).
- **Live-adapter tests**: against exchange **testnet/sandbox** only (ccxt
  `set_sandbox_mode(True)`), marked `@pytest.mark.sandbox`, skipped in CI/normal runs,
  executed at the M7 manual checkpoint.

## 2. Self-verification checklist (run after EVERY milestone; all must pass before stopping)
```
ruff check . && ruff format --check .
pytest -q                              # unit + integration
python -m tradecore --selfcheck        # implement: boots app, checks config, DB migration
                                       # current, dashboard route 200s, then exits 0
alembic current                        # matches head
```
If anything fails: fix, re-run all, repeat until green. Only then present the manual
checkpoint from Milestones.md.

## 3. Fixtures
`tests/fixtures/candles_btc_1h.parquet` — 500 synthetic candles engineered to contain
exactly 3 EMA crossovers (document the generator script in tests/fixtures/make_fixtures.py).
