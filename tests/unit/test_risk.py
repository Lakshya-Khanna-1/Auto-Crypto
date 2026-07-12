import pytest
from tradecore.riskengine.sizing import calculate_position_size


def test_sizing_normal():
    # equity = 10,000, risk = 1%, risk_amount = 100 USD
    # entry_price = 100, stop_price = 90 (stop_distance = 10)
    # qty = 100 / 10 = 10 units
    # notional = 10 * 100 = 1,000 USD
    # remaining exposure limit = 30% of 10k (3,000 USD) - current_exposure (0) = 3,000 USD
    qty = calculate_position_size(
        equity=10000.0,
        entry_price=100.0,
        stop_price=90.0,
        risk_per_trade_pct=1.0,
        max_total_exposure_pct=30.0,
        current_exposure=0.0,
    )
    assert qty == pytest.approx(10.0)


def test_sizing_capped_by_exposure():
    # equity = 10,000, risk = 5%, risk_amount = 500 USD
    # entry_price = 100, stop_price = 90 (stop_distance = 10)
    # qty = 50 units (notional = 50 * 100 = 5,000 USD)
    # remaining exposure limit = 30% of 10k (3,000 USD) - current_exposure (2,000) = 1,000 USD
    # Notional exceeds remaining exposure limit (1,000). Qty capped to 1,000 / 100 = 10 units.
    qty = calculate_position_size(
        equity=10000.0,
        entry_price=100.0,
        stop_price=90.0,
        risk_per_trade_pct=5.0,
        max_total_exposure_pct=30.0,
        current_exposure=2000.0,
    )
    assert qty == pytest.approx(10.0)


def test_sizing_under_min_notional():
    # equity = 1,000, risk = 0.5%, risk_amount = 5 USD
    # entry_price = 100, stop_price = 50 (stop_distance = 50)
    # qty = 5 / 50 = 0.1 units
    # notional = 0.1 * 100 = 10.0 USD
    # min_notional is set to 15.0 USD. Sizing should reject and return 0.0.
    qty = calculate_position_size(
        equity=1000.0,
        entry_price=100.0,
        stop_price=50.0,
        risk_per_trade_pct=0.5,
        max_total_exposure_pct=30.0,
        current_exposure=0.0,
        min_notional=15.0,
    )
    assert qty == 0.0


def test_sizing_invalid_prices():
    # Stop price >= entry price
    assert (
        calculate_position_size(
            equity=10000.0,
            entry_price=100.0,
            stop_price=105.0,
            risk_per_trade_pct=1.0,
            max_total_exposure_pct=30.0,
            current_exposure=0.0,
        )
        == 0.0
    )

    # Stop price is None
    assert (
        calculate_position_size(
            equity=10000.0,
            entry_price=100.0,
            stop_price=None,
            risk_per_trade_pct=1.0,
            max_total_exposure_pct=30.0,
            current_exposure=0.0,
        )
        == 0.0
    )
