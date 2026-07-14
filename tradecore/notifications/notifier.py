import logging
import time
from datetime import UTC, datetime

from sqlalchemy import insert
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from tradecore.core.config import get_settings
from tradecore.core.events import Event, get_event_bus
from tradecore.core.state import get_state
from tradecore.execution.adapter import get_adapter
from tradecore.store.db import get_engine
from tradecore.store.repo import get_kv, get_open_positions
from tradecore.store.schema import killswitch_events

logger = logging.getLogger(__name__)

# Global Telegram application instance reference
telegram_app: Application | None = None

# Timestamp tracking for rearm /confirm flow
last_rearm_request_time = 0.0


def check_chat_id(update: Update) -> bool:
    settings = get_settings()
    if update.effective_chat is None:
        return False
    msg_chat_id = str(update.effective_chat.id)
    target_chat_id = str(settings.telegram.chat_id)
    if msg_chat_id != target_chat_id:
        logger.warning(
            f"Unauthorized command attempt from chat_id {msg_chat_id} "
            f"(Configured: {target_chat_id})."
        )
        return False
    return True


# --- Command Handlers ---


async def tg_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_chat_id(update):
        return
    from tradecore.riskengine.engine import get_portfolio_equity

    state = get_state()
    settings = get_settings()
    mode = str(state.current_mode)

    if mode == "paper":
        bal_str = get_kv("paper_balance")
        balance = float(bal_str) if bal_str is not None else settings.paper.starting_balance
    else:
        bal_str = get_kv("live_balance")
        balance = float(bal_str) if bal_str is not None else 10000.0

    equity = get_portfolio_equity(mode)
    starting_balance = settings.paper.starting_balance if mode == "paper" else 10000.0
    pnl_total = equity - starting_balance

    msg = (
        f"📊 *Auto-Crypto Status*\n"
        f"Mode: `{mode.upper()}`\n"
        f"Equity: `${equity:.2f}`\n"
        f"Balance: `${balance:.2f}`\n"
        f"Total P&L: `${pnl_total:.2f}`\n"
        f"Killswitch: `{'HALTED/TRIGGERED' if state.kill_switch_active else 'ARMED'}`\n"
        f"Strategy: `{'PAUSED' if state.strategy_paused else 'RUNNING'}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def tg_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_chat_id(update):
        return
    state = get_state()
    mode = str(state.current_mode)
    open_pos = get_open_positions(mode)

    if not open_pos:
        await update.message.reply_text("No active open positions.")
        return

    lines = ["💼 *Active Open Positions:*"]
    for pos in open_pos:
        symbol = pos["symbol"]
        price = state.get_ticker_price(symbol) or pos["entry_price"]
        unrealized = pos["qty"] * (price - pos["entry_price"])
        unrealized_pct = (unrealized / (pos["entry_price"] * pos["qty"])) * 100
        sign = "+" if unrealized >= 0 else ""
        lines.append(
            f"• *{symbol}* {pos['side'].upper()}\n"
            f"  Qty: {pos['qty']}\n"
            f"  Entry: ${pos['entry_price']:.2f} | Current: ${price:.2f}\n"
            f"  Unrealized: {sign}${unrealized:.2f} ({sign}{unrealized_pct:.2f}%)"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def tg_kill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_chat_id(update):
        return
    state = get_state()
    mode = str(state.current_mode)
    state.set_kill_switch(True)

    adapter = get_adapter(mode)
    try:
        await adapter.flatten()
        flatten_msg = "Positions flattened successfully."
    except Exception as e:
        flatten_msg = f"Flattening failed: {e}"

    # Persistent log in DB
    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                insert(killswitch_events).values(
                    timestamp=datetime.now(UTC),
                    reason="Manual Telegram Operator Command",
                    resolved=0,
                    positions_flattened=1,
                    details_json='{"operator": "telegram"}',
                )
            )

    await update.message.reply_text(
        f"🚨 *KILL SWITCH TRIGGERED!*\nEngine halted. {flatten_msg}",
        parse_mode="Markdown",
    )
    await get_event_bus().publish(
        Event("killswitch", {"status": "triggered", "reason": "manual_telegram"})
    )


async def tg_rearm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_chat_id(update):
        return
    global last_rearm_request_time
    last_rearm_request_time = time.time()
    await update.message.reply_text(
        "⚠️ *Rearm requested.* Please send /confirm within 60 " "seconds to unlock the mechanism.",
        parse_mode="Markdown",
    )


async def tg_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_chat_id(update):
        return
    global last_rearm_request_time
    elapsed = time.time() - last_rearm_request_time
    if elapsed > 60.0:
        await update.message.reply_text(
            "❌ *Confirmation expired.* Please initiate using /rearm again.",
            parse_mode="Markdown",
        )
        return

    from tradecore.riskengine.killswitch import rearm_killswitch

    rearm_killswitch("RE-ARM")

    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                update(killswitch_events)
                .where(killswitch_events.c.resolved == 0)
                .values(resolved=1, resolved_time=datetime.now(UTC))
            )

    await update.message.reply_text(
        "✅ *Risk watchdogs re-armed.* Strategy execution unlocked.",
        parse_mode="Markdown",
    )
    await get_event_bus().publish(Event("killswitch", {"status": "armed"}))


async def tg_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_chat_id(update):
        return
    state = get_state()
    state.set_strategy_paused(True)
    await update.message.reply_text("⏸️ *Strategy ticks paused.*", parse_mode="Markdown")
    await get_event_bus().publish(Event("status", {"paused": True}))


async def tg_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not check_chat_id(update):
        return
    state = get_state()
    state.set_strategy_paused(False)
    await update.message.reply_text("▶️ *Strategy ticks resumed.*", parse_mode="Markdown")
    await get_event_bus().publish(Event("status", {"paused": False}))


# --- Startup / Shutdown Lifecycle Control ---


async def init_telegram_bot() -> None:
    global telegram_app
    settings = get_settings()
    token = settings.telegram_bot_token
    chat_id = settings.telegram.chat_id

    if not settings.telegram.enabled:
        logger.info("Telegram notifier disabled in configuration.")
        return

    if not token or not chat_id:
        logger.warning(
            "Telegram enabled but bot token or chat ID is missing in "
            "environment/config. Notifications is running as a fallback "
            "no-op logger."
        )
        return

    try:
        telegram_app = ApplicationBuilder().token(token).build()

        # Wire commands
        telegram_app.add_handler(CommandHandler("status", tg_status))
        telegram_app.add_handler(CommandHandler("positions", tg_positions))
        telegram_app.add_handler(CommandHandler("kill", tg_kill))
        telegram_app.add_handler(CommandHandler("rearm", tg_rearm))
        telegram_app.add_handler(CommandHandler("confirm", tg_confirm))
        telegram_app.add_handler(CommandHandler("pause", tg_pause))
        telegram_app.add_handler(CommandHandler("resume", tg_resume))

        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()
        logger.info("Telegram bot started polling successfully.")
    except Exception as e:
        logger.error(
            f"Failed to initialize Telegram connection: {e}. " "Running as fallback no-op logger."
        )
        telegram_app = None


async def stop_telegram_bot() -> None:
    global telegram_app
    if telegram_app is not None:
        try:
            await telegram_app.updater.stop()
            await telegram_app.stop()
            await telegram_app.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down Telegram bot: {e}")
        finally:
            telegram_app = None


async def send_telegram_alert(msg: str) -> None:
    """
    Unified outbound notifier. Falls back to standard logger if Telegram token missing or disabled.
    """
    logger.info(f"[OUTBOUND ALERT] {msg}")
    global telegram_app
    if telegram_app is not None:
        settings = get_settings()
        chat_id = settings.telegram.chat_id
        try:
            await telegram_app.bot.send_message(chat_id=chat_id, text=msg)
        except Exception as e:
            logger.error(f"Failed to deliver Telegram outbound alert: {e}")
