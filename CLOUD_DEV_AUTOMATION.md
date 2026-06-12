# AJOS Cloud Dev Automation

Scheduled (or manual) implementation of approved dev feedback via **Cursor Cloud Automation**.

## One-time setup

1. Open [Cursor Automations](https://cursor.com/automations).
2. Create a new automation:

| Field | Value |
| --- | --- |
| **Name** | `AJOS Dev Agent` |
| **Description** | Implement approved dev feedback from AJOS queue |
| **Trigger** | Cron: `0 */6 * * *` (every 6 hours) — or **Manual** for on-demand runs |
| **Repository** | Your `opportunity-engine` GitHub repo |
| **Branch** | `main` |
| **Tools** | Git commit + push enabled |

3. Paste the **Agent instructions** below into the automation prompt.
4. Save and enable.

**Important:** Streamlit Cloud writes `dev_feedback.json` and `dev_agent_queue.json` on its server filesystem. The cloud agent reads **GitHub**. After approving feedback in the app, commit and push those JSON files (or use a workflow that syncs them) so the automation sees queued items.

## Agent instructions (paste into automation)

```text
You are the AJOS development agent. Follow DEV_AGENT.md.

## Start
1. Read data/learning/dev_agent_queue.json
2. If items is empty or no item has status "queued": stop (no git push)

## Implement
3. Read AGENTS.md and DEV_AGENT.md
4. Process each queued item (oldest first):
   - Implement the feedback in the opportunity-engine repo
   - Mark item done in dev_agent_queue.json and dev_feedback.json per DEV_AGENT.md
5. Run: python -c "import learning; import app"

## Finish
6. Git commit only changed paths. Message: dev: <summary>
7. Push to main
```

## Manual trigger

You can also run the dev agent locally in Cursor with:

```text
Read DEV_AGENT.md and implement any queued items in data/learning/dev_agent_queue.json
```

## Polling alternative

If you prefer not to use cron, add a GitHub Action or webhook that runs when `dev_agent_queue.json` changes on `main`. The agent instructions stay the same.
