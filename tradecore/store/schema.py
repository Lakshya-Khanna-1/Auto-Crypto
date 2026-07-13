from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, MetaData, String, Table

metadata = MetaData()

# positions Table
positions = Table(
    "positions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("mode", String, nullable=False),
    Column("symbol", String, nullable=False),
    Column("side", String, nullable=False),
    Column("qty", Float, nullable=False),
    Column("entry_price", Float, nullable=False),
    Column("stop_price", Float, nullable=True),
    Column("opened_ts", String, nullable=False),
    Column("closed_ts", String, nullable=True),
    Column("exit_price", Float, nullable=True),
    Column("realized_pnl", Float, nullable=True),
    Column("fees_total", Float, nullable=True),
    Column("status", String, nullable=False),
)

# trades Table
trades = Table(
    "trades",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    sa_fk := Column("position_id", Integer, ForeignKey("positions.id"), nullable=True),
    Column("ts", String, nullable=False),
    Column("mode", String, nullable=False),
    Column("symbol", String, nullable=False),
    Column("side", String, nullable=False),
    Column("qty", Float, nullable=False),
    Column("price", Float, nullable=False),
    Column("fee", Float, nullable=False),
    Column("order_id", String, nullable=False),
    Column("strategy", String, nullable=True),
)

# equity_snapshots Table
equity_snapshots = Table(
    "equity_snapshots",
    metadata,
    Column("ts", String, primary_key=True),
    Column("mode", String, primary_key=True),
    Column("balance", Float, nullable=False),
    Column("equity", Float, nullable=False),
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
    Column("details_json", String, nullable=True),
    Column("positions_flattened", Integer, nullable=True),
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
    Column("confidence", Float, nullable=True),
    Column("risk_decision", String, nullable=True),
    Column("risk_reason", String, nullable=True),
)

# app_kv Table
app_kv = Table(
    "app_kv",
    metadata,
    Column("key", String, primary_key=True),
    Column("value", String, nullable=False),
)
