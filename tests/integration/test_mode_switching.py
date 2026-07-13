import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tradecore.core.config import TradingMode, get_settings
from tradecore.core.state import get_state, switch_mode


@pytest.mark.asyncio
async def test_live_to_paper_direct():
    state = get_state()
    state.set_mode(TradingMode.LIVE)
    state.set_strategy_paused(False)

    settings = get_settings()
    settings.trading.mode = TradingMode.LIVE

    with (
        patch("tradecore.notifications.notifier.send_telegram_alert", AsyncMock()) as mock_alert,
        patch("tradecore.app.update_config_file_mode") as mock_update_cfg,
        patch("tradecore.store.repo.save_mode_change_log", return_value=1) as mock_audit,
    ):
        await switch_mode("paper")

        assert state.current_mode == TradingMode.PAPER
        mock_update_cfg.assert_called_once_with("paper")
        mock_audit.assert_called_once_with(
            from_mode="live", to_mode="paper", source="dashboard", override_used=False
        )
        mock_alert.assert_called_once()


@pytest.mark.asyncio
async def test_paper_to_live_blocked_on_confirmation():
    state = get_state()
    state.set_mode(TradingMode.PAPER)

    with pytest.raises(ValueError, match="Must type GO-LIVE"):
        await switch_mode("live", confirmation="NOT-CONFIRMED")


@pytest.mark.asyncio
async def test_paper_to_live_blocked_on_credentials():
    state = get_state()
    state.set_mode(TradingMode.PAPER)

    mock_ccxt = MagicMock()
    mock_ccxt.apiKey = None

    with patch("tradecore.datafeed.feed.get_ccxt_client", return_value=mock_ccxt):
        with pytest.raises(ValueError, match="live keys invalid"):
            await switch_mode("live", confirmation="GO-LIVE")


@pytest.mark.asyncio
async def test_paper_to_live_blocked_on_killswitch():
    state = get_state()
    state.set_mode(TradingMode.PAPER)
    state.set_kill_switch(True)

    mock_ccxt = MagicMock()
    mock_ccxt.apiKey = "key"
    mock_ccxt.secret = "secret"
    mock_ccxt.fetch_balance = AsyncMock()

    with patch("tradecore.datafeed.feed.get_ccxt_client", return_value=mock_ccxt):
        with pytest.raises(ValueError, match="Kill-switch is currently active"):
            await switch_mode("live", confirmation="GO-LIVE")


@pytest.mark.asyncio
async def test_paper_to_live_blocked_on_stale_data():
    state = get_state()
    state.set_mode(TradingMode.PAPER)
    state.set_kill_switch(False)

    settings = get_settings()
    settings.trading.symbols = ["BTC/USDT"]

    mock_ccxt = MagicMock()
    mock_ccxt.apiKey = "key"
    mock_ccxt.secret = "secret"
    mock_ccxt.fetch_balance = AsyncMock()

    with patch("tradecore.datafeed.feed.get_ccxt_client", return_value=mock_ccxt):
        # Mismatch: No ticker time cached in state -> raises stale feed error
        with pytest.raises(ValueError, match="No data feed active"):
            await switch_mode("live", confirmation="GO-LIVE")

        # Cache a stale ticker time
        state.update_ticker("BTC/USDT", 60000.0, time.time() - 600)  # 10 min stale
        with pytest.raises(ValueError, match="Stale data feed"):
            await switch_mode("live", confirmation="GO-LIVE")


@pytest.mark.asyncio
async def test_paper_to_live_blocked_on_history():
    state = get_state()
    state.set_mode(TradingMode.PAPER)
    state.set_kill_switch(False)
    state.update_ticker("BTC/USDT", 60000.0, time.time())

    settings = get_settings()
    settings.trading.symbols = ["BTC/USDT"]
    settings.live_guard.require_paper_trades = 20
    settings.live_guard.require_paper_days = 14
    settings.live_guard.allow_override = False

    mock_ccxt = MagicMock()
    mock_ccxt.apiKey = "key"
    mock_ccxt.secret = "secret"
    mock_ccxt.fetch_balance = AsyncMock()

    # DB stub returning 0 transactions
    with (
        patch("tradecore.datafeed.feed.get_ccxt_client", return_value=mock_ccxt),
        patch("tradecore.store.db.get_engine") as mock_get_engine,
    ):
        mock_conn = MagicMock()
        mock_conn.execute = MagicMock()
        # Return 0 index scalar count, and None min_ts
        mock_conn.execute.return_value.scalar.side_effect = [0, None]

        mock_get_engine.return_value.connect.return_value.__enter__.return_value = mock_conn

        with pytest.raises(ValueError, match="Paper trades history check failed"):
            await switch_mode("live", confirmation="GO-LIVE")


@pytest.mark.asyncio
async def test_paper_to_live_success_with_override():
    state = get_state()
    state.set_mode(TradingMode.PAPER)
    state.set_kill_switch(False)
    state.update_ticker("BTC/USDT", 60000.0, time.time())

    settings = get_settings()
    settings.trading.symbols = ["BTC/USDT"]
    settings.live_guard.require_paper_trades = 20
    settings.live_guard.require_paper_days = 14
    settings.live_guard.allow_override = True  # Enable override config

    mock_ccxt = MagicMock()
    mock_ccxt.apiKey = "key"
    mock_ccxt.secret = "secret"
    mock_ccxt.fetch_balance = AsyncMock()

    with (
        patch("tradecore.datafeed.feed.get_ccxt_client", return_value=mock_ccxt),
        patch("tradecore.store.db.get_engine") as mock_get_engine,
        patch("tradecore.notifications.notifier.send_telegram_alert", AsyncMock()) as mock_alert,
        patch("tradecore.app.update_config_file_mode") as mock_update_cfg,
        patch("tradecore.store.repo.save_mode_change_log", return_value=1) as mock_audit,
    ):
        mock_conn = MagicMock()
        mock_conn.execute = MagicMock()
        mock_conn.execute.return_value.scalar.side_effect = [0, None]
        mock_get_engine.return_value.connect.return_value.__enter__.return_value = mock_conn

        # Test switch with override checkbox ticked
        await switch_mode("live", confirmation="GO-LIVE", override=True)

        assert state.current_mode == TradingMode.LIVE
        mock_update_cfg.assert_called_once_with("live")
        mock_audit.assert_called_once_with(
            from_mode="paper", to_mode="live", source="dashboard", override_used=True
        )
        mock_alert.assert_called_once()
