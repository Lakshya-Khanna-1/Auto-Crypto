from sqlalchemy import insert, select

from tradecore.store.db import get_engine
from tradecore.store.schema import app_kv


def test_db_read_write():
    engine = get_engine()

    # Write a test key-value pair
    with engine.begin() as conn:
        # Clear existing keys first to keep test clean
        conn.execute(app_kv.delete())

        conn.execute(insert(app_kv).values(key="test_key", value="test_value"))

    # Read the key-value pair back
    with engine.connect() as conn:
        result = conn.execute(select(app_kv.c.value).where(app_kv.c.key == "test_key")).scalar()

    assert result == "test_value"
