# AJOS Cloud Orchestrator Automation

Event-driven and scheduled processing of the unified AJOS work queue.

## One-time setup

1. Open [Cursor Automations](https://cursor.com/automations).
2. Create a new automation:

| Field | Value |
| --- | --- |
| **Name** | `AJOS Orchestrator` |
| **Description** | Drain orchestrator queue — outreach, dev, improve |
| **Trigger** | Webhook + Cron backup `*/30 * * * *` |
| **Repository** | Your `opportunity-engine` GitHub repo |
| **Branch** | `main` |
| **Tools** | Git commit + push enabled |

3. Save automation, copy **Webhook URL** and **Auth token**.
4. Add GitHub secrets: `CURSOR_WEBHOOK_URL`, `CURSOR_WEBHOOK_TOKEN`.
5. Enable `.github/workflows/ajos-orchestrator-trigger.yml`.

## Agent instructions (paste into automation)

```text
You are the AJOS orchestrator agent. Follow ORCHESTRATOR.md.

## Start
1. Read data/orchestrator/queue.json
2. If no items with status "queued": stop (no git push)

## Process
3. Read AGENTS.md and ORCHESTRATOR.md
4. For each queued item (priority asc, oldest first, max 3):
   - outreach_pipeline: python pipeline_runner.py --company "<company>"
   - dev_implement: follow DEV_AGENT.md for feedback_id
   - outreach_improve: update data/ankit_profile.json outreach_voice examples from data/outreach/outcomes.json
   - Mark done in queue.json

## Finish
5. Run: python3 -m py_compile *.py
6. Git commit changed paths. Message: orchestrator: <summary>
7. Push to main
```

## Webhook trigger

GitHub Action fires on push to `data/orchestrator/**`, `data/learning/dev_agent_queue.json`, or `data/learning/state.json`.

Manual trigger:

```bash
curl -X POST "$CURSOR_WEBHOOK_URL" \
  -H "Authorization: Bearer $CURSOR_WEBHOOK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"event":"ajos.run"}'
```

## Slack slash commands

Deploy `slack_bot.py` with `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, and webhook secrets.

- `/ajos status` — queue depth
- `/ajos run` — trigger orchestrator now
- `/ajos improve <text>` — submit dev feedback
- `/ajos sent <company>` — record sent email + learn

See [`automation/ajos-orchestrator-setup.md`](automation/ajos-orchestrator-setup.md).
