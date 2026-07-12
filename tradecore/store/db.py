from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

# Ensure database directory exists
DATABASE_DIR = Path("data") / "db"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = DATABASE_DIR / "tradecore.sqlite3"

# SQLite connection URL
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URL, connect_args={"timeout": 30}, echo=False)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore
    """
    Enforce WAL mode and foreign key constraints on every connection.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine() -> Engine:
    """
    Retrieve the global database engine.
    """
    return engine
