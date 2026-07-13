from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tradecore.execution.adapter import ApprovedOrder
from tradecore.execution.live import LiveAdapter


@pytest.mark.asyncio
async def test_live_adapter_place_success():
    mock_exchange = MagicMock()
    mock_exchange.load_markets = AsyncMock()
    mock_exchange.fetch_ticker = AsyncMock(return_value={"last": 65000.0})
    mock_exchange.amount_to_precision = MagicMock(return_value="0.05")
    mock_exchange.market = MagicMock(return_value={"limits": {"cost": {"min": 10.0}}})

    mock_exchange.create_order = AsyncMock(return_value={"id": "order-123", "status": "open"})
    mock_exchange.fetch_order = AsyncMock(
        return_value={
            "id": "order-123",
            "status": "closed",
            "filled": 0.05,
            "price": 65000.0,
            "fee": {"cost": 3.25},
        }
    )

    order = ApprovedOrder(symbol="BTC/USDT", side="long", qty=0.05, stop_price=64000.0)

    adapter = LiveAdapter(exchange=mock_exchange)

    with patch("tradecore.execution.live.track_fill", AsyncMock()) as mock_track:
        fill = await adapter.place(order)

        assert fill.order_id == "order-123"
        assert fill.qty == 0.05
        assert fill.price == 65000.0
        assert fill.fee == 3.25
        mock_track.assert_called_once_with(fill, stop_price=64000.0, mode="live")


@pytest.mark.asyncio
async def test_live_adapter_place_notional_rejection():
    mock_exchange = MagicMock()
    mock_exchange.load_markets = AsyncMock()
    mock_exchange.fetch_ticker = AsyncMock(return_value={"last": 65000.0})
    mock_exchange.amount_to_precision = MagicMock(return_value="0.0001")
    mock_exchange.market = MagicMock(return_value={"limits": {"cost": {"min": 10.0}}})

    order = ApprovedOrder(symbol="BTC/USDT", side="long", qty=0.0001)
    adapter = LiveAdapter(exchange=mock_exchange)

    with pytest.raises(ValueError, match="below the exchange limit"):
        await adapter.place(order)


@pytest.mark.asyncio
async def test_live_adapter_place_timeout():
    mock_exchange = MagicMock()
    mock_exchange.load_markets = AsyncMock()
    mock_exchange.fetch_ticker = AsyncMock(return_value={"last": 65000.0})
    mock_exchange.amount_to_precision = MagicMock(return_value="0.05")
    mock_exchange.market = MagicMock(return_value={"limits": {"cost": {"min": 10.0}}})

    mock_exchange.create_order = AsyncMock(return_value={"id": "order-123", "status": "open"})
    mock_exchange.fetch_order = AsyncMock(return_value={"id": "order-123", "status": "open"})
    mock_exchange.cancel_order = AsyncMock()

    order = ApprovedOrder(symbol="BTC/USDT", side="long", qty=0.05)
    adapter = LiveAdapter(exchange=mock_exchange)

    # Mock asyncio.sleep to not wait during testing and mock time.time to simulate timeout
    start_time = 100.0
    time_vals = [start_time, start_time + 40.0]

    def mock_time():
        if time_vals:
            return time_vals.pop(0)
        return start_time + 50.0

    with patch("asyncio.sleep", AsyncMock()), patch("time.time", side_effect=mock_time):
        with pytest.raises(TimeoutError, match="timed out"):
            await adapter.place(order)

        mock_exchange.cancel_order.assert_called_once_with("order-123", "BTC/USDT")


@pytest.mark.asyncio
async def test_live_adapter_flatten():
    mock_exchange = MagicMock()
    adapter = LiveAdapter(exchange=mock_exchange)

    open_positions = [
        {"symbol": "BTC/USDT", "qty": 0.05, "id": 1},
        {"symbol": "ETH/USDT", "qty": 1.5, "id": 2},
    ]

    with (
        patch("tradecore.execution.live.get_open_positions", return_value=open_positions),
        patch.object(adapter, "place", AsyncMock(return_value="fill")) as mock_place,
    ):
        fills = await adapter.flatten()
        assert len(fills) == 2
        assert mock_place.call_count == 2


@pytest.mark.asyncio
async def test_live_adapter_get_balance():
    mock_exchange = MagicMock()
    mock_exchange.fetch_balance = AsyncMock(return_value={"total": {"USDT": 5000.0}})

    adapter = LiveAdapter(exchange=mock_exchange)

    res = await adapter.get_balance()
    assert res["balance"] == 5000.0
    assert res["mode"] == "live"


@pytest.mark.asyncio
async def test_live_adapter_get_open_orders():
    mock_exchange = MagicMock()
    mock_exchange.fetch_open_orders = AsyncMock(return_value=[{"id": "order-1"}])
    adapter = LiveAdapter(exchange=mock_exchange)

    orders = await adapter.get_open_orders()
    assert len(orders) > 0
    assert orders[0]["id"] == "order-1"


@pytest.mark.asyncio
async def test_live_adapter_cancel_all():
    mock_exchange = MagicMock()
    mock_exchange.fetch_open_orders = AsyncMock(return_value=[{"id": "order-1"}])
    mock_exchange.cancel_order = AsyncMock()
    adapter = LiveAdapter(exchange=mock_exchange)

    await adapter.cancel_all()
    assert mock_exchange.cancel_order.call_count > 0
