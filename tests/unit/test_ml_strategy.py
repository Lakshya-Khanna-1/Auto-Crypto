import os

import numpy as np
import pandas as pd
import pytest

from tradecore.execution.adapter import Position
from tradecore.strategy.ml_lgbm import MLStrategy


def test_ml_strategy_missing_model():
    with pytest.raises(FileNotFoundError):
        MLStrategy(model_path="data/models/non_existent_model_file_xyz.txt")


def test_ml_strategy_on_candle():
    latest_model = "data/models/lgbm_latest.txt"
    if not os.path.exists(latest_model):
        pytest.skip(f"Model file {latest_model} not available for testing. Skip.")

    strat = MLStrategy(model_path=latest_model, threshold=0.5)

    # 1. Build a dummy series of candles of length 110
    dates = pd.date_range("2026-01-01", periods=110, freq="1h")
    df = pd.DataFrame(
        {
            "ts": dates.astype(int) // 10**6,
            "open": np.linspace(100, 110, 110),
            "high": np.linspace(101, 111, 110),
            "low": np.linspace(99, 109, 110),
            "close": np.linspace(100.5, 110.5, 110),
            "volume": np.linspace(1000, 2000, 110),
            "symbol": ["BTC/USDT"] * 110,
        }
    )

    # Check compute_indicators
    df_ind = strat.compute_indicators(df)
    assert "ret_24" in df_ind.columns
    assert "atr" in df_ind.columns

    # Check on_candle with no position
    sig = strat.on_candle(df, position=None)
    # The return should be either a Signal or None
    if sig is not None:
        assert sig.symbol == "BTC/USDT"
        assert sig.side in ["long", "flat"]

    # Check on_candle with trailing stop hit
    # entry_price is 100, stop_price is 150 (which is > current close 110.5)
    pos = Position(
        id="test_ml_pos",
        symbol="BTC/USDT",
        side="long",
        qty=1.0,
        entry_price=100.0,
        stop_price=150.0,
        opened_ts=0,
    )
    sig_stop = strat.on_candle(df, position=pos)
    assert sig_stop is not None
    assert sig_stop.side == "flat"
    assert sig_stop.reason == "atr_stop_hit"
