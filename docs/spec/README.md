# CryptoTrader Blueprint — Master Index

This package is the **complete, decision-final specification** for building a crypto
algorithmic trading platform that runs on a single Windows Server without Docker.

**Audience:** an implementation agent (any coding AI — see AGENT_INSTRUCTIONS.md for the agent operating procedure) that follows instructions literally
and must never make architectural decisions. All decisions are already made in these
documents. If a document does not specify something, choose the simplest option that
satisfies the acceptance criteria — do NOT invent features.

---

## Non-negotiable global rules

1. **No Docker.** Everything runs natively on Windows Server. Services are managed with NSSM.
2. **Modular monolith.** One Python application (`tradecore`) + one web dashboard served by the same process. NOT microservices.
3. **LLMs never make trading decisions.** They only summarize, annotate, and report. Deterministic strategies decide; the Risk Engine can veto everything.
4. **Paper-first.** Live trading is unlocked only through the mode-switch interlocks defined in `Configuration.md` and `TradingEngine.md`.
5. **Reuse libraries** (ccxt, pandas, FastAPI, APScheduler, vectorbt). Never hand-roll exchange connectivity, backtesting math, or web servers.
6. **One code path for paper and live.** Only the `ExecutionAdapter` implementation differs. See `TradingEngine.md §4`.
7. Follow `Milestones.md` in order. Never skip. Stop only at the manual checkpoints listed there.

## Reading order for the implementation model

| # | Document | Purpose |
|---|----------|---------|
| 1 | `Architecture.md` | System shape, modules, data flow |
| 2 | `TechStack.md` | Exact libraries and versions policy |
| 3 | `FolderStructure.md` | Repository layout (authoritative) |
| 4 | `Configuration.md` | Config file, env vars, **paper/live mode switch** |
| 5 | `Database.md` | SQLite schema + Parquet market-data store |
| 6 | `DataPipeline.md` | Market data ingestion & storage |
| 7 | `Backtesting.md` | Backtester and baseline strategy validation |
| 8 | `TradingEngine.md` | Strategy runner, ExecutionAdapters, order lifecycle |
| 9 | `RiskManagement.md` | Risk Engine and kill-switch (highest-priority module) |
| 10 | `Dashboard.md` | Web dashboard + full API contract |
| 11 | `Notifications.md` | Telegram bot alerts and commands |
| 12 | `AILayer.md` | Ollama models, roles, prompts (built last) |
| 13 | `WindowsDeployment.md` | NSSM services, Ollama install, ops runbook |
| 14 | `TestingPlan.md` | Test strategy and self-verification checklist |
| 15 | `Milestones.md` | Build order, acceptance criteria, checkpoints |
| 16 | `TaskList.md` | Hierarchical task breakdown with IDs |
| 17 | `CodingStandards.md` | Style, error handling, logging conventions |
| 18 | `HandoverSpecification.md` | Format of Handover.md between chat sessions |
| 19 | `MLStrategy.md` | Optional ML strategy (LightGBM), trained locally at M9 |

## Glossary (minimal)

- **Mode** — `backtest` | `paper` | `live`. Global runtime state. See `Configuration.md §3`.
- **ExecutionAdapter** — the only component that differs between paper and live.
- **Kill-switch** — deterministic halt that flattens positions and blocks new orders.
- **Flatten** — close all open positions at market.
- **TDS drag** — India's 1% tax deducted at source per crypto trade; motivates low-frequency strategies.
