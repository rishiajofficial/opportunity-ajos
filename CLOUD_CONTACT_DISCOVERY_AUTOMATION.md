# AJOS Cloud Contact Discovery Automation

Scheduled contact seeding for **Interested** companies via **Cursor Cloud Automation** and the Hunter.io API.

## One-time setup (Cursor dashboard)

1. Open [Cursor Automations](https://cursor.com/automations).
2. Ensure [Cloud Agents](https://cursor.com/dashboard?tab=cloud-agents) compute is enabled.
3. Create a new automation:

| Field | Value |
| --- | --- |
| **Name** | `AJOS Contact Discovery` |
| **Description** | Seed contacts for Interested companies via Hunter API |
| **Trigger** | Cron: `0 9,21 * * *` (09:00 and 21:00 UTC daily) — before email finder |
| **Repository** | `rishiajofficial/opportunity-ajos` |
| **Branch** | `main` |
| **Tools** | Git commit + push enabled |

4. Add **`HUNTER_API_KEY`** in **Cursor Secrets** (never commit). Get it from [hunter.io](https://hunter.io/api-keys) — free plan includes 50 credits/month + API access.
5. Paste the **Agent instructions** below into the automation prompt field.
6. Save and enable the automation.

Quick checklist: [`automation/ajos-contact-discovery-setup.md`](automation/ajos-contact-discovery-setup.md)

## Agent instructions (paste into automation)

```text
You are the AJOS contact discovery agent. Follow CONTACT_DISCOVERY_AGENT.md and this runbook.

## Verify environment (do this first)
1. Run `pwd && ls CONTACT_DISCOVERY_AGENT.md contact_discovery_engine.py`
2. Run `test -n "$HUNTER_API_KEY" && echo HUNTER_OK || echo HUNTER_MISSING` — if HUNTER_MISSING, STOP.

## Start
3. Read data/contact_discovery/config.json
4. If enabled is false: run `python3 contact_discovery_engine.py record-run --processed 0 --contacts-added 0 --credits-used 0` and stop

## Run
5. Read data/learning/state.json and data/companies.csv for context
6. Run `python3 contact_discovery_engine.py list-queue`
7. If queue is empty, record run with zeros and stop
8. Run:
   python3 contact_discovery_engine.py run --max <config.max_companies_per_run>
9. For any company still missing contacts after bootstrap, research and use:
   python3 contact_discovery_engine.py add --json @/tmp/<slug>-contacts.json

## Finish
10. Git commit ONLY these paths if changed:
   - data/contacts/companies/*.json
   - data/actions/companies/*.json
   - data/contact_discovery/runs.json
   Commit message: contact-discovery: add contacts for <companies> (<N> credits)
11. Push to main

## Rules
- Never edit MEMORY.md, DECISIONS.md, ROADMAP.md, VISION.md
- Never send email or LinkedIn
- Never hand-edit contacts JSON — use contact_discovery_engine.py CLI only
- Never commit HUNTER_API_KEY
```

## Contact discovery config

Edit [`data/contact_discovery/config.json`](data/contact_discovery/config.json):

| Field | Default | Purpose |
| --- | --- | --- |
| `enabled` | `true` | Master switch |
| `max_companies_per_run` | `2` | Cap companies per cron run |
| `max_contacts_per_company` | `5` | Max contacts seeded per company |
| `max_credits_per_run` | `15` | Protect Hunter free credits |
| `allow_generic_emails` | `false` | Reject `info@`, `support@`, etc. |

## Local testing

```bash
export HUNTER_API_KEY="your-key-here"
python3 contact_discovery_engine.py list-queue
python3 contact_discovery_engine.py run --max 1 --dry-run
python3 contact_discovery_engine.py run --max 1
```

## Hunter credits

- Domain Search: **1 credit per email returned**
- Free plan: **50 credits/month** — enough for ~10 companies at 5 contacts each if emails exist
- Email not found = 0 credits (Email Finder endpoint, used by email finder agent)

## Verify a run

- GitHub: latest commit touching `data/contacts/companies/` or `data/contact_discovery/runs.json`
- Local: `python3 contact_discovery_engine.py list-queue` (RemotePass should disappear once seeded)
- AJOS: Interested company → Research tab shows contact names
