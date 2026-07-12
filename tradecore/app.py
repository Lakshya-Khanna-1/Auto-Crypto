import asyncio
import logging
import time
from contextlib import asynccontextmanager

import pandas as pd
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradecore.core.config import get_settings
from tradecore.datafeed.feed import get_data_feed
from tradecore.store import candles as candle_store
from tradecore.store.repo import set_kv

logger = logging.getLogger(__name__)

# Initialize FastAPI App
app = FastAPI(title="Auto-Crypto Trader API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = AsyncIOScheduler()


def parse_timeframe_to_ms(timeframe: str) -> int:
    unit = timeframe[-1]
    value = int(timeframe[:-1])
    if unit == "m":
        return value * 60 * 1000
    elif unit == "h":
        return value * 60 * 60 * 1000
    elif unit == "d":
        return value * 24 * 60 * 60 * 1000
    else:
        raise ValueError(f"Unknown timeframe unit: {unit}")


async def candle_sync_job() -> None:
    """
    Live candle updates job. Fetches latest 3 candles, discards in-progress,
    caches closed candles to Parquet, and writes tracking state to db app_kv.
    """
    logger.info("Triggering candle_sync job...")
    feed = get_data_feed()
    settings = get_settings()
    symbols = settings.trading.symbols
    timeframe = settings.trading.timeframe
    timeframe_ms = parse_timeframe_to_ms(timeframe)
    now_ms = int(time.time() * 1000)

    for sym in symbols:
        try:
            loop = asyncio.get_running_loop()
            candles = await loop.run_in_executor(None, feed.fetch_candles, sym, timeframe, None, 3)
            if not candles:
                continue

            closed_candles = [c for c in candles if c.ts + timeframe_ms <= now_ms]
            if not closed_candles:
                continue

            df = pd.DataFrame(
                [
                    {
                        "ts": c.ts,
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                        "volume": c.volume,
                    }
                    for c in closed_candles
                ]
            )

            await loop.run_in_executor(None, candle_store.append, sym, timeframe, df)

            max_closed_ts = max(c.ts for c in closed_candles)
            await loop.run_in_executor(None, set_kv, f"last_candle_ts.{sym}", str(max_closed_ts))
            logger.info(
                f"candle_sync successful for {sym}: last closed candle ts is {max_closed_ts}"
            )
        except Exception as e:
            logger.error(f"Failed to sync candles for symbol {sym}: {e}")


async def ticker_poll_job() -> None:
    """
    Poll ticker prices via REST when WebSocket connection is unhealthy or inactive.
    """
    feed = get_data_feed()
    if not feed.ws_active:
        settings = get_settings()
        symbols = settings.trading.symbols
        logger.debug("WS inactive. Polling tickers via REST fallback...")
        await asyncio.gather(*(feed.poll_ticker(sym) for sym in symbols))


async def ws_reconnect_job() -> None:
    """
    Hourly WebSocket connection check and reconnection trigger.
    """
    feed = get_data_feed()
    if not feed.ws_active:
        logger.info("Attempting scheduled hourly WebSocket reconnection...")
        settings = get_settings()
        symbols = settings.trading.symbols
        asyncio.create_task(feed.start_ws_loop(symbols))


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    """
    Application startup & shutdown wiring router.
    """
    settings = get_settings()
    symbols = settings.trading.symbols

    # Register interval scheduler tasks
    scheduler.add_job(candle_sync_job, "interval", minutes=5, id="candle_sync")
    scheduler.add_job(ticker_poll_job, "interval", seconds=10, id="ticker_poll")
    scheduler.add_job(ws_reconnect_job, "interval", hours=1, id="ws_reconnect")

    scheduler.start()
    logger.info("APScheduler initialized and jobs started.")

    ws_task = asyncio.create_task(get_data_feed().start_ws_loop(symbols))

    yield

    # Shutdown sequence
    scheduler.shutdown()
    get_data_feed().ws_active = False
    ws_task.cancel()
    try:
        await ws_task
    except asyncio.CancelledError:
        pass
    logger.info("APScheduler and WebSocket task stopped.")


# Assign custom lifespan context manager
app.router.lifespan_context = lifespan


@app.get("/health")
def health_endpoint() -> dict[str, str]:
    """
    Standard service health endpoint returning current mode.
    """
    return {"status": "ok", "mode": get_settings().trading.mode.value}
