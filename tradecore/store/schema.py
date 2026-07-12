from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table

metadata = MetaData()

# trades Table
trades = Table(
    "trades",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("symbol", String, nullable=False),
    Column("side", String, nullable=False),
    Column("mode", String, nullable=False),
    Column("entry_time", DateTime, nullable=False),
    Column("entry_price", Float, nullable=False),
    Column("entry_qty", Float, nullable=False),
    Column("exit_time", DateTime, nullable=True),
    Column("exit_price", Float, nullable=True),
    Column("exit_qty", Float, nullable=True),
    Column("pnl", Float, nullable=True),
    Column("pnl_pct", Float, nullable=True),
    Column("status", String, nullable=False),
    Column("exchange_order_id", String, nullable=True),
    Column("notes", String, nullable=True),
)

# positions Table
positions = Table(
    "positions",
    metadata,
    Column("symbol", String, primary_key=True),
    Column("side", String, nullable=False),
    Column("mode", String, nullable=False),
    Column("qty", Float, nullable=False),
    Column("entry_price", Float, nullable=False),
    Column("entry_time", DateTime, nullable=False),
    Column("unrealized_pnl", Float, nullable=False),
    Column("stop_loss", Float, nullable=True),
    Column("take_profit", Float, nullable=True),
)

# equity_snapshots Table
equity_snapshots = Table(
    "equity_snapshots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime, nullable=False),
    Column("mode", String, nullable=False),
    Column("balance", Float, nullable=False),
    Column("equity", Float, nullable=False),
    Column("drawdown_pct", Float, nullable=False),
)

# mode_changes Table
mode_changes = Table(
    "mode_changes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime, nullable=False),
    Column("from_mode", String, nullable=False),
    Column("to_mode", String, nullable=False),
    Column("source", String, nullable=False),
    Column("override_used", Integer, nullable=False),  # 0 or 1 (boolean representation)
)

# killswitch_events Table
killswitch_events = Table(
    "killswitch_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime, nullable=False),
    Column("reason", String, nullable=False),
    Column("resolved", Integer, nullable=False),  # 0 or 1
    Column("resolved_time", DateTime, nullable=True),
)

# signals Table
signals = Table(
    "signals",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime, nullable=False),
    Column("symbol", String, nullable=False),
    Column("indicator_value", Float, nullable=True),
    Column("signal_type", String, nullable=False),
    Column("executed", Integer, nullable=False),  # 0 or 1
)

# app_kv Table
app_kv = Table(
    "app_kv",
    metadata,
    Column("key", String, primary_key=True),
    Column("value", String, nullable=False),
)
