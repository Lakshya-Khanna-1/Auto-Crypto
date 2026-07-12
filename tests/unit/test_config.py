import os
from unittest import mock
import pytest
from tradecore.core.config import get_settings, TradingMode

def test_load_default_settings():
    # Force reload with default Path configuration
    with mock.patch.dict(os.environ, {"TRADECORE_CONFIG": "config/config.yaml"}):
        settings = get_settings(force_reload=True)
        assert settings.trading.mode == TradingMode.PAPER
        assert settings.trading.exchange == "binance"
        assert "BTC/USDT" in settings.trading.symbols
        assert settings.paper.starting_balance == 10000.0
        assert settings.risk.risk_per_trade_pct == 1.0

def test_environment_overrides():
    custom_env = {
        "EXCHANGE_API_KEY": "test-key",
        "EXCHANGE_API_SECRET": "test-secret",
        "TELEGRAM_BOT_TOKEN": "test-token",
        "TRADECORE_CONFIG": "config/config.yaml"
    }

    with mock.patch.dict(os.environ, custom_env):
        settings = get_settings(force_reload=True)
        assert settings.exchange_api_key == "test-key"
        assert settings.exchange_api_secret == "test-secret"
        assert settings.telegram_bot_token == "test-token"
