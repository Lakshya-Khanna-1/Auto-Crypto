import pandas as pd

from tradecore.strategy.donchian_breakout import DonchianBreakoutStrategy
from tradecore.strategy.ema_trend_adx import EmaTrendAdxStrategy


def test_ema_trend_adx_strategy_crossovers():
    df = pd.read_parquet("tests/fixtures/candles_btc_1h.parquet")
    # Low adx_min to ensure it enters on a standard crossover
    strategy = EmaTrendAdxStrategy(
        ema_fast=9,
        ema_slow=26,
        atr_period=14,
        atr_stop_mult=3.0,
        adx_period=14,
        adx_min=10.0,
    )

    has_entered = False
    for i in range(60, 150):
        sliced_df = df.iloc[:i]
        signal = strategy.on_candle(sliced_df, position=None)
        if signal is not None and signal.side == "long":
            has_entered = True
            assert "cross" in signal.reason
            break

    assert has_entered, "Should have triggered long entry on crossover with low adx_min"


def test_ema_trend_adx_strategy_adx_filter():
    df = pd.read_parquet("tests/fixtures/candles_btc_1h.parquet")
    # Extremely high adx_min to ensure it blocks any crossover entries
    strategy = EmaTrendAdxStrategy(
        ema_fast=9,
        ema_slow=26,
        atr_period=14,
        atr_stop_mult=3.0,
        adx_period=14,
        adx_min=105.0,
    )

    for i in range(60, 150):
        sliced_df = df.iloc[:i]
        signal = strategy.on_candle(sliced_df, position=None)
        assert signal is None, "Should not enter since ADX check should fail on high min threshold"


def test_donchian_breakout_strategy_triggers():
    df = pd.read_parquet("tests/fixtures/candles_btc_1h.parquet")
    strategy = DonchianBreakoutStrategy(
        donchian_entry=10,
        donchian_exit=5,
        atr_period=14,
        atr_stop_mult=3.0,
    )

    has_breakout = False
    for i in range(15, 120):
        sliced_df = df.iloc[:i]
        signal = strategy.on_candle(sliced_df, position=None)
        if signal is not None and signal.side == "long":
            has_breakout = True
            assert "bar high" in signal.reason
            break

    assert has_breakout, "Should trigger a Donchian breakout on one of the historical candle closes"
