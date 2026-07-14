import numpy as np
import pandas as pd


def compute_labels(df: pd.DataFrame) -> pd.Series:
    """
    Compute binary labels for a historical candlesticks DataFrame based on the
    triple-barrier method. Meets exact spec:
    - Look forward up to 24 candles.
    - Label 1 if close reaches entry + 1xATR(t) before entry - 1xATR(t), else 0.
    - Set the final 24 candles to NaN (unknowable labels).
    """
    cols = {c.lower(): c for c in df.columns}
    if "close" not in cols:
        raise ValueError("Missing 'close' column in DataFrame")
    c_col = cols["close"]

    # Compute default ATR(14) if not already present
    if "atr" not in df.columns:
        from tradecore.strategy.features import compute_atr

        h_col = cols.get("high", "high")
        l_col = cols.get("low", "low")
        atr_series = compute_atr(df[h_col], df[l_col], df[c_col], 14)
    else:
        atr_series = df["atr"]

    closes = df[c_col].values
    atrs = atr_series.values
    n = len(df)
    labels = np.zeros(n, dtype=np.float64)

    for i in range(n):
        if i >= n - 24:
            labels[i] = np.nan
            continue

        entry_price = closes[i]
        atr_val = atrs[i]

        if pd.isna(atr_val) or atr_val <= 0:
            labels[i] = np.nan
            continue

        upper_barrier = entry_price + atr_val
        lower_barrier = entry_price - atr_val

        assigned = False
        for k in range(1, 25):
            future_close = closes[i + k]
            if future_close >= upper_barrier:
                labels[i] = 1.0
                assigned = True
                break
            elif future_close <= lower_barrier:
                labels[i] = 0.0
                assigned = True
                break

        if not assigned:
            labels[i] = 0.0

    return pd.Series(labels, index=df.index, name="label")
