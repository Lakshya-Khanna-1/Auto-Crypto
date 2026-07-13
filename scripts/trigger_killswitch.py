import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert, select

# Resolve project path in sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from tradecore.core.state import get_state
from tradecore.execution.adapter import ApprovedOrder
from tradecore.riskengine.killswitch import rearm_killswitch, trigger_killswitch
from tradecore.store.db import get_engine
from tradecore.store.schema import killswitch_events, positions

# Configure basic logging to console
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("trigger_killswitch")


class DummyAdapter:
    """
    Simulation adapter that removes open positions from database on flatten.
    """

    async def cancel_all(self):
        logger.info("[DummyAdapter] Canceling all active open orders.")

    async def flatten(self):
        logger.info("[DummyAdapter] Flattening all open positions.")
        # Clear positions from DB during simulation
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(positions.delete())
        logger.info("[DummyAdapter] Database positions cleared/flattened.")

    async def place(self, order: ApprovedOrder):
        logger.info(f"[DummyAdapter] Placed order: {order}")


async def main():
    logger.info("Initializing manual killswitch trigger simulation...")

    state = get_state()
    mode = state.current_mode.value
    logger.info(f"Current operating mode: {mode}")

    # Seed mock data in DB
    engine = get_engine()
    with engine.begin() as conn:
        # Clear old positions and events for clean tracking
        conn.execute(positions.delete())
        conn.execute(killswitch_events.delete())

        logger.info("Seeding test open positions into the database...")
        conn.execute(
            insert(positions).values(
                symbol="BTC/USDT",
                side="long",
                mode=mode,
                qty=0.05,
                entry_price=60000.0,
                entry_time=datetime.now(UTC),
                unrealized_pnl=0.0,
                stop_loss=58000.0,
            )
        )
        conn.execute(
            insert(positions).values(
                symbol="ETH/USDT",
                side="long",
                mode=mode,
                qty=1.5,
                entry_price=3000.0,
                entry_time=datetime.now(UTC),
                unrealized_pnl=0.0,
                stop_loss=2800.0,
            )
        )

    # Cache tickers in state
    state.update_ticker("BTC/USDT", 59500.0, datetime.now(UTC).timestamp())
    state.update_ticker("ETH/USDT", 2980.0, datetime.now(UTC).timestamp())

    # Double check our seed did insert positions
    with engine.connect() as conn:
        before_rows = conn.execute(select(positions)).fetchall()
        logger.info(f"Pre-killswitch open positions count: {len(before_rows)}")
        for r in before_rows:
            logger.info(f"  - Position: {r._mapping}")

    # Invoke killswitch trigger
    logger.info("Triggering killswitch now...")
    adapter = DummyAdapter()
    await trigger_killswitch(
        reason="Manual operator request via CLI trigger script", adapter=adapter
    )

    # Verify audit persistence
    with engine.connect() as conn:
        event_rows = conn.execute(select(killswitch_events)).fetchall()
        logger.info(f"Auditing database event logs: found {len(event_rows)} killswitch events.")
        for ev in event_rows:
            logger.info(f"  - Ev ID: {ev._mapping['id']}, Reason: {ev._mapping['reason']}")
            logger.info(f"  - Position flattened status: {ev._mapping['positions_flattened'] == 1}")
            logger.info(f"  - details: {json.loads(ev._mapping['details_json'])}")

        after_rows = conn.execute(select(positions)).fetchall()
        logger.info(f"Post-killswitch open positions count: {len(after_rows)}")

    # Verify manual re-arming
    logger.info("Resetting/re-arming killswitch configuration...")
    success = rearm_killswitch("RE-ARM")
    logger.info(f"Re-arm success (expected True): {success}")
    logger.info("Simulation run completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
