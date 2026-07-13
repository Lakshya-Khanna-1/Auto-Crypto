from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tradecore.core.config import TradingMode, get_settings
from tradecore.core.state import get_state


@pytest.mark.asyncio
async def test_startup_reconciliation_match():
    # Setup state to live
    state = get_state()
    state.set_mode(TradingMode.LIVE)
    state.set_strategy_paused(False)

    settings = get_settings()
    settings.trading.mode = TradingMode.LIVE

    mock_adapter = MagicMock()
    mock_adapter.get_open_orders = AsyncMock(return_value=[])
    # Expect empty positions in DB, so expect 0.0 balances
    mock_adapter.exchange.fetch_balance = AsyncMock(
        return_value={"total": {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0, "BNB": 0.0, "XRP": 0.0}}
    )

    with (
        patch("tradecore.execution.live.LiveAdapter", return_value=mock_adapter),
        patch("tradecore.notifications.notifier.send_telegram_alert", AsyncMock()) as mock_alert,
        patch("tradecore.app.get_open_positions", return_value=[]),
    ):
        # Import app locally so the mocks are active when context starts
        from tradecore.app import app

        with TestClient(app) as _:
            pass

        assert not state.strategy_paused
        # Verify no mismatch alert was sent
        for call_args in mock_alert.call_args_list:
            assert "STARTUP RECONCILIATION MISMATCH" not in call_args[0][0]


@pytest.mark.asyncio
async def test_startup_reconciliation_balance_mismatch():
    # Setup state to live
    state = get_state()
    state.set_mode(TradingMode.LIVE)
    state.set_strategy_paused(False)

    settings = get_settings()
    settings.trading.mode = TradingMode.LIVE

    mock_adapter = MagicMock()
    mock_adapter.get_open_orders = AsyncMock(return_value=[])
    # Mismatch: Return 0.5 BTC on exchange, but DB expects 0.0 (no open positions)
    mock_adapter.exchange.fetch_balance = AsyncMock(return_value={"total": {"BTC": 0.5}})

    with (
        patch("tradecore.execution.live.LiveAdapter", return_value=mock_adapter),
        patch("tradecore.notifications.notifier.send_telegram_alert", AsyncMock()) as mock_alert,
        patch("tradecore.app.get_open_positions", return_value=[]),
    ):
        from tradecore.app import app

        with TestClient(app) as _:
            pass

        # Strategy must be paused on mismatch
        assert state.strategy_paused
        mismatch_alert_sent = any(
            "STARTUP RECONCILIATION MISMATCH" in call_args[0][0]
            for call_args in mock_alert.call_args_list
        )
        assert mismatch_alert_sent


@pytest.mark.asyncio
async def test_startup_reconciliation_open_orders_exist():
    # Setup state to live
    state = get_state()
    state.set_mode(TradingMode.LIVE)
    state.set_strategy_paused(False)

    settings = get_settings()
    settings.trading.mode = TradingMode.LIVE

    mock_adapter = MagicMock()
    # Mismatch: Open orders exist on exchange
    mock_adapter.get_open_orders = AsyncMock(return_value=[{"id": "order-123"}])
    mock_adapter.exchange.fetch_balance = AsyncMock(return_value={"total": {"BTC": 0.0}})

    with (
        patch("tradecore.execution.live.LiveAdapter", return_value=mock_adapter),
        patch("tradecore.notifications.notifier.send_telegram_alert", AsyncMock()) as mock_alert,
        patch("tradecore.app.get_open_positions", return_value=[]),
    ):
        from tradecore.app import app

        with TestClient(app) as _:
            pass

        assert state.strategy_paused
        mismatch_alert_sent = any(
            "STARTUP RECONCILIATION MISMATCH" in call_args[0][0]
            for call_args in mock_alert.call_args_list
        )
        assert mismatch_alert_sent
