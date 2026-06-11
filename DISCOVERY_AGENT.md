# AJOS Discovery Agent

Background opportunity research for the Opportunity Engine. Runs while Cursor IDE is open.

## Mission

Find founders, companies, and emerging environments where Ankit can create disproportionate value. This is opportunity creation, not job matching.

## Before each run — read these files

1. `AGENTS.md` — mission and Ankit profile context
2. `data/ankit_profile.json` — capabilities, themes, geographies
3. `data/learning/state.json` — especially `alignment_memory`
4. `data/learning/proposals.json` — `opportunity_source_suggestions`
5. `data/companies.csv` — existing companies (do not duplicate)
6. `data/discovery/candidates.json` — pending and rejected candidates

Also check rejected slugs:

```bash
python discovery_engine.py list-rejected
```

## Each run — tasks

1. Pick **1–2 themes** from alignment memory and liked feedback patterns.
2. Research founders, accelerators, and emerging companies in target geographies:
   - UAE, Singapore, India, Netherlands, Finland, Switzerland
3. Propose **0–3 candidates max** per run. Quality over quantity.
4. Every candidate must have a **verified website** and at least one `source_url`.
5. Add candidates only through `discovery_engine.py` — never hand-edit JSON.

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

Valid themes: `Future of Work`, `Creator Economy`, `Education`, `Wellness & Mental Wellbeing`.

Score each `base_scores` field 0–100. Weighted average uses 30/30/25/15.

## Add a candidate

Save candidate JSON to a temp file, then:

```bash
python discovery_engine.py add --json @/tmp/candidate.json
```

If stderr prints `NOTIFY`, send a desktop alert (max one per run):

```bash
python scripts/notify_discovery.py --message "New opportunity: <name> in <theme> — open AJOS"
```

## After adding candidates

Record the run:

```bash
python discovery_engine.py record-run --themes "Wellness & Mental Wellbeing" "Human Potential" --added 2
```

## Rules

- Do **not** re-suggest rejected companies.
- Do **not** duplicate names or websites already in `companies.csv` or pending candidates.
- Do **not** auto-edit `MEMORY.md`, `DECISIONS.md`, `ROADMAP.md`, or `VISION.md`.
- Do **not** send emails or LinkedIn messages.
- Do **not** scrape aggressively or bypass robots.txt.
- Notify only when weighted score ≥ 85. Max **one** notification per run.

## Optional — on approval

When a candidate is merged into the pipeline, a follow-up run may create a skeleton intelligence report at `data/intelligence/companies/{slug}.json` using `company_intelligence.py` schema with `hypothesis` kinds only.

## Loop command (Cursor Agents window)

```
/loop 3h Research new opportunities per DISCOVERY_AGENT.md. Max 3 candidates. Run notify script if strong match.
```

The loop only runs while Cursor IDE and the monitored shell stay alive.
