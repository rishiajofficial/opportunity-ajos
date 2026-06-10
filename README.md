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
- A ranked alignment score
- Why Ankit fits each environment
- Problems Ankit could solve
- A suggested emerging role

Suggested roles are strategic hypotheses. They may not exist inside the company
today and do not imply that the company is hiring.

## Run Locally

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

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

## Project Structure

```text
.
├── app.py
├── data
│   ├── ankit_profile.json
│   └── companies.csv
├── README.md
└── requirements.txt
```

## Future Direction

A later version can use the OpenAI API to enrich company research, generate
evidence-backed opportunity hypotheses, and explain alignment dynamically.
Any AI-generated analysis should remain traceable to source material and
clearly distinguished from verified facts.
