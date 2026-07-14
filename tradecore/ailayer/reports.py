import json
from datetime import UTC, datetime, timedelta

from tradecore.ailayer.client import generate_response
from tradecore.ailayer.prompts import DAILY_REPORT_PROMPT
from tradecore.core.config import get_settings
from tradecore.store import repo


def build_report_context(mode: str) -> dict:
    """
    Build report context for yesterday (00:00:00 to 23:59:59 UTC).
    """
    now = datetime.now(UTC)
    yesterday = now - timedelta(days=1)

    start_dt = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)

    start_str = start_dt.isoformat()
    end_str = end_dt.isoformat()

    # Query database
    trades_list = repo.get_trades_in_range(mode, start_str, end_str)
    closed_pos = repo.get_positions_closed_in_range(mode, start_str, end_str)
    rejections = repo.get_rejected_signals_in_range(start_dt, end_dt)
    ks_events = repo.get_killswitch_events_in_range(start_dt, end_dt)
    open_pos = repo.get_open_positions(mode)

    starting_equity = repo.get_equity_snapshot_closest_to(mode, start_str, order="asc")
    ending_equity = repo.get_equity_snapshot_closest_to(mode, end_str, order="desc")

    if starting_equity is None:
        settings = get_settings()
        starting_equity = settings.paper.starting_balance if mode == "paper" else 10000.0
    if ending_equity is None:
        ending_equity = starting_equity

    realized_pnl = sum(p.get("realized_pnl") or 0.0 for p in closed_pos)

    # Format structures
    formatted_trades = []
    for t in trades_list:
        formatted_trades.append(
            {
                "ts": t.get("ts"),
                "symbol": t.get("symbol"),
                "side": t.get("side"),
                "qty": t.get("qty"),
                "price": t.get("price"),
                "fee": t.get("fee"),
            }
        )

    formatted_rejections = []
    for r in rejections:
        formatted_rejections.append(
            {
                "timestamp": r.get("timestamp").isoformat()
                if isinstance(r.get("timestamp"), datetime)
                else str(r.get("timestamp")),
                "symbol": r.get("symbol"),
                "reason": r.get("risk_reason"),
            }
        )

    formatted_ks = []
    for ks in ks_events:
        formatted_ks.append(
            {
                "timestamp": ks.get("timestamp").isoformat()
                if isinstance(ks.get("timestamp"), datetime)
                else str(ks.get("timestamp")),
                "reason": ks.get("reason"),
            }
        )

    formatted_open = []
    for op in open_pos:
        formatted_open.append(
            {
                "symbol": op.get("symbol"),
                "side": op.get("side"),
                "qty": op.get("qty"),
                "entry_price": op.get("entry_price"),
            }
        )

    return {
        "date": yesterday.date().isoformat(),
        "mode": mode,
        "starting_equity": starting_equity,
        "ending_equity": ending_equity,
        "equity_change": ending_equity - starting_equity,
        "realized_pnl": realized_pnl,
        "trades_count": len(trades_list),
        "trades": formatted_trades,
        "rejections": formatted_rejections,
        "killswitch_events": formatted_ks,
        "open_positions": formatted_open,
    }


async def generate_daily_report(mode: str) -> str:
    """
    Query yesterday's context, compile prompt, call client, return report text.
    """
    settings = get_settings()
    ctx = build_report_context(mode)
    json_ctx_str = json.dumps(ctx, indent=2)
    prompt = DAILY_REPORT_PROMPT.format(json_context=json_ctx_str)

    report_text = await generate_response(settings.ollama.main_model, prompt)
    if not report_text:
        return "AI report unavailable"
    return report_text.strip()
