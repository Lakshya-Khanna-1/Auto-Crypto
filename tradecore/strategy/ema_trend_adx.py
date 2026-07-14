from __future__ import annotations

import pandas as pd

from tradecore.core.config import get_settings
from tradecore.execution.adapter import Position, Signal
from tradecore.strategy.base import Strategy


def _ema(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(span=period, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    cols = {c.lower(): c for c in df.columns}
    c_col = cols.get("close", "close")
    h_col = cols.get("high", "high")
    l_col = cols.get("low", "low")

    prev_close = df[c_col].shift(1)
    tr = pd.concat(
        [
            df[h_col] - df[l_col],
            (df[h_col] - prev_close).abs(),
            (df[l_col] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _adx(df: pd.DataFrame, period: int) -> pd.Series:
    """Wilder's ADX, plain pandas."""
    cols = {c.lower(): c for c in df.columns}
    h_col = cols.get("high", "high")
    l_col = cols.get("low", "low")

    up = df[h_col].diff()
    down = -df[l_col].diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down
    atr = _atr(df, period)
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


class EmaTrendAdxStrategy(Strategy):
    """EMA crossover entries gated by an ADX trend-strength filter."""

    name = "ema_trend_adx"

    def __init__(
        self,
        ema_fast: int | None = None,
        ema_slow: int | None = None,
        atr_period: int | None = None,
        atr_stop_mult: float | None = None,
        adx_period: int | None = None,
        adx_min: float | None = None,
    ) -> None:
        cfg = get_settings().strategy
        self.ema_fast = ema_fast if ema_fast is not None else cfg.ema_fast
        self.ema_slow = ema_slow if ema_slow is not None else cfg.ema_slow
        self.atr_period = atr_period if atr_period is not None else cfg.atr_period
        self.atr_stop_mult = atr_stop_mult if atr_stop_mult is not None else cfg.atr_stop_mult
        self.adx_period = adx_period if adx_period is not None else getattr(cfg, "adx_period", 14)
        self.adx_min = adx_min if adx_min is not None else getattr(cfg, "adx_min", 22.0)

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        cols = {c.lower(): c for c in df.columns}
        c_col = cols.get("close", "close")

        df_out = df.copy()
        df_out["ema_fast"] = df[c_col].ewm(span=self.ema_fast, adjust=False).mean()
        df_out["ema_slow"] = df[c_col].ewm(span=self.ema_slow, adjust=False).mean()
        df_out["atr"] = _atr(df, self.atr_period)
        df_out["adx"] = _adx(df, self.adx_period)
        return df_out

    def on_candle(self, df: pd.DataFrame, position: Position | None) -> Signal | None:
        min_rows = max(self.ema_slow, self.adx_period * 2) + 2
        if len(df) < min_rows:
            return None

        df_ind = self.compute_indicators(df)
        cols = {c.lower(): c for c in df_ind.columns}
        c_col = cols.get("close", "close")

        close = df_ind[c_col]
        fast = df_ind["ema_fast"]
        slow = df_ind["ema_slow"]
        adx = df_ind["adx"]
        atr = df_ind["atr"]

        crossed_up = fast.iloc[-1] > slow.iloc[-1] and fast.iloc[-2] <= slow.iloc[-2]
        crossed_down = fast.iloc[-1] < slow.iloc[-1] and fast.iloc[-2] >= slow.iloc[-2]
        trending = pd.notna(adx.iloc[-1]) and adx.iloc[-1] >= self.adx_min

        symbol = df_ind["symbol"].iloc[-1] if "symbol" in cols else df_ind.attrs.get("symbol", "UNKNOWN")

        if position is None:
            if crossed_up and trending:
                entry = float(close.iloc[-1])
                stop = entry - self.atr_stop_mult * float(atr.iloc[-1])
                return Signal(
                    symbol=symbol,
                    side="long",
                    confidence=1.0,
                    reason=(
                        f"ema{self.ema_fast}>ema{self.ema_slow} cross, "
                        f"ADX {adx.iloc[-1]:.1f}>={self.adx_min} | stop={stop:.2f}"
                    ),
                )
            return None

        # In position: exit on cross-down or close below stop.
        if crossed_down:
            return Signal(
                symbol=position.symbol,
                side="flat",
                confidence=1.0,
                reason=f"ema{self.ema_fast}<ema{self.ema_slow} cross",
            )
        if position.stop_price is not None and float(close.iloc[-1]) < position.stop_price:
            return Signal(
                symbol=position.symbol,
                side="flat",
                confidence=1.0,
                reason=f"close {close.iloc[-1]:.2f} < stop {position.stop_price:.2f}",
            )
        return None
