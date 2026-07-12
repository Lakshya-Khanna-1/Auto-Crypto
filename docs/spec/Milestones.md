# Milestones.md

Execute strictly in order. After each milestone: run the full self-verification
checklist (TestingPlan.md §2), fix until green, THEN stop at the manual checkpoint and
wait for user approval. On approval, be ready to emit `Handover.md`
(HandoverSpecification.md) before starting the next milestone.

---

## M1 — Skeleton & core
**Build:** repo per FolderStructure.md; core/ (config, logging, events, state); empty
FastAPI app with `/api/status` stub; alembic init with full schema from Database.md;
`--selfcheck` flag; ruff + pytest wired; scripts/install_service.ps1 written (not run).
**Accept:** selfcheck exits 0 on a clean machine with empty .env; all tables exist;
`ruff` and `pytest` green (config + events unit tests exist).
**Manual checkpoint:** user runs selfcheck on the server, confirms Python/venv works.

## M2 — Data pipeline & storage
**Build:** datafeed/, store/candles.py, scripts/backfill.py, candle_sync + ticker jobs,
staleness flag.
**Accept:** backfill pulls 2 years of 1h BTC/USDT + ETH/USDT with zero gap (automated
gap check in the script's exit summary); candle_sync keeps Parquet current across a
15-min observed window; ws→polling fallback proven by unit test with mocked failures.
**Manual checkpoint:** user runs backfill, sees gap report = 0.

## M3 — Backtester & baseline strategy
**Build:** strategy/base.py, ema_trend.py, backtest/runner.py, run_backtest.py incl.
--walk-forward.
**Accept:** 2-year backtests on both symbols complete; ≥10 trades each; JSON reports
saved; strategy unit tests pass on fixtures (3 known crossovers detected exactly).
**Manual checkpoint:** user reviews backtest metrics (README reminds: gate is machinery,
not profitability).

## M4 — Risk Engine & kill-switch
**Build:** riskengine/ complete per RiskManagement.md; signals + killswitch_events
persistence.
**Accept:** all RiskManagement.md §5 tests pass; watchdog triggers correctly in
integration test; exits never blocked.
**Manual checkpoint:** user triggers kill-switch via a temporary CLI and sees flatten
in logs (paper positions from a seeded state).

## M5 — Paper trading end-to-end
**Build:** execution/ (adapter ABC, PaperAdapter, tracker), strategy_tick job,
equity snapshots, crash-recovery startup sequence.
**Accept:** integration test: FakeFeed drives a crossover → paper fill → position →
exit → correct P&L rows; restart test reloads open positions; app runs 24 h on the
server in paper mode without unhandled exceptions (user-observed).
**Manual checkpoint:** 24-h paper soak test approved by user.

## M6 — Dashboard & notifications
**Build:** full Dashboard.md (API + static UI + WebSocket) and Notifications.md.
**Accept:** every endpoint in Dashboard.md §3 implemented and covered by an integration
test; UI shows live equity/positions/history; Telegram /status and /kill work.
**Manual checkpoint:** user clicks through every panel, tests /kill from phone.

## M7 — Live adapter & mode switch
**Build:** LiveAdapter, reconcile-on-startup, switch_mode with all interlocks,
mode UI modal, paper-reset endpoint.
**Accept:** sandbox-marked tests pass against exchange testnet; preflight endpoint
returns correct check states; going live blocked without keys/paper-history; LIVE→PAPER
instant; mode_changes audited.
**Manual checkpoint (extended):** user provides testnet keys, performs a full
paper→live(testnet)→paper cycle from the dashboard, verifies one tiny testnet order
round-trips. **Real live keys are the user's decision alone, after
`require_paper_days` of paper trading.**

## M8 — AI layer & polish
**Build:** ailayer/ per AILayer.md, annotation migration, daily report job, dashboard
panel 6, final README for the repo, ops runbook check.
**Accept:** report generates from a seeded day of data; Ollama-down degrades
gracefully (integration test with unreachable host); full self-verification green.
**Manual checkpoint:** user reads a real daily report; project handover complete.

## M9 — ML strategy (mandatory)
**Prereq:** M1–M8 approved AND M2 backfill covers all configured symbols.
**Build:** everything in MLStrategy.md — feature builder, training script, MLStrategy
class, backtest comparison report.
**Accept:** `python scripts/train_model.py` produces `data/models/lgbm_latest.txt` with
a walk-forward validation report; backtest comparison vs ema_trend runs on all symbols;
MLStrategy passes the same integration tests as ema_trend; strategy switch is one
config line.
**Manual checkpoint:** user reviews the walk-forward report and DECIDES whether to
activate ml_lgbm in paper. The spec forbids activating it if walk-forward performance
is worse than ema_trend.
