from datetime import UTC, datetime

from sqlalchemy import func, insert, select, update

from tradecore.store.db import get_engine
from tradecore.store.schema import app_kv, killswitch_events, positions, signals


def get_kv(key: str) -> str | None:
    """
    Retrieve value for a given key from the app_kv SQLite storage.
    """
    engine = get_engine()
    with engine.connect() as conn:
        stmt = select(app_kv.c.value).where(app_kv.c.key == key)
        return conn.execute(stmt).scalar()


def set_kv(key: str, value: str) -> None:
    """
    Store or update key-value pair in app_kv SQLite storage.
    """
    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            # Check if entry already exists to decide between insert/update
            stmt_select = select(app_kv.c.value).where(app_kv.c.key == key)
            exists = conn.execute(stmt_select).scalar() is not None

            if exists:
                stmt_write = update(app_kv).where(app_kv.c.key == key).values(value=str(value))
            else:
                stmt_write = insert(app_kv).values(key=key, value=str(value))

            conn.execute(stmt_write)


def save_signal_log(
    symbol: str,
    side: str,
    confidence: float,
    executed: int,
    risk_decision: str,
    risk_reason: str,
    indicator_value: float | None = None,
) -> int:
    """
    Log a strategy signal run and its risk decision to the signals table.
    """
    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            stmt = insert(signals).values(
                timestamp=datetime.now(UTC),
                symbol=symbol,
                indicator_value=indicator_value,
                signal_type=side,
                executed=executed,
                confidence=confidence,
                risk_decision=risk_decision,
                risk_reason=risk_reason,
            )
            res = conn.execute(stmt)
            return res.inserted_primary_key[0]


def save_killswitch_log(
    reason: str,
    details_json: str,
    positions_flattened: bool,
) -> int:
    """
    Log a killswitch event to the killswitch_events table.
    """
    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            stmt = insert(killswitch_events).values(
                timestamp=datetime.now(UTC),
                reason=reason,
                resolved=0,
                resolved_time=None,
                details_json=details_json,
                positions_flattened=1 if positions_flattened else 0,
            )
            res = conn.execute(stmt)
            return res.inserted_primary_key[0]


def get_open_positions(mode: str) -> list[dict]:
    """
    Retrieve all open positions for a given trading mode.
    """
    engine = get_engine()
    with engine.connect() as conn:
        stmt = select(positions).where((positions.c.mode == mode) & (positions.c.status == "open"))
        rows = conn.execute(stmt).fetchall()
        # Convert row objects/mappings to dicts for clean usage
        return [dict(row._mapping) for row in rows]


def get_open_positions_count(mode: str) -> int:
    """
    Get the count of currently open positions for a given trading mode.
    """
    engine = get_engine()
    with engine.connect() as conn:
        stmt = (
            select(func.count())
            .select_from(positions)
            .where((positions.c.mode == mode) & (positions.c.status == "open"))
        )
        return conn.execute(stmt).scalar() or 0
