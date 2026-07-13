from tradecore.core.config import TradingMode, get_settings


class RuntimeState:
    """
    Monages the global mutable runtime state of the trading engine.
    """

    def __init__(self) -> None:
        self._current_mode: TradingMode = get_settings().trading.mode
        self._kill_switch_active: bool = False
        self._consecutive_rejections: int = 0
        self._daily_drawdown_pct: float = 0.0
        self._total_drawdown_pct: float = 0.0
        self._last_ticker_times: dict[str, float] = {}
        self._last_ticker_prices: dict[str, float] = {}

    def update_ticker(self, symbol: str, price: float, timestamp: float) -> None:
        """
        Update the cached price and timestamp of the last ticker.
        """
        self._last_ticker_times[symbol] = timestamp
        self._last_ticker_prices[symbol] = price

    def get_ticker_time(self, symbol: str) -> float | None:
        """
        Get the last cached ticker timestamp for a given symbol.
        """
        return self._last_ticker_times.get(symbol)

    def get_ticker_price(self, symbol: str) -> float | None:
        """
        Get the last cached ticker close price for a given symbol.
        """
        return self._last_ticker_prices.get(symbol)

    @property
    def current_mode(self) -> TradingMode:
        return self._current_mode

    def set_mode(self, mode: TradingMode) -> None:
        """
        Transition the system's trading mode.
        """
        self._current_mode = mode

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch_active

    def set_kill_switch(self, active: bool) -> None:
        """
        Activate or deactivate the risk management kill switch.
        """
        self._kill_switch_active = active

    @property
    def consecutive_rejections(self) -> int:
        return self._consecutive_rejections

    def increment_rejections(self) -> None:
        """
        Increment the consecutive exchange order rejection counter.
        """
        self._consecutive_rejections += 1

    def reset_rejections(self) -> None:
        """
        Reset the consecutive exchange order rejection counter.
        """
        self._consecutive_rejections = 0


# Global runtime state instance
_state = RuntimeState()


def get_state() -> RuntimeState:
    return _state
