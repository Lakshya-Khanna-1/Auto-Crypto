from unittest.mock import MagicMock

import ccxt
import pytest

from tradecore.datafeed.feed import DataFeed, ccxt_retry
from tradecore.datafeed.models import Candle


def test_ccxt_retry_failure():
    # Verify that it fails after 5 retries on NetworkError
    mock_func = MagicMock(side_effect=ccxt.NetworkError("Demo connectivity error"))
    decorated = ccxt_retry(mock_func)

    with pytest.raises(ccxt.NetworkError):
        # Disable wait delay during testing to speed it up
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda x: None)
            decorated()

    assert mock_func.call_count == 5


def test_ccxt_no_retry_auth_error():
    # Verify AuthenticationError fails fast without retrying
    mock_func = MagicMock(side_effect=ccxt.AuthenticationError("Invalid API key"))
    decorated = ccxt_retry(mock_func)

    with pytest.raises(ccxt.AuthenticationError):
        decorated()

    assert mock_func.call_count == 1


def test_fetch_candles():
    mock_client = MagicMock()
    mock_client.fetch_ohlcv.return_value = [
        [1719878400000, 60000.0, 61000.0, 59500.0, 60500.0, 150.0],
    ]
    feed = DataFeed(client=mock_client)
    candles = feed.fetch_candles("BTC/USDT", "1h")

    assert len(candles) == 1
    assert isinstance(candles[0], Candle)
    assert candles[0].ts == 1719878400000
    assert candles[0].close == 60500.0
    mock_client.fetch_ohlcv.assert_called_once_with("BTC/USDT", "1h", None, None)


@pytest.mark.asyncio
async def test_rest_ticker_polling():
    mock_client = MagicMock()
    mock_client.fetch_ticker.return_value = {
        "last": 65000.0,
        "close": 65000.0,
    }
    feed = DataFeed(client=mock_client)
    await feed.poll_ticker("BTC/USDT")

    assert "BTC/USDT" in feed.last_tick
    assert feed.last_tick["BTC/USDT"].price == 65000.0
    mock_client.fetch_ticker.assert_called_once_with("BTC/USDT")


@pytest.mark.asyncio
async def test_websocket_degradation_trigger():
    # Mock fallback to check that consecutive failures switch ws_active to False
    mock_pro_client = MagicMock()
    mock_pro_client.watch_ticker.side_effect = Exception("WS Connect Failed")

    feed = DataFeed()
    feed.ws_active = True

    # Simulate loop step failure directly
    await feed._watch_ticker_loop(mock_pro_client, "BTC/USDT")

    # The failure count increments and switches off ws_active
    assert not feed.ws_active
    assert feed.ws_fail_count >= 2
