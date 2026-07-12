import pandas as pd

from tradecore.execution.adapter import Position, Signal
from tradecore.strategy.base import Strategy


class EMATrendStrategy(Strategy):
    def __init__(
        self,
        fast_period: int = 20,
        slow_period: int = 50,
        atr_period: int = 14,
        atr_stop_mult: float = 3.0,
    ) -> None:
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.atr_period = atr_period
        self.atr_stop_mult = atr_stop_mult

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute fast EMA, slow EMA, and ATR on the given DataFrame.
        Works with both lowercase (standard store) and uppercase (backtesting) column names.
        """
        # Create a mapping for case independence
        cols = {c.lower(): c for c in df.columns}
        required = ["close", "high", "low"]
        for req in required:
            if req not in cols:
                raise ValueError(f"Missing required column: '{req}'")

        c_col = cols["close"]
        h_col = cols["high"]
        l_col = cols["low"]

        df_out = df.copy()

        # Compute EMA
        df_out["ema_fast"] = df[c_col].ewm(span=self.fast_period, adjust=False).mean()
        df_out["ema_slow"] = df[c_col].ewm(span=self.slow_period, adjust=False).mean()

        # Compute ATR
        close_prev = df[c_col].shift(1)
        tr = pd.concat(
            [
                df[h_col] - df[l_col],
                (df[h_col] - close_prev).abs(),
                (df[l_col] - close_prev).abs(),
            ],
            axis=1,
        ).max(axis=1)

        df_out["atr"] = tr.ewm(alpha=1 / self.atr_period, adjust=False).mean()

        return df_out

    def on_candle(self, df: pd.DataFrame, position: Position | None) -> Signal | None:
        """
        Check for entry/exit crossover of EMA and ATR trailing stop hits.
        """
        if len(df) < self.slow_period:
            return None

        # Compute indicators
        df_ind = self.compute_indicators(df)

        close = df_ind["close" if "close" in df_ind.columns else "Close"].iloc[-1]
        curr_fast = df_ind["ema_fast"].iloc[-1]
        curr_slow = df_ind["ema_slow"].iloc[-1]
        prev_fast = df_ind["ema_fast"].iloc[-2]
        prev_slow = df_ind["ema_slow"].iloc[-2]

        crossed_above = (curr_fast > curr_slow) and (prev_fast <= prev_slow)
        crossed_below = (curr_fast < curr_slow) and (prev_fast >= prev_slow)

        # Detect symbol
        symbol = df_ind["symbol"].iloc[-1] if "symbol" in df_ind.columns else "UNKNOWN"

        if position is None:
            if crossed_above:
                return Signal(
                    symbol=symbol,
                    side="long",
                    confidence=1.0,
                    reason="ema_fast_crossed_above_ema_slow",
                )
        else:
            # Check exit conditions
            # 1. Trailing stop hit
            if position.stop_price is not None and close < position.stop_price:
                return Signal(
                    symbol=symbol,
                    side="flat",
                    confidence=1.0,
                    reason="atr_stop_hit",
                )

            # 2. Crossover below
            if crossed_below:
                return Signal(
                    symbol=symbol,
                    side="flat",
                    confidence=1.0,
                    reason="ema_fast_crossed_below_ema_slow",
                )

        return None
