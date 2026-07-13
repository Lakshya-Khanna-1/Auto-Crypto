from datetime import UTC, datetime

import pandas as pd
import pytest
from sqlalchemy import select

from tradecore.core.config import get_settings
from tradecore.core.state import get_state
from tradecore.scheduler.jobs import strategy_tick_job
from tradecore.store import candles as candle_store
from tradecore.store.db import get_engine
from tradecore.store.repo import get_open_positions
from tradecore.store.schema import equity_snapshots, positions, trades


@pytest.fixture(autouse=True)
def temp_environment(monkeypatch, tmp_path):
    from sqlalchemy import create_engine

    from tradecore.store import db as store_db
    from tradecore.store.schema import metadata

    # 1. Sandbox the database engine
    test_db_url = f"sqlite:///{tmp_path / 'test_trading.db'}"
    test_engine = create_engine(test_db_url, connect_args={"timeout": 30})
    metadata.create_all(test_engine)

    monkeypatch.setattr(store_db, "engine", test_engine)
    monkeypatch.setattr(store_db, "get_engine", lambda: test_engine)

    # 2. Sandbox the Parquet candles path
    from pathlib import Path

    from tradecore.store import candles as candle_store

    def mock_get_parquet_path(symbol: str, timeframe: str) -> Path:
        symbol_sanitized = symbol.upper().replace("/", "-")
        return tmp_path / "candles" / symbol_sanitized / f"{timeframe}.parquet"

    monkeypatch.setattr(candle_store, "get_parquet_path", mock_get_parquet_path)

    # Clear runtime state caching
    state = get_state()
    state._kill_switch_active = False
    state.reset_rejections()
    state._last_ticker_times.clear()
    state._last_ticker_prices.clear()

    yield


@pytest.mark.asyncio
async def test_paper_trading_end_to_end_flow():
    state = get_state()
    settings = get_settings()
    symbol = "BTC/USDT"
    timeframe = settings.trading.timeframe

    # Set initial mode to paper
    settings.trading.mode = "paper"
    state._current_mode = settings.trading.mode

    # Override strategy settings to match seeded data length
    settings.strategy.ema_fast = 9
    settings.strategy.ema_slow = 21
    settings.strategy.atr_period = 14

    # Initialize mock ticker prices in state to make ticks fresh
    now_ts = datetime.now(UTC).timestamp()
    state.update_ticker(symbol, 10000.0, now_ts)
    for sym in settings.trading.symbols:
        if sym != symbol:
            state.update_ticker(sym, 1.0, now_ts)

    # 1. Seed historical candle series generating a golden cross (Buy/Long)
    # Slow EMA = 21, Fast EMA = 9
    prices = [200.0] * 30 + [100.0] * 10 + [350.0]

    # Generate OHLCV DataFrame
    ts_start = int((now_ts - len(prices) * 3600) * 1000)
    rows = []
    for idx, p in enumerate(prices):
        rows.append(
            {
                "ts": ts_start + idx * 3600000,
                "open": p,
                "high": p + 1.0,
                "low": p - 1.0,
                "close": p,
                "volume": 10.0,
            }
        )
    df = pd.DataFrame(rows)
    candle_store.append(symbol, timeframe, df)

    # Update ticker to match last closed candle price
    state.update_ticker(symbol, 350.0, now_ts)

    # 2. Trigger Strategy Evaluator Job (Long entry)
    await strategy_tick_job()

    # 3. Verify Database Trades and Positions tables
    engine = get_engine()
    with engine.connect() as conn:
        pos_rows = conn.execute(select(positions)).fetchall()
        trade_rows = conn.execute(select(trades)).fetchall()
        snapshot_rows = conn.execute(select(equity_snapshots)).fetchall()

    # Verify a new position is opened
    assert len(pos_rows) == 1
    pos_data = pos_rows[0]._mapping
    assert pos_data["symbol"] == symbol
    assert pos_data["side"] == "long"
    assert pos_data["status"] == "open"
    assert pos_data["qty"] > 0.0
    assert pos_data["entry_price"] > 340.0
    assert pos_data["stop_price"] is not None
    assert pos_data["closed_ts"] is None
    assert pos_data["exit_price"] is None

    # Verify trades table logs the buy fill
    assert len(trade_rows) == 1
    trade_data = trade_rows[0]._mapping
    assert trade_data["symbol"] == symbol
    assert trade_data["side"] == "buy"
    assert trade_data["qty"] == pos_data["qty"]
    assert trade_data["position_id"] == pos_data["id"]

    # Verify that an equity snapshot was logged immediately at fill
    assert len(snapshot_rows) == 1
    assert snapshot_rows[0]._mapping["mode"] == "paper"
    assert snapshot_rows[0]._mapping["balance"] < 10000.0  # deducted fee/notional
    assert snapshot_rows[0]._mapping["equity"] == pytest.approx(10000.0, abs=10.0)

    # 4. Seed falling candles to trigger a death cross (Flat/Exit)
    exit_prices = [250.0] * 5 + [100.0] * 3
    ts_start_exit = ts_start + len(prices) * 3600000
    exit_rows = []
    for idx, p in enumerate(exit_prices):
        exit_rows.append(
            {
                "ts": ts_start_exit + idx * 3600000,
                "open": p,
                "high": p + 1.0,
                "low": p - 1.0,
                "close": p,
                "volume": 10.0,
            }
        )
    df_exit = pd.DataFrame(exit_rows)
    candle_store.append(symbol, timeframe, df_exit)

    # Update ticker price to match last candle price
    state.update_ticker(symbol, 100.0, datetime.now(UTC).timestamp())

    # 5. Trigger Strategy Evaluator Job again to execute Flat
    await strategy_tick_job()

    # 6. Verify Database states (Position updated in-place to closed)
    with engine.connect() as conn:
        pos_after = conn.execute(select(positions)).fetchall()
        trade_after = conn.execute(select(trades)).fetchall()
        snapshot_after = conn.execute(select(equity_snapshots)).fetchall()

    # Verify positions count is still 1, but status is closed
    assert len(pos_after) == 1
    pos_data_after = pos_after[0]._mapping
    assert pos_data_after["status"] == "closed"
    assert pos_data_after["closed_ts"] is not None
    assert pos_data_after["exit_price"] == pytest.approx(100.0, abs=1.5)
    # Realized PnL is negative because the exit price (100) is less than entry price (~350)
    assert pos_data_after["realized_pnl"] < 0.0

    # Verify a new flat close trade row is inserted
    assert len(trade_after) == 2
    trade_sell = next(t for t in trade_after if t._mapping["side"] == "sell")
    assert trade_sell._mapping["symbol"] == symbol
    assert trade_sell._mapping["qty"] == pos_data_after["qty"]
    assert trade_sell._mapping["position_id"] == pos_data_after["id"]

    # Verify a second equity snapshot is logged on the exit fill
    assert len(snapshot_after) >= 2


@pytest.mark.asyncio
async def test_startup_reconciliation_recovery_flow():
    # Simulate database having one open position at startup
    state = get_state()
    settings = get_settings()

    settings.trading.mode = "paper"
    state._current_mode = settings.trading.mode
    symbol = "BTC/USDT"

    # Seed open position directly into the DB
    from sqlalchemy import insert

    from tradecore.store.schema import positions

    engine = get_engine()
    now_str = datetime.now(UTC).isoformat()
    with engine.begin() as conn:
        conn.execute(
            insert(positions).values(
                mode="paper",
                symbol=symbol,
                side="long",
                qty=2.5,
                entry_price=60000.0,
                stop_price=57000.0,
                opened_ts=now_str,
                closed_ts=None,
                exit_price=None,
                realized_pnl=None,
                fees_total=10.0,
                status="open",
            )
        )

    # Reconcile manually using the database repository
    open_pos = get_open_positions("paper")
    assert len(open_pos) == 1
    assert open_pos[0]["symbol"] == symbol
    assert open_pos[0]["qty"] == 2.5
    assert open_pos[0]["status"] == "open"
