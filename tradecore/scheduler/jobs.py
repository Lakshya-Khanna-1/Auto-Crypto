import asyncio
import logging
import time
from datetime import datetime

import pandas as pd

from tradecore.core.config import get_settings
from tradecore.core.state import get_state
from tradecore.datafeed.feed import get_data_feed
from tradecore.execution.adapter import Position, get_adapter
from tradecore.execution.tracker import save_equity_snapshot
from tradecore.riskengine.engine import approve
from tradecore.riskengine.killswitch import run_watchdog
from tradecore.store import candles as candle_store
from tradecore.store.repo import get_open_positions, set_kv

logger = logging.getLogger("tradecore.scheduler.jobs")


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


async def strategy_tick_job() -> None:
    """
    Strategy tick executor. Reads historical OHLCV data, runs strategy logic,
    and places approved orders.
    """
    state = get_state()
    if state.strategy_paused:
        logger.info("Strategy execution is currently paused. Skipping tick.")
        return
    mode = str(state.current_mode)
    if mode == "backtest":
        return

    settings = get_settings()
    logger.info(f"Triggering strategy check ticks in mode: {mode}")

    # Load active strategy
    if settings.strategy.name == "ema_trend":
        from tradecore.strategy.ema_trend import EMATrendStrategy

        strategy = EMATrendStrategy(
            fast_period=settings.strategy.ema_fast,
            slow_period=settings.strategy.ema_slow,
            atr_period=settings.strategy.atr_period,
            atr_stop_mult=settings.strategy.atr_stop_mult,
        )
    else:
        logger.error(f"Unknown strategy configured: {settings.strategy.name}")
        return

    # Retrieve all open positions for mapping
    # status must be 'open'
    open_pos_dicts = get_open_positions(mode)

    def parse_time(ts_str):
        if not ts_str:
            return 0.0
        try:
            return datetime.fromisoformat(ts_str).timestamp()
        except Exception:
            return 0.0

    for symbol in settings.trading.symbols:
        try:
            # 1. Read historical candle DataFrame
            df = candle_store.read(symbol, settings.trading.timeframe)
            if len(df) < settings.strategy.ema_slow:
                logger.debug(f"Skipping strategy check for {symbol}: insufficient candles.")
                continue

            # 2. Map open position for symbol if it exists
            pos_dict = next((p for p in open_pos_dicts if p["symbol"] == symbol), None)
            position = None
            if pos_dict is not None:
                position = Position(
                    id=str(pos_dict["id"]),
                    symbol=pos_dict["symbol"],
                    side=pos_dict["side"],
                    qty=pos_dict["qty"],
                    entry_price=pos_dict["entry_price"],
                    stop_price=pos_dict["stop_price"],
                    opened_ts=parse_time(pos_dict["opened_ts"]),
                )

            # 3. Request signal decision
            df["symbol"] = symbol
            signal = strategy.on_candle(df, position)
            if signal is not None:
                # Calculate entry ATR trailing stop if LONG signal
                stop_price = None
                if signal.side == "long":
                    df_ind = strategy.compute_indicators(df)
                    last_row = df_ind.iloc[-1]
                    close_col = "close" if "close" in df_ind.columns else "Close"
                    close_val = last_row[close_col]
                    atr_val = last_row["atr"]
                    stop_price = close_val - settings.strategy.atr_stop_mult * atr_val

                # 4. Route signal through risk engine gate
                approved, reason, order = approve(signal, stop_price=stop_price)

                # 5. Place approved orders using adapter
                if approved and order is not None:
                    adapter = get_adapter(mode)
                    logger.info(f"Placing: {order.side}, qty={order.qty}, stop={order.stop_price}")
                    try:
                        await adapter.place(order)
                        state.reset_rejections()
                    except Exception as e:
                        logger.error(f"Failed to place strategy-approved order for {symbol}: {e}")
                        state.increment_rejections()
                else:
                    logger.debug(f"Strategy signal rejected or empty for {symbol}: {reason}")
        except Exception as e:
            logger.error(f"Error executing strategy tick for {symbol}: {e}")


async def equity_snapshot_job() -> None:
    """
    Saves recurring 15-minute equity snapshots to database.
    """
    mode = str(get_state().current_mode)
    if mode == "backtest":
        return
    try:
        await save_equity_snapshot(mode)
        logger.info(f"Recorded scheduled equity snapshot for mode: {mode}")
    except Exception as e:
        logger.error(f"Failed to record scheduled equity snapshot: {e}")


async def risk_watchdog_job() -> None:
    """
    Main risk watchdog triggers checking drawdowns, staleness, stops.
    """
    mode = str(get_state().current_mode)
    if mode == "backtest":
        return
    try:
        adapter = get_adapter(mode)
        await run_watchdog(adapter)
    except Exception as e:
        logger.error(f"Error encountered running watchdog job: {e}")
