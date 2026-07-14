# Setup Guide — Auto Crypto Trader

This guide assumes no programming background. Follow it top to bottom the first
time. Commands are PowerShell, run from the project folder unless stated
otherwise. **DO** lines are commands to run; **EXPECT** lines describe what you
should see; **IF NOT** lines tell you what to do if it doesn't match.

---

## 1. Prerequisites

Install these one at a time and verify each before moving to the next
(from `docs/spec/WindowsDeployment.md`):

1. **Python 3.12 (64-bit)** from [python.org](https://python.org) — during
   install, check the box "Add python.exe to PATH".
   - DO: `python --version`
   - EXPECT: `Python 3.12.x`
2. **Git for Windows** from [git-scm.com](https://git-scm.com).
   - DO: `git --version`
3. **Ollama** from [ollama.com](https://ollama.com) — powers the optional AI
   report/annotation features. Trading works without it.
   - DO: `ollama --version`
4. **NSSM 2.24** from [nssm.cc](https://nssm.cc) — lets the bot run as a real
   Windows service that survives reboots and restarts itself after a crash.
   Unzip and place `nssm.exe` in `C:\tools\nssm\`, then add that folder to
   your PATH (System Properties → Environment Variables).
   - DO: `nssm.exe` (with no arguments)
   - EXPECT: NSSM's usage banner

---

## 2. Install the project

```powershell
git clone <repo-url> "C:\cryptotrader"
cd "C:\cryptotrader"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env
copy config\config.example.yaml config\config.yaml
alembic upgrade head
```
- EXPECT: `alembic upgrade head` prints migration steps ending without errors.
- IF NOT: re-run `pip install -r requirements.txt -r requirements-dev.txt` and
  check the error text — most failures here are a missing Python version or a
  locked `data\tradecore.db` file (close any running instance first).

You do not have to clone to `C:\cryptotrader` specifically — any short path
works. `scripts\install_service.ps1` figures out the install location on its
own.

Verify everything is wired correctly:
```powershell
python -m tradecore --selfcheck
```
- EXPECT: a checklist ending in `All checks passed.`

---

## 3. Configuration, explained key by key (`config/config.yaml`)

Never edit `.env` casually — it holds secrets only. Everything tunable lives
in `config/config.yaml`.

### `trading:`
| Key | Meaning |
|---|---|
| `mode` | `paper`, `live`, or `backtest`. Always start on `paper`. |
| `exchange` | The exchange the bot reads prices from / trades on (via ccxt). |
| `symbols` | The five pairs the bot watches. Adding a symbol requires a backfill + backtest first — don't just add it here. |
| `timeframe` | **Must be `1h`.** This is the candle size the strategy reacts to. Do not change this — see the warning below. |
| `base_currency` | The currency your balance and P&L are denominated in. |

> **Why `timeframe` must stay `1h`:** on 5-minute candles the EMA-crossover
> strategy re-enters and exits far more often, and every round-trip costs
> ~0.3% in simulated fees + slippage (`paper.fee_pct` + `paper.slippage_pct`
> applied on both the entry and exit). That churn is what caused the
> account's earlier paper losses — the strategy was fighting noise, not
> trend. On 1-hour candles it trades far less often and each signal reflects
> an actual trend change, so fees stop dominating the outcome. If you ever
> change this back to something shorter, expect the same fee-bleed problem
> to return.

### `paper:`
| Key | Meaning |
|---|---|
| `starting_balance` | Simulated starting cash (USDT) for paper mode. |
| `fee_pct` | Simulated taker fee charged on every fill, both entry and exit. |
| `slippage_pct` | Simulated price slippage applied against you on every fill. |

### `risk:`
| Key | Meaning |
|---|---|
| `risk_per_trade_pct` | % of equity risked on a single trade (used to size positions off the ATR stop distance). |
| `max_open_positions` | Hard cap on simultaneous open positions. |
| `max_total_exposure_pct` | Hard cap on total notional exposure as % of equity. |
| `max_daily_drawdown_pct` | Kill-switch trips if equity falls this % below today's high-water mark. |
| `max_total_drawdown_pct` | Kill-switch trips if equity falls this % below the all-time high-water mark. |
| `max_data_staleness_sec` | If price data is older than this, trading pauses (protects against a dead feed). |
| `max_consecutive_rejections` | Consecutive order errors/rejections before the kill-switch trips. |

### `strategy:`
| Key | Meaning |
|---|---|
| `name` | Active strategy: `ema_trend`, `ema_trend_adx`, `donchian_breakout`, or `ml_lgbm`. Only one runs at a time. |
| `ema_fast` / `ema_slow` | EMA crossover periods for `ema_trend` / `ema_trend_adx`. |
| `adx_period` / `adx_min` | Trend-strength filter for `ema_trend_adx` (only takes EMA crossovers when ADX confirms a real trend). |
| `donchian_entry` / `donchian_exit` | Channel breakout lengths for `donchian_breakout`. |
| `atr_period` / `atr_stop_mult` | ATR-based stop-loss distance, shared by all strategies. |
| `ml_model_path` / `ml_threshold` | Path to the trained LightGBM model and the minimum predicted probability to enter (only used when `name: ml_lgbm`). |

### `live_guard:`
Interlocks that must pass before you're allowed to switch from paper to live
— see section 8.

### `dashboard:`
| Key | Meaning |
|---|---|
| `host` | `127.0.0.1` = only this PC can reach it. `0.0.0.0` exposes it to your LAN and requires a `DASHBOARD_PASSWORD` env var. |
| `port` | **This deployment uses `9090`**, not the `8080` shown in some spec examples — that's a deliberate, documented choice for this install, not a bug. Dashboard URL: `http://127.0.0.1:9090/` (redirects to the full dashboard page). |

### `telegram:`
See section 11 for full setup. `chat_id` goes here; the bot token goes in
`.env`, never here.

### `ollama:`
| Key | Meaning |
|---|---|
| `main_model` | Used for the daily AI report (longer, higher-quality generation). |
| `fast_model` | Used for one-sentence trade annotations (needs to be quick). |
| `embed_model` | Reserved for a future feature; currently unused at runtime. |

This install currently has both `main_model` and `fast_model` set to
`llama3.1:8b`. That works, but it means the same 8B model is loaded for both
jobs — no speed benefit from a smaller "fast" model, and 8B is a bit large to
keep resident alongside everything else on a 12 GB GPU. Per
`docs/spec/AILayer.md`, the recommended pair for an RTX A2000 12GB machine is:

```powershell
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull llama3.2:3b
```

Then set in `config/config.yaml`:
```yaml
ollama:
  main_model: qwen2.5:7b-instruct-q4_K_M
  fast_model: llama3.2:3b
```
This is optional — the AI layer is advisory-only and never affects trading
decisions, sizing, or risk checks either way.

---

## 4. Backfill historical candles

The bot needs local price history before it can backtest or trade. This
install already has ~2 years of 1h candles for all five symbols. To
(re-)backfill any symbol, or to patch small gaps, run (idempotent — safe to
re-run, it only fills missing candles):

```powershell
python scripts\backfill.py --symbol BTC/USDT --timeframe 1h --days 730
python scripts\backfill.py --symbol ETH/USDT --timeframe 1h --days 730
python scripts\backfill.py --symbol SOL/USDT --timeframe 1h --days 730
python scripts\backfill.py --symbol BNB/USDT --timeframe 1h --days 730
python scripts\backfill.py --symbol XRP/USDT --timeframe 1h --days 730
```
- EXPECT: a "Backfill Summary" per symbol ending in `Gap report: 0 gaps detected.`
- IF NOT: re-run the same command again — it only fetches what's missing, so
  it's always safe to retry.

> A minor gap was found on this install (missing candles around
> 2026-07-13 03:00 and 17:00 UTC for all five symbols, likely from the
> service being stopped briefly). Re-running the five commands above patches
> it automatically.

---

## 5. Backtest and compare strategies

Run a backtest per symbol before trusting a strategy in paper mode. This
compares the currently-configured strategy against the others on the same
data:

```powershell
python scripts\run_backtest.py --symbol BTC/USDT --timeframe 1h --days 730 --strategy ema_trend --compare ema_trend_adx,donchian_breakout
python scripts\run_backtest.py --symbol ETH/USDT --timeframe 1h --days 730 --strategy ema_trend --compare ema_trend_adx,donchian_breakout
python scripts\run_backtest.py --symbol SOL/USDT --timeframe 1h --days 730 --strategy ema_trend --compare ema_trend_adx,donchian_breakout
python scripts\run_backtest.py --symbol BNB/USDT --timeframe 1h --days 730 --strategy ema_trend --compare ema_trend_adx,donchian_breakout
python scripts\run_backtest.py --symbol XRP/USDT --timeframe 1h --days 730 --strategy ema_trend --compare ema_trend_adx,donchian_breakout
```
- EXPECT: a printed table per strategy (total return %, max drawdown %,
  Sharpe, win rate, trade count, profit factor, vs. buy-and-hold) plus a JSON
  file saved under `data\backtests\`.
- Note: the machinery passing (≥10 trades, no errors) is the acceptance bar,
  not profitability — a strategy can validly show negative alpha, that's
  useful information, not a failure.

Add `--walk-forward` to any of the above to split the range into 4 sequential
folds and see how the strategy holds up regime-to-regime, instead of one
average number.

---

## 6. Training and using the ML strategy (optional, advanced)

`ml_lgbm` is an optional fourth strategy, trained locally on your own
backfilled data. It never ships pre-trained.

```powershell
python scripts\train_model.py --symbols all --timeframe 1h
```
- EXPECT: `data\models\lgbm_YYYYMMDD.txt` (copied to `lgbm_latest.txt`) and
  `data\models\report_YYYYMMDD.md`.

### Reading the report
Open `data\models\report_YYYYMMDD.md`. Check, in order:
1. **Walk-forward folds table** — per-fold AUC and precision; look for
   consistency across folds, not just a high average.
2. **Held-out test metrics** — performance on the most recent ~90 days the
   model never trained on. This is the most honest number in the report.
3. **Feature importances** — sanity-check nothing implausible dominates.
4. **Label balance** — how many candles were labeled "price rises 1×ATR
   before it falls 1×ATR" vs. not.
5. **Backtest comparison section** — `ml_lgbm` vs. `ema_trend`.
6. **The honesty clause at the footer** — read it every time. A model that
   validated well can still lose money in a new market regime.

### Activation gate
Only set `strategy.name: ml_lgbm` in `config.yaml` if the report's comparison
shows `ml_lgbm` beating `ema_trend` on total return **and** not more than 20%
worse (relative) on max drawdown. If it doesn't clear that bar, that's a
legitimate outcome — keep `ema_trend` active and keep the report for the
record.

### Retraining
Manual only, monthly at most. Re-run `train_model.py`, review the new
report, and restart the service (section 10) to pick up `lgbm_latest.txt`.
There is no auto-retraining in this system by design — a silently drifting
model trading live money is dangerous, so a human reviews every retrain.

---

## 7. Paper trading

```powershell
python -m tradecore
```
Open `http://127.0.0.1:9090/` in a browser — it redirects to the dashboard.
Leave this window open, or install it as a service (section 10) for
unattended operation.

The dashboard shows: equity curve, open positions, trade history, the
signal/risk log, system status (data feed, scheduler, Ollama), and the daily
AI report. The strategy re-evaluates once per hour, 30 seconds after the
hour closes (matching the 1h timeframe) — see section 12 for how to confirm
this yourself.

---

## 8. Going from paper to live (read this fully before attempting it)

Live mode moves real money. The switch (dashboard "Mode Switch" button, or
Telegram is deliberately **not** able to do this) is blocked until **all** of
these pass:

| Interlock | What it checks |
|---|---|
| Valid exchange API keys | `EXCHANGE_API_KEY`/`EXCHANGE_API_SECRET` in `.env` work — a real `fetch_balance` call succeeds |
| Kill-switch armed | Not currently tripped |
| Data feed fresh | Not stale |
| Paper track record | At least `live_guard.require_paper_trades` closed paper trades **and** `live_guard.require_paper_days` days of paper history (both configured, default 20 trades / 14 days) |
| Typed confirmation | You must type `GO-LIVE` exactly in the modal |

If a check fails, the modal shows exactly which one and why — there is no
override unless you deliberately set `live_guard.allow_override: true` first
(not recommended). Going live → paper is always instant, no confirmation
needed, but any open live positions are **not** auto-closed — the dashboard
will show a warning banner until you flatten them manually.

---

## 9. Kill-switch re-arm and paper account reset

**Kill-switch** trips automatically on excess drawdown, stale data, or
repeated order errors — or you can trip it manually (dashboard red button,
or Telegram `/kill`, no confirmation needed since speed matters there). Once
tripped, it cancels open orders, flattens all positions, and blocks new
entries until you re-arm it:
- Dashboard: click "Re-arm", type `RE-ARM` exactly.
- Telegram: `/rearm` then `/confirm` within 60 seconds.
- **Re-arming does not reset drawdown counters** — if the drawdown that
  tripped it is still breached, it will trip again immediately. That's
  intentional; if you want to keep trading through it, you have to
  consciously raise the limits in `config.yaml` first.

**Paper account reset** wipes paper trade history and open positions and
restores `paper.starting_balance`. Only works while `trading.mode: paper`:
```powershell
curl.exe -s -X POST http://127.0.0.1:9090/api/paper/reset
```
- EXPECT: `409` if you're not in paper mode; otherwise the dashboard shows a
  fresh $10,000 (or your configured starting balance) with no trade history.

---

## 10. Running persistently with NSSM

Do not use ad-hoc `.bat`/`.vbs` launchers for long-running operation — they
have no crash-restart and don't start on boot. `scripts\install_service.ps1`
is the only supported way to run this unattended:

```powershell
# Run as Administrator, from the project root:
.\scripts\install_service.ps1
```
- EXPECT: `Service 'tradecore' registered and started.`

Day-to-day operations:
| Task | Command |
|---|---|
| Check status | `nssm status tradecore` |
| Tail logs | check `data\logs\service-out.log` / `service-err.log` |
| Restart after a config edit | `nssm restart tradecore` |
| Stop | `nssm stop tradecore` |
| Update code | `git pull; pip install -r requirements.txt; alembic upgrade head; nssm restart tradecore` |

The service is configured to auto-restart on crash and auto-start on boot.

---

## 11. Telegram setup

1. Message **@BotFather** on Telegram, send `/newbot`, follow the prompts.
   Copy the token it gives you.
2. Put that token in `.env` (not `config.yaml`):
   ```
   TELEGRAM_BOT_TOKEN=<your token>
   ```
3. Message your new bot anything, then find your `chat_id`: visit
   `https://api.telegram.org/bot<your token>/getUpdates` in a browser and
   read `"chat":{"id": ...}` from the JSON.
4. Put that id in `config/config.yaml` under `telegram.chat_id`.
5. Restart (`nssm restart tradecore`, or just re-run `python -m tradecore`).

Available bot commands: `/status`, `/positions`, `/kill`, `/rearm` then
`/confirm`, `/pause`, `/resume`. Mode switching is intentionally dashboard-only.
If `telegram.enabled: false` or the token is empty, the bot silently no-ops —
trading is unaffected either way.

---

## 12. Verifying the bot now ticks hourly

After the timeframe/scheduler fixes in this update, confirm it yourself:
1. Start the app and watch `data\logs\service-out.log` (or the console).
2. You should see one `strategy_tick` log line at HH:00:30 each hour — not
   one every minute.
3. Dashboard Panel 5 (System status) shows the scheduler's last-run time for
   each job; `strategy_tick`'s should advance by ~1 hour between updates,
   not ~1 minute.

---

## 13. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `alembic upgrade head` fails | Another process has `data\tradecore.db` open — stop the service/console first. |
| Dashboard won't load | Check the app is actually running (`nssm status tradecore`); confirm you're using the port in `config.yaml` (`9090` on this install), not the spec's example `8080`. |
| "live keys invalid" when switching to live | `.env` `EXCHANGE_API_KEY`/`EXCHANGE_API_SECRET` are empty or wrong, or the exchange rejected them — paper mode works with these empty, live mode does not. |
| Kill-switch keeps re-tripping after re-arm | Drawdown is still breached — re-arming never clears drawdown counters by design. Either wait for equity to recover or consciously raise `risk.max_daily_drawdown_pct` / `max_total_drawdown_pct`. |
| Telegram bot doesn't respond | Check `telegram.enabled: true`, a valid `TELEGRAM_BOT_TOKEN` in `.env`, and that `telegram.chat_id` in `config.yaml` matches the chat you're messaging from — messages from other chats are silently ignored and logged. |
| Ollama panel shows ✗ | Check `ollama --version` works and `ollama.host` in config points at a running Ollama; the AI layer is advisory-only, so trading continues regardless. |
| "Insufficient paper balance" | Paper balance is too low for the position size at current risk settings — reset the paper account (section 9) or lower `risk.risk_per_trade_pct`. |
| Strategy never seems to fire | Confirm `trading.timeframe: 1h` (not something shorter) and check `strategy_tick` is actually running hourly per section 12 — a churning-every-few-minutes strategy is the exact bug this update fixed. |
