from tradecore.execution.adapter import ApprovedOrder, ExecutionAdapter, Fill


class LiveAdapter(ExecutionAdapter):
    """
    Live trading ExecutionAdapter stub. Replaced with exchange API interface in Milestone 7.
    """

    async def place(self, order: ApprovedOrder) -> Fill:
        raise NotImplementedError("LiveAdapter.place is not implemented in Paper mode.")

    async def flatten(self, symbol: str | None = None) -> list[Fill]:
        raise NotImplementedError("LiveAdapter.flatten is not implemented in Paper mode.")

    async def get_balance(self) -> dict:
        raise NotImplementedError("LiveAdapter.get_balance is not implemented in Paper mode.")

    async def get_open_orders(self) -> list:
        raise NotImplementedError("LiveAdapter.get_open_orders is not implemented in Paper mode.")

    async def cancel_all(self) -> None:
        raise NotImplementedError("LiveAdapter.cancel_all is not implemented in Paper mode.")
