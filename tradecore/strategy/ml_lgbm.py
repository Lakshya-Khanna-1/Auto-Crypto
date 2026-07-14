import os

import lightgbm as lgb
import pandas as pd

from tradecore.core.config import get_settings
from tradecore.execution.adapter import Position, Signal
from tradecore.strategy.base import Strategy
from tradecore.strategy.features import compute_features


class MLStrategy(Strategy):
    feature_cols = [
        "symbol",
        "ret_1",
        "ret_3",
        "ret_6",
        "ret_12",
        "ret_24",
        "ema20_dist",
        "ema50_dist",
        "rsi_14",
        "atr_pct",
        "volume_z",
        "body_range_ratio",
        "hl_range_pct",
        "hour_sin",
        "hour_cos",
        "day_sin",
        "day_cos",
    ]

    def __init__(
        self,
        model_path: str | None = None,
        threshold: float | None = None,
        atr_stop_mult: float | None = None,
    ) -> None:
        settings = get_settings()

        # Prioritize params, fallback to settings configs
        self.model_path = model_path or settings.strategy.ml_model_path
        self.threshold = threshold or settings.strategy.ml_threshold
        self.atr_stop_mult = atr_stop_mult or settings.strategy.atr_stop_mult

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"Model file not found at {self.model_path}. "
                "Please run model training first: python scripts/train_model.py"
            )

        self.model = lgb.Booster(model_file=str(self.model_path))

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all required indicators and ML features.
        """
        return compute_features(df)

    def on_candle(self, df: pd.DataFrame, position: Position | None) -> Signal | None:
        """
        Standard inference handler.
        """
        if len(df) < 100:
            return None

        # Clean/Compute indicators
        df_ind = self.compute_indicators(df)
        row = df_ind.iloc[-1]

        # Extract context variables
        cols = {c.lower(): c for c in df_ind.columns}
        c_col = cols["close"]
        close = row[c_col]
        symbol = row["symbol"] if "symbol" in df_ind.columns else "UNKNOWN"

        # Prepare X input dataframe with 1 row
        row_dict = {}
        for col in self.feature_cols:
            if col == "symbol":
                row_dict["symbol"] = symbol
            else:
                row_dict[col] = row.get(col, 0.0)

        x = pd.DataFrame([row_dict])
        x["symbol"] = x["symbol"].astype("category")

        # Perform LightGBM prediction
        # booster.predict returns probability of class 1 directly
        p_val = self.model.predict(x)[0]

        if position is None:
            if p_val >= self.threshold:
                return Signal(
                    symbol=symbol,
                    side="long",
                    confidence=float(p_val),
                    reason=f"ml_prob_{p_val:.4f}_above_threshold",
                )
        else:
            # Check exit conditions
            # 1. Trailing stop check
            if position.stop_price is not None and close < position.stop_price:
                return Signal(
                    symbol=symbol,
                    side="flat",
                    confidence=1.0,
                    reason="atr_stop_hit",
                )

            # 2. Exit crossover condition (P <= 1 - threshold)
            if p_val <= (1.0 - self.threshold):
                return Signal(
                    symbol=symbol,
                    side="flat",
                    confidence=float(p_val),
                    reason=f"ml_prob_{p_val:.4f}_below_exit_threshold",
                )

        return None
