from datetime import UTC, datetime

from sqlalchemy import func, insert, select, update

from tradecore.store.db import get_engine
from tradecore.store.schema import (
    app_kv,
    equity_snapshots,
    killswitch_events,
    mode_changes,
    positions,
    signals,
    trades,
)


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


def save_mode_change_log(
    from_mode: str,
    to_mode: str,
    source: str,
    override_used: bool,
) -> int:
    """
    Log a trading mode transition event.
    """
    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            stmt = insert(mode_changes).values(
                timestamp=datetime.now(UTC),
                from_mode=from_mode,
                to_mode=to_mode,
                source=source,
                override_used=1 if override_used else 0,
            )
            res = conn.execute(stmt)
            return res.inserted_primary_key[0]


def get_trades_in_range(mode: str, start_ts: str, end_ts: str) -> list[dict]:
    """Retrieve trades executed within the specified time range."""
    engine = get_engine()
    with engine.connect() as conn:
        stmt = select(trades).where(
            (trades.c.mode == mode) & (trades.c.ts >= start_ts) & (trades.c.ts <= end_ts)
        )
        rows = conn.execute(stmt).fetchall()
        return [dict(row._mapping) for row in rows]


def get_positions_closed_in_range(mode: str, start_ts: str, end_ts: str) -> list[dict]:
    """Retrieve positions closed within the specified time range."""
    engine = get_engine()
    with engine.connect() as conn:
        stmt = select(positions).where(
            (positions.c.mode == mode)
            & (positions.c.status == "closed")
            & (positions.c.closed_ts >= start_ts)
            & (positions.c.closed_ts <= end_ts)
        )
        rows = conn.execute(stmt).fetchall()
        return [dict(row._mapping) for row in rows]


def get_rejected_signals_in_range(start_dt: datetime, end_dt: datetime) -> list[dict]:
    """Retrieve rejected signals logged within the specified time range."""
    engine = get_engine()
    with engine.connect() as conn:
        stmt = select(signals).where(
            (signals.c.risk_decision == "rejected")
            & (signals.c.timestamp >= start_dt)
            & (signals.c.timestamp <= end_dt)
        )
        rows = conn.execute(stmt).fetchall()
        return [dict(row._mapping) for row in rows]


def get_killswitch_events_in_range(start_dt: datetime, end_dt: datetime) -> list[dict]:
    """Retrieve killswitch events within the specified time range."""
    engine = get_engine()
    with engine.connect() as conn:
        stmt = select(killswitch_events).where(
            (killswitch_events.c.timestamp >= start_dt) & (killswitch_events.c.timestamp <= end_dt)
        )
        rows = conn.execute(stmt).fetchall()
        return [dict(row._mapping) for row in rows]


def get_equity_snapshot_closest_to(mode: str, target_ts: str, order: str = "desc") -> float | None:
    """Retrieve the equity value of the snapshot closest to target_ts."""
    engine = get_engine()
    with engine.connect() as conn:
        if order == "desc":
            stmt = (
                select(equity_snapshots.c.equity)
                .where((equity_snapshots.c.mode == mode) & (equity_snapshots.c.ts <= target_ts))
                .order_by(equity_snapshots.c.ts.desc())
                .limit(1)
            )
        else:
            stmt = (
                select(equity_snapshots.c.equity)
                .where((equity_snapshots.c.mode == mode) & (equity_snapshots.c.ts >= target_ts))
                .order_by(equity_snapshots.c.ts.asc())
                .limit(1)
            )

        val = conn.execute(stmt).scalar()
        if val is not None:
            return float(val)

        # Fallback if no matching snaps (e.g. get first/last available)
        stmt_fallback = (
            select(equity_snapshots.c.equity)
            .where(equity_snapshots.c.mode == mode)
            .order_by(
                equity_snapshots.c.ts.asc() if order == "asc" else equity_snapshots.c.ts.desc()
            )
            .limit(1)
        )
        fallback_val = conn.execute(stmt_fallback).scalar()
        return float(fallback_val) if fallback_val is not None else None


def get_unannotated_closed_positions(mode: str) -> list[dict]:
    """Retrieve closed positions that do not have any AI annotation yet."""
    engine = get_engine()
    with engine.connect() as conn:
        stmt = select(positions).where(
            (positions.c.mode == mode)
            & (positions.c.status == "closed")
            & (positions.c.annotation.is_(None))
        )
        rows = conn.execute(stmt).fetchall()
        return [dict(row._mapping) for row in rows]


def update_position_annotation(pos_id: int, text: str) -> None:
    """Update annotation column for a specific position."""
    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            stmt = update(positions).where(positions.c.id == pos_id).values(annotation=text)
            conn.execute(stmt)


def get_signal_reason_for_position(symbol: str, opened_ts_str: str) -> str | None:
    """Find the latest approved entry signal reason on or before opened_ts."""
    engine = get_engine()
    try:
        opened_dt = datetime.fromisoformat(opened_ts_str)
    except Exception:
        opened_dt = datetime.now(UTC)

    with engine.connect() as conn:
        stmt = (
            select(signals.c.risk_reason)
            .where(
                (signals.c.symbol == symbol)
                & (signals.c.risk_decision == "approved")
                & (signals.c.signal_type == "long")
                & (signals.c.timestamp <= opened_dt)
            )
            .order_by(signals.c.timestamp.desc())
            .limit(1)
        )

        return conn.execute(stmt).scalar()
