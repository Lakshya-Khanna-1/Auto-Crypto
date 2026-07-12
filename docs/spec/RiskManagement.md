# RiskManagement.md

**Highest-priority module.** Fully deterministic. No AI involvement of any kind.
Every order passes through `riskengine.approve()`; there is no code path around it.

## 1. approve(signal) pipeline (`riskengine/engine.py`)
Checks run in order; first failure rejects (logged to `signals` table with reason):

1. Kill-switch not triggered.
2. Data feed not stale.
3. Mode != BACKTEST (backtests use the backtester, not live approval).
4. Exit signals (Flat) are ALWAYS approved past this point — closing risk is never blocked.
5. Entry checks:
   - open positions < `max_open_positions`
   - projected total exposure (sum notional of open + new) ≤ `max_total_exposure_pct` of equity
   - daily drawdown and total drawdown below limits (§2)
   - computed qty ≥ exchange min notional
6. Position sizing (`sizing.py`):
   `risk_amount = equity × risk_per_trade_pct/100`
   `stop_distance = entry_price − stop_price` (from strategy's ATR stop)
   `qty = risk_amount / stop_distance`, capped so notional ≤ remaining exposure allowance.

## 2. Drawdown accounting
- `daily_hwm` = max equity since 00:00 UTC (persisted in app_kv, reset by scheduler at midnight).
- `total_hwm` = all-time max equity (per mode; paper and live tracked separately).
- daily_dd = (daily_hwm − equity)/daily_hwm × 100; same for total.

## 3. Watchdog (60 s loop, `riskengine/killswitch.py`)
Triggers the kill-switch when ANY of:
| Condition | Threshold |
|-----------|-----------|
| Daily drawdown | > max_daily_drawdown_pct |
| Total drawdown | > max_total_drawdown_pct |
| Data staleness | > max_data_staleness_sec |
| Consecutive order rejections/errors | ≥ max_consecutive_rejections |
| Manual trigger | dashboard button or Telegram /kill |

Also enforces stops intracandle: for each open position, if last ticker price ≤ stop_price
→ emit Flat signal (approved unconditionally per §1.4).

## 4. Kill-switch behaviour
1. Set `killswitch=triggered` in app_kv (survives restart).
2. `adapter.cancel_all()` then `adapter.flatten()` — all positions closed at market.
   If flatten fails (exchange down): retry every 60 s, alarm-level Telegram every 5 min.
3. Block all new entries. Write `killswitch_events` row. Telegram + dashboard banner.
4. **Re-arming is manual only**: dashboard "Re-arm" button with typed confirmation
   `RE-ARM`, or Telegram `/rearm` followed by `/confirm` within 60 s. Re-arming does
   not clear drawdown counters (if drawdown still breached, it re-triggers — user must
   raise limits in config consciously).

## 5. Testing requirements (blocking for milestone acceptance)
Unit tests must cover: sizing math, each rejection reason, each watchdog trigger,
kill-switch flatten with a mocked adapter, exit-signals-never-blocked, re-arm flow.
