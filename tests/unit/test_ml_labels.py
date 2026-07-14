import pandas as pd

from tradecore.strategy.labels import compute_labels


def test_compute_labels_nan_tail():
    # Construct a sample sequence of length 50
    df = pd.DataFrame(
        {
            "open": [10.0] * 50,
            "high": [12.0] * 50,
            "low": [8.0] * 50,
            "close": [10.0] * 50,
            "atr": [1.0] * 50,
        }
    )

    lbls = compute_labels(df)
    assert len(lbls) == 50
    # Final 24 must be NaN
    assert lbls.iloc[-24:].isna().all()
    # Prior should not be NaN
    assert not lbls.iloc[:-24].isna().any()


def test_compute_labels_barrier_cross():
    # Construct a layout where target is hit
    # Close entry is 100, ATR is 5
    # Future close rises to 106 at i+5 (hits upper barrier)
    closes = [100.0] * 50
    # Modulate index 2 to go high
    closes[5] = 106.0

    df = pd.DataFrame(
        {
            "open": [100.0] * 50,
            "high": [100.0] * 50,
            "low": [100.0] * 50,
            "close": closes,
            "atr": [5.0] * 50,
        }
    )

    lbls = compute_labels(df)
    # Index 0 looks forward up to 24 candles.
    # At i=0 + 5 (index 5), close is 106 (>= 100 + 5 = 105).
    # Since it reaches 105 first, index 0 label should be 1.0.
    assert lbls.iloc[0] == 1.0

    # Test stop/lower loss hit
    closes_low = [100.0] * 50
    closes_low[3] = 94.0  # Under 95 threshold

    df_low = pd.DataFrame(
        {
            "open": [100.0] * 50,
            "high": [100.0] * 50,
            "low": [100.0] * 50,
            "close": closes_low,
            "atr": [5.0] * 50,
        }
    )

    lbls_low = compute_labels(df_low)
    assert lbls_low.iloc[0] == 0.0
