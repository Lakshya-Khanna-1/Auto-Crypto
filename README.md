# Auto-Crypto Algorithmic Trading Platform

A production-ready, modular algorithmic trading platform built specifically for native deployment on Windows Server. It automates trade execution, ensures strict risk management, sends prompt Telegram notifications, hosts an elegant dark-theme control dashboard, and features a local AI advisory layer for operations analysis.

---

## 🏗️ Architecture & Component Overview

The codebase is organized into a modular monolith structure under the `tradecore/` package:

```text
auto-crypto-trader/
├── config/                  # Configuration YAML files
├── alembic/                 # SQLite database version history
├── tradecore/               # Main application source code
│   ├── app.py               # FastAPI server, WebSocket hub, and API routes
│   ├── core/                # Configuration schemas and application state
│   ├── store/               # SQLite DB schemas and data access repository
│   ├── strategy/            # Technical indicators and signal generators
│   ├── riskengine/          # Drawdown limits, exposure limits, and dog/killswitch
│   ├── execution/           # Spot execution adapters (Paper and Live)
│   ├── notifications/       # Telegram notification dispatcher
│   ├── scheduler/           # APScheduler background tasks coordinator
│   └── ailayer/             # LLM prompt orchestration and client connection
```

*   **`core/`**: Controls settings parsing (`config.py`) and global runtime mode state (`state.py`).
*   **`store/`**: Data access layer (`repo.py`) routing all trades, fills, and mode changes securely to an SQLite database.
*   **`strategy/`**: Holds modular strategies (like the ATR-filtered `ema_trend` trend follower).
*   **`riskengine/`**: Hard-stop safeguard controlling daily drawdowns, data feed staleness, position limits, and the crucial killswitch interlock.
*   **`execution/`**: Unifies order placement with the abstract `get_adapter(mode)` interface.
*   **`notifications/`**: Channels critical messages, fills, and reports to a configured Telegram chat.
*   **`scheduler/`**: Drives background task tick, polling fallbacks, watchdog guard, and AI operations.
*   **`ailayer/`**: Client interface connecting to Ollama, building reports, and annotating closed position executions.

---

## 🦾 Core Platform Features

1.  **Strict Risk Engine & Guardrails**: Automatically enforces position size calculations, max open position counts, daily and total drawdown safety limits, and max feed delay tolerances.
2.  **Double-Lock Killswitch & Watchdog**: Flat-lines exposing spots instantly if risk limits are violated, locking trading until an operator logs into the dashboard and types `RE-ARM` to authorize a reset.
3.  **Real-Time Dashboard**: Features 6 interactive panels rendering real-time equity growth curves, live position tracking, paginated trade history, execution signals, overall systems status, and AI analyst outputs.
4.  **Flexible Modes & Switch safeguards**: Supports seamless transitions between `PAPER` and `LIVE` trading. Mode changes check preflight interlock criteria (balance fetches, API keys, and paper trade history minimums), requiring manual operator overrides or explicit `GO-LIVE` type confirmation.
5.  **Local AI layer Integration**: Connects to the local Ollama server. Includes a daily operations reporting cron job (run at 00:15 UTC everyday) and real-time trade annotation explaining buy/sell logic in trade history records.

---

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.12+ (recommend using virtual environments)
- SQLite3
- [Ollama](https://ollama.com/) running locally (optional but required for AI features)

### Installation
1. Clone the repository and navigate to the project directory:
   ```powershell
   git clone <repo-url>
   cd "auto crypto trader"
   ```
2. Set up virtual environment and install dependencies:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Set your configuration values in `config/config.yaml`.
4. Apply database schema migrations:
   ```powershell
   .venv\Scripts\alembic upgrade head
   ```

### Running the Platform
Launch the server in development mode:
```powershell
.venv\Scripts\python -m tradecore
```
Open your browser and navigate to `http://127.0.0.1:9090/` to access the trading controller
(this redirects to the dashboard; the full path is `/dashboard/static/index.html`).

For persistent, always-on operation, use the NSSM Windows service instead of running this
directly — see `scripts/install_service.ps1` and `SETUP_GUIDE.md`.
