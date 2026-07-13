import logging

logger = logging.getLogger("tradecore.riskengine.sizing")


def calculate_position_size(
    equity: float,
    entry_price: float,
    stop_price: float | None,
    risk_per_trade_pct: float,
    max_total_exposure_pct: float,
    current_exposure: float,
    min_notional: float = 10.0,
) -> float:
    """
    Calculate the risk-adjusted position size (quantity) for a potential trade.

    Formula:
      risk_amount = equity * (risk_per_trade_pct / 100)
      stop_distance = entry_price - stop_price
      qty = risk_amount / stop_distance

    Capped so that:
      qty * entry_price <= remaining_exposure_allowance

    Returns:
      float: The calculated quantity (0.0 if calculations are invalid or size is under min).
    """
    if stop_price is None or stop_price >= entry_price or entry_price <= 0:
        logger.warning(
            f"Invalid prices for sizing: entry_price={entry_price}, "
            f"stop_price={stop_price}. Sizing aborted."
        )
        return 0.0

    # Risk-based position sizing
    risk_amount = equity * (risk_per_trade_pct / 100.0)
    stop_distance = entry_price - stop_price
    qty = risk_amount / stop_distance

    # Calculate remaining exposure allowance
    max_allowed_exposure = equity * (max_total_exposure_pct / 100.0)
    remaining_exposure = max_allowed_exposure - current_exposure
    if remaining_exposure < 0:
        remaining_exposure = 0.0

    # Cap notional exposure
    notional = qty * entry_price
    if notional > remaining_exposure:
        qty = remaining_exposure / entry_price
        notional = qty * entry_price
        logger.info(
            f"Position size capped to respect remaining exposure limit: {remaining_exposure:.2f}"
        )

    # Check against minimum notional limit
    if notional < min_notional:
        logger.warning(
            f"Calculated notional {notional:.2f} is below exchange minimum notional "
            f"{min_notional:.2f}. Rejecting size."
        )
        return 0.0

    return qty
