# AJOS Discovery Agent

Opportunity research for the Opportunity Engine. **Primary runtime: Cursor Cloud Automation** (scheduled, no local PC). See [`CLOUD_DISCOVERY_AUTOMATION.md`](CLOUD_DISCOVERY_AUTOMATION.md).

Legacy: local `/loop` while Cursor IDE is open (dev/testing only).

## Mission

Find founders, companies, and emerging environments where Ankit can create disproportionate value. This is opportunity creation, not job matching.

## Before each run — read these files

1. `AGENTS.md` — mission and Ankit profile context
2. **`data/discovery/config.json`** — enabled flag, countries, themes, industries, exclude keywords, caps
3. `data/ankit_profile.json` — capabilities and role patterns
4. `data/learning/state.json` — especially `alignment_memory` (committed copy on GitHub)
5. `data/learning/proposals.json` — `opportunity_source_suggestions`
6. `data/companies.csv` — existing companies (do not duplicate)
7. `data/discovery/candidates.json` — pending and rejected candidates

If `config.enabled` is `false`, **stop immediately** and record a run with `candidates_added: 0`.

```bash
python discovery_engine.py show-config
python discovery_engine.py list-rejected
```

## Each run — tasks

1. Read **`active_themes`** and **`active_countries`** from `config.json` (not hardcoded lists).
2. Use **`active_industries`** as extra search tags; skip anything matching **`exclude_keywords`**.
3. Cross-check alignment memory and liked feedback — prefer themes/countries that match both config and memory when possible.
4. Propose **0–N candidates** where N = `config.max_candidates_per_run` (quality over quantity).
5. Every candidate must have a **verified website** and at least one `source_url`.
6. Candidate `country` must be in `active_countries`; `theme` should align with `active_themes`.
7. Add candidates only through `discovery_engine.py` — never hand-edit JSON.
8. **Cloud runs:** commit and push `data/discovery/candidates.json` and `data/discovery/runs.json` to `main` when done.

## Candidate JSON shape

```json
{
  "name": "Company Name",
  "country": "India",
  "theme": "Wellness & Mental Wellbeing",
  "website": "https://example.com",
  "one_liner": "One sentence on what they do.",
  "why_ankit_fits": ["bullet 1", "bullet 2"],
  "problems_to_solve": ["bullet 1", "bullet 2"],
  "suggested_role": "Strategic Advisor, ...",
  "base_scores": {
    "theme": 90,
    "capability": 85,
    "role": 88,
    "geography": 92
  },
  "source_urls": [
    {"url": "https://...", "label": "Company homepage"}
  ]
}
```

Valid themes include: `Future of Work`, `Creator Economy`, `Education`, `Wellness & Mental Wellbeing`, `Human Potential`, and any theme listed in `config.active_themes`.

Score each `base_scores` field 0–100. Weighted average uses 30/30/25/15.

## Add a candidate

```bash
python discovery_engine.py add --json @/tmp/candidate.json
```

If stderr prints `NOTIFY` (score ≥ `config.notify_threshold`):

- **Cloud automation:** post one Slack message (if configured) — see `CLOUD_DISCOVERY_AUTOMATION.md`
- **Local dev:** `python scripts/notify_discovery.py --message "New opportunity: <name> in <theme> — open AJOS"`

Max **one** notification per run.

## After adding candidates

```bash
python discovery_engine.py record-run --themes "Wellness & Mental Wellbeing" "Human Potential" --added 2
```

## Rules

- Do **not** re-suggest rejected companies.
- Do **not** duplicate names or websites already in `companies.csv` or pending candidates.
- Do **not** auto-edit `MEMORY.md`, `DECISIONS.md`, `ROADMAP.md`, or `VISION.md`.
- Do **not** send emails or LinkedIn messages.
- Do **not** scrape aggressively or bypass robots.txt.

## Optional — on approval

When a candidate is merged into the pipeline, a follow-up run may create a skeleton intelligence report at `data/intelligence/companies/{slug}.json` using `company_intelligence.py` schema with `hypothesis` kinds only.

## Legacy — local loop (dev only)

```
/loop 3h Research new opportunities per DISCOVERY_AGENT.md. Read data/discovery/config.json first. Max candidates per config. Run notify script if strong match.
```

The loop only runs while Cursor IDE and the monitored shell stay alive.
