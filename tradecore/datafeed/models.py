from dataclasses import dataclass


@dataclass
class Candle:
    """
    Standard OHLCV candle model representation.
    """

    ts: int  # Unix timestamp in milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Ticker:
    """
    Real-time price ticker tracking.
    """

    symbol: str
    price: float
    received_at: float  # Unix timestamp in seconds
