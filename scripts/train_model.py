import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import precision_score, roc_auc_score

# Resolve workspace path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tradecore.backtest.runner import run_backtest
from tradecore.core.config import get_settings
from tradecore.store.candles import read
from tradecore.strategy.ema_trend import EMATrendStrategy
from tradecore.strategy.features import compute_features
from tradecore.strategy.labels import compute_labels


def main():
    parser = argparse.ArgumentParser(description="Model Trainer CLI")
    parser.add_argument("--symbols", default="all", help="Symbols comma separated or 'all'")
    parser.add_argument("--timeframe", default="1h", help="Timeframe, e.g. 1h")
    args = parser.parse_args()

    settings = get_settings()

    # Parse symbols
    if args.symbols.lower() == "all":
        symbols = settings.trading.symbols
    else:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    print(f"Loading data for symbols: {symbols}")

    all_dfs = []
    for sym in symbols:
        print(f"Reading candles for {sym} ({args.timeframe})...")
        df_candles = read(sym, args.timeframe)
        if df_candles.empty:
            print(f"Warning: No candles found for {sym}")
            continue

        print(f"Computing features and labels for {sym}...")
        df_feats = compute_features(df_candles)
        df_feats["label"] = compute_labels(df_feats)
        df_feats["symbol"] = sym

        all_dfs.append(df_feats)

    if not all_dfs:
        print("Error: No data available for any symbol. Aborting training.")
        sys.exit(1)

    df_full = pd.concat(all_dfs, ignore_index=True)
    # Sort chronologically
    df_full = df_full.sort_values(by="ts").reset_index(drop=True)

    # Filter NaN features or labels
    feature_cols = [
        "symbol",
        "ret_1",
        "ret_3",
        "ret_6",
        "ret_12",
        "ret_24",
        "ema20_dist",
        "ema50_dist",
        "rsi_14",
        "atr_pct",
        "volume_z",
        "body_range_ratio",
        "hl_range_pct",
        "hour_sin",
        "hour_cos",
        "day_sin",
        "day_cos",
    ]

    df_clean = df_full.dropna(subset=feature_cols + ["label"]).copy()
    df_clean["symbol"] = df_clean["symbol"].astype("category")

    if len(df_clean) < 1000:
        print(f"Error: Insufficient data rows ({len(df_clean)} rows). Need at least 1000 rows.")
        sys.exit(1)

    # Held-out split (most recent 90 days)
    max_ts = df_clean["ts"].max()
    heldout_cutoff = max_ts - (90 * 24 * 3600 * 1000)

    pre_heldout_df = df_clean[df_clean["ts"] < heldout_cutoff].copy()
    heldout_df = df_clean[df_clean["ts"] >= heldout_cutoff].copy()

    print(f"Total clean rows: {len(df_clean)}")
    print(f"Pre-heldout (training/val) rows: {len(pre_heldout_df)}")
    print(f"Held-out (test) rows: {len(heldout_df)}")

    # 1. 5-Fold Walk-Forward Cross Validation on pre-held-out set
    unique_ts = sorted(pre_heldout_df["ts"].unique())
    n_ts = len(unique_ts)
    part_size = n_ts // 6

    fold_results = []
    ml_threshold = settings.strategy.ml_threshold

    for f_idx in range(1, 6):
        train_ts_limit = unique_ts[f_idx * part_size]
        val_ts_limit = unique_ts[(f_idx + 1) * part_size] if f_idx < 5 else unique_ts[-1] + 1

        train_fold = pre_heldout_df[pre_heldout_df["ts"] < train_ts_limit]
        val_fold = pre_heldout_df[
            (pre_heldout_df["ts"] >= train_ts_limit) & (pre_heldout_df["ts"] < val_ts_limit)
        ]

        x_tr, y_tr = train_fold[feature_cols], train_fold["label"]
        x_va, y_va = val_fold[feature_cols], val_fold["label"]

        clf = lgb.LGBMClassifier(
            num_leaves=31,
            learning_rate=0.05,
            n_estimators=400,
            random_state=42,
            verbosity=-1,
        )

        callbacks = [lgb.early_stopping(50, verbose=False)]
        clf.fit(x_tr, y_tr, eval_set=[(x_va, y_va)], callbacks=callbacks)

        # Predict
        preds_prob = clf.predict_proba(x_va)[:, 1]
        auc = roc_auc_score(y_va, preds_prob)

        # Precision at threshold
        preds_bin = (preds_prob >= ml_threshold).astype(int)
        precision = precision_score(y_va, preds_bin, zero_division=0)
        simulated_trades = int(np.sum(preds_bin))

        fold_results.append(
            {
                "fold": f_idx,
                "train_rows": len(train_fold),
                "val_rows": len(val_fold),
                "auc": float(auc),
                "precision": float(precision),
                "simulated_trades": simulated_trades,
            }
        )
        print(
            f"Fold {f_idx} : Train rows={len(train_fold)}, Val rows={len(val_fold)}, "
            f"AUC={auc:.4f}, Precision={precision:.4f}, Trades={simulated_trades}"
        )

    # 2. Final Training on pre-held-out set (split 90% train, 10% validation chronologically)
    split_idx = int(len(pre_heldout_df) * 0.9)
    train_final = pre_heldout_df.iloc[:split_idx]
    val_final = pre_heldout_df.iloc[split_idx:]

    x_train_f, y_train_f = train_final[feature_cols], train_final["label"]
    x_val_f, y_val_f = val_final[feature_cols], val_final["label"]

    final_clf = lgb.LGBMClassifier(
        num_leaves=31,
        learning_rate=0.05,
        n_estimators=400,
        random_state=42,
        verbosity=-1,
    )
    final_clf.fit(
        x_train_f,
        y_train_f,
        eval_set=[(x_val_f, y_val_f)],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )

    # Evaluate on held-out set
    x_test, y_test = heldout_df[feature_cols], heldout_df["label"]
    test_probs = final_clf.predict_proba(x_test)[:, 1]

    test_auc = float(roc_auc_score(y_test, test_probs))
    test_preds_bin = (test_probs >= ml_threshold).astype(int)
    test_precision = float(precision_score(y_test, test_preds_bin, zero_division=0))
    test_trades = int(np.sum(test_preds_bin))

    print(
        f"\nHeld-out Test Set (90 days) Metrics: "
        f"AUC={test_auc:.4f}, Precision={test_precision:.4f}, Trades={test_trades}"
    )

    # 3. Save Model Files
    models_dir = Path("data") / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d")
    model_name = f"lgbm_{timestamp}.txt"
    model_path = models_dir / model_name
    latest_path = models_dir / "lgbm_latest.txt"

    final_clf.booster_.save_model(str(model_path))
    final_clf.booster_.save_model(str(latest_path))
    print(f"Model saved to {model_path} and copied to {latest_path}")

    # 4. Comparative Backtest on Held-Out Period (90 days) vs EMATrendStrategy
    # Since we saved the model to data/models/lgbm_latest.txt,
    # MLStrategy can now be instantiated successfully!
    from tradecore.strategy.ml_lgbm import MLStrategy

    # Gather backtest results for each symbol over heldout timeframe
    comparison_rows = []
    for sym in symbols:
        # Fetch raw candle slice matching heldout ts
        df_sym_candles = read(sym, args.timeframe)
        # Select chronological range of last 90 days
        heldout_start_ms = heldout_df[heldout_df["symbol"] == sym]["ts"].min()
        heldout_end_ms = heldout_df[heldout_df["symbol"] == sym]["ts"].max()

        if pd.isna(heldout_start_ms) or pd.isna(heldout_end_ms):
            continue

        df_slice_bt = df_sym_candles[
            (df_sym_candles["ts"] >= heldout_start_ms) & (df_sym_candles["ts"] <= heldout_end_ms)
        ].copy()

        if df_slice_bt.empty:
            continue

        print(f"Running comparative backtest for {sym} over {len(df_slice_bt)} candles...")

        # EMA Trend Backtest
        ema_res = run_backtest(
            df_slice_bt.copy(),
            symbol=sym,
            strategy_class=EMATrendStrategy,
            fast_period=settings.strategy.ema_fast,
            slow_period=settings.strategy.ema_slow,
            atr_period=settings.strategy.atr_period,
            atr_stop_mult=settings.strategy.atr_stop_mult,
        )

        # ML Strategy Backtest
        ml_res = run_backtest(
            df_slice_bt.copy(),
            symbol=sym,
            strategy_class=MLStrategy,
            model_path=str(latest_path),
            threshold=ml_threshold,
            atr_stop_mult=settings.strategy.atr_stop_mult,
        )

        comparison_rows.append(
            {
                "symbol": sym,
                "ema_return": ema_res["total_return_pct"],
                "ema_dd": ema_res["max_drawdown_pct"],
                "ml_return": ml_res["total_return_pct"],
                "ml_dd": ml_res["max_drawdown_pct"],
            }
        )

    # Top 15 Feature Importances
    importances = final_clf.feature_importances_
    feat_imp = sorted(
        zip(feature_cols, importances, strict=False), key=lambda x: x[1], reverse=True
    )[:15]

    # Label Balance in training set
    pos_labels = int(np.sum(pre_heldout_df["label"] == 1.0))
    neg_labels = int(np.sum(pre_heldout_df["label"] == 0.0))
    balance_pct = (pos_labels / len(pre_heldout_df)) * 100.0 if len(pre_heldout_df) > 0 else 0.0

    # Write Markdown Report
    report_path = models_dir / f"report_{timestamp}.md"

    with open(report_path, "w") as f_rep:
        f_rep.write(f"# LightGBM Model Training Report ({timestamp})\n\n")

        # Ranges
        start_date = datetime.fromtimestamp(df_clean["ts"].min() / 1000, tz=UTC).strftime(
            "%Y-%m-%d"
        )
        end_date = datetime.fromtimestamp(max_ts / 1000, tz=UTC).strftime("%Y-%m-%d")
        f_rep.write(f"- **Data Range**: {start_date} to {end_date}\n")
        f_rep.write(f"- **Target Timeframe**: {args.timeframe}\n")
        f_rep.write(
            f"- **Label Balance (Pre-heldout)**: {pos_labels} Positive (1), {neg_labels} Negative (0) [{balance_pct:.2f}% Positive]\n\n"  # noqa: E501
        )

        # Folds Table
        f_rep.write("## 1. Walk-Forward Cross Validation (5 Folds)\n\n")
        f_rep.write("| Fold | Train Rows | Val Rows | AUC | Precision | Simulated Trades |\n")
        f_rep.write("| --- | --- | --- | --- | --- | --- |\n")
        for fr in fold_results:
            f_rep.write(
                f"| {fr['fold']} | {fr['train_rows']} | {fr['val_rows']} | {fr['auc']:.4f} | {fr['precision']:.4f} | {fr['simulated_trades']} |\n"  # noqa: E501
            )
        f_rep.write("\n")

        # Held-out Test Set
        f_rep.write("## 2. Held-Out Final Test Set (Last 90 Days) Metrics\n\n")
        f_rep.write(f"- **Held-Out AUC**: {test_auc:.4f}\n")
        f_rep.write(f"- **Held-Out Precision**: {test_precision:.4f}\n")
        f_rep.write(f"- **Held-Out Simulated Trades**: {test_trades}\n\n")

        # Top 15 Feature Importances
        f_rep.write("## 3. Top 15 Feature Importances\n\n")
        f_rep.write("| Feature | Importance Score |\n")
        f_rep.write("| --- | --- |\n")
        for feat, imp in feat_imp:
            f_rep.write(f"| {feat} | {imp} |\n")
        f_rep.write("\n")

        # Strategy Switch Verification Comparison
        f_rep.write("## 4. Strategy Comparison on Held-Out Test Set (Last 90 Days)\n\n")
        f_rep.write(
            "| Symbol | EMA Return (%) | EMA Max DD (%) | ML Return (%) | ML Max DD (%) |\n"
        )
        f_rep.write("| --- | --- | --- | --- | --- |\n")
        for cr in comparison_rows:
            f_rep.write(
                f"| {cr['symbol']} | {cr['ema_return']:.2f}% | {cr['ema_dd']:.2f}% | {cr['ml_return']:.2f}% | {cr['ml_dd']:.2f}% |\n"  # noqa: E501
            )
        f_rep.write("\n")

        # Honesty Warning Clause
        f_rep.write("## Disclaimer & Honesty Clause\n\n")
        f_rep.write("> [!WARNING]\n")
        f_rep.write(
            "> Walk-forward metrics estimate past regularities only. A model that validates well can\n"  # noqa: E501
        )
        f_rep.write(
            "> still lose money in a new market regime. Paper-trade any newly activated model for at\n"  # noqa: E501
        )
        f_rep.write("> least the configured require_paper_days before considering live use.\n")

    print(f"\nFinal training report written to: {report_path}")


if __name__ == "__main__":
    main()
