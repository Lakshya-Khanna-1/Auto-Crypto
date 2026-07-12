# TechStack.md

All choices are final. Pin exact versions in `requirements.txt` at Milestone M1 using
the latest stable release at implementation time; never use unpinned dependencies.

## Runtime
| Component | Choice | Why |
|-----------|--------|-----|
| Language | Python 3.12 (64-bit, python.org installer) | Ecosystem for trading libs; 3.12 is fast and stable on Windows |
| Process mgmt | NSSM 2.24+ | Turns any exe into a Windows service with auto-restart and log rotation; no Docker needed |
| Async runtime | asyncio (stdlib) | Single-process concurrency for feeds + web + scheduler |

## Core libraries
| Purpose | Library | Why chosen / rules |
|---------|---------|--------------------|
| Exchange connectivity | `ccxt` | Industry standard, 100+ exchanges, unified API. NEVER call exchange REST endpoints directly. |
| Backtesting | `vectorbt` | Fast vectorized backtests + built-in metrics. Fallback if install fails on Windows: `backtesting.py`. |
| Dataframes | `pandas` + `pyarrow` | Candle manipulation; pyarrow for Parquet IO |
| Web framework | `FastAPI` + `uvicorn` | REST + WebSocket + static file serving in one process |
| Scheduler | `APScheduler` | Cron-style in-process jobs; no external scheduler |
| DB | `sqlite3` (stdlib) via `SQLAlchemy` (core, not ORM-heavy) | Zero-admin persistence; SQLAlchemy for schema migrations via `alembic` |
| Retry | `tenacity` | Declarative backoff for network calls |
| Config | `pydantic-settings` + YAML (`pyyaml`) | Typed, validated config; env-var overrides |
| Telegram | `python-telegram-bot` | Mature, async, handles both alerts and inbound commands |
| Ollama client | `ollama` (official Python client) | Local LLM calls |
| Technical indicators | `pandas-ta` | EMA/ATR/RSI without hand-rolled math. Fallback: compute EMA/ATR directly with pandas `ewm` (allowed, trivial). |
| Testing | `pytest`, `pytest-asyncio`, `respx` | Unit + async tests; respx mocks HTTP |
| Lint/format | `ruff` (lint + format) | One tool, fast on Windows |

## Frontend (dashboard)
**No build toolchain.** Plain HTML + vanilla JS + Chart.js and Tailwind via CDN, served
as static files by FastAPI. Rationale: zero Node/npm on the server, trivially deployable,
sufficient for a single-user dashboard. See Dashboard.md for exact pages/components.

## Explicitly forbidden
Docker, docker-compose, Redis, PostgreSQL, Celery, RabbitMQ, Node build tools, React/Vue
build pipelines, Kubernetes, custom exchange HTTP clients, custom backtest math.
