import pandas as pd

from tradecore.backtest.runner import run_backtest


def test_run_backtest_fixture():
    df = pd.read_parquet("tests/fixtures/candles_btc_1h.parquet")
    results = run_backtest(df, symbol="BTC/USDT", atr_stop_mult=3.0)

    # Basic validations
    assert isinstance(results, dict)
    assert "total_return_pct" in results
    assert "max_drawdown_pct" in results
    assert "sharpe_ratio" in results
    assert "win_rate_pct" in results
    assert "trades_count" in results
    assert "profit_factor" in results
    assert "buy_and_hold_return_pct" in results

    # The synthetic fixture has exactly 3 crossovers, resulting in trades
    assert results["trades_count"] > 0
