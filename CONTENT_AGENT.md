# AJOS Content Refinement Agent

Refine AJOS review-facing opportunity copy so it feels specific to Ankit and easy
to evaluate quickly.

## Mission

Turn generic English opportunity copy into Roman Hinglish that explains:

- what the company does in plain language,
- why Ankit specifically fits the environment, and
- what concrete problems he could help solve.

The goal is opportunity creation, not job matching. Suggested roles can remain in
English because they are labels, but review-facing explanation should feel like
Ankit is reading a sharp, contextual brief.

## Before each run

Read:

1. `data/content/config.json`
2. `AGENTS.md`
3. `data/ankit_profile.json`
4. `data/learning/state.json`
5. `data/learning/proposals.json`

If `config.enabled` is `false`, record a zero-refinement run and stop:

```bash
python content_engine.py record-run --refined 0
```

## Each run

1. Run `python content_engine.py list-pending`.
2. Process all pending companies first. Pending items come from explicit
   "Didn't understand" style feedback or feedback asking for more clarity.
3. For each company, up to `config.max_companies_per_run`:

```bash
python content_engine.py brief --company "<name>"
python content_engine.py update --company "<name>" --json @/tmp/copy.json
python content_engine.py mark-refined --company "<name>"
```

4. If the queue is empty, optionally refine one company whose copy still feels
   English or generic.
5. Finish with:

```bash
python content_engine.py record-run --refined <count>
```

## Copy rules

- Refine only `description`, `why_fit`, and `problems_to_solve`.
- Use Roman Hinglish for review-facing copy.
- Keep email drafts English.
- Be specific to Ankit: systems thinking, product strategy, AI workflows,
  teaching, research, conceptual modeling, explorer/architect/builder energy.
- Avoid generic praise like "great company" or "strong fit" unless the reason is
  concrete.
- Do not edit `MEMORY.md`, `DECISIONS.md`, `ROADMAP.md`, or `VISION.md`.
- Use `content_engine.py` for queue and CSV updates.
