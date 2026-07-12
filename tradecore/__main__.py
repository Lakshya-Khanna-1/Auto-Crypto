import argparse
import os
import socket
import sys

import uvicorn
from sqlalchemy import text

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from tradecore.core.config import get_settings
from tradecore.core.logging import setup_logging
from tradecore.store.db import get_engine


def run_selfcheck() -> bool:
    """
    Perform a complete self-verification checklist: config loading, DB connectivity,
    WAL mode, Alembic migration alignment, and port bind availability.
    """
    print("Starting Self-Verification Checks...")

    # 1. Configuration load
    try:
        settings = get_settings()
        print(f"[-] Config load: OK (mode={settings.trading.mode.value})")
    except Exception as e:
        print(f"[X] Config load failed: {e}")
        return False

    # 2. DB Connectivity & WAL check
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1")).scalar()
            journal_mode = conn.execute(text("PRAGMA journal_mode")).scalar()

        if journal_mode.upper() != "WAL":
            print(f"[X] DB WAL check failed: journal_mode={journal_mode} (expected WAL)")
            return False

        print("[-] DB connectivity & WAL check: OK")
    except Exception as e:
        print(f"[X] DB connectivity check failed: {e}")
        return False

    # 3. Alembic migration check
    try:
        alembic_cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(alembic_cfg)
        head_revision = script.get_current_head()

        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()

        if current_rev != head_revision:
            print(
                f"[X] Alembic migration mismatch: DB revision={current_rev}, HEAD={head_revision}"
            )
            return False

        print(f"[-] Alembic migration context: OK (revision={current_rev})")
    except Exception as e:
        print(f"[X] Alembic migration check failed: {e}")
        return False

    # 4. Port binding availability
    try:
        host = settings.dashboard.host
        port = settings.dashboard.port
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.close()
        print(f"[-] Port binding check: OK ({host}:{port} is free to bind)")
    except OSError as e:
        print(f"[X] Port binding check failed: {port} on {host} is in use: {e}")
        return False

    print("Selfcheck Passed")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-Crypto Algorithmic Trading Platform")
    parser.add_argument(
        "--selfcheck", action="store_true", help="Run self-verification checks and exit"
    )
    parser.add_argument("--config", type=str, help="Path to custom config YAML file")

    args = parser.parse_args()

    # Configure custom config path environmental override
    if args.config:
        os.environ["TRADECORE_CONFIG"] = args.config

    if args.selfcheck:
        success = run_selfcheck()
        sys.exit(0 if success else 1)

    setup_logging(debug=False)
    settings = get_settings()

    print("Starting tradecore service...")
    uvicorn.run(
        "tradecore.app:app",
        host=settings.dashboard.host,
        port=settings.dashboard.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
