import pandas as pd
from backtesting import Backtest
from backtesting import Strategy as BtStrategy

from tradecore.execution.adapter import Position
from tradecore.strategy.ema_trend import EMATrendStrategy


class BacktestStrategyWrapper(BtStrategy):
    strategy_class = None
    strategy_params = {}
    data_full = None
    symbol = ""

    def init(self):
        self.strat = self.strategy_class(**self.strategy_params)
        self.curr_stop_price = None

    def next(self):
        # If position was closed internally (e.g. stopped out), reset local stop price tracker
        if not self.position:
            self.curr_stop_price = None

        # Slice input data to match index available at current step
        df_slice = self.data_full.iloc[: len(self.data)]

        # Map active position to standard tradecore representation
        current_position = None
        if self.position and len(self.trades) > 0:
            current_position = Position(
                id="backtest_pos",
                symbol=self.symbol,
                side="long",
                qty=self.position.size,
                entry_price=self.trades[0].entry_price,
                stop_price=self.curr_stop_price,
                opened_ts=0,
            )

        # Call the underlying strategy's on_candle check
        signal = self.strat.on_candle(df_slice, current_position)

        if signal is not None:
            if signal.side == "long" and not self.position:
                close_price = df_slice["Close"].iloc[-1]
                atr_val = df_slice["atr"].iloc[-1]
                # stop_price = entryPrice - atrStopMult * ATR
                stop_price = close_price - self.strat.atr_stop_mult * atr_val
                self.curr_stop_price = stop_price
                self.buy(sl=stop_price)
            elif signal.side == "flat" and self.position:
                self.position.close()
                self.curr_stop_price = None


def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    init_cash: float = 10000.0,
    commission: float = 0.001,
    spread: float = 0.0005,
    **strategy_params,
) -> dict:
    """
    Run backtest on a candle DataFrame for a specified symbol.
    """
    if df.empty:
        return {
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "win_rate_pct": 0.0,
            "trades_count": 0,
            "profit_factor": 0.0,
            "buy_and_hold_return_pct": 0.0,
            "equity_final": init_cash,
        }

    # Precalculate indicators
    strat_calc = EMATrendStrategy(**strategy_params)
    df_bt = strat_calc.compute_indicators(df)

    # Format column names for backtesting.py compatibility
    df_bt = df_bt.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
            "ts": "ts",
        }
    )
    df_bt.index = pd.to_datetime(df_bt["ts"], unit="ms")
    df_bt = df_bt.sort_index()

    # Define dedicated wrapper class
    class ActiveBtStrategy(BacktestStrategyWrapper):
        pass

    ActiveBtStrategy.strategy_class = EMATrendStrategy
    ActiveBtStrategy.strategy_params = strategy_params
    ActiveBtStrategy.data_full = df_bt
    ActiveBtStrategy.symbol = symbol

    bt = Backtest(
        df_bt,
        ActiveBtStrategy,
        cash=init_cash,
        commission=commission,
        spread=spread,
        finalize_trades=True,
    )

    stats = bt.run()

    # Convert Metrics
    metrics = {
        "total_return_pct": float(stats["Return [%]"]),
        "max_drawdown_pct": float(stats["Max. Drawdown [%]"]),
        "sharpe_ratio": (
            float(stats["Sharpe Ratio"])
            if not pd.isna(stats["Sharpe Ratio"])
            else 0.0
        ),
        "win_rate_pct": (
            float(stats["Win Rate [%]"])
            if not pd.isna(stats["Win Rate [%]"])
            else 0.0
        ),
        "trades_count": int(stats["# Trades"]),
        "profit_factor": (
            float(stats["Profit Factor"])
            if not pd.isna(stats["Profit Factor"])
            else 0.0
        ),
        "buy_and_hold_return_pct": float(stats["Buy & Hold Return [%]"]),
        "equity_final": float(stats["Equity Final [$]"]),
    }

    return metrics
