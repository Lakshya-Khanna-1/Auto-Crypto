# Handover — 2026-07-13 — after M9

## Position
Completed milestones: M1..M9 (100% complete)
Current milestone: None (Milestone plan successfully finished)
Next steps: Production paper trading evaluation followed by live deployment.

## Repo state
Branch: main; working tree clean: yes
Files currently mid-edit: none

## Environment
Installed deps changed since last handover: `lightgbm`, `scikit-learn`
Env vars required now: OLLAMA_HOST, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (optional)
Config values changed from defaults: none

## Data & DB
Alembic revision: 24048a0e2890 (= head: yes)
Backfill state: BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT backfilled
Paper account state: balance 10000.0, open positions 0
Model state: LightGBM classification model trained and saved as `data/models/lgbm_latest.txt`

## Issues
Known bugs: none
Open TODOs: none
Current blockers: none
Assumptions / Pending Checkpoints:
- E7.T5 manual testnet round-trip check skipped at user request; logged as pending checkpoint for future key injection.
- ML Strategy activation gate was evaluated over the 90 days held-out period. Since EMA out-performed ML on SOL/USDT (16.80% vs 0.00%), the active strategy is kept as `ema_trend` in `config/config.yaml` for production safety.

## Continue
Commands to resume work:
- run_platform.bat (Runs trading server for 30 days, retrains model, restarts loop)
- .venv\Scripts\activate
- python -m tradecore --selfcheck
- pytest
