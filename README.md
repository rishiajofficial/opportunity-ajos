# Opportunity Discovery Engine

A lean Streamlit dashboard for discovering companies where Ankit could create
disproportionate value.

This is not a job search or vacancy-matching tool. It looks for environments
where Ankit's multipotentialite profile, systems thinking, product strategy,
AI transformation, innovation, teaching, and future-facing interests could
unlock meaningful new work.

## Dashboard

The dashboard provides:

- Geography and theme filters
- A ranked base score with a transparent learned adjustment capped at +/-10
- Why Ankit fits each environment
- Problems Ankit could solve
- A suggested emerging role
- Like, Neutral, and Not Interested feedback with optional reasons
- Opportunity outcome tracking
- One opportunity intelligence question at a time
- Learning insights and improvement proposals

Suggested roles are strategic hypotheses. They may not exist inside the company
today and do not imply that the company is hiring.

## Run Locally

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy (mobile access from anywhere)

AJOS is a **Streamlit** app. **Vercel is not a good fit** — it targets static
sites and serverless functions, not long-running Python apps.

Use **[Streamlit Community Cloud](https://share.streamlit.io/)** (free):

1. Push this repo to GitHub.
2. Sign in at [share.streamlit.io](https://share.streamlit.io/) with GitHub.
3. Click **New app** → pick this repo, branch `main`, main file `app.py`.
4. Deploy. You get a URL like `https://your-app.streamlit.app` — open it on
   your phone from anywhere.
5. **Password:** App settings → **Secrets** → add:
   ```toml
   AJOS_PASSWORD = "your-static-password"
   ```
   Redeploy if needed. The password is not stored in git.

**Local password:** copy `.streamlit/secrets.toml.example` to
`.streamlit/secrets.toml` and set `AJOS_PASSWORD`.

**Note:** Cloud deploys start from the committed JSON in the repo. Local changes
you make after deploy (feedback, actions, drafts) stay on whichever environment
you used unless you commit and redeploy, or later add shared storage.

## Data

`data/companies.csv` contains 12 curated companies across UAE, Singapore,
India, Netherlands, Finland, and Switzerland.

Each company has four manually curated score components:

| Component | Weight | Meaning |
| --- | ---: | --- |
| Theme alignment | 30% | Fit with Ankit's priority themes |
| Capability leverage | 30% | Scope to use several of Ankit's strengths together |
| Role emergence | 25% | Potential for valuable work beyond a fixed job description |
| Geography fit | 15% | Alignment with target geographies |

The dashboard calculates the final score on a 0–100 scale. Scores and narratives
are editorial hypotheses for exploration, not objective company assessments.

`data/ankit_profile.json` is the editable source of truth for Ankit's current
positioning, capabilities, themes, geographies, and possible role patterns.

## Background Discovery Agent

While Cursor IDE is open, a discovery agent can research new opportunities in the
background and queue them for review.

**Start the loop** in the Cursor Agents window:

```text
/loop 3h Research new opportunities per DISCOVERY_AGENT.md. Max 3 candidates. Run notify script if strong match.
```

The agent reads alignment memory and proposals, researches up to 3 candidates per
run, and writes them via `discovery_engine.py`. Strong matches (weighted score ≥
85) trigger a Linux desktop notification:

```bash
python scripts/notify_discovery.py --message "New opportunity: <name> in <theme> — open AJOS"
```

Discovered opportunities appear first in the review queue with a **Discovered**
badge. Pass rejects them; Save or Interested merges them into `companies.csv`.

See [`DISCOVERY_AGENT.md`](DISCOVERY_AGENT.md) for full agent instructions.

Manual utilities:

```bash
python discovery_engine.py add --json @/tmp/candidate.json
python discovery_engine.py list-pending
python discovery_engine.py list-rejected
python discovery_engine.py record-run --themes "Wellness & Mental Wellbeing" --added 1
```

## Learning Layer

The learning layer uses local JSON only:

- `data/learning/questions.json` contains the curated question bank.
- `data/learning/state.json` stores complete answer, feedback, and outcome
  history plus derived alignment memory.
- `data/learning/proposals.json` stores suggestions for sources, scoring,
  roadmap changes, and features.

Explicit answers and actions are stored as facts. Repeated evidence can support
beliefs, while tentative interpretations remain hypotheses. Learning adjusts
rankings without replacing the original editorial score:

```text
Final Score = Base Score + Learned Adjustment
Learned Adjustment is capped from -10 to +10
```

AJOS never automatically edits `MEMORY.md`, `DECISIONS.md`, `ROADMAP.md`, or
`VISION.md`. Proposed changes require later review and approval.

## Project Structure

```text
.
├── app.py
├── discovery_engine.py
├── DISCOVERY_AGENT.md
├── learning.py
├── scripts
│   └── notify_discovery.py
├── data
│   ├── ankit_profile.json
│   ├── companies.csv
│   ├── discovery
│   │   ├── candidates.json
│   │   └── runs.json
│   └── learning
│       ├── proposals.json
│       ├── questions.json
│       └── state.json
├── README.md
└── requirements.txt
```

## Future Direction

A later version can use the OpenAI API to enrich company research, generate
evidence-backed opportunity hypotheses, and explain alignment dynamically.
Any AI-generated analysis should remain traceable to source material and
clearly distinguished from verified facts.
