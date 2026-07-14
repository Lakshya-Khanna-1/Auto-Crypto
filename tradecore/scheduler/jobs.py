import asyncio
import logging
import time
from datetime import UTC, datetime

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
            df_existing = await loop.run_in_executor(None, candle_store.read, sym, timeframe)
            limit = 3
            if len(df_existing) < settings.strategy.ema_slow:
                limit = max(settings.strategy.ema_slow + 50, 100)
                logger.info(
                    f"Bootstrapping candles for {sym} (limit={limit}) on timeframe {timeframe}..."
                )

            candles = await loop.run_in_executor(
                None, feed.fetch_candles, sym, timeframe, None, limit
            )
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
    mode = str(getattr(state.current_mode, "value", state.current_mode))
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
    elif settings.strategy.name == "ema_trend_adx":
        from tradecore.strategy.ema_trend_adx import EmaTrendAdxStrategy

        strategy = EmaTrendAdxStrategy(
            ema_fast=settings.strategy.ema_fast,
            ema_slow=settings.strategy.ema_slow,
            atr_period=settings.strategy.atr_period,
            atr_stop_mult=settings.strategy.atr_stop_mult,
            adx_period=settings.strategy.adx_period,
            adx_min=settings.strategy.adx_min,
        )
    elif settings.strategy.name == "donchian_breakout":
        from tradecore.strategy.donchian_breakout import DonchianBreakoutStrategy

        strategy = DonchianBreakoutStrategy(
            donchian_entry=settings.strategy.donchian_entry,
            donchian_exit=settings.strategy.donchian_exit,
            atr_period=settings.strategy.atr_period,
            atr_stop_mult=settings.strategy.atr_stop_mult,
        )
    elif settings.strategy.name == "ml_lgbm":
        from tradecore.strategy.ml_lgbm import MLStrategy

        strategy = MLStrategy(
            model_path=settings.strategy.ml_model_path,
            threshold=settings.strategy.ml_threshold,
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
    mode = str(getattr(get_state().current_mode, "value", get_state().current_mode))
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
    mode = str(getattr(get_state().current_mode, "value", get_state().current_mode))
    if mode == "backtest":
        return
    try:
        adapter = get_adapter(mode)
        await run_watchdog(adapter)
    except Exception as e:
        logger.error(f"Error encountered running watchdog job: {e}")


async def daily_report_job() -> None:
    """
    Generate daily AI operations report for the active trading mode,
    save it to app_kv, and dispatch it to Telegram if configured.
    """
    state = get_state()
    mode = str(getattr(state.current_mode, "value", state.current_mode))
    if mode == "backtest":
        return
    logger.info(f"Triggering daily_report_job for mode: {mode}")
    try:
        import json

        from tradecore.ailayer.reports import generate_daily_report
        from tradecore.notifications.notifier import send_telegram_alert

        report_text = await generate_daily_report(mode)
        ts_str = datetime.now(UTC).isoformat()

        # Save JSON string structure to app_kv
        report_data = {"ts": ts_str, "text": report_text}
        set_kv("latest_report", json.dumps(report_data))
        logger.info("Daily report successfully generated and saved to app_kv.")

        # Dispatch to Telegram
        await send_telegram_alert(f"📋 *Daily Operations Report ({mode.upper()})*\n\n{report_text}")
    except Exception as e:
        logger.error(f"Error executing daily_report_job: {e}")


async def annotate_closed_positions_job() -> None:
    """
    Background job to annotate closed positions with explanations using the fast AI model.
    """
    settings = get_settings()
    if not settings.ollama.enabled:
        return

    state = get_state()
    mode = str(getattr(state.current_mode, "value", state.current_mode))
    if mode == "backtest":
        return

    try:
        from tradecore.ailayer.client import generate_response
        from tradecore.ailayer.prompts import TRADE_ANNOTATION_PROMPT
        from tradecore.store.repo import (
            get_signal_reason_for_position,
            get_unannotated_closed_positions,
            update_position_annotation,
        )

        unannotated = get_unannotated_closed_positions(mode)
        if not unannotated:
            return

        logger.info(f"Found {len(unannotated)} unannotated closed positions in mode: {mode}")

        for pos in unannotated:
            pos_id = pos["id"]
            symbol = pos["symbol"]
            opened_ts = pos["opened_ts"]
            entry_price = pos["entry_price"]
            exit_price = pos.get("exit_price") or 0.0
            pnl = pos.get("realized_pnl") or 0.0

            # Find matching signal reason
            reason = get_signal_reason_for_position(symbol, opened_ts)
            if not reason:
                reason = "technical crossover"

            # Format the prompt
            prompt = TRADE_ANNOTATION_PROMPT.format(
                reason=reason, entry_price=entry_price, exit_price=exit_price, pnl=pnl
            )

            # Generate response
            explanation = await generate_response(settings.ollama.fast_model, prompt)
            if explanation:
                clean_exp = explanation.strip().replace("\n", " ")
                update_position_annotation(pos_id, clean_exp)
                logger.info(f"Successfully annotated position {pos_id}: {clean_exp}")
            else:
                logger.warning(f"Failed to generate annotation for position {pos_id}.")

    except Exception as e:
        logger.error(f"Error in annotate_closed_positions_job: {e}")
