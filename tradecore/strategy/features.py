import numpy as np
import pandas as pd


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Wilder's exponential smoothing RSI calculation.
    """
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-12)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Wilder's Average True Range calculation.
    """
    close_prev = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - close_prev).abs(),
            (low - close_prev).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    return atr


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute features for a given historical candlesticks DataFrame.
    Supports both lowercase and uppercase column names case-independently.
    Returns a copy of the DataFrame with computed features and raw 'atr' column appended.
    """
    cols = {c.lower(): c for c in df.columns}
    required = ["open", "high", "low", "close", "volume"]
    for req in required:
        if req not in cols:
            raise ValueError(f"Missing required candle column: '{req}'")

    o_col = cols["open"]
    h_col = cols["high"]
    l_col = cols["low"]
    c_col = cols["close"]
    v_col = cols["volume"]

    df_out = df.copy()

    # Raw values
    close = df[c_col]
    high = df[h_col]
    low = df[l_col]
    open_val = df[o_col]
    volume = df[v_col]

    # 1. Returns over 1/3/6/12/24 candles
    for n in [1, 3, 6, 12, 24]:
        df_out[f"ret_{n}"] = close / close.shift(n) - 1.0

    # 2. EMA20/EMA50 distance from close (pct)
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    df_out["ema20_dist"] = (close - ema20) / ema20
    df_out["ema50_dist"] = (close - ema50) / ema50

    # 3. RSI(14)
    df_out["rsi_14"] = compute_rsi(close, 14)

    # 4. ATR(14) and ATR(14)/close (volatility pct)
    df_out["atr"] = compute_atr(high, low, close, 14)
    df_out["atr_pct"] = df_out["atr"] / (close + 1e-12)

    # 5. Rolling volume z-score(24)
    vol_mean = volume.rolling(window=24).mean()
    vol_std = volume.rolling(window=24).std(ddof=0)
    df_out["volume_z"] = (volume - vol_mean) / (vol_std + 1e-8)

    # 6. Candle body/range ratio
    body = (close - open_val).abs()
    total_range = high - low
    df_out["body_range_ratio"] = body / (total_range + 1e-8)

    # 7. High-low range pct
    df_out["hl_range_pct"] = total_range / (close + 1e-8)

    # 8-9. Hour-of-day and Day-of-week sin/cos
    ts_col = cols.get("ts", None)
    if ts_col is not None:
        dt = pd.to_datetime(df[ts_col], unit="ms", utc=True)
        # Hour of day (0-23)
        hour = dt.dt.hour
        df_out["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
        df_out["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
        # Day of week (0-6)
        dayofweek = dt.dt.dayofweek
        df_out["day_sin"] = np.sin(2 * np.pi * dayofweek / 7.0)
        df_out["day_cos"] = np.cos(2 * np.pi * dayofweek / 7.0)
    else:
        # Fallback if no timestamps (mostly unit test mock candles)
        df_out["hour_sin"] = 0.0
        df_out["hour_cos"] = 0.0
        df_out["day_sin"] = 0.0
        df_out["day_cos"] = 0.0

    return df_out
