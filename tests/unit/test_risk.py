from datetime import UTC, datetime

import pytest
from sqlalchemy import insert, select

from tradecore.core.config import get_settings
from tradecore.core.state import get_state
from tradecore.execution.adapter import Signal
from tradecore.riskengine.engine import approve
from tradecore.riskengine.killswitch import rearm_killswitch, run_watchdog
from tradecore.riskengine.sizing import calculate_position_size
from tradecore.store.db import get_engine
from tradecore.store.repo import set_kv
from tradecore.store.schema import app_kv, killswitch_events, positions, signals


class MockAdapter:
    def __init__(self, raise_flatten_error=False, raise_place_error=False):
        self.cancel_called = False
        self.flatten_called = False
        self.placed_orders = []
        self.raise_flatten_error = raise_flatten_error
        self.raise_place_error = raise_place_error

    async def cancel_all(self):
        self.cancel_called = True

    async def flatten(self, symbol=None):
        if self.raise_flatten_error:
            raise Exception("Exchange down")
        self.flatten_called = True

    async def place(self, order):
        if self.raise_place_error:
            raise Exception("Order failed")
        self.placed_orders.append(order)


@pytest.fixture(autouse=True)
def clean_db():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(app_kv.delete())
        conn.execute(signals.delete())
        conn.execute(killswitch_events.delete())
        conn.execute(positions.delete())

    state = get_state()
    state._kill_switch_active = False
    state.reset_rejections()
    state._last_ticker_times.clear()
    state._last_ticker_prices.clear()
    yield


# ==========================================
# 1. Sizing Tests (re-added for completeness)
# ==========================================


def test_sizing_normal():
    qty = calculate_position_size(
        equity=10000.0,
        entry_price=100.0,
        stop_price=90.0,
        risk_per_trade_pct=1.0,
        max_total_exposure_pct=30.0,
        current_exposure=0.0,
    )
    assert qty == pytest.approx(10.0)


def test_sizing_capped_by_exposure():
    qty = calculate_position_size(
        equity=10000.0,
        entry_price=100.0,
        stop_price=90.0,
        risk_per_trade_pct=5.0,
        max_total_exposure_pct=30.0,
        current_exposure=2000.0,
    )
    assert qty == pytest.approx(10.0)


def test_sizing_under_min_notional():
    qty = calculate_position_size(
        equity=1000.0,
        entry_price=100.0,
        stop_price=50.0,
        risk_per_trade_pct=0.5,
        max_total_exposure_pct=30.0,
        current_exposure=0.0,
        min_notional=15.0,
    )
    assert qty == 0.0


def test_sizing_invalid_prices():
    assert (
        calculate_position_size(
            equity=10000.0,
            entry_price=100.0,
            stop_price=105.0,
            risk_per_trade_pct=1.0,
            max_total_exposure_pct=30.0,
            current_exposure=0.0,
        )
        == 0.0
    )


# ==========================================
# 2. Risk Engine Rejection Pipeline Tests
# ==========================================


def test_approve_killswitch_active():
    state = get_state()
    state.set_kill_switch(True)

    sig = Signal(symbol="BTC/USDT", side="long", confidence=1.0, reason="cross")
    approved, reason, order = approve(sig)
    assert approved is False
    assert reason == "killswitch_active"


def test_approve_data_feed_stale():
    state = get_state()
    # Cache ticker but make timestamp very stale (e.g. 10 hours ago)
    state.update_ticker("BTC/USDT", 100.0, datetime.now(UTC).timestamp() - 36000.0)

    sig = Signal(symbol="BTC/USDT", side="long", confidence=1.0, reason="cross")
    approved, reason, order = approve(sig)
    assert approved is False
    assert reason == "data_feed_stale"


def test_approve_max_positions_reached():
    state = get_state()
    state.update_ticker("BTC/USDT", 100.0, datetime.now(UTC).timestamp())
    state.update_ticker("ETH/USDT", 10.0, datetime.now(UTC).timestamp())

    # Mock open positions up to risk limit in DB
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            insert(positions).values(
                symbol="ETH/USDT",
                side="long",
                mode=str(state.current_mode),
                qty=10.0,
                entry_price=10.0,
                opened_ts=datetime.now(UTC).isoformat(),
                stop_price=8.0,
                status="open",
            )
        )
        conn.execute(
            insert(positions).values(
                symbol="SOL/USDT",
                side="long",
                mode=str(state.current_mode),
                qty=10.0,
                entry_price=10.0,
                opened_ts=datetime.now(UTC).isoformat(),
                stop_price=8.0,
                status="open",
            )
        )

    # settings.risk.max_open_positions is 2. So next entry should fail.
    sig = Signal(symbol="BTC/USDT", side="long", confidence=1.0, reason="cross")
    approved, reason, order = approve(sig, stop_price=90.0)
    assert approved is False
    assert reason == "max_positions_exceeded"


def test_approve_exit_never_blocked():
    state = get_state()
    # Even if watchdog/killswitch pre-checks are not active, exits are always allowed
    # Seed open position to Flat
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            insert(positions).values(
                symbol="BTC/USDT",
                side="long",
                mode=str(state.current_mode),
                qty=5.0,
                entry_price=20000.0,
                opened_ts=datetime.now(UTC).isoformat(),
                status="open",
            )
        )

    state.update_ticker("BTC/USDT", 19000.0, datetime.now(UTC).timestamp())

    # Verify Flat gets approved unconditionally post-staleness checks (must have active ticker)
    sig = Signal(symbol="BTC/USDT", side="flat", confidence=1.0, reason="exit")
    approved, reason, order = approve(sig)
    assert approved is True
    assert reason == "exit_approved"
    assert order.qty == 5.0


def test_approve_drawdown_limit_breaches():
    state = get_state()
    engine = get_engine()

    state.update_ticker("BTC/USDT", 100.0, datetime.now(UTC).timestamp())

    # Set HWM high to breach daily drawdown limit (starting paper balance is 10,000)
    # HWM = 11,000, current = 10,000 (Daily dd = 9.09% > limit of 3%)
    with engine.begin() as conn:
        conn.execute(
            insert(app_kv).values(key=f"daily_hwm_{str(state.current_mode)}", value="11000.0")
        )
        conn.execute(
            insert(app_kv).values(
                key=f"daily_hwm_date_{str(state.current_mode)}",
                value=datetime.now(UTC).strftime("%Y-%m-%d"),
            )
        )

    sig = Signal(symbol="BTC/USDT", side="long", confidence=1.0, reason="cross")
    approved, reason, order = approve(sig, stop_price=90.0)
    assert approved is False
    assert reason == "max_daily_drawdown_exceeded"


# ==========================================
# 3. Watchdog Triggers & Kill-switch Tests
# ==========================================


@pytest.mark.asyncio
async def test_watchdog_trigger_by_staleness():
    state = get_state()
    # Mock BTC tick to be extremely stale
    state.update_ticker("BTC/USDT", 100.0, datetime.now(UTC).timestamp() - 36000.0)
    # Mock others to be active
    for sym in get_settings().trading.symbols:
        if sym != "BTC/USDT":
            state.update_ticker(sym, 10.0, datetime.now(UTC).timestamp())

    adapter = MockAdapter()
    await run_watchdog(adapter)

    assert state.kill_switch_active is True
    assert adapter.cancel_called is True
    assert adapter.flatten_called is True


@pytest.mark.asyncio
async def test_watchdog_trigger_by_rejections_and_errors():
    state = get_state()
    settings = get_settings()
    for sym in settings.trading.symbols:
        state.update_ticker(sym, 10.0, datetime.now(UTC).timestamp())

    # Increment rejections up to risk limit
    for _ in range(settings.risk.max_consecutive_rejections):
        state.increment_rejections()

    adapter = MockAdapter()
    await run_watchdog(adapter)

    assert state.kill_switch_active is True


@pytest.mark.asyncio
async def test_watchdog_stop_loss_hit_flat_order():
    state = get_state()
    settings = get_settings()

    # Seed an open position with ATR stop in DB
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            insert(positions).values(
                symbol="BTC/USDT",
                side="long",
                mode=str(state.current_mode),
                qty=1.2,
                entry_price=100.0,
                opened_ts=datetime.now(UTC).isoformat(),
                stop_price=90.0,
                status="open",
            )
        )

    # Set ticker price to 85 (breaching stop loss of 90)
    state.update_ticker("BTC/USDT", 85.0, datetime.now(UTC).timestamp())
    for sym in settings.trading.symbols:
        if sym != "BTC/USDT":
            state.update_ticker(sym, 10.0, datetime.now(UTC).timestamp())

    adapter = MockAdapter()
    await run_watchdog(adapter)

    # Watchdog should trigger the stop Flat exit order pipeline
    assert len(adapter.placed_orders) == 1
    assert adapter.placed_orders[0].symbol == "BTC/USDT"
    assert adapter.placed_orders[0].side == "flat"
    assert adapter.placed_orders[0].qty == 1.2
    # Verify killswitch was NOT triggered (just a standard stop execution)
    assert state.kill_switch_active is False


@pytest.mark.asyncio
async def test_watchdog_flatten_failed_saves_retry():
    state = get_state()
    settings = get_settings()
    state.update_ticker("BTC/USDT", 100.0, datetime.now(UTC).timestamp() - 36000.0)
    for sym in settings.trading.symbols:
        if sym != "BTC/USDT":
            state.update_ticker(sym, 10.0, datetime.now(UTC).timestamp())

    # Trigger with an adapter that raises an exception on flatten
    adapter = MockAdapter(raise_flatten_error=True)
    await run_watchdog(adapter)

    assert state.kill_switch_active is True
    # The event log should indicate flatten failed / was false
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(select(killswitch_events)).fetchone()
        assert row is not None
        assert row._mapping["positions_flattened"] == 0


# ==========================================
# 4. Re-arm Flow Tests
# ==========================================


def test_rearm_flow():
    state = get_state()
    set_kv("killswitch", "triggered")
    state.set_kill_switch(True)
    state.increment_rejections()

    # Rearm rejected with invalid string
    assert rearm_killswitch("CONFIRM") is False
    assert get_state().kill_switch_active is True

    # Rearm passed with "RE-ARM"
    assert rearm_killswitch("RE-ARM") is True
    assert get_state().kill_switch_active is False
    assert get_state().consecutive_rejections == 0
