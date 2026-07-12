# AILayer.md

**Advisory only.** The AI layer never emits signals, never sizes positions, never
touches the ExecutionAdapter or Risk Engine. If Ollama is down, trading continues
unaffected (dashboard panel 5 shows ✗). Built LAST (Milestone M8).

## 1. Models for RTX A2000 12GB / 32GB RAM

Only the main model stays resident; others load on demand (Ollama handles swapping;
jobs are async and infrequent so swap latency is acceptable).

| Role | Model | Pull command | VRAM (approx) | Fallback |
|------|-------|--------------|---------------|----------|
| Main (reports, summarization, explanation) | `qwen2.5:7b-instruct-q4_K_M` | `ollama pull qwen2.5:7b-instruct-q4_K_M` | ~5.5 GB | `mistral:7b-instruct-q4_K_M` |
| Fast (classification/routing, short tasks) | `llama3.2:3b` | `ollama pull llama3.2:3b` | ~2.5 GB | `phi3.5:3.8b` |
| Embeddings (v1: unused at runtime; pulled for FutureImprovements news-dedup) | `nomic-embed-text` | `ollama pull nomic-embed-text` | ~0.5 GB | `all-minilm` |

Why: Qwen2.5-7B at q4_K_M is the best quality/speed balance that fits 12 GB with
headroom; 3B-class model answers classification prompts in ~1 s. Set env
`OLLAMA_MAX_LOADED_MODELS=1` and `OLLAMA_KEEP_ALIVE=30m` (WindowsDeployment.md).

## 2. v1 features (only these two)

**Daily report** (`ailayer/reports.py`, scheduler 00:15 UTC): build a compact context
(yesterday's trades, P&L, equity change, rejections, kill-switch events, open
positions) → main model → plain-text report ≤ 300 words → save to `app_kv`
(`latest_report`) + Telegram + dashboard panel 6.

**Trade annotation** (fast model): on each closed position, generate a one-sentence
plain-English explanation from the signal reason + outcome; stored in a nullable
`annotation` column on `positions` (add via migration in M8).

## 3. Client rules (`ailayer/client.py`)
- Timeout `ollama.request_timeout_sec` (60 s); on timeout/error: log WARNING, return
  None, caller degrades gracefully (report says "AI report unavailable").
- Never block the event loop: run in `asyncio.to_thread` or use async client.
- All prompt templates live ONLY in `ailayer/prompts.py`.

## 4. Prompt templates (final wording, fill placeholders)

daily_report:
"You are the reporting assistant of an automated crypto trading system. Write a factual
daily report under 300 words. No advice, no predictions, no hype. Data: {json_context}.
Structure: 1) P&L summary 2) trades taken and why (signal reasons given) 3) risk events
4) open positions. If there were no trades, say so plainly."

trade_annotation:
"In one sentence, explain this closed trade to a non-expert. Entry reason: {reason}.
Entry {entry_price}, exit {exit_price}, P&L {pnl}. Be factual, no speculation."
