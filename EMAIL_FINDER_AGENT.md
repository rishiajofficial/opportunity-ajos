# AJOS Email Finder Agent

Find professional emails for **Interested** companies via Apollo.io API. **Primary runtime: Cursor Cloud Automation** (scheduled). See [`CLOUD_EMAIL_FINDER_AUTOMATION.md`](CLOUD_EMAIL_FINDER_AUTOMATION.md).

## Mission

Populate contact emails for companies Ankit marked **Like**, so outreach drafts in AJOS have a ready `To` address. This is data enrichment only — never send email or LinkedIn messages.

## Before each run — read these files

1. `AGENTS.md` — mission context
2. **`data/email_finder/config.json`** — enabled flag, caps, verification rules
3. `data/learning/state.json` — which companies are Interested (`Like`)
4. `data/companies.csv` — company websites (domains for Apollo)
5. `data/contacts/companies/{slug}.json` — who to reach and current emails

If `config.enabled` is `false`, **stop immediately** and record a run with zero processed.

```bash
python email_finder_engine.py show-config
python email_finder_engine.py list-queue
```

Requires **`APOLLO_API_KEY`** in the environment (never commit the key).

## Each run — tasks

1. Confirm `APOLLO_API_KEY` is set in the automation environment.
2. Run `python email_finder_engine.py list-queue` to see Interested companies missing emails.
3. Run the finder (engine calls Apollo — do not hand-edit contact JSON):

```bash
python email_finder_engine.py run --max <config.max_companies_per_run>
```

4. Optional dry-run first when testing:

```bash
python email_finder_engine.py run --max 1 --dry-run
```

5. **Cloud runs:** commit and push changed paths when done (see below).

## What the engine does

- Targets companies with latest feedback rating `Like`
- For each contact without `email`, calls Apollo `people/match` (name + domain)
- On failure, free `mixed_people/api_search` by title + domain, then `people/match` by id
- Writes `email`, `email_status`, `email_source`, `email_source_url`, `email_found_at` on contacts
- Refreshes action drafts via `action_engine` so mailto `To` fills automatically
- Respects `max_credits_per_run` to protect the free-tier credit balance

## After a run

```bash
python email_finder_engine.py record-run --processed 2 --emails-found 2 --credits-used 2
```

(`run` records automatically unless `--dry-run`.)

## Rules

- Do **not** send emails or LinkedIn messages.
- Do **not** hand-edit `data/contacts/**` or `data/actions/**` — use `email_finder_engine.py` only.
- Do **not** commit `APOLLO_API_KEY` or `.env`.
- Do **not** overwrite existing contact emails unless testing with `--force`.
- Do **not** auto-edit `MEMORY.md`, `DECISIONS.md`, `ROADMAP.md`, or `VISION.md`.
- Skip generic addresses (`info@`, `support@`, etc.) unless `config.allow_generic_emails` is true.

## Git paths (cloud)

Commit only if changed:

- `data/contacts/companies/*.json`
- `data/actions/companies/*.json`
- `data/email_finder/runs.json`

Commit message example: `email-finder: add emails for Graphy, Futurice (2 credits)`
