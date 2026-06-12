# AJOS Content Refinement Agent

Keeps opportunity copy in **Ankit's Hinglish voice** — specific, deep, profile-matched. Runs on a schedule via **Cursor Cloud Automation**. See [`CLOUD_CONTENT_AUTOMATION.md`](CLOUD_CONTENT_AUTOMATION.md).

## Mission

Ankit ko har profile **turant samajh aani chahiye** — company kya karti hai, woh kaise fit hai, kya solve kar sakta hai. Generic English ya vague bullets nahi.

This agent:
1. Reads Ankit's profile and learning signals
2. Refines `companies.csv` copy (and optionally intelligence briefs)
3. Re-queues refined profiles for review

## Before each run — read these files

1. `AGENTS.md` — mission and Ankit context
2. **`data/content/config.json`** — enabled flag, caps
3. `data/ankit_profile.json` — especially `content_voice`
4. `data/learning/state.json` — `alignment_memory`, feedback with `Didn't Understand`
5. `data/learning/proposals.json` — `content_suggestions`
6. `data/content/refinement_queue.json` — pending items from review
7. `data/companies.csv` — current copy
8. `data/intelligence/companies/*.json` — if brief exists for company

If `config.enabled` is `false`, record a run with `companies_refined: 0` and stop.

```bash
python content_engine.py show-config
python content_engine.py list-pending
```

## Copy rules (Hinglish voice)

From `ankit_profile.json` → `content_voice`:

| Field | Format |
| --- | --- |
| `description` | 1 sentence — company actually kya karti hai, kaun customers |
| `why_fit` | 3 bullets, `;` separated — **tum/tera** tone, Ankit-specific strengths |
| `problems_to_solve` | 3 bullets, `;` separated — concrete problems, not generic |
| `suggested_role` | English role title OK (e.g. "AI Transformation Lead") |

**Must avoid:** great fit, synergy, leverage, passionate team, vague AI buzzwords.

**Good examples** (from profile):
- *Tum Graphy pe teacher ho — UI friction, creator pain firsthand pata hai*
- *Multipotentialite yahan survive karta hai — silos kam, ambiguous mandates zyada*

**Profile match:** Cross-check `alignment_memory.preferences`, liked feedback (`Like`), and stated themes/geographies. Copy should reflect why *this* person fits *this* company — not a template.

## Each run — tasks

1. `python content_engine.py list-pending` — work pending queue first (from "Didn't understand" feedback).
2. If queue empty and config allows: pick up to `max_companies_per_run` companies whose copy is still English-heavy or stale (compare against `content_voice` examples).
3. For each company:
   ```bash
   python content_engine.py brief --company "Graphy"
   ```
4. Research if needed (website, intelligence JSON). Rewrite copy deeply.
5. Update CSV:
   ```bash
   python content_engine.py update --company "Graphy" --json @/tmp/copy.json
   ```
   JSON shape:
   ```json
   {
     "description": "…",
     "why_fit": "bullet1; bullet2; bullet3",
     "problems_to_solve": "bullet1; bullet2; bullet3"
   }
   ```
6. Mark refined (re-queues profile for Ankit's review):
   ```bash
   python content_engine.py mark-refined --company "Graphy"
   ```
7. Optionally update `data/intelligence/companies/{slug}.json` sections `what_they_do` and `value_for_aj` via `company_intelligence.save_company_report`.

## Finish

```bash
python content_engine.py record-run --refined <count> --skipped <count>
```

Git commit if changed:
- `data/companies.csv`
- `data/content/refinement_queue.json`
- `data/content/runs.json`
- `data/intelligence/companies/*.json` (if updated)
- `data/learning/state.json` (only if `mark-refined` re-queued — usually modified on server)

Commit message: `content: refine N companies (Hinglish copy)`

Push to `main`.

## Rules

- Never edit MEMORY.md, DECISIONS.md, ROADMAP.md, VISION.md
- Never hand-edit `refinement_queue.json` — use `content_engine.py`
- Never change score columns unless explicitly wrong
- Email/outreach drafts stay English — only review copy is Hinglish
- Quality over quantity — 1 deep rewrite beats 5 shallow ones

## Relationship to discovery agent

| Agent | Finds | Writes |
| --- | --- | --- |
| Discovery | New companies | `candidates.json` (often English) |
| Content | Copy clarity + voice | `companies.csv` Hinglish |

When discovery approves a candidate, content agent may refine on next run if copy is not in voice.
