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
        # Stub: See Epic E5.T1 for full paper/live execution engine implementation
        raise NotImplementedError("ExecutionAdapter.place will be implemented in Epic E5.T1")

    @abstractmethod
    async def flatten(self, symbol: str | None = None) -> list[Fill]:
        # Stub: See Epic E5.T1 for full paper/live execution engine implementation
        raise NotImplementedError("ExecutionAdapter.flatten will be implemented in Epic E5.T1")

    @abstractmethod
    async def get_balance(self) -> dict:
        # Stub: See Epic E5.T1 for full paper/live execution engine implementation
        raise NotImplementedError("ExecutionAdapter.get_balance will be implemented in Epic E5.T1")
