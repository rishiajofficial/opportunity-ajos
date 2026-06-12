# AJOS Cloud Email Finder Automation

Scheduled email enrichment for **Interested** companies via **Cursor Cloud Automation** and the Apollo.io API.

## One-time setup (Cursor dashboard)

1. Open [Cursor Automations](https://cursor.com/automations).
2. Ensure [Cloud Agents](https://cursor.com/dashboard?tab=cloud-agents) compute is enabled.
3. Create a new automation:

| Field | Value |
| --- | --- |
| **Name** | `AJOS Email Finder` |
| **Description** | Find emails for Interested companies via Apollo API |
| **Trigger** | Cron: `0 10,22 * * *` (10:00 and 22:00 UTC daily) — after discovery runs |
| **Repository** | `rishiajofficial/opportunity-ajos` |
| **Branch** | `main` |
| **Tools** | Git commit + push enabled |

4. Add environment variable **`APOLLO_API_KEY`** (from Apollo → Settings → API keys). **Never commit this key.**
5. Paste the **Agent instructions** below into the automation prompt field.
6. Save and enable the automation.

## Agent instructions (paste into automation)

```text
You are the AJOS email finder agent. Follow EMAIL_FINDER_AGENT.md and this runbook.

## Start
1. Read data/email_finder/config.json
2. If enabled is false: run `python email_finder_engine.py record-run --processed 0 --emails-found 0 --credits-used 0` and stop
3. Confirm APOLLO_API_KEY is available in the environment

## Run
4. Read data/learning/state.json and data/companies.csv for context
5. Run `python email_finder_engine.py list-queue`
6. If queue is empty, record run with zeros and stop
7. Run:
   python email_finder_engine.py run --max <config.max_companies_per_run>
8. Note processed count, emails_found, and credits_used from JSON output

## Finish
9. Git commit ONLY these paths if changed:
   - data/contacts/companies/*.json
   - data/actions/companies/*.json
   - data/email_finder/runs.json
   Commit message: email-finder: add emails for <companies> (<N> credits)
10. Push to main

## Rules
- Never edit MEMORY.md, DECISIONS.md, ROADMAP.md, VISION.md
- Never send email or LinkedIn
- Never hand-edit contacts/actions JSON — use email_finder_engine.py CLI only
- Never commit APOLLO_API_KEY
```

## Email finder config

Edit [`data/email_finder/config.json`](data/email_finder/config.json):

| Field | Default | Purpose |
| --- | --- | --- |
| `enabled` | `true` | Master switch |
| `max_companies_per_run` | `3` | Cap companies per cron run |
| `max_contacts_per_company` | `2` | Top-priority contacts without email |
| `max_credits_per_run` | `10` | Protect Apollo free credits |
| `require_verified_email` | `false` | Only write `email_status: verified` |
| `allow_generic_emails` | `false` | Reject `info@`, `support@`, etc. |

## Local testing

```bash
export APOLLO_API_KEY="your-key-here"
python email_finder_engine.py list-queue
python email_finder_engine.py run --max 1 --dry-run
python email_finder_engine.py run --max 1
```

Dry-run calls Apollo but does not write JSON or record a run.

## Apollo credits

- `people/match` costs **1 credit** per successful enrichment call
- `mixed_people/api_search` is **free** (used as fallback before match)
- Free plan includes a limited monthly credit pool (e.g. 75) — monitor usage in Apollo dashboard

## Streamlit Cloud (optional)

For a future in-app trigger, add to Streamlit secrets (not git):

```toml
APOLLO_API_KEY = "your-key-here"
```

The CLI engine reads `APOLLO_API_KEY` from the environment first.
