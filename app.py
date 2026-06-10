import json
from pathlib import Path

import pandas as pd
import streamlit as st


BASE_DIR = Path(__file__).parent
COMPANIES_PATH = BASE_DIR / "data" / "companies.csv"
PROFILE_PATH = BASE_DIR / "data" / "ankit_profile.json"
TARGET_GEOGRAPHIES = [
    "UAE",
    "Singapore",
    "India",
    "Netherlands",
    "Finland",
    "Switzerland",
]
PRIORITY_THEMES = [
    "Future of Work",
    "Creator Economy",
    "Education",
    "Wellness & Mental Wellbeing",
]
SCORE_WEIGHTS = {
    "theme_score": 0.30,
    "capability_score": 0.30,
    "role_score": 0.25,
    "geography_score": 0.15,
}


@st.cache_data
def load_data() -> tuple[pd.DataFrame, dict]:
    companies = pd.read_csv(COMPANIES_PATH)
    with PROFILE_PATH.open(encoding="utf-8") as profile_file:
        profile = json.load(profile_file)

    required_columns = {
        "company",
        "country",
        "theme",
        "description",
        "website",
        "theme_score",
        "capability_score",
        "role_score",
        "geography_score",
        "why_fit",
        "problems_to_solve",
        "suggested_role",
    }
    missing_columns = required_columns.difference(companies.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required company fields: {missing}")

    for score_column in SCORE_WEIGHTS:
        companies[score_column] = pd.to_numeric(
            companies[score_column], errors="raise"
        ).clip(0, 100)

    companies["alignment_score"] = sum(
        companies[column] * weight for column, weight in SCORE_WEIGHTS.items()
    ).round().astype(int)

    return companies.sort_values(
        ["alignment_score", "company"], ascending=[False, True]
    ), profile


def render_score(score: int) -> None:
    if score >= 85:
        label = "Exceptional alignment"
    elif score >= 75:
        label = "Strong alignment"
    else:
        label = "Promising alignment"

    st.markdown(
        f"""
        <div class="score-card">
            <div class="score-number">{score}</div>
            <div>
                <div class="score-label">Alignment score / 100</div>
                <div class="score-caption">{label}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_score_breakdown(company: pd.Series) -> None:
    labels = {
        "theme_score": "Theme alignment",
        "capability_score": "Capability leverage",
        "role_score": "Role emergence",
        "geography_score": "Geography fit",
    }
    columns = st.columns(4)
    for column, (field, label) in zip(columns, labels.items()):
        column.metric(label, f"{int(company[field])}/100")


def render_company_brief(company: pd.Series) -> None:
    st.divider()
    heading, score = st.columns([3, 1])
    with heading:
        st.subheader(company["company"])
        st.caption(f"{company['country']}  ·  {company['theme']}")
        st.write(company["description"])
        st.link_button("Visit company website", company["website"])
    with score:
        render_score(int(company["alignment_score"]))

    render_score_breakdown(company)

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("#### Why Ankit Fits")
        st.write(company["why_fit"])
        st.markdown("#### Problems Ankit Can Solve")
        st.write(company["problems_to_solve"])
    with right:
        st.markdown("#### Suggested Role")
        st.markdown(
            f'<div class="role-card">{company["suggested_role"]}</div>',
            unsafe_allow_html=True,
        )
        st.info(
            "This is an emerging value-creation hypothesis, not an advertised vacancy."
        )


st.set_page_config(
    page_title="Ankit's Opportunity Engine",
    page_icon="✦",
    layout="wide",
)

st.markdown(
    """
    <style>
        .stApp { background: #f7f7f3; }
        .block-container { max-width: 1180px; padding-top: 2.5rem; }
        h1, h2, h3, h4 { color: #18251f; }
        .eyebrow {
            color: #28705a;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }
        .hero-copy {
            color: #53615b;
            font-size: 1.08rem;
            line-height: 1.65;
            max-width: 760px;
        }
        .score-card {
            align-items: center;
            background: #173f34;
            border-radius: 14px;
            color: white;
            display: flex;
            gap: 0.9rem;
            padding: 1rem 1.2rem;
        }
        .score-number { font-size: 2.35rem; font-weight: 750; line-height: 1; }
        .score-label { font-size: 0.8rem; opacity: 0.75; }
        .score-caption { font-size: 0.95rem; font-weight: 650; }
        .role-card {
            background: #e7efe9;
            border-left: 4px solid #28705a;
            border-radius: 8px;
            color: #173f34;
            font-size: 1.2rem;
            font-weight: 700;
            margin-bottom: 1rem;
            padding: 1.15rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    companies_df, ankit_profile = load_data()
except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
    st.error(f"Opportunity data could not be loaded: {error}")
    st.stop()

st.markdown('<div class="eyebrow">Opportunity Discovery Engine</div>', unsafe_allow_html=True)
st.title("Where can Ankit create disproportionate value?")
st.markdown(
    """
    <div class="hero-copy">
        Explore high-alignment environments where a multipotentialite operator can connect
        systems thinking, product strategy, AI transformation, innovation, education,
        and new ways of working.
    </div>
    """,
    unsafe_allow_html=True,
)

with st.expander("Ankit's value-creation lens"):
    st.write(ankit_profile["positioning"])
    st.markdown("**Core capabilities:** " + " · ".join(ankit_profile["capabilities"]))
    st.markdown("**Role patterns:** " + " · ".join(ankit_profile["role_patterns"]))

st.divider()
st.markdown("### Discover environments")

filter_one, filter_two = st.columns(2)
with filter_one:
    selected_geographies = st.multiselect(
        "Geography",
        TARGET_GEOGRAPHIES,
        default=TARGET_GEOGRAPHIES,
        placeholder="Choose geographies",
    )
with filter_two:
    selected_themes = st.multiselect(
        "Theme",
        PRIORITY_THEMES,
        default=PRIORITY_THEMES,
        placeholder="Choose themes",
    )

filtered = companies_df[
    companies_df["country"].isin(selected_geographies)
    & companies_df["theme"].isin(selected_themes)
].copy()

metric_one, metric_two, metric_three = st.columns(3)
metric_one.metric("Environments found", len(filtered))
metric_two.metric(
    "Average alignment",
    f"{filtered['alignment_score'].mean():.0f}/100" if not filtered.empty else "—",
)
metric_three.metric(
    "Highest alignment",
    (
        f"{filtered.iloc[0]['company']} · {filtered.iloc[0]['alignment_score']}"
        if not filtered.empty
        else "—"
    ),
)

if filtered.empty:
    st.warning("No environments match these filters. Broaden a geography or theme.")
    st.stop()

st.markdown("### Ranked opportunities")
table = filtered[["company", "country", "theme", "alignment_score", "suggested_role"]]
st.dataframe(
    table,
    hide_index=True,
    use_container_width=True,
    column_config={
        "company": "Company",
        "country": "Geography",
        "theme": "Theme",
        "alignment_score": st.column_config.ProgressColumn(
            "Alignment",
            help="Weighted value-creation alignment score",
            min_value=0,
            max_value=100,
            format="%d",
        ),
        "suggested_role": "Emerging role",
    },
)

selected_company = st.selectbox(
    "Open an opportunity brief",
    filtered["company"].tolist(),
)
selected = filtered.loc[filtered["company"] == selected_company].iloc[0]
render_company_brief(selected)

st.caption(
    "Curated strategic hypotheses for exploration. This dashboard does not identify "
    "job openings or imply that the companies listed are hiring."
)
