from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
from sqlalchemy import insert

from tradecore.ailayer.reports import build_report_context, generate_daily_report
from tradecore.store import repo
from tradecore.store.schema import equity_snapshots, positions, signals, trades


@pytest.fixture(autouse=True)
def temp_environment(monkeypatch, tmp_path):
    from sqlalchemy import create_engine

    from tradecore.store import db as store_db
    from tradecore.store.schema import metadata

    test_db_url = f"sqlite:///{tmp_path / 'test_trading.db'}"
    test_engine = create_engine(test_db_url, connect_args={"timeout": 30})
    metadata.create_all(test_engine)

    monkeypatch.setattr(store_db, "engine", test_engine)
    monkeypatch.setattr(store_db, "get_engine", lambda: test_engine)

    # Initialize app state
    from tradecore.core.state import get_state

    state = get_state()
    state._kill_switch_active = False
    state.reset_rejections()

    yield


def test_build_report_context():
    engine = repo.get_engine()

    # Seed yesterday's data
    with engine.begin() as conn:
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)
        yest_str = yesterday.strftime("%Y-%m-%dT12:00:00")

        # Closed position
        conn.execute(
            insert(positions).values(
                mode="paper",
                symbol="BTC/USDT",
                side="long",
                qty=1.5,
                entry_price=60000.0,
                exit_price=61000.0,
                opened_ts=yest_str,
                closed_ts=yest_str,
                realized_pnl=1500.0,
                fees_total=25.0,
                status="closed",
                annotation=None,
            )
        )

        # Trade
        conn.execute(
            insert(trades).values(
                position_id=1,
                ts=yest_str,
                mode="paper",
                symbol="BTC/USDT",
                side="long",
                qty=1.5,
                price=60000.0,
                fee=12.5,
                order_id="order-123",
                strategy="ema_trend",
            )
        )

        # Rejected signal
        conn.execute(
            insert(signals).values(
                timestamp=yesterday,
                symbol="ETH/USDT",
                signal_type="long",
                executed=0,
                confidence=0.8,
                risk_decision="rejected",
                risk_reason="max_positions_exceeded",
            )
        )

        # Equity snapshots
        conn.execute(
            insert(equity_snapshots).values(
                ts=yesterday.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
                mode="paper",
                balance=10000.0,
                equity=10000.0,
            )
        )
        conn.execute(
            insert(equity_snapshots).values(
                ts=yesterday.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat(),
                mode="paper",
                balance=11500.0,
                equity=11500.0,
            )
        )

    ctx = build_report_context("paper")

    assert ctx["mode"] == "paper"
    assert ctx["starting_equity"] == 10000.0
    assert ctx["ending_equity"] == 11500.0
    assert ctx["equity_change"] == 1500.0
    assert ctx["realized_pnl"] == 1500.0
    assert ctx["trades_count"] == 1
    assert len(ctx["trades"]) == 1
    assert ctx["trades"][0]["symbol"] == "BTC/USDT"
    assert len(ctx["rejections"]) == 1
    assert ctx["rejections"][0]["symbol"] == "ETH/USDT"
    assert ctx["rejections"][0]["reason"] == "max_positions_exceeded"


@pytest.mark.asyncio
async def test_generate_daily_report():
    with mock.patch(
        "tradecore.ailayer.reports.generate_response", new_callable=mock.AsyncMock
    ) as mock_gen:
        mock_gen.return_value = "Mocked AI report text"
        res = await generate_daily_report("paper")
        assert res == "Mocked AI report text"
