import numpy as np
import pandas as pd

from tradecore.strategy.features import compute_features


def test_compute_features_basic():
    # Build 50 mock candles
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=50, freq="1h").astype(int) // 10**6,
            "open": np.linspace(100, 150, 50),
            "high": np.linspace(102, 152, 50),
            "low": np.linspace(98, 148, 50),
            "close": np.linspace(101, 151, 50),
            "volume": np.linspace(1000, 2000, 50),
        }
    )

    df_feats = compute_features(df)

    assert "ret_1" in df_feats.columns
    assert "ret_24" in df_feats.columns
    assert "ema20_dist" in df_feats.columns
    assert "rsi_14" in df_feats.columns
    assert "atr" in df_feats.columns
    assert "atr_pct" in df_feats.columns
    assert "volume_z" in df_feats.columns
    assert "hour_sin" in df_feats.columns

    # Verify return calculation: ret_1 on index 1 should be close[1] / close[0] - 1
    expected_ret = df["close"].iloc[1] / df["close"].iloc[0] - 1.0
    assert np.isclose(df_feats["ret_1"].iloc[1], expected_ret)


def test_compute_features_shift_safety():
    # Verify that modifying the last element does not change feature outputs for historical indices
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=30, freq="1h").astype(int) // 10**6,
            "open": np.linspace(100, 130, 30),
            "high": np.linspace(102, 132, 30),
            "low": np.linspace(98, 128, 30),
            "close": np.linspace(101, 131, 30),
            "volume": np.linspace(1000, 2000, 30),
        }
    )

    df_base = compute_features(df.copy())

    # Mutate the last row of raw data
    df_mutated = df.copy()
    df_mutated.loc[29, "close"] = 999.0
    df_mutated.loc[29, "high"] = 1000.0

    df_mut = compute_features(df_mutated)

    # All features up to index 28 must be identical
    for col in df_base.columns:
        if col in ["ts", "open", "high", "low", "close", "volume"]:
            continue
        # Compare first 28 values
        pd.testing.assert_series_equal(
            df_base[col].iloc[:28],
            df_mut[col].iloc[:28],
            obj=f"Column: {col}",
        )
