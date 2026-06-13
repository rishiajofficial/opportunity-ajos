# AJOS Contact Discovery Agent

Identify **who to reach** at **Interested** companies and create `data/contacts/companies/{slug}.json`. **Primary runtime: Cursor Cloud Automation** (scheduled). See [`CLOUD_CONTACT_DISCOVERY_AUTOMATION.md`](CLOUD_CONTACT_DISCOVERY_AUTOMATION.md).

## Mission

Before the email finder can enrich contacts, each Liked company needs a contacts file with founders, CEOs, and relevant leaders. This is research + data seeding only — never send email or LinkedIn messages.

## Before each run — read these files

1. `AGENTS.md` — mission context
2. **`data/contact_discovery/config.json`** — enabled flag, caps
3. `data/learning/state.json` — which companies are Interested (`Like`)
4. `data/companies.csv` — company websites (domains)
5. `data/contacts/companies/` — existing contact files

If `config.enabled` is `false`, **stop immediately** and record a run with zero processed.

```bash
python3 contact_discovery_engine.py show-config
python3 contact_discovery_engine.py list-queue
```

Requires **`HUNTER_API_KEY`** for automated bootstrap (never commit the key).

## Each run — tasks

1. Confirm `HUNTER_API_KEY` is set in the automation environment.
2. Run `python3 contact_discovery_engine.py list-queue` — Interested companies missing contacts.
3. **Bootstrap** via Hunter domain search (preferred for new companies):

```bash
python3 contact_discovery_engine.py run --max <config.max_companies_per_run>
```

4. For companies Hunter cannot seed (empty domain results), research manually and add via CLI:

```bash
python3 contact_discovery_engine.py add --json @/tmp/remotepass-contacts.json
```

5. **Cloud runs:** commit and push changed paths when done (see below).

## Contact JSON shape (`add --json`)

```json
{
  "entity_id": "RemotePass",
  "contacts": [
    {
      "contact_id": "remotepass-founder-name",
      "name": "Full Name",
      "title": "CEO & Co-Founder",
      "why_they_matter": "One sentence on why Ankit should reach this person.",
      "priority_score": 95,
      "source_url": "https://www.remotepass.com/about",
      "role_tags": ["founder", "ceo"]
    }
  ]
}
```

Valid `role_tags`: `founder`, `ceo`, `head_of_product`, `head_of_innovation`, `head_of_partnerships`, `head_of_growth`, `head_of_education`.

## What the engine does (bootstrap)

- Targets Interested companies with no contacts file or empty contacts
- Calls Hunter **Domain Search** on company domain
- Picks executive titles (founder, CEO, head of product, etc.)
- Writes contacts **with emails** when Hunter returns them
- Refreshes action drafts via `action_engine` so outreach names fill in
- Respects `max_credits_per_run` (1 Hunter credit per email returned)

## After a run

```bash
python3 contact_discovery_engine.py record-run --processed 1 --contacts-added 3 --credits-used 3
```

(`run` records automatically unless `--dry-run`.)

## Pipeline order

1. **Contact discovery** (this agent) — cron `0 9,21 * * *` UTC
2. **Email finder** — cron `0 10,22 * * *` UTC — fills emails for contacts still missing them

## Rules

- Do **not** send emails or LinkedIn messages.
- Do **not** hand-edit `data/contacts/**` — use `contact_discovery_engine.py` only.
- Do **not** commit `HUNTER_API_KEY` or `.env`.
- Do **not** auto-edit `MEMORY.md`, `DECISIONS.md`, `ROADMAP.md`, or `VISION.md`.

## Git paths (cloud)

Commit only if changed:

- `data/contacts/companies/*.json`
- `data/actions/companies/*.json`
- `data/contact_discovery/runs.json`

Commit message example: `contact-discovery: add contacts for RemotePass (3 credits)`
