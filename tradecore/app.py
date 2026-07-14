import asyncio
import csv
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

import httpx
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import (
    FastAPI,
    Form,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import desc, func, insert, select, update

from tradecore.core.config import get_settings
from tradecore.core.events import Event, get_event_bus
from tradecore.core.state import get_state
from tradecore.datafeed.feed import get_ccxt_client, get_data_feed
from tradecore.execution.adapter import ApprovedOrder, get_adapter
from tradecore.scheduler.jobs import (
    annotate_closed_positions_job,
    candle_sync_job,
    daily_report_job,
    equity_snapshot_job,
    risk_watchdog_job,
    strategy_tick_job,
    ticker_poll_job,
    ws_reconnect_job,
)
from tradecore.store.db import get_engine
from tradecore.store.repo import get_kv, get_open_positions, set_kv
from tradecore.store.schema import equity_snapshots, killswitch_events, positions, signals, trades

logger = logging.getLogger(__name__)

# Track server startup time
start_time = time.time()

# Generate session security token for 0.0.0.0 binds
SESSION_TOKEN = secrets.token_hex(16)


def get_session_token() -> str:
    return SESSION_TOKEN


# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                pass


ws_manager = ConnectionManager()

# Initialize FastAPI App
app = FastAPI(title="Auto-Crypto Trader API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security middleware enforcing session checks on 0.0.0.0
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    settings = get_settings()
    if settings.dashboard.host == "0.0.0.0":
        path = request.url.path
        # Exclude login and login static assets
        if path in ("/login", "/dashboard/static/login.html"):
            return await call_next(request)

        # Check session cookie validation
        session = request.cookies.get("session_id")
        if session != get_session_token():
            if path.startswith("/api"):
                return Response(
                    content='{"error": "Unauthorized"}',
                    status_code=401,
                    media_type="application/json",
                )
            return RedirectResponse("/login")

    return await call_next(request)


scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    """
    Application startup & shutdown wiring router.
    """
    global scheduler
    scheduler = AsyncIOScheduler()
    settings = get_settings()
    symbols = settings.trading.symbols
    state = get_state()
    mode = str(state.current_mode)

    logger.info("Starting Auto-Crypto Trader startup sequence.")

    # Security check for 0.0.0.0 host Configuration
    if settings.dashboard.host == "0.0.0.0" and not os.environ.get("DASHBOARD_PASSWORD"):
        raise ValueError(
            "DASHBOARD_PASSWORD env var is required when dashboard host is set to 0.0.0.0"
        )

    # 1. Crash recovery/startup position reconciliation
    try:
        open_pos = get_open_positions(mode)
        logger.info(f"RECONCILED: Startup recovered {len(open_pos)} open positions from database.")

        if mode == "live":
            logger.info("Performing live exchange position and order startup reconciliation...")
            from tradecore.execution.live import LiveAdapter
            from tradecore.notifications.notifier import send_telegram_alert

            adapter = LiveAdapter()
            mismatch_detected = False
            details = []

            # Check open orders
            try:
                open_orders = await adapter.get_open_orders()
                if open_orders:
                    mismatch_detected = True
                    details.append(
                        f"Open orders found on exchange: {len(open_orders)} orders pending."
                    )
            except Exception as ex:
                logger.error(f"Reconciliation: failed to fetch open orders: {ex}")
                mismatch_detected = True
                details.append(f"Failed to fetch open orders from exchange: {ex}")

            # Check balances
            try:
                # Group active positions by base currency
                db_by_base = {}
                for pos in open_pos:
                    base = pos["symbol"].split("/")[0]
                    db_by_base[base] = db_by_base.get(base, 0.0) + pos["qty"]

                exchange_bal = await adapter.exchange.fetch_balance()

                for symbol in symbols:
                    base = symbol.split("/")[0]
                    actual_bal = (
                        exchange_bal.get("total", {}).get(base, 0.0)
                        or exchange_bal.get(base, {}).get("total", 0.0)
                        or 0.0
                    )
                    expected_bal = db_by_base.get(base, 0.0)

                    if abs(actual_bal - expected_bal) > 1e-4:
                        mismatch_detected = True
                        details.append(
                            f"Balance mismatch on {base}: DB expected {expected_bal:.5f}, "
                            f"Exchange actual {actual_bal:.5f}."
                        )
            except Exception as ex:
                logger.error(f"Reconciliation: failed to fetch balance: {ex}")
                mismatch_detected = True
                details.append(f"Failed to fetch balance from exchange: {ex}")

            if mismatch_detected:
                logger.warning(f"Startup reconciliation mismatch: {details}")
                state.set_strategy_paused(True)
                # Send warning message
                alert_msg = (
                    "⚠️ *STARTUP RECONCILIATION MISMATCH!*\n"
                    + "\n".join(details)
                    + "\nTrading ticks have been PAUSED. Please resolve manually via the dashboard."
                )
                await send_telegram_alert(alert_msg)
            else:
                logger.info("Startup reconciliation complete. DB and Exchange are matched.")

    except Exception as e:
        logger.error(f"Startup crash recovery/reconciliation failed: {e}")

    # Reset consecutive error statistics on startup
    state.reset_rejections()

    # WebSocket bridge to EventBus
    async def ws_event_bridge(event: Event):
        try:
            await ws_manager.broadcast({"type": event.type, "data": event.data})
        except Exception as e:
            logger.error(f"Failed to bridge event {event.type} to web sockets: {e}")

    event_bus = get_event_bus()
    for etype in ["tick", "fill", "mode", "killswitch", "equity", "status"]:
        event_bus.subscribe(etype, ws_event_bridge)

    # 2. Risk Watchdog registration & immediate startup run
    if mode != "backtest":
        scheduler.remove_all_jobs()
        scheduler.add_job(risk_watchdog_job, "interval", seconds=60, id="risk_watchdog")
        logger.info("Watchdog job registered.")

        # Seed tickers on startup to prevent immediate watchdog data staleness trigger
        logger.info("Seeding initial ticker prices to prevent data staleness trigger...")
        feed = get_data_feed()
        for symbol in symbols:
            try:
                await feed.poll_ticker(symbol)
            except Exception as e:
                logger.error(f"Failed to fetch initial ticker for {symbol} on startup: {e}")

        try:
            await risk_watchdog_job()
        except Exception as e:
            logger.error(f"Failed to execute initial watchdog check at startup: {e}")

        try:
            await candle_sync_job()
        except Exception as e:
            logger.error(f"Failed to execute initial candle sync at startup: {e}")

        try:
            await strategy_tick_job()
        except Exception as e:
            logger.error(f"Failed to execute initial strategy tick at startup: {e}")

        # 3. Add remaining interval scheduler tasks
        scheduler.add_job(candle_sync_job, "interval", minutes=5, id="candle_sync")
        scheduler.add_job(ticker_poll_job, "interval", seconds=10, id="ticker_poll")
        scheduler.add_job(ws_reconnect_job, "interval", hours=1, id="ws_reconnect")
        scheduler.add_job(equity_snapshot_job, "interval", minutes=15, id="equity_snapshot")
        scheduler.add_job(
            strategy_tick_job,
            "cron",
            minute="*",
            second="30",
            id="strategy_tick",
        )
        scheduler.add_job(
            daily_report_job,
            "cron",
            hour="0",
            minute="15",
            timezone="UTC",
            id="daily_report",
        )
        scheduler.add_job(
            annotate_closed_positions_job,
            "interval",
            seconds=60,
            id="annotate_closed_positions",
        )

    scheduler.start()
    logger.info("APScheduler initialized and all jobs started.")

    ws_task = asyncio.create_task(get_data_feed().start_ws_loop(symbols))

    # 4. Initialize Telegram notification bot
    from tradecore.notifications.notifier import (
        init_telegram_bot,
        send_telegram_alert,
        stop_telegram_bot,
    )

    await init_telegram_bot()

    # Send startup outbound message
    open_pos_count = len(open_pos) if "open_pos" in locals() else 0
    await send_telegram_alert(
        f"🚀 System started in {mode.upper()} mode. Active open positions: {open_pos_count}"
    )

    yield

    # Shutdown sequence
    try:
        await send_telegram_alert(f"🛑 System is shutting down. Current mode: {mode.upper()}")
    except Exception:
        pass
    scheduler.shutdown()
    await stop_telegram_bot()
    get_data_feed().ws_active = False
    ws_task.cancel()
    try:
        await ws_task
    except asyncio.CancelledError:
        pass

    # Unsubscribe WS Bridge
    for etype in ["tick", "fill", "mode", "killswitch", "equity", "status"]:
        event_bus.unsubscribe(etype, ws_event_bridge)

    logger.info("APScheduler and WebSocket task stopped.")


# Assign custom lifespan context manager
app.router.lifespan_context = lifespan


# Host dashboard redirects and files
@app.get("/")
async def root_endpoint(request: Request):
    settings = get_settings()
    if settings.dashboard.host == "0.0.0.0":
        session = request.cookies.get("session_id")
        if session != get_session_token():
            return RedirectResponse("/login")
    return RedirectResponse("/dashboard/static/index.html")


@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    login_path = Path(__file__).parent / "dashboard" / "static" / "login.html"
    if not login_path.exists():
        raise HTTPException(status_code=404, detail="login.html template missing")
    return HTMLResponse(content=login_path.read_text(encoding="utf-8"))


@app.post("/login")
async def login_post(password: str = Form(...)):
    expected = os.environ.get("DASHBOARD_PASSWORD")
    if expected and password == expected:
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("session_id", get_session_token(), httponly=True, samesite="lax")
        return response
    return HTMLResponse(content="<h1>Unauthorized: Incorrect Password</h1>", status_code=401)


# WebSocket /ws Route
@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    settings = get_settings()
    if settings.dashboard.host == "0.0.0.0":
        session = websocket.cookies.get("session_id")
        if session != get_session_token():
            await websocket.close(code=1008)
            return

    await websocket.accept()
    await ws_manager.connect(websocket)
    try:
        while True:
            # Maintain active connection receiver details
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket)


# --- REST API CONTRACT ---


@app.get("/health")
def health_endpoint() -> dict[str, str]:
    """
    Standard service health endpoint returning current mode.
    """
    return {"status": "ok", "mode": str(get_settings().trading.mode)}


@app.get("/api/status")
async def api_status() -> dict:
    from tradecore.riskengine.engine import get_portfolio_equity

    state = get_state()
    settings = get_settings()
    mode = str(state.current_mode)

    # Get balance
    if mode == "paper":
        bal_str = get_kv("paper_balance")
        balance = float(bal_str) if bal_str is not None else settings.paper.starting_balance
    else:
        bal_str = get_kv("live_balance")
        balance = float(bal_str) if bal_str is not None else 10000.0

    equity = get_portfolio_equity(mode)

    # Calculate PNL Total
    starting_balance = settings.paper.starting_balance if mode == "paper" else 10000.0
    pnl_total = equity - starting_balance

    # Calculate PNL today relative to midnight UTC snapshot
    midnight_today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    engine = get_engine()
    with engine.connect() as conn:
        stmt = (
            select(equity_snapshots.c.equity)
            .where(equity_snapshots.c.mode == mode)
            .where(equity_snapshots.c.ts <= midnight_today.isoformat())
            .order_by(desc(equity_snapshots.c.ts))
            .limit(1)
        )
        row = conn.execute(stmt).first()
        if row is None:
            # Fallback to the first available snapshot in the DB
            stmt_first = (
                select(equity_snapshots.c.equity)
                .where(equity_snapshots.c.mode == mode)
                .order_by(equity_snapshots.c.ts)
                .limit(1)
            )
            row = conn.execute(stmt_first).first()

        midnight_equity = row[0] if row is not None else starting_balance

    pnl_today = equity - midnight_equity
    uptime = time.time() - start_time

    return {
        "mode": mode,
        "equity": equity,
        "balance": balance,
        "pnl_today": pnl_today,
        "pnl_total": pnl_total,
        "killswitch": state.kill_switch_active,
        "paused": state.strategy_paused,
        "uptime_sec": int(uptime),
    }


@app.get("/api/positions")
async def api_positions() -> list:
    state = get_state()
    mode = str(state.current_mode)
    open_pos = get_open_positions(mode)

    result = []
    for pos in open_pos:
        symbol = pos["symbol"]
        price = state.get_ticker_price(symbol) or pos["entry_price"]
        unrealized = pos["qty"] * (price - pos["entry_price"])
        result.append(
            {
                "id": pos["id"],
                "symbol": symbol,
                "side": pos["side"],
                "qty": pos["qty"],
                "entry_price": pos["entry_price"],
                "stop_price": pos["stop_price"],
                "current_price": price,
                "unrealized_pnl": unrealized,
                "opened_ts": pos["opened_ts"],
            }
        )
    return result


@app.post("/api/positions/{position_id}/close")
async def api_close_position(position_id: int) -> dict:
    state = get_state()
    mode = str(state.current_mode)
    engine = get_engine()

    with engine.connect() as conn:
        stmt = select(positions).where(positions.c.id == position_id)
        pos = conn.execute(stmt).first()

    if pos is None:
        raise HTTPException(status_code=404, detail="Position not found.")

    if pos.status == "closed":
        raise HTTPException(status_code=400, detail="Position is already closed.")

    adapter = get_adapter(mode)
    order = ApprovedOrder(
        symbol=pos.symbol,
        side="flat",
        qty=pos.qty,
    )

    try:
        fill = await adapter.place(order)
        # Notify subscribers
        await get_event_bus().publish(
            Event(
                type="fill",
                data={
                    "order_id": fill.order_id,
                    "symbol": fill.symbol,
                    "side": fill.side,
                    "qty": fill.qty,
                    "price": fill.price,
                },
            )
        )
        return {"fill": fill.__dict__}
    except Exception as e:
        logger.error(f"Manual close failed: {e}")
        raise HTTPException(status_code=409, detail=f"Manual close failed: {e}") from e


@app.get("/api/report/latest")
async def api_report_latest() -> dict:
    import json

    val = get_kv("latest_report")
    if not val:
        return {"ts": None, "text": "No daily report generated yet."}
    try:
        return json.loads(val)
    except Exception:
        return {"ts": None, "text": "No daily report generated yet."}


@app.get("/api/trades")
async def api_trades(mode: str = "paper", page: int = 1, page_size: int = 50) -> dict[str, Any]:
    offset = (page - 1) * page_size
    engine = get_engine()

    with engine.connect() as conn:
        # Get total counts of closed positions
        stmt_count = (
            select(func.count(positions.c.id))
            .where(positions.c.status == "closed")
            .where(positions.c.mode == mode)
        )
        total = conn.execute(stmt_count).scalar() or 0

        # Query closed positions joining matching exit trades
        stmt = (
            select(
                positions.c.symbol,
                positions.c.side,
                positions.c.qty,
                positions.c.entry_price,
                positions.c.exit_price,
                positions.c.realized_pnl,
                positions.c.fees_total,
                positions.c.opened_ts,
                positions.c.closed_ts,
                positions.c.mode,
                positions.c.annotation,
                trades.c.strategy,
            )
            .select_from(
                positions.join(
                    trades,
                    positions.c.id == trades.c.position_id,
                    isouter=True,
                )
            )
            .where(positions.c.status == "closed")
            .where(positions.c.mode == mode)
            .distinct()
            .order_by(desc(positions.c.closed_ts))
            .limit(page_size)
            .offset(offset)
        )
        rows = conn.execute(stmt).all()

    items = []
    for r in rows:
        items.append(
            {
                "symbol": r.symbol,
                "side": r.side,
                "qty": r.qty,
                "entry_price": r.entry_price,
                "exit_price": r.exit_price or 0.0,
                "realized_pnl": r.realized_pnl or 0.0,
                "fees_total": r.fees_total or 0.0,
                "opened_ts": r.opened_ts,
                "closed_ts": r.closed_ts,
                "strategy": r.strategy or "unknown",
                "mode": r.mode,
                "annotation": r.annotation or "",
            }
        )

    return {"items": items, "total": total}


@app.get("/api/trades/export.csv")
async def api_trades_export(mode: str = "paper") -> StreamingResponse:
    engine = get_engine()

    with engine.connect() as conn:
        stmt = (
            select(
                positions.c.id,
                positions.c.symbol,
                positions.c.side,
                positions.c.qty,
                positions.c.entry_price,
                positions.c.exit_price,
                positions.c.realized_pnl,
                positions.c.fees_total,
                positions.c.opened_ts,
                positions.c.closed_ts,
                positions.c.mode,
            )
            .where(positions.c.status == "closed")
            .where(positions.c.mode == mode)
            .order_by(desc(positions.c.closed_ts))
        )
        rows = conn.execute(stmt).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "symbol",
            "side",
            "qty",
            "entry_price",
            "exit_price",
            "realized_pnl",
            "fees_total",
            "opened_ts",
            "closed_ts",
            "mode",
        ]
    )

    for r in rows:
        writer.writerow(
            [
                r.id,
                r.symbol,
                r.side,
                r.qty,
                r.entry_price,
                r.exit_price or "",
                r.realized_pnl or 0.0,
                r.fees_total or 0.0,
                r.opened_ts,
                r.closed_ts,
                r.mode,
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=trades_export_{mode}.csv"},
    )


@app.get("/api/equity")
async def api_equity(range: str = "all") -> list:
    state = get_state()
    mode = str(state.current_mode)
    engine = get_engine()

    # range settings
    now_dt = datetime.utcnow()
    stmt = select(equity_snapshots.c.ts, equity_snapshots.c.equity).where(
        equity_snapshots.c.mode == mode
    )

    if range == "1d":
        since_t = (now_dt - datetime.timedelta(days=1)).isoformat()
        stmt = stmt.where(equity_snapshots.c.ts >= since_t)
    elif range == "1w":
        since_t = (now_dt - datetime.timedelta(days=7)).isoformat()
        stmt = stmt.where(equity_snapshots.c.ts >= since_t)
    elif range == "1m":
        since_t = (now_dt - datetime.timedelta(days=30)).isoformat()
        stmt = stmt.where(equity_snapshots.c.ts >= since_t)

    stmt = stmt.order_by(equity_snapshots.c.ts.asc())

    with engine.connect() as conn:
        rows = conn.execute(stmt).all()

    return [{"ts": r.ts, "equity": r.equity} for r in rows]


@app.get("/api/candles")
async def api_candles(symbol: str, timeframe: str = "1h", range: str = "all") -> list:
    from tradecore.store import candles as candle_store
    import datetime

    df = candle_store.read(symbol, timeframe)
    if df.empty:
        return []

    if range != "all":
        now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        start_ms = now_ms
        if range == "1d":
            start_ms = now_ms - (24 * 60 * 60 * 1000)
        elif range == "1w":
            start_ms = now_ms - (7 * 24 * 60 * 60 * 1000)
        elif range == "1m":
            start_ms = now_ms - (30 * 24 * 60 * 60 * 1000)

        df = df[df["ts"] >= start_ms]

    result = []
    for _, row in df.iterrows():
        result.append({
            "time": int(row["ts"] // 1000),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        })
    return result


@app.get("/api/trades/markers")
async def api_trades_markers(symbol: str, mode: str | None = None) -> list:
    import datetime
    if mode is None:
        state = get_state()
        mode = str(state.current_mode)

    engine = get_engine()
    stmt = (
        select(trades.c.ts, trades.c.side, trades.c.price)
        .where(trades.c.symbol == symbol)
        .where(trades.c.mode == mode)
        .order_by(trades.c.ts.asc())
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).all()

    result = []
    for r in rows:
        try:
            clean_str = r.ts.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(clean_str)
            time_sec = int(dt.timestamp())
        except Exception:
            time_sec = 0
        result.append({
            "time": time_sec,
            "side": r.side,
            "price": r.price,
        })
    return result


@app.get("/api/signals")
async def api_signals(limit: int = 100) -> list:
    engine = get_engine()
    stmt = (
        select(
            signals.c.timestamp,
            signals.c.symbol,
            signals.c.signal_type,
            signals.c.risk_decision,
            signals.c.risk_reason,
        )
        .order_by(desc(signals.c.timestamp))
        .limit(limit)
    )

    with engine.connect() as conn:
        rows = conn.execute(stmt).all()

    return [
        {
            "ts": r.timestamp.isoformat(),
            "symbol": r.symbol,
            "side": r.signal_type,
            "risk_decision": r.risk_decision,
            "risk_reason": r.risk_reason,
        }
        for r in rows
    ]


@app.get("/api/mode/preflight")
async def api_preflight() -> dict:
    state = get_state()
    settings = get_settings()
    current_time = time.time()

    checks = []

    # 1. API Keys & ccxt check
    client = get_ccxt_client()
    balance_ok = False
    balance_detail = "Live API keys missing in environment"
    if client.apiKey and client.secret:
        try:
            # Verify connectivity using to_thread
            await asyncio.to_thread(client.fetch_balance)
            balance_ok = True
            balance_detail = "API Connection Valid"
        except Exception as e:
            balance_detail = f"credentials error: {e}"

    checks.append(
        {
            "name": "exchange API credentials check",
            "ok": balance_ok,
            "detail": balance_detail,
        }
    )

    # 2. Kill-switch check
    checks.append(
        {
            "name": "kill-switch status",
            "ok": not state.kill_switch_active,
            "detail": "armed" if not state.kill_switch_active else "halted/triggered",
        }
    )

    # 3. Data feed staleness check
    stale_ok = True
    stale_detail = "Active"
    for symbol in settings.trading.symbols:
        t = state.get_ticker_time(symbol)
        if t is None or (current_time - t) > settings.risk.max_data_staleness_sec:
            stale_ok = False
            stale_detail = f"Stale feed on {symbol}"
            break

    checks.append({"name": "data feed freshness check", "ok": stale_ok, "detail": stale_detail})

    # 4. Paper practice history check
    engine = get_engine()
    with engine.connect() as conn:
        # closed paper trades count
        stmt_count = (
            select(func.count(positions.c.id))
            .where(positions.c.status == "closed")
            .where(positions.c.mode == "paper")
        )
        closed_count = conn.execute(stmt_count).scalar() or 0

        # paper start date
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
    history_detail = f"Recorded: {closed_count}/{req_trades} trades, {paper_days}/{req_days} days"

    checks.append(
        {
            "name": "paper trades history check",
            "ok": history_ok,
            "detail": history_detail,
        }
    )

    # Check overall live activation possibility
    can_go_live = balance_ok and (not state.kill_switch_active) and stale_ok
    if not history_ok:
        # Require override settings permissions
        if not settings.live_guard.allow_override:
            can_go_live = False

    return {"checks": checks, "can_go_live": can_go_live}


class ModeChangeRequest(BaseModel):
    target: str
    confirmation: str | None = None
    override: bool = False


@app.post("/api/mode")
async def api_mode(req: ModeChangeRequest) -> dict:
    from tradecore.core.state import switch_mode

    try:
        await switch_mode(target=req.target, confirmation=req.confirmation, override=req.override)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    # Publish mode transition
    await get_event_bus().publish(Event(type="mode", data={"mode": req.target.lower()}))
    return {"mode": req.target.lower()}


def update_config_file_mode(target: str) -> None:
    config_path = os.getenv("TRADECORE_CONFIG", "config/config.yaml")
    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            data = {}
        if "trading" not in data:
            data["trading"] = {}
        data["trading"]["mode"] = target
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f)
    except Exception as e:
        logger.error(f"Failed to persist mode {target} inside config.yaml: {e}")


@app.post("/api/killswitch")
async def api_killswitch() -> dict:
    state = get_state()
    mode = str(state.current_mode)
    state.set_kill_switch(True)

    # Flatten open positions instantly
    adapter = get_adapter(mode)
    try:
        await adapter.flatten()
    except Exception as e:
        logger.error(f"Manual killswitch flatten failed: {e}")

    # Persistent log in db
    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                insert(killswitch_events).values(
                    timestamp=datetime.now(UTC),
                    reason="Manual Dashboard Trigger",
                    resolved=0,
                    positions_flattened=1,
                    details_json='{"operator": "dashboard"}',
                )
            )

    # Publish alert
    await get_event_bus().publish(Event("killswitch", {"status": "triggered", "reason": "manual"}))
    return {"status": "triggered"}


class RearmRequest(BaseModel):
    confirmation: str


@app.post("/api/killswitch/rearm")
async def api_rearm(req: RearmRequest) -> dict:
    if req.confirmation != "RE-ARM":
        raise HTTPException(
            status_code=409, detail="Must type RE-ARM to authorize watchdog release."
        )

    from tradecore.riskengine.killswitch import rearm_killswitch
    rearm_killswitch("RE-ARM")

    # Clear unresolved DB indicators
    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                update(killswitch_events)
                .where(killswitch_events.c.resolved == 0)
                .values(resolved=1, resolved_time=datetime.now(UTC))
            )

    # Publish rearm alert
    await get_event_bus().publish(Event("killswitch", {"status": "armed"}))
    return {"status": "armed"}


@app.post("/api/strategy/pause")
async def api_pause_strategy() -> dict:
    state = get_state()
    state.set_strategy_paused(True)
    await get_event_bus().publish(Event("status", {"paused": True}))
    return {"paused": True}


@app.post("/api/strategy/resume")
async def api_resume_strategy() -> dict:
    state = get_state()
    state.set_strategy_paused(False)
    await get_event_bus().publish(Event("status", {"paused": False}))
    return {"paused": False}


@app.post("/api/paper/reset")
async def api_reset_paper() -> dict:
    state = get_state()
    settings = get_settings()
    if str(state.current_mode) != "paper":
        raise HTTPException(status_code=409, detail="Can only reset paper tables in PAPER mode.")

    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(trades.delete().where(trades.c.mode == "paper"))
            conn.execute(positions.delete().where(positions.c.mode == "paper"))
            conn.execute(equity_snapshots.delete().where(equity_snapshots.c.mode == "paper"))

    # Reset balance in kv
    set_kv("paper_balance", str(settings.paper.starting_balance))

    # Publish updates
    await get_event_bus().publish(Event("status", {}))
    await get_event_bus().publish(Event("equity", {}))
    return {"status": "reset"}


@app.get("/api/system")
async def api_system() -> dict:
    state = get_state()
    settings = get_settings()

    feeds = []
    current_time = time.time()
    for symbol in settings.trading.symbols:
        t = state.get_ticker_time(symbol)
        delay = (current_time - t) if t else -1.0
        feeds.append({"symbol": symbol, "delay_sec": delay})

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            }
        )

    # Check Ollama connection status
    ollama_ok = False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.ollama.host}/api/tags", timeout=1.0)
            ollama_ok = resp.status_code == 200
    except Exception:
        pass

    return {
        "feeds": feeds,
        "jobs": jobs,
        "ollama_ok": ollama_ok,
        "version": "1.0.0",
        "uptime_sec": int(time.time() - start_time),
    }


# Mount Static Files Router (html=True allows default index.html maps)
app.mount(
    "/dashboard/static",
    StaticFiles(directory="tradecore/dashboard/static", html=True),
    name="static",
)
