# Opportunity Engine

## Mission

Discover and create high-alignment opportunities.

The system should not limit itself to existing jobs.

Its purpose is to identify founders, companies, and emerging opportunities where Ankit can create disproportionate value.

When a strong alignment exists, the system should explore how a new opportunity could be created through conversation, collaboration, advisory work, entrepreneurship, or leadership.

Primary questions:

* Who should Ankit meet?
* Which founders are likely to resonate with him?
* What problems can he help solve?
* What opportunity could be created together?
* How can value be exchanged fairly for both sides?

The goal is not matching.

The goal is opportunity creation.


## About Ankit

Ankit is a multipotentialite.

Strengths:

* Systems thinking
* Product strategy
* AI workflows
* Innovation
* Pattern recognition
* Teaching
* Problem solving
* Deep research
* Conceptual modeling

Natural mode:

* Explorer
* Architect
* Builder

Not a fit for:

* Bureaucratic environments
* Repetitive execution
* Process-heavy operations
* Narrow specialist roles

## Priority Themes

* Future of Work
* Creator Economy
* Education
* Wellness
* Human Potential

## Product Philosophy

Prefer working solutions over perfect architecture.

Build simple first.
Validate.
Then improve.

Avoid overengineering.


## Daily highlights (automatic)

At the end of any meaningful agent session, update **today's** file under `highlights/YYYY-MM-DD.md` without waiting to be asked.

**One file per calendar day.** If the file exists, append or merge — do not create duplicates.

**Structure:**

1. **Top 10** — numbered list of the day's most important outcomes, decisions, or blockers (newest/most important first).
2. **Session log** — 10–20 bullets total, grouped under three labels:
   - *Decided* — choices made with the user or architecture locked in.
   - *Built & shipped* — code, data, deploy, commits.
   - *Learned & open* — status, gaps, next steps, things still pending.

Keep bullets short. Skip trivial turns (e.g. pure git push with no product change) unless it unblocked deploy.

See [`highlights/2026-06-11.md`](highlights/2026-06-11.md) for the reference format.

## Cursor Cloud specific instructions

This repo is a single **Streamlit** app (`app.py`) plus supporting Python engines/CLIs. No build step and no automated test suite exist.

- **Run the app:** `python3 -m streamlit run app.py --server.port 8501 --server.headless true`. The `streamlit` console script installs to `~/.local/bin` (not on `PATH`), so invoke it via `python3 -m streamlit`.
- **Login gate:** the app stops at a password screen unless `AJOS_PASSWORD` is set. For local/cloud dev, create `.streamlit/secrets.toml` (gitignored) containing `AJOS_PASSWORD = "..."`; alternatively export `AJOS_PASSWORD` as an env var. Without it the app shows "Password not configured" and halts.
- **No linter / tests configured:** use `python3 -m py_compile *.py scripts/*.py` as a quick syntax/sanity check.
- **Runtime writes:** giving feedback/actions in the UI mutates files under `data/` (e.g. `companies.csv`, `data/learning/*.json`, `data/actions/...`). After manual testing, `git checkout -- data/` to avoid committing test state.
- **Optional AI chat / email finder:** `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` enable LLM company chat (falls back to CSV snippets without them); `APOLLO_API_KEY` powers the email finder CLI. None are required to run the dashboard.
