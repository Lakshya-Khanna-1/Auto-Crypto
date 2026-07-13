from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Signal:
    symbol: str
    side: str  # "long" | "flat"
    confidence: float
    reason: str


@dataclass
class ApprovedOrder:
    symbol: str
    side: str
    qty: float
    order_type: str = "market"
    stop_price: float | None = None
    signal_id: int | None = None


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    fee: float
    ts: float


@dataclass
class Position:
    id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    stop_price: float | None
    opened_ts: float
    status: str = "open"


class ExecutionAdapter(ABC):
    @abstractmethod
    async def place(self, order: ApprovedOrder) -> Fill:
        raise NotImplementedError()

    @abstractmethod
    async def flatten(self, symbol: str | None = None) -> list[Fill]:
        raise NotImplementedError()

    @abstractmethod
    async def get_balance(self) -> dict:
        raise NotImplementedError()

    @abstractmethod
    async def get_open_orders(self) -> list:
        raise NotImplementedError()

    @abstractmethod
    async def cancel_all(self) -> None:
        raise NotImplementedError()


_adapters: dict[str, ExecutionAdapter] = {}


def get_adapter(mode) -> ExecutionAdapter:
    """
    Lazy singleton registry to retrieve the appropriate execution adapter.
    """
    global _adapters
    if hasattr(mode, "value"):
        mode = mode.value
    else:
        mode = str(mode)

    if "." in mode:
        mode = mode.split(".")[-1]
    mode = mode.lower()

    if mode not in _adapters:
        if mode == "paper":
            from tradecore.execution.paper import PaperAdapter

            _adapters[mode] = PaperAdapter()
        elif mode == "live":
            from tradecore.execution.live import LiveAdapter

            _adapters[mode] = LiveAdapter()
        else:
            raise ValueError(f"Unknown execution adapter mode: {mode}")
    return _adapters[mode]
