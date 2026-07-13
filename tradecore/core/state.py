from tradecore.core.config import TradingMode, get_settings


class RuntimeState:
    """
    Monages the global mutable runtime state of the trading engine.
    """

    def __init__(self) -> None:
        self._current_mode: TradingMode = get_settings().trading.mode
        self._kill_switch_active: bool = False
        self._consecutive_rejections: int = 0
        self._daily_drawdown_pct: float = 0.0
        self._total_drawdown_pct: float = 0.0
        self._last_ticker_times: dict[str, float] = {}
        self._last_ticker_prices: dict[str, float] = {}
        self._strategy_paused: bool = False

    @property
    def strategy_paused(self) -> bool:
        return self._strategy_paused

    def set_strategy_paused(self, paused: bool) -> None:
        self._strategy_paused = paused

    def update_ticker(self, symbol: str, price: float, timestamp: float) -> None:
        """
        Update the cached price and timestamp of the last ticker.
        """
        self._last_ticker_times[symbol] = timestamp
        self._last_ticker_prices[symbol] = price

    def get_ticker_time(self, symbol: str) -> float | None:
        """
        Get the last cached ticker timestamp for a given symbol.
        """
        return self._last_ticker_times.get(symbol)

    def get_ticker_price(self, symbol: str) -> float | None:
        """
        Get the last cached ticker close price for a given symbol.
        """
        return self._last_ticker_prices.get(symbol)

    @property
    def current_mode(self) -> TradingMode:
        return self._current_mode

    def set_mode(self, mode: TradingMode) -> None:
        """
        Transition the system's trading mode.
        """
        self._current_mode = mode

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch_active

    def set_kill_switch(self, active: bool) -> None:
        """
        Activate or deactivate the risk management kill switch.
        """
        self._kill_switch_active = active

    @property
    def consecutive_rejections(self) -> int:
        return self._consecutive_rejections

    def increment_rejections(self) -> None:
        """
        Increment the consecutive exchange order rejection counter.
        """
        self._consecutive_rejections += 1

    def reset_rejections(self) -> None:
        """
        Reset the consecutive exchange order rejection counter.
        """
        self._consecutive_rejections = 0


# Global runtime state instance
_state = RuntimeState()


def get_state() -> RuntimeState:
    return _state


async def switch_mode(target: str, confirmation: str | None = None, override: bool = False) -> None:
    """
    Transition the system's trading mode with safety interlocks.
    """
    import asyncio
    import time
    from datetime import datetime

    from sqlalchemy import func, select

    from tradecore.core.config import TradingMode, get_settings
    from tradecore.datafeed.feed import get_ccxt_client
    from tradecore.notifications.notifier import send_telegram_alert
    from tradecore.store.db import get_engine
    from tradecore.store.repo import save_mode_change_log
    from tradecore.store.schema import positions

    state = get_state()
    settings = get_settings()

    target_mode = target.lower()
    if target_mode not in ("paper", "live"):
        raise ValueError("Invalid target mode chosen.")

    old_mode = str(state.current_mode)
    if target_mode == old_mode:
        return

    if target_mode == "live":
        # 1. Confirmation check
        if confirmation != "GO-LIVE":
            raise ValueError("Must type GO-LIVE to confirm live transition.")

        # 2. Exchange keys & fetch_balance check
        client = get_ccxt_client()
        if not client.apiKey or not client.secret:
            raise ValueError("live keys invalid: credentials error or missing keys")
        try:
            await asyncio.to_thread(client.fetch_balance)
        except Exception as e:
            raise ValueError(f"live keys invalid: Connection/credentials error: {e}") from e

        # 3. Kill-switch check
        if state.kill_switch_active:
            raise ValueError("Live transition blocked: Kill-switch is currently active/triggered.")

        # 4. Data feed staleness check
        current_time = time.time()
        for symbol in settings.trading.symbols:
            t = state.get_ticker_time(symbol)
            if t is None:
                raise ValueError(f"Live transition blocked: No data feed active for {symbol}")
            if (current_time - t) > settings.risk.max_data_staleness_sec:
                raise ValueError(f"Live transition blocked: Stale data feed on {symbol}")

        # 5. Paper practice history check
        engine = get_engine()
        with engine.connect() as conn:
            stmt_count = (
                select(func.count(positions.c.id))
                .where(positions.c.status == "closed")
                .where(positions.c.mode == "paper")
            )
            closed_count = conn.execute(stmt_count).scalar() or 0

            stmt_min_ts = select(func.min(positions.c.opened_ts)).where(positions.c.mode == "paper")
            min_ts = conn.execute(stmt_min_ts).scalar()

        paper_days = 0
        if min_ts:
            try:
                val_dt = datetime.fromisoformat(min_ts)
                paper_days = (datetime.now() - val_dt).days
            except Exception:
                pass

        req_trades = settings.live_guard.require_paper_trades
        req_days = settings.live_guard.require_paper_days
        history_ok = (closed_count >= req_trades) and (paper_days >= req_days)

        if not history_ok:
            if settings.live_guard.allow_override and override:
                pass
            else:
                raise ValueError(
                    f"Live transition blocked: Paper trades history check failed. "
                    f"Recorded: {closed_count}/{req_trades} trades, {paper_days}/{req_days} days"
                )

    # Success: transition mode
    # 1. Update config file
    from tradecore.app import update_config_file_mode

    update_config_file_mode(target_mode)

    # 2. Set runtime state
    state.set_mode(TradingMode(target_mode))

    # 3. Save mode changes audit row
    save_mode_change_log(
        from_mode=old_mode,
        to_mode=target_mode,
        source="dashboard",
        override_used=override if target_mode == "live" else False,
    )

    # 4. Telegram alert
    if target_mode == "live":
        await send_telegram_alert(
            f"⚠️ *Mode Change Alert*\n"
            f"Transition: `{old_mode.upper()} → LIVE`\n"
            f"Source: Web Dashboard\n"
            f"Override: {'Yes' if override else 'No'}"
        )
    else:
        await send_telegram_alert(
            f"⚠️ *Mode Change Alert*\n"
            f"Transition: `{old_mode.upper()} → PAPER`\n"
            f"Source: Web Dashboard"
        )
