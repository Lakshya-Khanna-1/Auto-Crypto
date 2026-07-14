DAILY_REPORT_PROMPT = (
    "You are the reporting assistant of an automated crypto trading system. Write a factual "
    "daily report under 300 words. No advice, no predictions, no hype. Data: {json_context}. "
    "Structure: 1) P&L summary 2) trades taken and why (signal reasons given) 3) risk events "
    "4) open positions. If there were no trades, say so plainly."
)

TRADE_ANNOTATION_PROMPT = (
    "In one sentence, explain this closed trade to a non-expert. Entry reason: {reason}. "
    "Entry {entry_price}, exit {exit_price}, P&L {pnl}. Be factual, no speculation."
)
