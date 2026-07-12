# TaskList.md

Hierarchy: Epic → Task → Subtask. IDs are stable references (E{n}.T{n}.S{n}).
Priority P1 (blocking) / P2 (normal). Difficulty S/M/L. Deps by ID.
Verification: U=unit test, I=integration test, C=selfcheck, M=manual checkpoint.
Epics map 1:1 to Milestones M1–M8; acceptance criteria live in Milestones.md.

## E1 Skeleton & core (M1)
- E1.T1 Repo + tooling — P1 S — deps: none — files: pyproject.toml, requirements*.txt — verify: C
  - S1 create FolderStructure.md layout; S2 ruff config; S3 pytest config
- E1.T2 core.config pydantic settings (YAML+env) — P1 M — deps E1.T1 — files core/config.py — verify U
- E1.T3 core.logging structured logs + rotation — P1 S — deps E1.T2 — verify C
- E1.T4 core.events asyncio pub/sub — P1 M — deps E1.T1 — verify U
- E1.T5 core.state TradingMode + runtime state — P1 S — deps E1.T2 — verify U
- E1.T6 store.db + schema.py + alembic baseline — P1 M — deps E1.T2 — verify C
- E1.T7 app.py wiring + FastAPI stub + --selfcheck — P1 M — deps E1.T3–T6 — verify C,M

## E2 Data pipeline (M2)
- E2.T1 datafeed.feed ccxt candle fetch + retries — P1 M — deps E1 — verify U
- E2.T2 store.candles Parquet append/dedupe/read — P1 M — deps E1.T6 — verify U
- E2.T3 scripts/backfill.py with gap report — P1 M — deps E2.T1,T2 — verify M
- E2.T4 ticker ws + polling fallback + staleness — P1 M — deps E2.T1 — verify U
- E2.T5 scheduler candle_sync + ticker_poll jobs — P1 S — deps E2.T1–T4 — verify I

## E3 Backtesting (M3)
- E3.T1 strategy.base ABC — P1 S — deps E1 — verify U
- E3.T2 strategy.ema_trend — P1 M — deps E3.T1 — verify U (fixture crossovers)
- E3.T3 backtest.runner vectorbt wrapper — P1 M — deps E3.T2,E2.T2 — verify I
- E3.T4 run_backtest.py CLI + walk-forward — P2 S — deps E3.T3 — verify M

## E4 Risk engine (M4)
- E4.T1 sizing.py — P1 S — deps E1 — verify U
- E4.T2 engine.approve pipeline — P1 M — deps E4.T1 — verify U (every rejection reason)
- E4.T3 killswitch watchdog + flatten + re-arm — P1 L — deps E4.T2 — verify U,I,M
- E4.T4 signals/killswitch_events persistence — P1 S — deps E1.T6 — verify U

## E5 Paper trading (M5)
- E5.T1 execution.adapter dataclasses + ABC — P1 S — deps E1 — verify U
- E5.T2 execution.tracker positions/PnL — P1 M — deps E5.T1 — verify U
- E5.T3 PaperAdapter fills w/ fee+slippage — P1 M — deps E5.T2,E2.T4 — verify U
- E5.T4 strategy_tick job (feed→strategy→risk→adapter) — P1 L — deps E3,E4,E5.T3 — verify I
- E5.T5 equity_snapshot job + drawdown HWM upkeep — P1 S — deps E5.T2 — verify U
- E5.T6 crash-recovery startup sequence — P1 M — deps E5.T4 — verify I
- E5.T7 24-h soak — P1 — verify M

## E6 Dashboard & notifier (M6)
- E6.T1 REST API all routes (Dashboard.md §3) — P1 L — deps E5 — verify I
- E6.T2 WebSocket push + client fallback — P1 M — deps E6.T1 — verify I
- E6.T3 static UI panels 1–5 + header + modals — P1 L — deps E6.T1 — verify M
- E6.T4 CSV export — P2 S — deps E6.T1 — verify I
- E6.T5 notifier.telegram outbound — P1 M — deps E1 — verify U (mocked)
- E6.T6 telegram inbound commands — P1 M — deps E6.T5 — verify M
- E6.T7 optional password gate for non-localhost — P2 S — deps E6.T1 — verify U

## E7 Live & mode switch (M7)
- E7.T1 LiveAdapter (place/poll/precision/min-notional) — P1 L — deps E5.T1 — verify sandbox tests
- E7.T2 reconcile-on-startup — P1 M — deps E7.T1 — verify sandbox
- E7.T3 switch_mode + interlocks + preflight endpoint — P1 L — deps E7.T1,E6.T1 — verify I
- E7.T4 mode modal UI + paper reset — P1 M — deps E7.T3 — verify M
- E7.T5 testnet round-trip — P1 — verify M

## E8 AI layer (M8)
- E8.T1 ailayer.client w/ timeout + degradation — P1 M — deps E1 — verify U
- E8.T2 daily report job + storage + panel 6 + Telegram — P1 M — deps E8.T1,E6 — verify I,M
- E8.T3 trade annotation + migration — P2 S — deps E8.T1 — verify U
- E8.T4 final README + runbook verification — P1 S — verify M

## E9 ML strategy (M9, mandatory)
- E9.T1 feature builder (MLStrategy.md §2) — P2 M — deps E2 — verify U (deterministic fixture features)
- E9.T2 label builder + dataset assembly — P2 M — deps E9.T1 — verify U
- E9.T3 scripts/train_model.py w/ walk-forward CV + report — P1 L — deps E9.T2 — verify M
- E9.T4 strategy/ml_lgbm.py MLStrategy class — P1 M — deps E9.T3,E3.T1 — verify U,I
- E9.T5 backtest comparison ema_trend vs ml_lgbm all symbols — P1 M — deps E9.T4 — verify M
