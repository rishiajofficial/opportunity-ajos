# AJOS Content Refinement Automation

Scheduled copy refinement via **Cursor Cloud Automation**. Rewrites opportunity profiles in Ankit's Hinglish voice and re-queues unclear ones.

## One-time setup (Cursor dashboard)

1. Open [Cursor Automations](https://cursor.com/automations).
2. Create a new automation:

| Field | Value |
| --- | --- |
| **Name** | `AJOS Content` |
| **Description** | Refine opportunity copy in Ankit's Hinglish voice |
| **Trigger** | Cron: `30 9,21 * * *` (09:30 and 21:30 UTC — after discovery runs) |
| **Repository** | `rishiajofficial/opportunity-ajos` |
| **Branch** | `main` |
| **Tools** | Git commit + push enabled |

3. Paste **Agent instructions** below into the prompt field.
4. Save and enable.

## Agent instructions (paste into automation)

```text
You are the AJOS content refinement agent. Follow CONTENT_AGENT.md and this runbook.

## Start
1. Read data/content/config.json
2. If enabled is false: run `python content_engine.py record-run --refined 0` and stop

## Refine
3. Read AGENTS.md, data/ankit_profile.json (content_voice), data/learning/state.json, data/learning/proposals.json (content_suggestions)
4. Run `python content_engine.py list-pending` — process all pending items first (from "Didn't understand" feedback)
5. For each company (max config.max_companies_per_run):
   a. `python content_engine.py brief --company "<name>"`
   b. Deep rewrite description, why_fit, problems_to_solve in Roman Hinglish — specific to Ankit, not generic
   c. `python content_engine.py update --company "<name>" --json @/tmp/copy.json`
   d. `python content_engine.py mark-refined --company "<name>"`
6. If queue was empty: optionally refine 1 company whose copy still feels English/generic

## Finish
7. `python content_engine.py record-run --refined <count>`
8. Git commit ONLY if changed:
   - data/companies.csv
   - data/content/refinement_queue.json
   - data/content/runs.json
   - data/intelligence/companies/*.json (if updated)
   Commit message: content: refine N companies (Hinglish copy)
9. Push to main

## Rules
- Never edit MEMORY.md, DECISIONS.md, ROADMAP.md, VISION.md
- Use content_engine.py CLI only for queue/CSV updates
- Email drafts stay English — only review-facing copy is Hinglish
```

## Config

[`data/content/config.json`](data/content/config.json):

```json
{
  "enabled": true,
  "max_companies_per_run": 3,
  "requeue_after_refine": true
}
```

- `requeue_after_refine: true` — after refine, profile returns to review queue with improved copy

## "Didn't understand" flow

In AJOS review, Ankit taps **Didn't understand** → optional note → profile leaves queue.

1. Feedback saved as `Didn't Understand` in learning state
2. Company added to `data/content/refinement_queue.json`
3. Content agent picks it up on next run
4. After refine + `mark-refined`, profile re-appears in queue

## Verify a run

```bash
python content_engine.py list-pending
python content_engine.py show-config
```

AJOS footer shows: `Content agent on · last run: … · refined N · pending M`

## Data caveat

Same as discovery: Streamlit Cloud `state.json` may not be on GitHub. Content agent uses **committed** learning state. For production, commit learning state periodically or sync shared storage.
