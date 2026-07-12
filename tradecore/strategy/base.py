from abc import ABC, abstractmethod

import pandas as pd

from tradecore.execution.adapter import Position, Signal


class Strategy(ABC):
    @abstractmethod
    def on_candle(self, df: pd.DataFrame, position: Position | None) -> Signal | None:
        """
        Evaluate historical candles and current position context to emit a Signal or None.
        """
        pass
