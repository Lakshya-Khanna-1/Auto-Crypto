# Handover — 2026-07-13 — after M5

## Position
Completed milestones: M1..M5
Current milestone: M6 (Dashboard & notifications) — not started
Next exact task: E6.T1 Implement Dashboard.md HTTP endpoints and WebSockets

## Repo state
Branch: main @ 3ef84f7; working tree clean: no (modified: tests/unit/test_risk.py, tradecore/__main__.py, tradecore/app.py, tradecore/execution/adapter.py, tradecore/riskengine/engine.py, tradecore/riskengine/killswitch.py, tradecore/store/repo.py, tradecore/store/schema.py; untracked: alembic/versions/4e9fc46b3a13_align_schema_to_spec.py, tests/integration/, tradecore/execution/live.py, tradecore/execution/paper.py, tradecore/execution/tracker.py, tradecore/scheduler/)
Files currently mid-edit: none

## Environment
Installed deps changed since last handover: none
Env vars required now: TRADECORE_CONFIG (optional, path to override config)
Config values changed from defaults: none

## Data & DB
Alembic revision: 4e9fc46b3a13 (= head: yes)
Backfill state: BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT historic candles
Paper account state: balance 10000.0, open positions 0

## Issues
Known bugs: none
Open TODOs: none
Current blockers: none
Assumptions currently in force: SQLite DB local persistence, paper simulation uses config.yaml settings

## Continue
Commands to resume work:
- Activate venv: `.\.venv\Scripts\activate`
- Run selfcheck: `.\.venv\Scripts\python -m tradecore --selfcheck`
- Run test suite: `.\.venv\Scripts\pytest`
- Start server: `.\.venv\Scripts\python -m tradecore`
