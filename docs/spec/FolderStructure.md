# FolderStructure.md

Authoritative repository layout. The implementation model must create exactly this
structure. New files are allowed only inside existing packages and must follow the
naming conventions shown.

```
cryptotrader/
├── README.md                     # short project readme (generated at M1)
├── requirements.txt              # pinned deps
├── requirements-dev.txt          # pytest, ruff, etc.
├── pyproject.toml                # ruff config, project metadata
├── config/
│   ├── config.yaml               # main config (committed with safe defaults, paper mode)
│   └── config.example.yaml       # documented template
├── .env.example                  # env var template (never commit real .env)
├── data/                         # runtime data (gitignored)
│   ├── candles/                  # Parquet: {exchange}/{symbol}/{timeframe}.parquet
│   ├── db/tradecore.sqlite3      # state DB
│   └── logs/                     # rotating log files
├── scripts/
│   ├── install_service.ps1       # NSSM install commands (see WindowsDeployment.md)
│   ├── backfill.py               # CLI: historical candle backfill
│   └── run_backtest.py           # CLI: run backtest per Backtesting.md
├── tradecore/
│   ├── __main__.py               # entrypoint: python -m tradecore
│   ├── app.py                    # wiring: build modules, start FastAPI + scheduler
│   ├── core/
│   │   ├── config.py             # pydantic settings, YAML+env loading
│   │   ├── events.py             # asyncio pub/sub event bus
│   │   ├── state.py              # TradingMode enum, global runtime state
│   │   └── logging.py            # structured logging setup
│   ├── datafeed/
│   │   ├── feed.py               # ccxt candle fetch, ticker stream, staleness tracking
│   │   └── models.py             # Candle, Ticker dataclasses
│   ├── store/
│   │   ├── db.py                 # SQLAlchemy engine, session helpers
│   │   ├── schema.py             # tables per Database.md
│   │   ├── repo.py               # typed repository functions (save_trade, get_positions...)
│   │   └── candles.py            # Parquet read/write/append
│   ├── strategy/
│   │   ├── base.py               # Strategy ABC: on_candle(df) -> Signal|None
│   │   └── ema_trend.py          # baseline strategy per TradingEngine.md §3
│   ├── riskengine/
│   │   ├── engine.py             # approve(signal) -> ApprovedOrder | Rejection
│   │   ├── killswitch.py         # watchdog + kill-switch per RiskManagement.md
│   │   └── sizing.py             # position sizing math
│   ├── execution/
│   │   ├── adapter.py            # ExecutionAdapter ABC + order/position dataclasses
│   │   ├── paper.py              # PaperAdapter
│   │   ├── live.py               # LiveAdapter (ccxt)
│   │   └── tracker.py            # position/PnL tracking shared by both adapters
│   ├── backtest/
│   │   └── runner.py             # vectorbt wrapper per Backtesting.md
│   ├── dashboard/
│   │   ├── api.py                # REST routes per Dashboard.md §3
│   │   ├── ws.py                 # WebSocket push
│   │   └── static/
│   │       ├── index.html
│   │       ├── app.js
│   │       └── style.css
│   ├── notifier/
│   │   └── telegram.py           # alerts + /status /kill /pause commands
│   ├── ailayer/
│   │   ├── client.py             # Ollama wrapper with timeouts
│   │   ├── reports.py            # daily performance report
│   │   └── prompts.py            # all prompt templates (only file with prompts)
│   └── scheduler/
│       └── jobs.py               # APScheduler job definitions
├── tests/
│   ├── unit/                     # mirrors tradecore/ package names
│   └── integration/              # end-to-end paper-mode tests
└── alembic/                      # DB migrations
```

Naming: modules `snake_case`, classes `PascalCase`, one class of responsibility per file.
