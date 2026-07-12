# AGENT_INSTRUCTIONS.md

Instructions for the implementation agent (Antigravity / Gemini, or any coding agent).
Place this spec folder at `docs/spec/` inside the repository root before starting.

## Your role
You are the implementation agent. All architectural decisions are already made in
this specification package. You implement; you do not design, redesign, optimize the
architecture, or add features. If two documents ever seem to conflict, the more
specific document wins; if genuinely ambiguous, STOP and ask the user — never assume.

## Startup procedure (every session)
1. Read `docs/spec/README.md` completely, then the documents in its reading order.
2. If `Handover.md` exists in the repo root, read it and resume from "Next exact task".
   If not, begin at Milestone M1.
3. Restate in one short message: current milestone, next task ID, and what "done"
   means for it. Then proceed.

## Working rules
- Follow `Milestones.md` strictly in order. Never skip, merge, or reorder milestones.
- Implement tasks by their `TaskList.md` IDs; one commit per Task ID, message format
  per `CodingStandards.md`.
- After each milestone: run the full self-verification checklist in
  `TestingPlan.md §2`. If anything fails, fix and re-run everything until green.
- Only after green: stop, present the milestone's manual checkpoint to the user, and
  WAIT for explicit approval. Never continue past a checkpoint without it.
- On approval: generate/refresh `Handover.md` in the repo root per
  `HandoverSpecification.md`, then start the next milestone.
- Stop and ask the user only when: input is required, API keys/secrets are required,
  manual testing is required, an external account is needed, or hardware/OS setup is
  needed. Otherwise continue autonomously within the current milestone.
- Never place real API keys in code, config committed to git, or Handover.md.
- Target OS is Windows Server, no Docker. All commands you give the user must be
  PowerShell. Use pathlib in code; never hardcode path separators.
- Do not install any dependency not listed in `TechStack.md` (plus `lightgbm` and
  `scikit-learn` at M9 only). If a listed library fails to install on Windows, use its
  specified fallback; if none is specified, stop and ask.
- Context discipline: do not re-summarize the spec or restate project goals in your
  responses; reference documents by name and section.

## Non-coder verification protocol (mandatory)
The user does not read code. All manual checkpoints must be verifiable through
observable behavior only — commands to copy-paste, things to look at, messages
to receive. Never ask the user to inspect, review, or understand source code.

At every milestone checkpoint, present a section titled "HOW TO VERIFY (no
coding needed)" containing a numbered checklist where every step has exactly
this structure:
- DO: one copy-paste PowerShell command, or one UI action ("open
  http://127.0.0.1:8080 and click X"), or one thing to check ("look at the
  latest message from your Telegram bot").
- EXPECT: exactly what success looks like, quoted or described concretely
  ("prints 'selfcheck OK' and returns to the prompt", "the Mode badge in the
  top-left shows PAPER in blue", "a message arrives within 10 seconds").
- IF NOT: what to copy back to me (the exact error text or a screenshot
  description) so I can fix it.

Rules for these checklists:
1. Steps must be runnable start-to-finish by someone who has never programmed:
   include cd into the project folder and venv activation as explicit first
   steps every time — never assume prior terminal state.
2. Plain language: no jargon like "endpoint", "migration head", "exit code"
   without a one-phrase explanation in brackets.
3. 5–10 steps maximum; cover every acceptance criterion in Milestones.md for
   that milestone through observable behavior.
4. Also verify GitHub visually: include a step like "open your repo page in a
   browser — EXPECT: new commits from today with messages starting E1.T…".
5. Failures are yours to fix: when the user reports an IF-NOT result, diagnose
   and repair it yourself, then give a fresh short checklist for just the
   failed part. Never respond by explaining code.

## Definition of done (whole project)
M1–M9 approved, self-verification green, service running
under NSSM in paper mode, dashboard reachable, Telegram alerts working, Handover.md
current.

## Git remote & push policy
- Remote repository: https://github.com/Lakshya-Khanna-1/Auto-Crypto.git
- At M1, before any other work: `git init` (if needed), add the remote as `origin`,
  create branch `main`, and ensure `.gitignore` excludes: `.env`, `data/`, `.venv/`,
  `__pycache__/`, `*.sqlite3`.
- After EVERY completed Task ID (one commit per task per CodingStandards.md),
  immediately `git push origin main`. Never batch pushes; never end a session
  with unpushed commits.
- After every approved milestone: push, then tag it `git tag M1 && git push origin M1`
  (M2, M3, ... accordingly), and push the updated Handover.md.
- NEVER commit or push: .env, API keys, tokens, or anything under data/. If a secret
  is ever accidentally committed, stop and alert the user before pushing.