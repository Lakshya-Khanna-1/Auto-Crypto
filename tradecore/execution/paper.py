import logging
import uuid
from datetime import UTC, datetime

from tradecore.core.config import get_settings
from tradecore.core.state import get_state
from tradecore.execution.adapter import ApprovedOrder, ExecutionAdapter, Fill
from tradecore.execution.tracker import track_fill
from tradecore.store.repo import get_kv, get_open_positions, set_kv

logger = logging.getLogger("tradecore.execution.paper")


class PaperAdapter(ExecutionAdapter):
    """
    Paper trading ExecutionAdapter simulating fills, slippage, fees,
    and persisting results to SQLite tables positions and trades.
    """

    def __init__(self) -> None:
        self._init_balance()

    def _init_balance(self) -> float:
        settings = get_settings()
        bal_str = get_kv("paper_balance")
        if bal_str is None:
            starting = settings.paper.starting_balance
            set_kv("paper_balance", str(starting))
            logger.info(f"Initialized paper balance to starting default: {starting}")
            return starting
        return float(bal_str)

    async def place(self, order: ApprovedOrder) -> Fill:
        settings = get_settings()
        state = get_state()

        # 1. Retrieve current cached ticker price and timestamp
        logger.info(
            f"Placing paper order: symbol={order.symbol}, side={order.side}, qty={order.qty}"
        )
        price = state.get_ticker_price(order.symbol)
        ts = state.get_ticker_time(order.symbol)
        current_time = datetime.now(UTC).timestamp()

        # 2. Assert availability and freshness of the pricing feed cache
        if price is None or price <= 0 or ts is None:
            raise ValueError(
                f"No price ticker available for symbol {order.symbol} to execute paper order."
            )

        max_stale = settings.risk.max_data_staleness_sec
        if (current_time - ts) > max_stale:
            raise ValueError(
                f"Ticker price is too stale to execute paper order: "
                f"elapsed={current_time - ts:.1f}s, max_stale={max_stale}s."
            )

        # 3. Calculate fees and slippage adjusted fill price of the transaction
        slippage = settings.paper.slippage_pct / 100.0
        fee_pct = settings.paper.fee_pct / 100.0

        if order.side == "long":
            fill_price = price * (1.0 + slippage)
            notional = order.qty * fill_price
            fee = notional * fee_pct
            total_cost = notional + fee

            # 4. Check paper balance constraints
            balance = self._init_balance()
            if balance < total_cost:
                raise ValueError(
                    f"Insufficient paper balance: cost={total_cost:.2f}, balance={balance:.2f}."
                )

            new_balance = balance - total_cost
        elif order.side == "flat":
            fill_price = price * (1.0 - slippage)
            notional = order.qty * fill_price
            fee = notional * fee_pct
            net_proceeds = notional - fee

            balance = self._init_balance()
            new_balance = balance + net_proceeds
        else:
            raise ValueError(f"Unsupported order side in PaperAdapter: {order.side}")

        # 5. Persist the updated balance in key-value store
        set_kv("paper_balance", str(new_balance))
        order_id = f"paper_{uuid.uuid4().hex[:12]}"

        fill = Fill(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            price=fill_price,
            fee=fee,
            ts=ts,
        )

        # 6. Record fill update to the database positions and trades tracker
        await track_fill(fill, stop_price=order.stop_price, mode="paper")

        logger.info(
            f"Paper order executed: id={order_id}, price={fill_price:.4f}, "
            f"fee={fee:.4f}, new_balance={new_balance:.2f}"
        )
        return fill

    async def flatten(self, symbol: str | None = None) -> list[Fill]:
        logger.info(f"Flattening paper positions for symbol: {symbol}")
        open_pos = get_open_positions("paper")
        fills = []

        for pos in open_pos:
            if symbol is None or pos["symbol"] == symbol:
                order = ApprovedOrder(
                    symbol=pos["symbol"],
                    side="flat",
                    qty=pos["qty"],
                )
                try:
                    fill = await self.place(order)
                    fills.append(fill)
                except Exception as e:
                    logger.error(f"Failed to place flattening order for {pos['symbol']}: {e}")
                    raise e
        return fills

    async def get_balance(self) -> dict:
        balance = self._init_balance()
        return {"balance": balance, "mode": "paper"}

    async def get_open_orders(self) -> list:
        # Fills are instant in paper mode, no open orders
        return []

    async def cancel_all(self) -> None:
        # Fills are instant, no open orders to cancel
        return
