# MLStrategy.md

Optional strategy built at M9, AFTER the core system is approved. Uses **LightGBM**
(gradient boosting) — NOT an LLM — trained **locally on the user's own backfilled
data**. The model file is produced by `scripts/train_model.py` on the user's server;
it is never shipped pre-trained. Add `lightgbm` and `scikit-learn` to requirements at M9.

## 1. Design summary
Binary classifier per candle: P(price rises ≥ 1×ATR before it falls 1×ATR within the
next 24 candles) — a triple-barrier-style label. The strategy enters long when
P ≥ `strategy.ml_threshold` and no position is open; exits on the opposite condition
or ATR stop (same stop mechanics as ema_trend). It plugs into the existing Strategy
ABC — the Risk Engine, adapters, and dashboard need ZERO changes.

## 2. Features (`strategy/features.py` — exact list, computed per closed candle)
Returns over 1/3/6/12/24 candles; EMA20/EMA50 distance from close (pct); RSI(14);
ATR(14)/close (volatility pct); rolling volume z-score(24); candle body/range ratio;
high-low range pct; hour-of-day (sin/cos encoded); day-of-week (sin/cos).
All features must be computable from OHLCV only (no external data), shift-safe
(no lookahead — every feature uses data up to and including the current CLOSED candle),
and identical between training and inference (single shared function).

## 3. Labels (`strategy/labels.py`)
For candle t: look forward up to 24 candles; label 1 if close reaches
entry + 1×ATR(t) before entry − 1×ATR(t), else 0; drop the final 24 candles of any
dataset (unknowable labels). Document label balance in the training report.

## 4. Training (`scripts/train_model.py`)
CLI: `python scripts/train_model.py --symbols all --timeframe 1h`
1. Load all configured symbols' Parquet history; build features+labels; concatenate
   with a `symbol` categorical feature.
2. **Walk-forward validation, never random split**: 5 sequential folds
   (train on past → validate on the next period). Report per fold: AUC, precision at
   the configured threshold, simulated trade count.
3. Train final model on all data except the most recent 90 days (held-out final test;
   report its metrics separately).
4. Save `data/models/lgbm_YYYYMMDD.txt` + copy to `lgbm_latest.txt`; write
   `data/models/report_YYYYMMDD.md` containing: folds table, held-out metrics, feature
   importances (top 15), label balance, data range, and the backtest comparison (§6).
5. Fixed sane hyperparameters in the script (num_leaves=31, lr=0.05, n_estimators=400,
   early stopping on fold validation). NO hyperparameter search in v1 — search
   multiplies overfitting risk and is FutureImprovements territory.

## 5. Inference (`strategy/ml_lgbm.py`)
`MLStrategy(Strategy)`: loads `ml_model_path` at startup (fail fast with a clear error
if missing → user must run training first). `on_candle`: build features for the latest
closed candle → predict → Signal(Long) if P ≥ threshold and flat; Signal(Flat) if in
position and P ≤ 1 − threshold; ATR stop identical to ema_trend. Prediction latency
is negligible (<10 ms); runs on CPU.

## 6. Activation gate (hard rule)
`run_backtest.py --strategy ml_lgbm --compare ema_trend` must run on every configured
symbol over the held-out period. The user may set `strategy.name: ml_lgbm` ONLY if the
comparison report shows ml_lgbm ≥ ema_trend on total return AND max drawdown not worse
by more than 20% relative. If it fails the gate, that is a valid, documented outcome —
ship the report, keep ema_trend active.

## 7. Retraining
Manual only in v1: user re-runs train_model.py monthly; the strategy picks up
`lgbm_latest.txt` on service restart. No auto-retraining (silent model drift into live
trading is dangerous).

## 8. Honesty clause (must appear in the training report footer)
"Walk-forward metrics estimate past regularities only. A model that validates well can
still lose money in a new market regime. Paper-trade any newly activated model for at
least the configured require_paper_days before considering live use."
