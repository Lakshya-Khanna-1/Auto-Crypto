from tradecore.core.config import TradingMode
from tradecore.core.state import RuntimeState


def test_runtime_state_defaults():
    state = RuntimeState()
    assert state.kill_switch_active is False
    assert state.consecutive_rejections == 0


def test_mode_transitions():
    state = RuntimeState()
    assert state.current_mode in (TradingMode.BACKTEST, TradingMode.PAPER, TradingMode.LIVE)

    state.set_mode(TradingMode.LIVE)
    assert state.current_mode == TradingMode.LIVE


def test_kill_switch_and_rejections():
    state = RuntimeState()
    state.set_kill_switch(True)
    assert state.kill_switch_active is True

    state.increment_rejections()
    state.increment_rejections()
    assert state.consecutive_rejections == 2

    state.reset_rejections()
    assert state.consecutive_rejections == 0
