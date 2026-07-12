from pathlib import Path

import pandas as pd


def generate_crossover_fixtures():
    # 500 candles
    n = 500
    close = [100.0] * n

    # Engineering 3 crossovers:
    # 1. Crossover above (Long entry)
    for idx in range(100, 150):
        close[idx] = 100.0 + (idx - 100) * 2.0

    for idx in range(150, 220):
        close[idx] = 200.0

    # 2. Crossover below (Exit)
    for idx in range(220, 270):
        close[idx] = 200.0 - (idx - 220) * 2.4

    for idx in range(270, 340):
        close[idx] = 80.0

    # 3. Crossover above (Long entry)
    for idx in range(340, 390):
        close[idx] = 80.0 + (idx - 340) * 2.4

    for idx in range(390, 500):
        close[idx] = 200.0

    # Construct dataframe columns
    start_ts = 1704067200000  # 2024-01-01 00:00:00 UTC
    ts = [start_ts + i * 3600 * 1000 for i in range(n)]

    df = pd.DataFrame(
        {
            "ts": ts,
            "open": [c - 0.5 for c in close],
            "high": [c + 1.0 for c in close],
            "low": [c - 1.0 for c in close],
            "close": close,
            "volume": [100.0] * n,
        }
    )

    # Double check calculations to verify count
    ef = df["close"].ewm(span=20, adjust=False).mean()
    es = df["close"].ewm(span=50, adjust=False).mean()

    diff = ef - es
    cross_above = (diff.shift(1) <= 0) & (diff > 0)
    cross_below = (diff.shift(1) >= 0) & (diff < 0)

    # First crossover above occurs around 100-110
    # Second crossover below occurs around 220-230
    # Third crossover above occurs around 340-350
    total_cross = cross_above.sum() + cross_below.sum()

    print(f"Generated synthetic fixture with {total_cross} crossovers:")
    print(f"Crossovers above at: {df.index[cross_above].tolist()}")
    print(f"Crossovers below at: {df.index[cross_below].tolist()}")

    assert total_cross == 3, f"Expected exactly 3 crossovers, got {total_cross}"

    # Save to parquet directory
    target_dir = Path("tests") / "fixtures"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "candles_btc_1h.parquet"

    # Enforce schema columns
    df["ts"] = df["ts"].astype("int64")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype("float64")

    df.to_parquet(target_file, index=False)
    print(f"File saved to: {target_file}")


if __name__ == "__main__":
    generate_crossover_fixtures()
