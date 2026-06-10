import json
from pathlib import Path

import pandas as pd
import streamlit as st

from learning import (
    answer_question,
    calculate_personalization,
    generate_insights,
    generate_proposals,
    get_open_questions,
    load_questions,
    load_state,
    persist_learning,
    record_feedback,
    record_outcome,
)


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

    companies["base_score"] = sum(
        companies[column] * weight for column, weight in SCORE_WEIGHTS.items()
    ).round().astype(int)

    return companies.sort_values(
        ["base_score", "company"], ascending=[False, True]
    ), profile


def render_score(company: pd.Series) -> None:
    score = int(company["final_score"])
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
                <div class="score-label">Final score / 100</div>
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


def render_company_brief(company: pd.Series, learning_state: dict) -> None:
    st.divider()
    heading, score = st.columns([3, 1])
    with heading:
        st.subheader(company["company"])
        st.caption(f"{company['country']}  ·  {company['theme']}")
        st.write(company["description"])
        st.link_button("Visit company website", company["website"])
    with score:
        render_score(company)

    render_score_breakdown(company)
    score_one, score_two, score_three = st.columns(3)
    score_one.metric("Base Score", f"{int(company['base_score'])}/100")
    score_two.metric(
        "Learned Adjustment", f"{int(company['learned_adjustment']):+d}"
    )
    score_three.metric("Final Score", f"{int(company['final_score'])}/100")
    with st.expander("Why this learned adjustment?"):
        for reason in company["adjustment_reasons"]:
            st.write(f"- {reason}")

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

    st.markdown("#### Teach AJOS about this opportunity")
    feedback_column, outcome_column = st.columns(2, gap="large")
    with feedback_column:
        latest_feedback = next(
            (
                item
                for item in reversed(learning_state["feedback"])
                if item["company"] == company["company"]
            ),
            None,
        )
        if latest_feedback:
            st.caption(
                f"Current feedback: {latest_feedback['rating']}"
                + (
                    f" · {latest_feedback['reason']}"
                    if latest_feedback["reason"]
                    else ""
                )
            )
        with st.form(f"feedback-{company['company']}"):
            rating = st.radio(
                "Feedback",
                ["Like", "Neutral", "Not Interested"],
                horizontal=True,
            )
            reason = st.text_input("Reason (optional)")
            if st.form_submit_button("Save feedback"):
                record_feedback(learning_state, company.to_dict(), rating, reason)
                st.rerun()

    with outcome_column:
        latest_outcome = next(
            (
                item
                for item in reversed(learning_state["outcomes"])
                if item["company"] == company["company"]
            ),
            None,
        )
        if latest_outcome:
            st.caption(f"Current outcome: {latest_outcome['outcome']}")
        with st.form(f"outcome-{company['company']}"):
            outcome = st.selectbox(
                "Opportunity outcome",
                [
                    "Not Pursued",
                    "Reached Out",
                    "Conversation Started",
                    "Ongoing Discussion",
                    "Opportunity Created",
                ],
            )
            if st.form_submit_button("Save outcome"):
                record_outcome(learning_state, company.to_dict(), outcome)
                st.rerun()


def render_question_engine(
    learning_state: dict, questions: list[dict]
) -> None:
    st.markdown("### Opportunity intelligence question")
    st.caption(
        "AJOS asks one question at a time. Answers improve opportunity discovery "
        "and creation, not self-understanding for its own sake."
    )
    open_questions = get_open_questions(learning_state, questions)
    if open_questions:
        question = open_questions[0]
    else:
        st.success("All current opportunity intelligence questions are answered.")
        question_labels = {item["prompt"]: item for item in questions}
        selected_prompt = st.selectbox(
            "Revisit a question",
            question_labels,
            help="A new answer is added to history; earlier answers are preserved.",
        )
        question = question_labels[selected_prompt]

    previous_answer = next(
        (
            item["answer"]
            for item in reversed(learning_state["answers"])
            if item["question_id"] == question["id"]
        ),
        [] if question["type"] == "multiselect" else "",
    )
    with st.form(f"question-{question['id']}"):
        if question["type"] == "multiselect":
            answer = st.multiselect(
                question["prompt"], question["options"], default=previous_answer
            )
        else:
            answer = st.text_area(question["prompt"], value=previous_answer)
        submitted = st.form_submit_button("Save answer")
        if submitted:
            has_answer = (
                bool(answer) if isinstance(answer, list) else bool(answer.strip())
            )
            if not has_answer:
                st.warning("Add an answer before saving.")
            else:
                answer_question(learning_state, question, answer)
                st.rerun()

    if learning_state["answers"]:
        with st.expander(
            f"Answer history ({len(learning_state['answers'])} saved answers)"
        ):
            for item in reversed(learning_state["answers"]):
                st.markdown(f"**{item['question']}**")
                value = item["answer"]
                st.write(", ".join(value) if isinstance(value, list) else value)
                st.caption(item["timestamp"])


def render_list(items: list[str], empty_message: str) -> None:
    if not items:
        st.caption(empty_message)
        return
    for item in items:
        st.write(f"- {item}")


def render_insights_and_proposals(
    learning_state: dict, questions: list[dict]
) -> None:
    insights = generate_insights(learning_state, questions)
    proposals = generate_proposals(learning_state, questions)

    st.markdown("### Opportunity insights")
    learned, hypotheses = st.columns(2, gap="large")
    with learned:
        st.markdown("#### What AJOS has learned")
        render_list(insights["learned"], "No learning evidence yet.")
    with hypotheses:
        st.markdown("#### Current hypotheses")
        render_list(insights["hypotheses"], "No evidence-backed hypotheses yet.")

    positive, negative = st.columns(2, gap="large")
    with positive:
        st.markdown("#### Positive opportunity signals")
        render_list(insights["positive_signals"], "No positive signals yet.")
    with negative:
        st.markdown("#### Negative opportunity signals")
        render_list(insights["negative_signals"], "No negative signals yet.")

    st.markdown("#### Open questions")
    render_list(insights["open_questions"], "No open questions.")

    st.markdown("### AJOS proposals")
    st.caption(proposals["notice"])
    labels = {
        "opportunity_source_suggestions": "Opportunity sources",
        "scoring_suggestions": "Scoring",
        "roadmap_suggestions": "Roadmap",
        "feature_suggestions": "Features",
    }
    columns = st.columns(4)
    for column, (key, label) in zip(columns, labels.items()):
        with column:
            st.markdown(f"#### {label}")
            render_list(proposals[key], "No proposal yet.")


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
    learning_questions = load_questions()
    learning_state = persist_learning(load_state())
except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
    st.error(f"Opportunity data could not be loaded: {error}")
    st.stop()

personalization = companies_df.apply(
    lambda company: calculate_personalization(company.to_dict(), learning_state),
    axis=1,
)
companies_df["learned_adjustment"] = [
    result[0] for result in personalization
]
companies_df["adjustment_reasons"] = [
    result[1] for result in personalization
]
companies_df["final_score"] = (
    companies_df["base_score"] + companies_df["learned_adjustment"]
).clip(0, 100)
companies_df = companies_df.sort_values(
    ["final_score", "base_score", "company"], ascending=[False, False, True]
)

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
    f"{filtered['final_score'].mean():.0f}/100" if not filtered.empty else "—",
)
metric_three.metric(
    "Highest alignment",
    (
        f"{filtered.iloc[0]['company']} · {filtered.iloc[0]['final_score']}"
        if not filtered.empty
        else "—"
    ),
)

if filtered.empty:
    st.warning("No environments match these filters. Broaden a geography or theme.")
    st.stop()

st.markdown("### Ranked opportunities")
table = filtered[
    [
        "company",
        "country",
        "theme",
        "base_score",
        "learned_adjustment",
        "final_score",
        "suggested_role",
    ]
]
st.dataframe(
    table,
    hide_index=True,
    width="stretch",
    column_config={
        "company": "Company",
        "country": "Geography",
        "theme": "Theme",
        "base_score": st.column_config.NumberColumn("Base Score", format="%d"),
        "learned_adjustment": st.column_config.NumberColumn(
            "Learned Adjustment", format="%+d"
        ),
        "final_score": st.column_config.ProgressColumn(
            "Final Score",
            help="Base score plus a learned adjustment capped at +/-10",
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
render_company_brief(selected, learning_state)

st.divider()
render_question_engine(learning_state, learning_questions)

st.divider()
render_insights_and_proposals(learning_state, learning_questions)

st.caption(
    "Curated strategic hypotheses for exploration. This dashboard does not identify "
    "job openings or imply that the companies listed are hiring."
)
