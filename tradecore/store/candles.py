import os
import tempfile
from pathlib import Path

import pandas as pd

from tradecore.core.config import get_settings

REQUIRED_COLUMNS = ["ts", "open", "high", "low", "close", "volume"]


def get_parquet_path(symbol: str, timeframe: str) -> Path:
    """
    Construct the standardized Parquet file path for a symbol and timeframe.
    Path matches: data/candles/{exchange}/{symbol_sanitized}/{timeframe}.parquet
    """
    settings = get_settings()
    exchange = settings.trading.exchange.lower()
    symbol_sanitized = symbol.upper().replace("/", "-")
    return Path("data") / "candles" / exchange / symbol_sanitized / f"{timeframe}.parquet"


def read(
    symbol: str, timeframe: str, start: int | None = None, end: int | None = None
) -> pd.DataFrame:
    """
    Read historical OHLCV candles from the Parquet store.
    Returns:
        pd.DataFrame containing columns: ts (int64), open, high, low, close, volume (float64)
    """
    file_path = get_parquet_path(symbol, timeframe)
    if not file_path.exists():
        # Return empty DataFrame with defined columns and types
        df = pd.DataFrame(columns=REQUIRED_COLUMNS)
        df["ts"] = df["ts"].astype("int64")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype("float64")
        return df

    df = pd.read_parquet(file_path)

    # Filter by start & end timestamps if supplied
    if start is not None:
        df = df[df["ts"] >= start]
    if end is not None:
        df = df[df["ts"] <= end]

    return df.sort_values(by="ts").reset_index(drop=True)


def append(symbol: str, timeframe: str, df: pd.DataFrame) -> None:
    """
    Append and deduplicate candle DataFrame to Parquet store atomically.
    """
    if df.empty:
        return

    # Validate and filter dataset to conform with expected structure
    df = df[REQUIRED_COLUMNS].copy()

    # Enforce type definitions
    df["ts"] = df["ts"].astype("int64")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype("float64")

    file_path = get_parquet_path(symbol, timeframe)

    if file_path.exists():
        existing_df = pd.read_parquet(file_path)
        combined_df = pd.concat([existing_df, df], ignore_index=True)
    else:
        combined_df = df

    # Deduplicate keeping the latest version of any given timestamp, then sort
    combined_df = combined_df.drop_duplicates(subset=["ts"], keep="last")
    combined_df = combined_df.sort_values(by="ts").reset_index(drop=True)

    # Create target directory
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write to temp file on same volume followed by replaced rename
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=file_path.parent, suffix=".tmp", delete=False
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)

        combined_df.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, file_path)
    except Exception as e:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise e
