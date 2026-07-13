import logging
from datetime import UTC, datetime

from tradecore.core.config import TradingMode, get_settings
from tradecore.core.state import get_state
from tradecore.execution.adapter import ApprovedOrder, Signal
from tradecore.riskengine.sizing import calculate_position_size
from tradecore.store.repo import (
    get_kv,
    get_open_positions,
    get_open_positions_count,
    save_signal_log,
    set_kv,
)

logger = logging.getLogger("tradecore.riskengine.engine")


def get_portfolio_equity(mode: str) -> float:
    """
    Calculate the total equity: balance + unrealized PnL.
    """
    settings = get_settings()
    if mode == "paper":
        balance_str = get_kv("paper_balance")
        balance = float(balance_str) if balance_str is not None else settings.paper.starting_balance
    else:
        balance_str = get_kv("live_balance")
        balance = float(balance_str) if balance_str is not None else 10000.0

    # Sum unrealized PnL
    unrealized_pnl = 0.0
    open_positions = get_open_positions(mode)
    for pos in open_positions:
        symbol = pos["symbol"]
        price = get_state().get_ticker_price(symbol)
        if price is not None:
            unrealized_pnl += pos["qty"] * (price - pos["entry_price"])

    return balance + unrealized_pnl


def update_and_get_drawdowns(mode: str, equity: float) -> tuple[float, float]:
    """
    Update Daily and Total High-Water Marks, returning (daily_drawdown_pct, total_drawdown_pct).
    """
    daily_hwm_key = f"daily_hwm_{mode}"
    total_hwm_key = f"total_hwm_{mode}"

    # Self-healing check for midnight HWM reset
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    date_key = f"daily_hwm_date_{mode}"
    last_reset_date = get_kv(date_key)

    if last_reset_date != today_str:
        daily_hwm = equity
        set_kv(daily_hwm_key, str(daily_hwm))
        set_kv(date_key, today_str)
    else:
        daily_hwm_str = get_kv(daily_hwm_key)
        if daily_hwm_str is not None:
            daily_hwm = max(float(daily_hwm_str), equity)
        else:
            daily_hwm = equity
        set_kv(daily_hwm_key, str(daily_hwm))

    total_hwm_str = get_kv(total_hwm_key)
    if total_hwm_str is not None:
        total_hwm = max(float(total_hwm_str), equity)
    else:
        total_hwm = equity
    set_kv(total_hwm_key, str(total_hwm))

    # Avoid zero division
    daily_dd = ((daily_hwm - equity) / daily_hwm * 100.0) if daily_hwm > 0 else 0.0
    total_dd = ((total_hwm - equity) / total_hwm * 100.0) if total_hwm > 0 else 0.0

    return daily_dd, total_dd


def get_current_exposure(mode: str) -> float:
    """
    Sum the notional value of all open positions.
    """
    open_positions = get_open_positions(mode)
    exposure = 0.0
    for pos in open_positions:
        symbol = pos["symbol"]
        price = get_state().get_ticker_price(symbol)
        if price is None:
            price = pos["entry_price"]
        exposure += pos["qty"] * price
    return exposure


def approve(
    signal: Signal, stop_price: float | None = None, db_session=None
) -> tuple[bool, str, ApprovedOrder | None]:
    """
    Evaluate strategy signal against all defined risk engine criteria.

    Returns:
      tuple: (approved: bool, reason: str, order: ApprovedOrder | None)
    """
    settings = get_settings()
    state = get_state()
    mode = state.current_mode.value

    # 1. Kill-switch check
    killswitch_active = state.kill_switch_active or (get_kv("killswitch") == "triggered")
    if killswitch_active:
        reason = "killswitch_active"
        save_signal_log(signal.symbol, signal.side, signal.confidence, 0, "rejected", reason)
        return False, reason, None

    # 2. Data feed staleness check
    max_stale = settings.risk.max_data_staleness_sec
    last_tick_time = state.get_ticker_time(signal.symbol)
    current_time = datetime.now(UTC).timestamp()

    if last_tick_time is None or (current_time - last_tick_time) > max_stale:
        reason = "data_feed_stale"
        save_signal_log(signal.symbol, signal.side, signal.confidence, 0, "rejected", reason)
        return False, reason, None

    # 3. Skip check for Backtests
    if state.current_mode == TradingMode.BACKTEST:
        # Standard exit or entry approval in backtest mode bypassed
        order = ApprovedOrder(
            symbol=signal.symbol,
            side=signal.side,
            qty=0.0,  # backtester computes size
            stop_price=stop_price,
        )
        return True, "backtest_approved", order

    # 4. Flats (Exits) are ALWAYS approved past pre-checks (1, 2, 3)
    if signal.side == "flat":
        # Determine the closing quantity from open positions
        open_positions = get_open_positions(mode)
        qty = 0.0
        for pos in open_positions:
            if pos["symbol"] == signal.symbol:
                qty = pos["qty"]
                break

        order = ApprovedOrder(
            symbol=signal.symbol,
            side=signal.side,
            qty=qty,
            stop_price=None,
        )
        # Log approval
        signal_id = save_signal_log(
            signal.symbol, signal.side, signal.confidence, 1, "approved", "exit_approved"
        )
        order.signal_id = signal_id
        return True, "exit_approved", order

    # 5. Entry checks (for side == "long")
    # A. Max open positions
    open_count = get_open_positions_count(mode)
    if open_count >= settings.risk.max_open_positions:
        reason = "max_positions_exceeded"
        save_signal_log(signal.symbol, signal.side, signal.confidence, 0, "rejected", reason)
        return False, reason, None

    # B. Drawdowns checks
    equity = get_portfolio_equity(mode)
    daily_dd, total_dd = update_and_get_drawdowns(mode, equity)

    if daily_dd > settings.risk.max_daily_drawdown_pct:
        reason = "max_daily_drawdown_exceeded"
        save_signal_log(signal.symbol, signal.side, signal.confidence, 0, "rejected", reason)
        return False, reason, None

    if total_dd > settings.risk.max_total_drawdown_pct:
        reason = "max_total_drawdown_exceeded"
        save_signal_log(signal.symbol, signal.side, signal.confidence, 0, "rejected", reason)
        return False, reason, None

    # C. Position sizing
    current_price = state.get_ticker_price(signal.symbol)
    if current_price is None or current_price <= 0:
        reason = "no_ticker_price_available"
        save_signal_log(signal.symbol, signal.side, signal.confidence, 0, "rejected", reason)
        return False, reason, None

    current_exposure = get_current_exposure(mode)
    qty = calculate_position_size(
        equity=equity,
        entry_price=current_price,
        stop_price=stop_price,
        risk_per_trade_pct=settings.risk.risk_per_trade_pct,
        max_total_exposure_pct=settings.risk.max_total_exposure_pct,
        current_exposure=current_exposure,
        min_notional=10.0,  # Safe spot size threshold
    )

    if qty <= 0:
        reason = "invalid_or_insufficient_size"
        save_signal_log(signal.symbol, signal.side, signal.confidence, 0, "rejected", reason)
        return False, reason, None

    # Projected total exposure check (double validation safeguard)
    projected_new_notional = qty * current_price
    max_allowed_exposure = equity * (settings.risk.max_total_exposure_pct / 100.0)
    if (current_exposure + projected_new_notional) > (max_allowed_exposure + 1e-5):
        reason = "exposure_limit_breached"
        save_signal_log(signal.symbol, signal.side, signal.confidence, 0, "rejected", reason)
        return False, reason, None

    # Approved!
    order = ApprovedOrder(
        symbol=signal.symbol,
        side=signal.side,
        qty=qty,
        stop_price=stop_price,
    )
    signal_id = save_signal_log(
        signal.symbol,
        signal.side,
        signal.confidence,
        1,
        "approved",
        "clear",
        indicator_value=None,
    )
    order.signal_id = signal_id
    return True, "clear", order
