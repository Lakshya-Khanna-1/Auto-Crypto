# Backtesting.md

## 1. Purpose
Validate strategies on historical Parquet data before paper, and paper before live.
Uses `vectorbt`; the implementation model must not write custom portfolio math.

## 2. Runner (`backtest/runner.py` + `scripts/run_backtest.py`)
CLI: `python scripts/run_backtest.py --symbol BTC/USDT --timeframe 1h --start 2024-07-01 --end 2026-06-30`
1. Load candles from Parquet.
2. Generate entry/exit boolean series by running the SAME `strategy/ema_trend.py`
   logic over the DataFrame (strategies are pure → directly reusable).
3. `vbt.Portfolio.from_signals(close, entries, exits, fees=0.001, slippage=0.0005, init_cash=10000, sl_stop=<ATR stop as pct series>)`.
4. Output: JSON + printed table with total return %, max drawdown %, Sharpe, win rate,
   number of trades, profit factor, vs buy-and-hold return. Save JSON to `data/backtests/`.

## 3. Walk-forward check
`--walk-forward` flag: split range into 4 sequential folds; strategy params are FIXED
(from config, no optimization in v1 — optimization is FutureImprovements territory);
report per-fold metrics. Purpose: reveal regime sensitivity, not param fitting.

## 4. Acceptance gate used in Milestones.md
Baseline strategy must complete a 2-year backtest on BTC/USDT and ETH/USDT without
errors and produce ≥ 10 trades per symbol. (Profitability is NOT an acceptance
criterion — the gate verifies the machinery, not the alpha. The README must state
this explicitly to the user.)
