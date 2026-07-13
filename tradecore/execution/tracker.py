import logging
from datetime import UTC, datetime

from sqlalchemy import insert, select, update

from tradecore.core.config import get_settings
from tradecore.core.state import get_state
from tradecore.execution.adapter import Fill
from tradecore.store.db import get_engine
from tradecore.store.schema import equity_snapshots, positions, trades

logger = logging.getLogger("tradecore.execution.tracker")


async def track_fill(fill: Fill, stop_price: float | None = None, mode: str = "paper") -> None:
    """
    Record a new buy/sell fill:
    - Long (buy): insert open position + insert trade fill row.
    - Flat (sell): update open position to closed in-place + insert trade fill row.
    - Captures an equity snapshot immediately after the database updates.
    """
    engine = get_engine()
    settings = get_settings()
    strategy_name = settings.strategy.name
    ts_str = datetime.fromtimestamp(fill.ts, UTC).isoformat()

    with engine.begin() as conn:
        if fill.side == "long":
            # 1. Insert open position
            pos_stmt = insert(positions).values(
                mode=mode,
                symbol=fill.symbol,
                side="long",
                qty=fill.qty,
                entry_price=fill.price,
                stop_price=stop_price,
                opened_ts=ts_str,
                closed_ts=None,
                exit_price=None,
                realized_pnl=None,
                fees_total=fill.fee,
                status="open",
            )
            res = conn.execute(pos_stmt)
            pos_id = res.inserted_primary_key[0]

            # 2. Insert trade fill row
            trade_stmt = insert(trades).values(
                position_id=pos_id,
                ts=ts_str,
                mode=mode,
                symbol=fill.symbol,
                side="buy",
                qty=fill.qty,
                price=fill.price,
                fee=fill.fee,
                order_id=fill.order_id,
                strategy=strategy_name,
            )
            conn.execute(trade_stmt)
            logger.info(f"Tracked entry fill for {fill.symbol}: pos_id={pos_id}")
            from tradecore.notifications.notifier import send_telegram_alert

            await send_telegram_alert(
                f"📥 *Fill (Entry)*\n"
                f"Symbol: `{fill.symbol}`\n"
                f"Side: `BUY`\n"
                f"Qty: `{fill.qty}`\n"
                f"Price: `${fill.price:.2f}`\n"
                f"Mode: `{mode.upper()}`"
            )

        elif fill.side == "flat":
            # 1. Retrieve open position to close
            sel_stmt = (
                select(positions)
                .where(
                    (positions.c.symbol == fill.symbol)
                    & (positions.c.mode == mode)
                    & (positions.c.status == "open")
                )
                .order_by(positions.c.id.desc())
                .limit(1)
            )
            pos_row = conn.execute(sel_stmt).fetchone()

            if pos_row is not None:
                pos_data = pos_row._mapping
                pos_id = pos_data["id"]
                entry_price = pos_data["entry_price"]
                fees_total = (pos_data["fees_total"] or 0.0) + fill.fee
                realized_pnl = (fill.price - entry_price) * fill.qty

                # 2. Update position row in place
                upd_stmt = (
                    update(positions)
                    .where(positions.c.id == pos_id)
                    .values(
                        closed_ts=ts_str,
                        exit_price=fill.price,
                        realized_pnl=realized_pnl,
                        fees_total=fees_total,
                        status="closed",
                    )
                )
                conn.execute(upd_stmt)
            else:
                pos_id = None
                realized_pnl = 0.0
                logger.warning(f"Attempted exit for {fill.symbol} but no open position in DB.")

            # 3. Insert trade fill exit row
            trade_stmt = insert(trades).values(
                position_id=pos_id,
                ts=ts_str,
                mode=mode,
                symbol=fill.symbol,
                side="sell",
                qty=fill.qty,
                price=fill.price,
                fee=fill.fee,
                order_id=fill.order_id,
                strategy=strategy_name,
            )
            conn.execute(trade_stmt)
            logger.info(f"Tracked exit: {fill.symbol}, id={pos_id}, pnl={realized_pnl}")
            from tradecore.notifications.notifier import send_telegram_alert

            await send_telegram_alert(
                f"📤 *Fill (Exit)*\n"
                f"Symbol: `{fill.symbol}`\n"
                f"Side: `SELL`\n"
                f"Qty: `{fill.qty}`\n"
                f"Price: `${fill.price:.2f}`\n"
                f"Realized P&L: `${realized_pnl:.2f}`\n"
                f"Mode: `{mode.upper()}`"
            )

    # Write equity snapshot on every fill
    try:
        await save_equity_snapshot(mode)
    except Exception as e:
        logger.error(f"Failed to record equity snapshot on fill: {e}")


async def save_equity_snapshot(mode: str) -> None:
    """
    Saves a point-in-time snapshot of the portfolio equity.
    """
    from tradecore.execution.adapter import get_adapter
    from tradecore.store.repo import get_open_positions

    # Get balance
    adapter = get_adapter(mode)
    balance_dict = await adapter.get_balance()
    balance = balance_dict["balance"]

    # Sum mark-to-market value of open positions
    open_pos_value = 0.0
    open_pos = get_open_positions(mode)
    state = get_state()
    for pos in open_pos:
        symbol = pos["symbol"]
        price = state.get_ticker_price(symbol)
        if price is not None:
            open_pos_value += pos["qty"] * price

    equity = balance + open_pos_value
    ts_str = datetime.now(UTC).isoformat()

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            insert(equity_snapshots).values(
                ts=ts_str,
                mode=mode,
                balance=balance,
                equity=equity,
            )
        )
