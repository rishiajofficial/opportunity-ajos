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

4. Add **`APOLLO_API_KEY`** in **Cursor**, not in the git repo. **Never commit this key.**
   - **Primary (recommended):** [cursor.com/dashboard](https://cursor.com/dashboard) → **Cloud Agents** / **Settings** → **Secrets** → add `APOLLO_API_KEY` = your Apollo API key (from apollo.io → Settings → API keys).
   - **Also check:** automation editor → **Environment variables** (if shown) → same name/value.
   - **Does not work:** Streamlit Cloud secrets, `.streamlit/secrets.toml`, or `.env` in the repo — cloud agents do not read those unless you copy values into Cursor Secrets.
   - Without Cursor Secrets, the agent correctly stops with `APOLLO_MISSING` and records `processed=0` (as in your run).
5. Paste the **Agent instructions** below into the automation prompt field.
6. Save and enable the automation.

Quick checklist: [`automation/ajos-email-finder-setup.md`](automation/ajos-email-finder-setup.md)

## Agent instructions (paste into automation)

```text
You are the AJOS email finder agent. Follow EMAIL_FINDER_AGENT.md and this runbook.

## Verify environment (do this first)
1. You must be in the cloned repo root — run `pwd && ls EMAIL_FINDER_AGENT.md email_finder_engine.py`
2. If files are missing, STOP: the automation Repository must be `rishiajofficial/opportunity-ajos` branch `main` with Git commit+push enabled. Do not use gh auth or guess paths under /agent.
3. Run `test -n "$APOLLO_API_KEY" && echo APOLLO_OK || echo APOLLO_MISSING` — if APOLLO_MISSING, STOP and report that APOLLO_API_KEY env var is not set on this automation.

## Start
4. Read data/email_finder/config.json
5. If enabled is false: run `python3 email_finder_engine.py record-run --processed 0 --emails-found 0 --credits-used 0` and stop

## Run
6. Read data/learning/state.json and data/companies.csv for context
7. Run `python3 email_finder_engine.py list-queue`
8. If queue is empty, record run with zeros and stop
9. Run:
   python3 email_finder_engine.py run --max <config.max_companies_per_run>
10. Note processed count, emails_found, and credits_used from JSON output

## Finish
11. Git commit ONLY these paths if changed:
   - data/contacts/companies/*.json
   - data/actions/companies/*.json
   - data/email_finder/runs.json
   Commit message: email-finder: add emails for <companies> (<N> credits)
12. Push to main

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

## Troubleshooting failed runs

| Symptom | Cause | Fix |
| --- | --- | --- |
| `EMAIL_FINDER_AGENT.md` / `email_finder_engine.py` not found under `/agent` | **Repository not linked** on the automation | Edit automation → set Repository `rishiajofficial/opportunity-ajos`, Branch `main`, enable **Git commit + push** |
| `gh` not authenticated | Agent tried GitHub CLI because repo was not cloned | Fix repository link above; Cursor clones the repo when configured — `gh` is not required |
| `APOLLO_API_KEY` missing (repo + queue OK) | Secret not in **Cursor dashboard Secrets** | [cursor.com/dashboard](https://cursor.com/dashboard) → Secrets → `APOLLO_API_KEY`; re-run until agent prints `APOLLO_OK` |
| Run on `cursor/email-finder-*` branch | Normal agent branch workflow | Open PR and merge to `main` after contacts JSON updates |
| No files committed | Run failed before Apollo calls, or queue empty | Fix blockers, then re-run; check `python3 email_finder_engine.py list-queue` locally |

Files are on `main` (commit `96c8c23`+). If the agent cannot see them, the automation is not pointed at this repo.

## Verify a run

- GitHub: latest commit on `main` touching `data/contacts/` or `data/email_finder/runs.json`
- Local: `python3 email_finder_engine.py list-queue`
- AJOS: Interested company → Research tab shows email on contact card
