# AJOS Development Agent

Implements approved product and code feedback from the AJOS dashboard.

## Trigger

The dev agent runs when [`data/learning/dev_agent_queue.json`](data/learning/dev_agent_queue.json)
contains one or more items with `"status": "queued"`.

Items are added when Ankit clicks **Approve** on a dev proposal in the AJOS **Learning**
tab (or after approving feedback submitted via the **Dev feedback** panel).

## Queue item shape

```json
{
  "id": "dev_20260612120000",
  "feedback": "Learning questions keep repeating after I answer them",
  "suggested_action": "Implement in opportunity-engine: Learning questions keep repeating...",
  "approved_at": "2026-06-12T12:00:00+00:00",
  "status": "queued"
}
```

## Agent workflow

1. Read `data/learning/dev_agent_queue.json`. If no queued items, stop.
2. For each queued item (oldest first):
   - Read the `feedback` and `suggested_action`.
   - Implement the change in this repo. Keep scope minimal; match `learning.py` and `app.py` style.
   - Run a quick sanity check (`python -c "import learning, app"` or relevant tests).
3. After implementing:
   - Mark the matching item in `data/learning/dev_feedback.json` as `"status": "implemented"`.
   - Remove the item from `dev_agent_queue.json` or set `"status": "done"`.
   - Regenerate `data/learning/proposals.json` if learning state changed.
4. Git commit changed code and data files. Commit message: `dev: <short summary from feedback>`.
5. Push to `main` so Streamlit Cloud rebuilds.

## Rules

- Never edit `MEMORY.md`, `DECISIONS.md`, `ROADMAP.md`, or `VISION.md` unless the feedback explicitly asks for doc updates.
- Do not auto-commit secrets or `.env` files.
- If feedback is ambiguous, implement the smallest reasonable interpretation and note assumptions in the commit message.
- Do not re-queue dismissed or already-implemented feedback.

## Related files

| File | Purpose |
| --- | --- |
| `data/learning/dev_feedback.json` | All submitted feedback and statuses |
| `data/learning/dev_agent_queue.json` | Approved items waiting for the agent |
| `data/learning/proposals.json` | Includes `dev_proposals` for pending feedback |

See [`CLOUD_DEV_AUTOMATION.md`](CLOUD_DEV_AUTOMATION.md) for Cursor Cloud Automation setup.
