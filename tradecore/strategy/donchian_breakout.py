from __future__ import annotations

import pandas as pd

from tradecore.core.config import get_settings
from tradecore.execution.adapter import Position, Signal
from tradecore.strategy.base import Strategy


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    cols = {c.lower(): c for c in df.columns}
    c_col = cols.get("close", "close")
    h_col = cols.get("high", "high")
    l_col = cols.get("low", "low")

    pc = df[c_col].shift(1)
    tr = pd.concat(
        [df[h_col] - df[l_col], (df[h_col] - pc).abs(), (df[l_col] - pc).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


class DonchianBreakoutStrategy(Strategy):
    name = "donchian_breakout"

    def __init__(
        self,
        donchian_entry: int | None = None,
        donchian_exit: int | None = None,
        atr_period: int | None = None,
        atr_stop_mult: float | None = None,
    ) -> None:
        cfg = get_settings().strategy
        self.entry_n = (
            donchian_entry if donchian_entry is not None else getattr(cfg, "donchian_entry", 55)
        )
        self.exit_n = (
            donchian_exit if donchian_exit is not None else getattr(cfg, "donchian_exit", 20)
        )
        self.atr_period = atr_period if atr_period is not None else cfg.atr_period
        self.atr_stop_mult = atr_stop_mult if atr_stop_mult is not None else cfg.atr_stop_mult

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df_out = df.copy()
        df_out["atr"] = _atr(df, self.atr_period)
        return df_out

    def on_candle(self, df: pd.DataFrame, position: Position | None) -> Signal | None:
        if len(df) < self.entry_n + 2:
            return None

        cols = {c.lower(): c for c in df.columns}
        c_col = cols.get("close", "close")
        h_col = cols.get("high", "high")
        l_col = cols.get("low", "low")

        close = float(df[c_col].iloc[-1])
        # Channels exclude the current candle (no lookahead on itself).
        upper = float(df[h_col].iloc[-(self.entry_n + 1) : -1].max())
        lower = float(df[l_col].iloc[-(self.exit_n + 1) : -1].min())
        atr = float(_atr(df, self.atr_period).iloc[-1])

        symbol = df["symbol"].iloc[-1] if "symbol" in cols else df.attrs.get("symbol", "UNKNOWN")

        if position is None:
            if close > upper:
                stop = close - self.atr_stop_mult * atr
                return Signal(
                    symbol=symbol,
                    side="long",
                    confidence=1.0,
                    reason=(
                        f"close {close:.2f} > {self.entry_n}-bar high {upper:.2f} "
                        f"| stop={stop:.2f}"
                    ),
                )
            return None

        if close < lower:
            return Signal(
                symbol=position.symbol,
                side="flat",
                confidence=1.0,
                reason=f"close {close:.2f} < {self.exit_n}-bar low {lower:.2f}",
            )
        if position.stop_price is not None and close < position.stop_price:
            return Signal(
                symbol=position.symbol,
                side="flat",
                confidence=1.0,
                reason=f"close {close:.2f} < stop {position.stop_price:.2f}",
            )
        return None
