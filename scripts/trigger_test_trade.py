import asyncio
import time

from tradecore.core.state import get_state
from tradecore.scheduler.jobs import strategy_tick_job
from tradecore.store import candles as candle_store


async def main():
    symbol = "BTC/USDT"
    timeframe = "5m"
    df = candle_store.read(symbol, timeframe)
    if len(df) < 50:
        print("Not enough candles, bootstrapping first...")
        from tradecore.scheduler.jobs import candle_sync_job

        await candle_sync_job()
        df = candle_store.read(symbol, timeframe)

    print(f"Current BTC/USDT 5m candle count: {len(df)}")

    # Set the historical closes to 62000 to drop Fast EMA below Slow EMA
    for i in range(len(df) - 30, len(df) - 1):
        df.loc[i, "close"] = 62000.0
        df.loc[i, "high"] = 62010.0
        df.loc[i, "low"] = 61990.0
        df.loc[i, "open"] = 62000.0

    # Spike the last candle to 70000 to force a golden cross
    df.loc[len(df) - 1, "close"] = 70000.0
    df.loc[len(df) - 1, "high"] = 70010.0
    df.loc[len(df) - 1, "low"] = 69990.0
    df.loc[len(df) - 1, "open"] = 70000.0

    # Update both the candle store and the local runner state price
    current_time = time.time()
    get_state().update_ticker(symbol, 70000.0, current_time)

    # Save modified series
    # Using append with matching timestamps will auto-replace the last 30 candles
    candle_store.append(symbol, timeframe, df)
    print("Forced golden cross crossover candle configuration saved.")

    # Run the strategy tick immediately
    print("Triggering strategy_tick_job execution...")
    await strategy_tick_job()
    print(
        "Verification execution complete. Open the dashboard to view the "
        "new position under Panel 6 / Positions tab."
    )


if __name__ == "__main__":
    asyncio.run(main())
