# AJOS Cloud Discovery Automation

Scheduled opportunity research via **Cursor Cloud Automation**. No local PC or open IDE required.

## One-time setup (Cursor dashboard)

1. Open [Cursor Automations](https://cursor.com/automations) (or Automations in the Cursor app).
2. Ensure [Cloud Agents](https://cursor.com/dashboard?tab=cloud-agents) compute is enabled.
3. Create a new automation:

| Field | Value |
| --- | --- |
| **Name** | `AJOS Discovery` |
| **Description** | Research and queue new opportunities for Ankit per discovery config |
| **Trigger** | Cron: `0 8,20 * * *` (08:00 and 20:00 UTC daily) — adjust to your timezone |
| **Repository** | `rishiajofficial/opportunity-ajos` |
| **Branch** | `main` |
| **Tools** | Git commit + push enabled |

4. Paste the **Agent instructions** below into the automation prompt field.
5. (Optional) Enable **Slack** — see [Slack notification](#slack-notification-optional).
6. Save and enable the automation.

After setup, each run clones `main`, researches candidates, updates JSON, and pushes. Streamlit Cloud rebuilds in ~1–3 minutes.

## Agent instructions (paste into automation)

```text
You are the AJOS discovery agent. Follow DISCOVERY_AGENT.md and this runbook.

## Start
1. Read data/discovery/config.json
2. If enabled is false: run `python discovery_engine.py record-run --themes none --added 0` and stop (no git push needed unless runs.json changed)

## Research
3. Read AGENTS.md, data/ankit_profile.json, data/learning/state.json, data/learning/proposals.json, data/companies.csv, data/discovery/candidates.json
4. Run `python discovery_engine.py list-rejected` and avoid those slugs
5. Search only within config.active_countries, config.active_themes, and config.active_industries; skip config.exclude_keywords
6. Add 0 to config.max_candidates_per_run candidates via:
   python discovery_engine.py add --json @/tmp/candidate.json
7. Track NOTIFY on stderr — if any candidate scores >= config.notify_threshold, note the best one for Slack (max one message per run)

## Finish
8. Record run:
   python discovery_engine.py record-run --themes "<themes searched>" --added <count>
9. Git commit ONLY these paths if changed:
   - data/discovery/candidates.json
   - data/discovery/runs.json
   Commit message: discovery: add N candidates (<theme summary>)
10. Push to main

## Rules
- Never edit MEMORY.md, DECISIONS.md, ROADMAP.md, VISION.md
- Never send email or LinkedIn
- Never hand-edit discovery JSON — use discovery_engine.py CLI only
- Require verified website + source_urls per candidate
```

## Discovery config (search scope)

Edit in AJOS **Discovery** panel or commit [`data/discovery/config.json`](data/discovery/config.json):

```json
{
  "enabled": true,
  "active_countries": ["UAE", "India", "Netherlands"],
  "active_themes": ["Wellness & Mental Wellbeing", "Human Potential"],
  "active_industries": ["workplace wellbeing"],
  "exclude_keywords": ["crypto"],
  "max_candidates_per_run": 3,
  "notify_threshold": 85
}
```

**Important:** Streamlit Cloud saves config on the server filesystem. The cloud agent reads **GitHub**. After changing settings in the app, commit and push `config.json`, or edit directly in the repo.

## Slack notification (optional)

In the automation editor:

1. Add tool: **Post to Slack**
2. Connect your Slack workspace and pick a channel (e.g. `#ajos` or DM yourself)
3. Add to the agent instructions after step 7:

```text
If NOTIFY was printed for a candidate, post one Slack message:
"AJOS: New opportunity — <name> (<country>, <theme>) score <weighted>. Open AJOS review queue."
```

Do not notify more than once per run.

## Verify a run

- GitHub: latest commit on `main` touching `data/discovery/`
- Local: `python discovery_engine.py list-pending`
- AJOS: review queue shows **Discovered** badge; footer shows last run

## Manual test (before enabling cron)

Run the agent instructions once manually from a Cursor cloud agent session against this repo, or locally:

```bash
python discovery_engine.py show-config
# ... research and add ...
python discovery_engine.py record-run --themes "Wellness & Mental Wellbeing" --added 1
```

## Legacy: local `/loop`

For development only while Cursor IDE is open:

```text
/loop 3h Research per DISCOVERY_AGENT.md. Read config.json first.
```

Prefer cloud automation for production.

## Data caveat

Feedback given on Streamlit Cloud (`data/learning/state.json`) is not on GitHub unless committed. The cloud agent uses the **committed** learning state. Shared storage is a future improvement.
