import asyncio
import logging
import time
from collections.abc import Sequence

import ccxt
import ccxt.pro as ccxtpro
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from tradecore.core.config import get_settings
from tradecore.core.state import get_state
from tradecore.datafeed.models import Candle, Ticker

logger = logging.getLogger(__name__)

# CCXT retriable exception types
RETRIABLE_EXCEPTIONS = (
    ccxt.NetworkError,
    ccxt.ExchangeNotAvailable,
    ccxt.RequestTimeout,
)

# Pinned Tenacity retry rule (5 attempts: 1s, 2s, 4s, 8s, 16s)
ccxt_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True,
)


def get_ccxt_client() -> ccxt.Exchange:
    """
    Instantiate standard CCXT client from active settings.
    """
    settings = get_settings()
    exchange_name = settings.trading.exchange.lower()

    if not hasattr(ccxt, exchange_name):
        raise ValueError(f"Exchange '{exchange_name}' is not supported by CCXT.")

    exchange_cls = getattr(ccxt, exchange_name)
    config = {
        "enableRateLimit": True,
    }

    if settings.exchange_api_key:
        config["apiKey"] = settings.exchange_api_key
    if settings.exchange_api_secret:
        config["secret"] = settings.exchange_api_secret

    return exchange_cls(config)


class DataFeed:
    """
    Unified Data Feed fetching market candles and real-time ticker prices.
    """

    def __init__(self, client: ccxt.Exchange | None = None) -> None:
        self.client = client or get_ccxt_client()
        self.last_tick: dict[str, Ticker] = {}
        self.ws_active = False
        self.ws_fail_count = 0
        self._fallback_warned = False
        self._ws_task: asyncio.Task[None] | None = None

    @ccxt_retry
    def _fetch_ohlcv_raw(
        self, symbol: str, timeframe: str, since: int | None = None, limit: int | None = None
    ) -> list[list[float]]:
        # Run blocking CCXT IO call
        return self.client.fetch_ohlcv(symbol, timeframe, since, limit)

    def fetch_candles(
        self, symbol: str, timeframe: str, since: int | None = None, limit: int | None = None
    ) -> list[Candle]:
        """
        Fetch OHLCV candles from CCXT with automatic network error retries.
        """
        raw_candles = self._fetch_ohlcv_raw(symbol, timeframe, since, limit)
        return [
            Candle(
                ts=int(c[0]),
                open=float(c[1]),
                high=float(c[2]),
                low=float(c[3]),
                close=float(c[4]),
                volume=float(c[5]),
            )
            for c in raw_candles
        ]

    async def start_ws_loop(self, symbols: Sequence[str]) -> None:
        """
        Start the background CCXT.pro WebSocket watch_ticker stream loop.
        """
        self.ws_active = True
        self.ws_fail_count = 0
        self._fallback_warned = False

        settings = get_settings()
        exchange_name = settings.trading.exchange.lower()
        exchange_cls = getattr(ccxtpro, exchange_name, None)

        if not exchange_cls:
            logger.warning(
                f"ccxt.pro WebSocket class not found for {exchange_name}. "
                "Defaulting to REST fallback."
            )
            self.ws_active = False
            return

        config = {"enableRateLimit": True}
        if settings.exchange_api_key:
            config["apiKey"] = settings.exchange_api_key
        if settings.exchange_api_secret:
            config["secret"] = settings.exchange_api_secret

        pro_client = exchange_cls(config)
        tasks = [self._watch_ticker_loop(pro_client, sym) for sym in symbols]

        try:
            await asyncio.gather(*tasks)
        finally:
            await pro_client.close()

    async def _watch_ticker_loop(self, pro_client: ccxtpro.Exchange, symbol: str) -> None:
        while self.ws_active:
            try:
                # Fetch WebSocket ticker update
                tick = await pro_client.watch_ticker(symbol)
                price = float(tick["last"] or tick["close"])
                self.last_tick[symbol] = Ticker(
                    symbol=symbol,
                    price=price,
                    received_at=time.time(),
                )
                get_state().update_ticker(symbol, price, self.last_tick[symbol].received_at)
                # Successful tick resets failure count
                self.ws_fail_count = 0
            except Exception as e:
                self.ws_fail_count += 1
                logger.error(f"WebSocket watch_ticker error on {symbol}: {e}")
                if self.ws_fail_count >= 2:
                    self.ws_active = False
                    if not self._fallback_warned:
                        logger.warning(
                            "CCXT.pro WebSocket failed twice consecutively. "
                            "Switching to REST polling fallback."
                        )
                        self._fallback_warned = True
                    break
                await asyncio.sleep(5)

    @ccxt_retry
    def _fetch_ticker_raw(self, symbol: str) -> dict[str, float]:
        return self.client.fetch_ticker(symbol)

    async def poll_ticker(self, symbol: str) -> None:
        """
        Poll price ticker via CCXT REST if WebSocket is currently inactive.
        """
        loop = asyncio.get_running_loop()
        try:
            tick = await loop.run_in_executor(None, self._fetch_ticker_raw, symbol)
            price = float(tick["last"] or tick["close"])
            self.last_tick[symbol] = Ticker(
                symbol=symbol,
                price=price,
                received_at=time.time(),
            )
            get_state().update_ticker(symbol, price, self.last_tick[symbol].received_at)
        except Exception as e:
            logger.error(f"REST fetch_ticker error for {symbol}: {e}")

    @property
    def is_stale(self) -> bool:
        """
        Determine if any configured symbol ticker is stale compared to max staleness rules.
        """
        settings = get_settings()
        symbols = settings.trading.symbols
        if not symbols:
            return False

        max_staleness = settings.risk.max_data_staleness_sec
        now = time.time()

        for sym in symbols:
            tick = self.last_tick.get(sym)
            if not tick:
                # Treat as stale if no data has been received yet
                return True
            if (now - tick.received_at) > max_staleness:
                return True

        return False


# Global data feed instance
_data_feed: DataFeed | None = None


def get_data_feed(force_reload: bool = False) -> DataFeed:
    """
    Retrieve or cache the global DataFeed instance.
    """
    global _data_feed
    if _data_feed is None or force_reload:
        _data_feed = DataFeed()
    return _data_feed
