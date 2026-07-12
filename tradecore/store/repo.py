from sqlalchemy import insert, select, update

from tradecore.store.db import get_engine
from tradecore.store.schema import app_kv


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
