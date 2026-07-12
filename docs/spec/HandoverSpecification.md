# HandoverSpecification.md

At every approved milestone the implementation model must be able to emit a single
`Handover.md` enabling a brand-new chat session to continue seamlessly. Keep it as
small as possible. NO project overview, business context, design rationale, history,
or completed discussion.

## Required sections (exactly these, in order)

```markdown
# Handover — <date> — after <Milestone ID>

## Position
Completed milestones: M1..Mx
Current milestone: Mx+1 (<name>) — not started | in progress at <Task ID>
Next exact task: <Epic.Task.Subtask ID + one-line action>

## Repo state
Branch: <name> @ <short sha>; working tree clean: yes/no (if no: list files)
Files currently mid-edit: <list or none>

## Environment
Installed deps changed since last handover: <list or none>
Env vars required now: <names only, never values>
Config values changed from defaults: <yaml paths + values>

## Data & DB
Alembic revision: <id> (= head: yes/no)
Backfill state: <symbols/ranges done>
Paper account state: balance <x>, open positions <n>

## Issues
Known bugs: <ID'd list or none>
Open TODOs: <list or none>
Current blockers: <list or none>
Assumptions currently in force: <list or none>

## Continue
Commands to resume work:
<venv activate, selfcheck, pytest, nssm status — only what applies>
```

Rules: bullet fragments, not prose; reference spec documents by name instead of
restating them; values that are secrets are NEVER included; target < 60 lines.
