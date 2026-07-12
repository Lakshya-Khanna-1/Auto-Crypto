import pandas as pd
import pytest

from tradecore.store.candles import append, get_parquet_path, read


@pytest.fixture
def temp_candles_dir(tmp_path, monkeypatch):
    # Mock settings folder paths into pytest tmp_path
    def mock_get_parquet_path(symbol, timeframe):
        symbol_sanitized = symbol.upper().replace("/", "-")
        return tmp_path / "candles" / "binance" / symbol_sanitized / f"{timeframe}.parquet"

    monkeypatch.setattr("tradecore.store.candles.get_parquet_path", mock_get_parquet_path)
    return tmp_path


def test_parquet_path_generator():
    path = get_parquet_path("BTC/USDT", "1h")
    # Matches data/candles/binance/BTC-USDT/1h.parquet under default test settings
    assert "candles" in path.parts
    assert "binance" in path.parts
    assert "BTC-USDT" in path.parts
    assert "1h.parquet" in path.parts


def test_read_empty_parquet(temp_candles_dir):
    df = read("BTC/USDT", "1h")
    assert df.empty
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]


def test_append_and_read_parquet(temp_candles_dir):
    data_1 = {
        "ts": [1719878400000, 1719882000000],
        "open": [60000.0, 60500.0],
        "high": [61000.0, 61500.0],
        "low": [59500.0, 60000.0],
        "close": [60500.0, 61000.0],
        "volume": [10.0, 12.0],
    }
    df1 = pd.DataFrame(data_1)

    append("BTC/USDT", "1h", df1)

    df_read = read("BTC/USDT", "1h")
    assert len(df_read) == 2
    assert df_read["ts"].iloc[0] == 1719878400000
    assert df_read["close"].iloc[1] == 61000.0


def test_append_deduplicate_and_sort(temp_candles_dir):
    data_1 = {
        "ts": [1719882000000, 1719878400000],  # Out of order
        "open": [60500.0, 60000.0],
        "high": [61500.0, 61000.0],
        "low": [60000.0, 59500.0],
        "close": [61000.0, 60500.0],
        "volume": [12.0, 10.0],
    }
    df1 = pd.DataFrame(data_1)

    append("BTC/USDT", "1h", df1)

    # Append duplicate of the second timestamp with updated close value
    data_2 = {
        "ts": [1719882000000],
        "open": [60500.0],
        "high": [61500.0],
        "low": [60000.0],
        "close": [62000.0],  # Updated
        "volume": [13.0],
    }
    df2 = pd.DataFrame(data_2)

    append("BTC/USDT", "1h", df2)

    df_read = read("BTC/USDT", "1h")
    assert len(df_read) == 2
    # Verify sorting
    assert df_read["ts"].iloc[0] == 1719878400000
    assert df_read["ts"].iloc[1] == 1719882000000
    # Verify new data overwrote duplicate timestamp
    assert df_read["close"].iloc[1] == 62000.0


def test_read_filtering(temp_candles_dir):
    data = {
        "ts": [1000, 2000, 3000, 4000],
        "open": [1.0, 2.0, 3.0, 4.0],
        "high": [1.1, 2.1, 3.1, 4.1],
        "low": [0.9, 1.9, 2.9, 3.9],
        "close": [1.0, 2.0, 3.0, 4.0],
        "volume": [100.0, 200.0, 300.0, 400.0],
    }
    df = pd.DataFrame(data)
    append("BTC/USDT", "1h", df)

    # Filter with start
    df_start = read("BTC/USDT", "1h", start=2500)
    assert len(df_start) == 2
    assert list(df_start["ts"]) == [3000, 4000]

    # Filter with end
    df_end = read("BTC/USDT", "1h", end=2500)
    assert len(df_end) == 2
    assert list(df_end["ts"]) == [1000, 2000]

    # Filter with both start and end
    df_both = read("BTC/USDT", "1h", start=2000, end=3000)
    assert len(df_both) == 2
    assert list(df_both["ts"]) == [2000, 3000]
