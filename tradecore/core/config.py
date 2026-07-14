import os
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class TradingMode(str, Enum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"

    def __str__(self) -> str:
        return self.value


class TradingSettings(BaseModel):
    mode: TradingMode
    exchange: str
    symbols: list[str]
    timeframe: str
    base_currency: str


class PaperSettings(BaseModel):
    starting_balance: float
    fee_pct: float
    slippage_pct: float


class RiskSettings(BaseModel):
    risk_per_trade_pct: float
    max_open_positions: int
    max_total_exposure_pct: float
    max_daily_drawdown_pct: float
    max_total_drawdown_pct: float
    max_data_staleness_sec: int
    max_consecutive_rejections: int


class StrategySettings(BaseModel):
    name: str
    ml_model_path: str
    ml_threshold: float
    ema_fast: int
    ema_slow: int
    atr_period: int
    atr_stop_mult: float
    adx_period: int = 14
    adx_min: float = 22.0
    donchian_entry: int = 55
    donchian_exit: int = 20


class LiveGuardSettings(BaseModel):
    require_paper_trades: int
    require_paper_days: int
    allow_override: bool


class DashboardSettings(BaseModel):
    host: str
    port: int


class TelegramSettings(BaseModel):
    enabled: bool
    chat_id: str


class OllamaSettings(BaseModel):
    enabled: bool
    host: str
    main_model: str
    fast_model: str
    embed_model: str
    request_timeout_sec: int


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """
    Source class to load configuration from YAML.
    """

    def __init__(self, settings_cls: type[BaseSettings], config_path: Path):
        super().__init__(settings_cls)
        self.config_path = config_path

    def get_field_value(self, field, field_name: str) -> tuple[Any, str, bool]:
        # Not used, we override __call__
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            with open(self.config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}


class Settings(BaseSettings):
    trading: TradingSettings
    paper: PaperSettings
    risk: RiskSettings
    strategy: StrategySettings
    live_guard: LiveGuardSettings
    dashboard: DashboardSettings
    telegram: TelegramSettings
    ollama: OllamaSettings

    # Environment variables (secrets) mapped via validation aliases
    exchange_api_key: str | None = Field(default=None, validation_alias="EXCHANGE_API_KEY")
    exchange_api_secret: str | None = Field(default=None, validation_alias="EXCHANGE_API_SECRET")
    telegram_bot_token: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        config_path = Path(os.getenv("TRADECORE_CONFIG", "config/config.yaml"))
        yaml_source = YamlConfigSettingsSource(settings_cls, config_path)
        return init_settings, env_settings, dotenv_settings, yaml_source


# Global settings object cached after first load
_settings: Settings | None = None


def get_settings(force_reload: bool = False) -> Settings:
    global _settings
    if _settings is None or force_reload:
        _settings = Settings()
    return _settings
