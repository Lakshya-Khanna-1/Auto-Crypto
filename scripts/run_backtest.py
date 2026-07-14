import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Resolve workspace path for direct execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tradecore.backtest.runner import run_backtest
from tradecore.store.candles import read


def parse_date(date_str: str) -> int:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
        return int(dt.timestamp() * 1000)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"Invalid date format: '{date_str}'. Expected 'YYYY-MM-DD'."
        ) from e


def format_metrics(m: dict) -> str:
    return (
        f"  Total Return:             {m['total_return_pct']:.2f}%\n"
        f"  Max Drawdown:             {m['max_drawdown_pct']:.2f}%\n"
        f"  Sharpe Ratio:             {m['sharpe_ratio']:.2f}\n"
        f"  Win Rate:                 {m['win_rate_pct']:.2f}%\n"
        f"  Trades Count:             {m['trades_count']}\n"
        f"  Profit Factor:            {m['profit_factor']:.2f}\n"
        f"  Buy & Hold Return:        {m['buy_and_hold_return_pct']:.2f}%\n"
        f"  Final Equity:             ${m['equity_final']:.2f}"
    )


def main():
    parser = argparse.ArgumentParser(description="Auto Crypto Backtest Runner Cli")
    parser.add_argument("--symbol", required=True, help="Target Symbol, e.g. BTC/USDT")
    parser.add_argument("--timeframe", default="1h", help="Timeframe, e.g. 1h")
    parser.add_argument("--start", type=parse_date, help="Start Date (YYYY-MM-DD)")
    parser.add_argument("--end", type=parse_date, help="End Date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, help="Historical Backfill limit in Days")
    parser.add_argument(
        "--strategy",
        default="ema_trend",
        choices=["ema_trend", "ml_lgbm", "ema_trend_adx", "donchian_breakout"],
        help="Strategy to run",
    )
    parser.add_argument(
        "--compare",
        nargs="?",
        const="all",
        default=None,
        help=(
            "Compare primary --strategy with comma-separated list of strategies "
            "(e.g. ema_trend,donchian_breakout)"
        ),
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="Run walk-forward simulation partitioned across 4 equal-sized folds",
    )

    args = parser.parse_args()

    # Determine start/end parameters
    start_ms = args.start
    end_ms = args.end

    if args.days is not None:
        if start_ms is not None:
            print("Warning: Both --start and --days specified. Prioritizing --days.")
        now = datetime.now(UTC)
        start_dt = now - timedelta(days=args.days)
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(now.timestamp() * 1000)

    # Read Parquet historical candle store
    print(f"Loading candles for {args.symbol} ({args.timeframe})...")
    df = read(args.symbol, args.timeframe, start=start_ms, end=end_ms)

    if df.empty:
        print(f"Error: No historical data loaded in storage for {args.symbol} {args.timeframe}.")
        sys.exit(1)

    print(f"Loaded {len(df)} candles.")

    from tradecore.core.config import get_settings

    settings = get_settings()

    def get_strat_helper(strat_name):
        if strat_name == "ml_lgbm":
            from tradecore.strategy.ml_lgbm import MLStrategy

            return MLStrategy, {
                "model_path": settings.strategy.ml_model_path,
                "threshold": settings.strategy.ml_threshold,
                "atr_stop_mult": settings.strategy.atr_stop_mult,
            }
        elif strat_name == "ema_trend_adx":
            from tradecore.strategy.ema_trend_adx import EmaTrendAdxStrategy

            return EmaTrendAdxStrategy, {
                "ema_fast": settings.strategy.ema_fast,
                "ema_slow": settings.strategy.ema_slow,
                "atr_period": settings.strategy.atr_period,
                "atr_stop_mult": settings.strategy.atr_stop_mult,
                "adx_period": settings.strategy.adx_period,
                "adx_min": settings.strategy.adx_min,
            }
        elif strat_name == "donchian_breakout":
            from tradecore.strategy.donchian_breakout import DonchianBreakoutStrategy

            return DonchianBreakoutStrategy, {
                "donchian_entry": settings.strategy.donchian_entry,
                "donchian_exit": settings.strategy.donchian_exit,
                "atr_period": settings.strategy.atr_period,
                "atr_stop_mult": settings.strategy.atr_stop_mult,
            }
        else:
            from tradecore.strategy.ema_trend import EMATrendStrategy

            return EMATrendStrategy, {
                "fast_period": settings.strategy.ema_fast,
                "slow_period": settings.strategy.ema_slow,
                "atr_period": settings.strategy.atr_period,
                "atr_stop_mult": settings.strategy.atr_stop_mult,
            }

    run_config = {
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "start_param": (
            datetime.fromtimestamp(start_ms / 1000, tz=UTC).isoformat() if start_ms else "None"
        ),
        "end_param": (
            datetime.fromtimestamp(end_ms / 1000, tz=UTC).isoformat() if end_ms else "None"
        ),
        "strategy": args.strategy,
        "compare": args.compare,
        "walk_forward": args.walk_forward,
    }

    results = {}

    if args.compare is not None:
        print("\nExecuting side-by-side Strategy Comparison...")
        if args.compare == "all":
            compare_strats = ["ema_trend", "ema_trend_adx", "donchian_breakout"]
        else:
            compare_strats = [s.strip() for s in args.compare.split(",")]
            if args.strategy not in compare_strats:
                compare_strats.append(args.strategy)

        compare_metrics = {}
        for sname in compare_strats:
            try:
                s_cls, s_params = get_strat_helper(sname)
                print(f"Running backtest for {sname}...")
                metrics = run_backtest(df, symbol=args.symbol, strategy_class=s_cls, **s_params)
                compare_metrics[sname] = metrics
            except Exception as e:
                print(f"Failed to run comparison backtest for strategy {sname}: {e}")

        for sname, metrics in compare_metrics.items():
            print(f"\n--- {sname} Performance ---")
            print(format_metrics(metrics))

        results["config"] = run_config
        results["comparison_metrics"] = compare_metrics

    elif args.walk_forward:
        print(f"Executing Walk-Forward Validation for {args.strategy} across 4 equal folds...")
        folds_metrics = []
        n = len(df)
        fold_size = n // 4

        strat_cls, strat_params = get_strat_helper(args.strategy)

        for i in range(4):
            s_idx = i * fold_size
            e_idx = (i + 1) * fold_size if i < 3 else n
            fold_df = df.iloc[s_idx:e_idx].reset_index(drop=True)

            fold_start_dt = datetime.fromtimestamp(fold_df["ts"].iloc[0] / 1000, tz=UTC)
            fold_end_dt = datetime.fromtimestamp(fold_df["ts"].iloc[-1] / 1000, tz=UTC)

            print(
                f"\n--- Fold {i+1} : {fold_start_dt.strftime('%Y-%m-%d')} to "
                f"{fold_end_dt.strftime('%Y-%m-%d')} ({len(fold_df)} candles) ---"
            )
            fold_results = run_backtest(
                fold_df, symbol=args.symbol, strategy_class=strat_cls, **strat_params
            )
            print(format_metrics(fold_results))

            folds_metrics.append(
                {
                    "fold": i + 1,
                    "start": fold_start_dt.strftime("%Y-%m-%d"),
                    "end": fold_end_dt.strftime("%Y-%m-%d"),
                    "metrics": fold_results,
                }
            )

        results["config"] = run_config
        results["folds"] = folds_metrics

    else:
        print(f"\nRunning Backtest for {args.strategy}...")
        strat_cls, strat_params = get_strat_helper(args.strategy)
        metrics = run_backtest(df, symbol=args.symbol, strategy_class=strat_cls, **strat_params)
        print("\n--- Performance Metrics Summary ---")
        print(format_metrics(metrics))

        results["config"] = run_config
        results["metrics"] = metrics

    # Save to disk
    out_dir = Path("data") / "backtests"
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    sym_sanitized = args.symbol.replace("/", "_")
    out_path = out_dir / f"backtest_{sym_sanitized}_{args.timeframe}_{timestamp}.json"

    with open(out_path, "w") as f:
        json.dump(results, f, indent=4)

    print(f"\nResults successfully written to: {out_path}")


if __name__ == "__main__":
    main()
