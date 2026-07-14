import asyncio
import logging
import time

import ccxt

from tradecore.core.config import get_settings
from tradecore.datafeed.feed import get_ccxt_client
from tradecore.execution.adapter import ApprovedOrder, ExecutionAdapter, Fill
from tradecore.execution.tracker import track_fill
from tradecore.store.repo import get_open_positions, set_kv

logger = logging.getLogger("tradecore.execution.live")


class LiveAdapter(ExecutionAdapter):
    """
    Live trading ExecutionAdapter utilizing CCXT client interface.
    """

    def __init__(self, exchange: ccxt.Exchange | None = None) -> None:
        self.exchange = exchange or get_ccxt_client()

    async def place(self, order: ApprovedOrder) -> Fill:
        logger.info(
            f"Placing live order: symbol={order.symbol}, side={order.side}, qty={order.qty}"
        )

        # 1. Load markets
        await self.exchange.load_markets()

        # 2. Get current ticker price
        ticker = await self.exchange.fetch_ticker(order.symbol)
        price = ticker.get("last") or ticker.get("close")
        if not price:
            raise ValueError(f"Could not retrieve ticker price for {order.symbol}")

        # 3. Precision round down amount
        qty = self.exchange.amount_to_precision(order.symbol, order.qty)
        qty = float(qty)

        # 4. Check min_notional limit
        market = self.exchange.market(order.symbol)
        min_cost = market.get("limits", {}).get("cost", {}).get("min", 0.0)
        if min_cost is None:
            min_cost = 0.0

        notional = qty * price
        if notional < min_cost:
            raise ValueError(
                f"Order notional {notional} is below the exchange limit "
                f"of {min_cost} for {order.symbol}"
            )

        # 5. Place market order
        side = "buy" if order.side == "long" else "sell"
        raw_order = await self.exchange.create_order(
            symbol=order.symbol,
            type="market",
            side=side,
            amount=qty,
        )

        # 6. Poll fill progress
        order_id = raw_order.get("id")
        if not order_id:
            raise ValueError(f"No order ID returned from exchange for symbol {order.symbol}")

        start_time = time.time()
        poll_interval = 1.0
        timeout = 30.0
        status_order = raw_order

        while True:
            status = status_order.get("status")
            if status == "closed":
                break
            elif status in ("canceled", "rejected"):
                raise ValueError(f"Order {order_id} was {status} by the exchange.")

            if time.time() - start_time > timeout:
                logger.warning(f"Order {order_id} timed out. Attempting to cancel...")
                try:
                    await self.exchange.cancel_order(order_id, order.symbol)
                except Exception as ce:
                    logger.error(f"Failed to cancel timed out order {order_id}: {ce}")
                raise TimeoutError(f"Order {order_id} execution timed out.")

            await asyncio.sleep(poll_interval)
            status_order = await self.exchange.fetch_order(order_id, order.symbol)

        # 7. Build Fill from actual filled qty/price/fee
        filled_qty = float(status_order.get("filled", qty))
        avg_price = float(status_order.get("average") or status_order.get("price") or price)

        fee_cost = 0.0
        fee = status_order.get("fee")
        if fee and isinstance(fee, dict):
            fee_cost = float(fee.get("cost", 0.0))
        elif status_order.get("fees") and isinstance(status_order["fees"], list):
            for f_info in status_order["fees"]:
                fee_cost += float(f_info.get("cost", 0.0))
        else:
            # Fallback to standard fee estimation if exchange doesn't return fee in fetch_order
            # standard maker/taker fee of 0.1%
            fee_cost = filled_qty * avg_price * 0.001

        ts = status_order.get("timestamp")
        ts_seconds = float(ts) / 1000.0 if ts is not None else time.time()

        fill = Fill(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            qty=filled_qty,
            price=avg_price,
            fee=fee_cost,
            ts=ts_seconds,
        )

        # 8. Record fill update to the database positions and trades tracker
        await track_fill(fill, stop_price=order.stop_price, mode="live")

        # 9. Refresh cached live balance from the exchange so the risk engine
        # never has to fall back to a fabricated equity figure.
        try:
            await self.get_balance()
        except Exception as e:
            logger.error(f"Failed to refresh live balance cache after fill: {e}")

        logger.info(
            f"Live order executed: id={order_id}, price={avg_price:.4f}, " f"fee={fee_cost:.4f}"
        )
        return fill

    async def flatten(self, symbol: str | None = None) -> list[Fill]:
        logger.info(f"Flattening live positions for symbol: {symbol}")
        open_pos = get_open_positions("live")
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
                    logger.error(f"Failed to place live flattening order for {pos['symbol']}: {e}")
                    raise e
        return fills

    async def get_balance(self) -> dict:
        settings = get_settings()
        base_curr = settings.trading.base_currency
        bal = await self.exchange.fetch_balance()

        total_val = 0.0
        if "total" in bal and base_curr in bal["total"]:
            total_val = float(bal["total"][base_curr])
        elif base_curr in bal and isinstance(bal[base_curr], dict) and "total" in bal[base_curr]:
            total_val = float(bal[base_curr]["total"])
        elif base_curr in bal:
            total_val = float(bal[base_curr])

        set_kv("live_balance", str(total_val))
        return {"balance": total_val, "mode": "live"}

    async def get_open_orders(self) -> list:
        settings = get_settings()
        all_orders = []
        for symbol in settings.trading.symbols:
            try:
                orders = await self.exchange.fetch_open_orders(symbol)
                all_orders.extend(orders)
            except Exception as e:
                logger.error(f"Failed to fetch open orders for {symbol}: {e}")
        return all_orders

    async def cancel_all(self) -> None:
        settings = get_settings()
        for symbol in settings.trading.symbols:
            try:
                orders = await self.exchange.fetch_open_orders(symbol)
                for o in orders:
                    await self.exchange.cancel_order(o["id"], symbol)
            except Exception as e:
                logger.error(f"Failed to cancel open orders for {symbol}: {e}")
