# AJOS Orchestrator Agent

Drains the unified work queue in `data/orchestrator/queue.json`.

## Trigger

Run when the queue contains items with `"status": "queued"`, or when triggered via webhook / `/ajos run`.

## Work types

| Type | Action |
|------|--------|
| `outreach_pipeline` | `python pipeline_runner.py --company "<name>"` |
| `dev_implement` | Follow `DEV_AGENT.md` for matching `feedback_id` |
| `outreach_improve` | Append sent email to profile few-shots; update angles |
| `discovery_run` | Follow `DISCOVERY_AGENT.md` |
| `content_refine` | Follow `CONTENT_AGENT.md` |
| `sync_check` | Verify `github_sync` status; re-queue stuck items |

## Workflow

1. Read `data/orchestrator/queue.json` and `data/orchestrator/config.json`.
2. Process up to `max_items_per_run` queued items (oldest/highest priority first).
3. For each item, run the appropriate CLI or agent runbook.
4. Mark item `done` or `failed` with result note.
5. Commit changed paths only. Message: `orchestrator: <summary>`
6. Push to `main`.

## Rules

- Never edit MEMORY.md, DECISIONS.md, ROADMAP.md, VISION.md unless feedback asks.
- Do not send email or LinkedIn on behalf of Ankit.
- Stop with no commit if queue is empty.

## Related files

| File | Purpose |
|------|---------|
| `data/orchestrator/queue.json` | Work queue |
| `data/orchestrator/config.json` | Orchestrator settings |
| `orchestrator_engine.py` | Enqueue/dequeue helpers |
| `pipeline_runner.py` | Outreach pipeline CLI |
| `CLOUD_ORCHESTRATOR_AUTOMATION.md` | Cursor Automation setup |
