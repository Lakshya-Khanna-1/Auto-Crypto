import json
import logging
from datetime import UTC, datetime

from tradecore.core.config import get_settings
from tradecore.core.state import get_state
from tradecore.execution.adapter import Signal
from tradecore.riskengine.engine import (
    approve,
    get_portfolio_equity,
    update_and_get_drawdowns,
)
from tradecore.store.repo import (
    get_kv,
    get_open_positions,
    save_killswitch_log,
    set_kv,
)

logger = logging.getLogger("tradecore.riskengine.killswitch")

# Tracks alarm-level notifications every 5 minutes (5 * 60 seconds / loop_interval)
flatten_retry_errors_count = 0


async def trigger_killswitch(reason: str, adapter=None) -> None:
    """
    Trigger the risk killswitch: mark DB and state, cancel all orders, and flatten positions.
    """
    logger.critical(f"CRITICAL: Triggering Risk Killswitch! Reason: {reason}")
    set_kv("killswitch", "triggered")
    get_state().set_kill_switch(True)

    mode = get_state().current_mode.value
    open_positions = get_open_positions(mode)
    details = {
        "reason": reason,
        "timestamp": datetime.now(UTC).isoformat(),
        "positions_before": open_positions,
    }

    flatten_success = True
    if adapter is not None:
        try:
            logger.info("Watchdog canceling all active orders...")
            await adapter.cancel_all()
            logger.info("Watchdog flattening all open positions...")
            await adapter.flatten()
        except Exception as e:
            logger.critical(f"Watchdog failed to cancel/flatten on kill-switch trigger: {e}")
            flatten_success = False
            # Route API/execution failure to consecutive failure counter
            get_state().increment_rejections()

    def json_serializer(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")

    save_killswitch_log(
        reason,
        json.dumps(details, default=json_serializer),
        positions_flattened=flatten_success,
    )


def rearm_killswitch(confirmation: str) -> bool:
    """
    Manually re-arm the killswitch with typed confirmation string "RE-ARM".
    """
    if confirmation != "RE-ARM":
        logger.warning(f"Kill-switch manual re-arm reject: expected 'RE-ARM', got '{confirmation}'")
        return False

    logger.warning(
        "Kill-switch manual re-arm SUCCESSFUL. Resetting risk status and rejection counters."
    )
    set_kv("killswitch", "armed")
    get_state().set_kill_switch(False)
    get_state().reset_rejections()
    return True


async def run_watchdog(adapter=None) -> None:
    """
    Main watchdog running logic check.
    """
    global flatten_retry_errors_count
    settings = get_settings()
    state = get_state()
    mode = state.current_mode.value

    # Check if killswitch is already active
    killswitch_active = state.kill_switch_active or (get_kv("killswitch") == "triggered")
    if killswitch_active:
        # Double check if any positions are left open and retry flattening
        open_positions = get_open_positions(mode)
        if open_positions and adapter is not None:
            flatten_retry_errors_count += 1
            logger.warning(
                f"Killswitch is active but open positions remain ({len(open_positions)}). "
                "Retrying flatten..."
            )
            try:
                await adapter.cancel_all()
                await adapter.flatten()
                logger.info("Positions successfully flattened during active kill-switch retry.")
            except Exception as e:
                logger.critical(f"Flatten retry failed: {e}")
                # Increment consecutive errors counter
                state.increment_rejections()
                if flatten_retry_errors_count % 5 == 0:
                    logger.error(
                        "ALARM: Kill-switch active but flatten retries repeatedly "
                        "failing (5 consecutive errors)!"
                    )
        return

    # Check 1: Drawdown thresholds
    equity = get_portfolio_equity(mode)
    daily_dd, total_dd = update_and_get_drawdowns(mode, equity)

    if daily_dd > settings.risk.max_daily_drawdown_pct:
        await trigger_killswitch(f"Daily drawdown limit breached ({daily_dd:.2f}%)", adapter)
        return

    if total_dd > settings.risk.max_total_drawdown_pct:
        await trigger_killswitch(f"Total drawdown limit breached ({total_dd:.2f}%)", adapter)
        return

    # Check 2: Data feed staleness
    current_time = datetime.now(UTC).timestamp()
    max_stale = settings.risk.max_data_staleness_sec
    for symbol in settings.trading.symbols:
        tick_time = state.get_ticker_time(symbol)
        if tick_time is None or (current_time - tick_time) > max_stale:
            stale_sec = (current_time - tick_time) if tick_time is not None else float("inf")
            await trigger_killswitch(
                f"Data staleness limit breached for {symbol} ({stale_sec:.1f} s)",
                adapter,
            )
            return

    # Check 3: Consecutive rejections / errors
    if state.consecutive_rejections >= settings.risk.max_consecutive_rejections:
        await trigger_killswitch(
            f"Consecutive order rejections/errors limit breached "
            f"({state.consecutive_rejections})",
            adapter,
        )
        return

    # Check 4: Enforce stop loss checks intracandle
    open_positions = get_open_positions(mode)
    for pos in open_positions:
        symbol = pos["symbol"]
        price = state.get_ticker_price(symbol)
        stop_loss = pos.get("stop_loss")

        if stop_loss is not None and price is not None:
            if price <= stop_loss:
                logger.warning(
                    f"Intracandle stop loss breached for {symbol}: "
                    f"price={price}, stop={stop_loss}. Routing Flat signal."
                )
                sig = Signal(
                    symbol=symbol,
                    side="flat",
                    confidence=1.0,
                    reason="intracandle_stop_hit",
                )
                # MUST route stop order Flat signal through engine.approve() per mandate
                approved, reason, approved_order = approve(sig)
                if approved and approved_order is not None and adapter is not None:
                    try:
                        logger.info(
                            f"Executing stop exit order for {symbol} (qty: {approved_order.qty})"
                        )
                        await adapter.place(approved_order)
                        state.reset_rejections()
                    except Exception as e:
                        logger.error(f"Failed to execute stop order flat exit for {symbol}: {e}")
                        state.increment_rejections()
                else:
                    logger.error(
                        f"Stop Flat signal for {symbol} was rejected by Risk Engine: {reason}"
                    )
                    state.increment_rejections()
