import pandas as pd

from tradecore.execution.adapter import Position
from tradecore.strategy.ema_trend import EMATrendStrategy


def test_strategy_crossovers():
    # Load synthetic fixture
    df = pd.read_parquet("tests/fixtures/candles_btc_1h.parquet")

    strategy = EMATrendStrategy()

    # Step 1: Check no signals are emitted during initial consolidation (candles 0-99)
    for i in range(1, 100):
        sliced_df = df.iloc[:i]
        signal = strategy.on_candle(sliced_df, position=None)
        assert signal is None

    # Step 2: Crossover 1 Above (Buy) should occur at index 101
    # Note: on_candle expects history *including* the currently closed candle at index 101
    sliced_df = df.iloc[:102]  # index 101 is the 102nd row
    signal = strategy.on_candle(sliced_df, position=None)
    assert signal is not None
    assert signal.side == "long"
    assert "crossed_above" in signal.reason

    # Open a simulated position at close of index 101 (close is 102.0, ATR mult stop mult = 3)
    # ATR is calculated during on_candle. Let's calculate ATR value at index 101
    df_ind = strategy.compute_indicators(df.iloc[:102])
    atr_val = df_ind["atr"].iloc[-1]
    stop_price = df_ind["close"].iloc[-1] - 3.0 * atr_val

    pos = Position(
        id="pos_1",
        symbol="BTC/USDT",
        side="long",
        qty=1.0,
        entry_price=df_ind["close"].iloc[-1],
        stop_price=stop_price,
        opened_ts=df_ind["ts"].iloc[-1],
    )

    # Step 3: From index 102 to 225, no exits should fire under normal crossover conditions
    for i in range(103, 226):
        sliced_df = df.iloc[:i]
        # stop price is not touched because price is high (200.0)
        signal = strategy.on_candle(sliced_df, position=pos)
        assert signal is None

    # Step 4: Crossover 2 Below (Exit) should occur at index 226
    sliced_df = df.iloc[:227]  # index 226 is the 227th row
    signal = strategy.on_candle(sliced_df, position=pos)
    assert signal is not None
    assert signal.side == "flat"
    assert "crossed_below" in signal.reason

    # Clear position
    pos = None

    # Step 5: Crossover 3 Above (Buy) should occur at index 347
    sliced_df = df.iloc[:348]  # index 347 is the 348th row
    signal = strategy.on_candle(sliced_df, position=pos)
    assert signal is not None
    assert signal.side == "long"
    assert "crossed_above" in signal.reason


def test_strategy_atr_stop_loss():
    df = pd.read_parquet("tests/fixtures/candles_btc_1h.parquet")

    strategy = EMATrendStrategy()

    # Let's simulate a position at index 150 where close is 200.0
    # If we set stop_price higher than the current index 151 close (which is 200.0), e.g. stop_price = 205.0
    pos = Position(
        id="pos_2",
        symbol="BTC/USDT",
        side="long",
        qty=1.0,
        entry_price=200.0,
        stop_price=205.0,  # Explicitly higher to trigger immediate stop check
        opened_ts=0,
    )

    # At step 151, close is 200.0 which is < stop_price (205.0) -> Should trigger ATR stop hit
    sliced_df = df.iloc[:152]
    signal = strategy.on_candle(sliced_df, position=pos)
    assert signal is not None
    assert signal.side == "flat"
    assert "atr_stop_hit" in signal.reason
