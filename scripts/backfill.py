import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Add project root to sys.path to enable tradecore imports
sys.path.append(str(Path(__file__).parent.parent.resolve()))

import pandas as pd

from tradecore.datafeed.feed import get_data_feed
from tradecore.store import candles as candle_store


def parse_timeframe_to_ms(timeframe: str) -> int:
    """
    Parse timeframe string (e.g. 5m, 1h, 1d) to milliseconds.
    """
    unit = timeframe[-1]
    value = int(timeframe[:-1])
    if unit == "m":
        return value * 60 * 1000
    elif unit == "h":
        return value * 60 * 60 * 1000
    elif unit == "d":
        return value * 24 * 60 * 60 * 1000
    else:
        raise ValueError(f"Unknown timeframe unit: {unit}")


def run_backfill(symbol: str, timeframe: str, days: int) -> None:
    """
    Execute historical OHLCV data backfill.
    """
    feed = get_data_feed()
    timeframe_ms = parse_timeframe_to_ms(timeframe)
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (days * 24 * 60 * 60 * 1000)

    print(f"=== Starting Backfill Pipeline for {symbol} ===")
    print(f"Target Timeframe: {timeframe}")
    print(f"Backfill Period: {days} days")
    print(f"Start Timestamp: {datetime.fromtimestamp(start_ms/1000, tz=UTC)}")

    curr_since = start_ms
    calls_made = 0
    total_candles_fetched = 0

    # Pagination loop
    while curr_since < now_ms:
        calls_made += 1
        curr_dt = datetime.fromtimestamp(curr_since / 1000, tz=UTC)
        print(f"[{calls_made}] Fetching candles since: {curr_dt}")

        try:
            candles = feed.fetch_candles(symbol, timeframe, since=curr_since, limit=1000)
            if not candles:
                print("No more candles returned by exchange.")
                break

            df = pd.DataFrame(
                [
                    {
                        "ts": c.ts,
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                        "volume": c.volume,
                    }
                    for c in candles
                ]
            )

            # Atomic append and deduplicate logic
            candle_store.append(symbol, timeframe, df)
            total_candles_fetched += len(candles)

            # Advance timestamp index
            max_ts = df["ts"].max()
            next_since = max_ts + timeframe_ms
            if next_since <= curr_since:
                # Loop safety check
                break
            curr_since = next_since

            # Rate limits safety buffer helper
            sleep_sec = max(0.1, feed.client.rateLimit / 1000.0)
            time.sleep(sleep_sec)

        except Exception as e:
            print(f"Critical error on CCXT API lookup: {e}")
            raise e

    # Build and print the post-backfill gap reports
    final_df = candle_store.read(symbol, timeframe)
    if final_df.empty:
        print("Gap report: 0 gaps detected (Data store holds 0 records).")
        return

    diffs = final_df["ts"].diff().dropna()
    gaps = diffs[diffs != timeframe_ms]

    print("\n=== Backfill Summary ===")
    print(f"Total entries loaded: {len(final_df)}")
    print(f"Gap report: {len(gaps)} gaps detected.")
    if len(gaps) > 0:
        print(f"Gaps list details: {gaps.tolist()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Historical OHLCV Candle Backfill Script")
    parser.add_argument(
        "-s", "--symbol", type=str, required=True, help="Crypto asset pair (e.g. BTC/USDT)"
    )
    parser.add_argument(
        "-t", "--timeframe", type=str, default="1h", help="Candle timeframe (e.g. 5m, 1h)"
    )
    parser.add_argument(
        "-d", "--days", type=int, default=730, help="Days of history (default: 730)"
    )
    args = parser.parse_args()

    run_backfill(symbol=args.symbol, timeframe=args.timeframe, days=args.days)
