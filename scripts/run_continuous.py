import argparse
import subprocess
import sys
import time
from datetime import UTC, datetime


def main():
    parser = argparse.ArgumentParser(
        description="Continuous 30-Day Platform Runner and Retraining Loop"
    )
    parser.add_argument(
        "--cycle-days",
        type=float,
        default=30.0,
        help="Number of days to trade before retraining the model (can be fractional for testing, e.g., 0.0007 for 1 minute)",  # noqa: E501
    )
    args = parser.parse_args()

    cycle_seconds = int(args.cycle_days * 24 * 3600)
    print(f"[{datetime.now(UTC).isoformat()}] Starting continuous loop.")
    print(f"Cycle duration: {args.cycle_days} days ({cycle_seconds} seconds)")

    while True:
        # 1. Start the trading process
        print(f"[{datetime.now(UTC).isoformat()}] Starting tradecore platform...")
        trading_proc = subprocess.Popen(
            [sys.executable, "-m", "tradecore"],
            stdout=None,  # Inherit stdout so user sees logs in terminal
            stderr=None,
        )

        # 2. Wait for the cycle duration
        print(
            f"[{datetime.now(UTC).isoformat()}] Platform running. Waiting for {args.cycle_days} days to complete cycle..."  # noqa: E501
        )
        try:
            # Sleep in 1-second chunks to allow CTRL+C interrupts
            slept = 0
            while slept < cycle_seconds:
                if trading_proc.poll() is not None:
                    print(
                        f"[{datetime.now(UTC).isoformat()}] Warning: Platform process stopped model early with exit code {trading_proc.returncode}!"  # noqa: E501
                    )
                    break
                time.sleep(1)
                slept += 1
        except KeyboardInterrupt:
            print(
                f"\n[{datetime.now(UTC).isoformat()}] Interrupt received. Shutting down platform..."  # noqa: E501
            )
            trading_proc.terminate()
            trading_proc.wait()
            sys.exit(0)

        # 3. Clean shutdown of the platform process
        print(f"[{datetime.now(UTC).isoformat()}] Cycle complete. Stopping platform...")
        trading_proc.terminate()
        try:
            trading_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print("Force killing platform process...")
            trading_proc.kill()
            trading_proc.wait()

        # 4. Retrain the LightGBM model
        print(f"[{datetime.now(UTC).isoformat()}] Starting model retraining...")
        try:
            retrain_proc = subprocess.run(
                [sys.executable, "scripts/train_model.py", "--symbols", "all", "--timeframe", "1h"],  # noqa: E501
                check=True,
            )
            print(
                f"[{datetime.now(UTC).isoformat()}] Model retraining complete (Exit code {retrain_proc.returncode})."  # noqa: E501
            )
        except subprocess.CalledProcessError as e:
            print(f"Error during retraining: {e}")
            print("Restarting next cycle with existing model...")

        print(
            f"[{datetime.now(UTC).isoformat()}] Beginning next trading cycle. SQLite database state persisted.\n"  # noqa: E501
        )


if __name__ == "__main__":
    main()
