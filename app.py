import json
from pathlib import Path

import pandas as pd
import streamlit as st

from action_engine import (
    ACTION_STATUSES,
    build_mailto_link,
    ensure_recommendation,
    get_all_action_history,
    map_action_status_to_learning_outcome,
    refresh_recommendation,
    resolve_draft_recipient,
    update_action_drafts,
    update_action_status,
)
from company_intelligence import (
    get_current_report,
    intelligence_status,
    load_company_intelligence,
)
from contact_discovery import contacts_status, get_contact_recommendations
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


KIND_LABELS = {
    "fact": "Fact",
    "observation": "Research observation",
    "hypothesis": "Hypothesis",
}


def render_kind_badge(kind: str) -> None:
    st.markdown(
        f'<span class="intel-badge intel-badge-{kind}">{KIND_LABELS[kind]}</span>',
        unsafe_allow_html=True,
    )


def render_source_links(source_urls: list[str]) -> None:
    if not source_urls:
        return
    for url in source_urls:
        st.markdown(f"- [{url}]({url})")


def render_company_header(company: pd.Series) -> None:
    st.subheader(company["company"])
    st.caption(
        f"{company['country']} · {company['theme']} · "
        f"Score {int(company['final_score'])}/100"
    )
    st.write(company["description"])
    st.link_button("Visit website", company["website"], use_container_width=True)


def render_opportunity_intelligence(company: pd.Series) -> None:
    st.markdown("#### Opportunity lens")
    st.caption("Editorial thesis from AJOS review.")
    st.markdown("**What opportunity may exist?**")
    st.write(company["why_fit"])
    st.markdown("**Problems AJ can solve**")
    st.write(company["problems_to_solve"])
    st.markdown("**Suggested emerging role**")
    st.markdown(
        f'<div class="role-card">{company["suggested_role"]}</div>',
        unsafe_allow_html=True,
    )


def render_company_intelligence(company_name: str) -> None:
    st.markdown("#### Company research")
    status = intelligence_status(company_name)
    if not status["exists"]:
        st.info(
            "No company intelligence brief yet. The curated opportunity lens below "
            "is based on editorial review, not live research."
        )
        return

    entity = load_company_intelligence(company_name)
    report = get_current_report(entity)
    researched_at = report["researched_at"]
    refresh_method = report.get("refresh_method", "manual").replace("_", " ").title()
    meta_one, meta_two = st.columns(2)
    with meta_one:
        st.caption(f"Researched: {researched_at}")
    with meta_two:
        st.caption(f"Refresh method: {refresh_method}")
    if status["is_stale"]:
        st.warning(
            "This brief may be stale. Consider refreshing company intelligence "
            "before acting on it."
        )

    sources = report.get("sources", [])
    if sources:
        with st.expander(f"Sources ({len(sources)})", expanded=False):
            for source in sources:
                label = source.get("label", source["url"])
                accessed = source.get("accessed_at")
                accessed_note = f" · accessed {accessed}" if accessed else ""
                st.markdown(f"- [{label}]({source['url']}){accessed_note}")

    for section in report["sections"]:
        st.markdown(f"#### {section['title']}")
        render_kind_badge(section["kind"])
        if section.get("content"):
            st.write(section["content"])
        for item in section.get("items", []):
            st.write(f"- {item}")
        section_sources = section.get("source_urls", [])
        if section_sources:
            with st.expander("Section sources", expanded=False):
                render_source_links(section_sources)


def render_contact_recommendations(company_name: str) -> dict:
    st.markdown("#### Contacts")
    st.caption("Curated people to reach. No automated outreach.")
    status = contacts_status(company_name)
    if not status["exists"]:
        st.info(
            "No contact intelligence yet. Action drafts will use generic greetings "
            "until contacts are curated for this company."
        )
        return get_contact_recommendations(company_name)

    recommendations = get_contact_recommendations(company_name)
    primary = recommendations["primary"]
    secondary = recommendations["secondary"]

    if primary:
        st.markdown("**Primary contact**")
        st.markdown(f"**{primary['name']}** · {primary['title']}")
        st.caption(f"Priority {primary['priority_score']}/100")
        st.write(primary["why_they_matter"])
        st.markdown(f"[Source]({primary['source_url']})")
        if secondary:
            st.divider()
            st.markdown("**Secondary contact**")
            st.markdown(f"**{secondary['name']}** · {secondary['title']}")
            st.caption(f"Priority {secondary['priority_score']}/100")
            st.write(secondary["why_they_matter"])
            st.markdown(f"[Source]({secondary['source_url']})")

    st.markdown("**Why AJOS selected them**")
    if recommendations["why_primary"]:
        st.write(f"- **Primary:** {recommendations['why_primary']}")
    if recommendations["why_secondary"]:
        st.write(f"- **Secondary:** {recommendations['why_secondary']}")

    with st.expander(f"All contacts ({len(recommendations['all_contacts'])})"):
        for contact in recommendations["all_contacts"]:
            tags = ", ".join(tag.replace("_", " ") for tag in contact.get("role_tags", []))
            st.markdown(
                f"**{contact['name']}** · {contact['title']} · "
                f"{contact['priority_score']}/100"
            )
            st.caption(tags)
            st.write(contact["why_they_matter"])
            st.markdown(f"[Source]({contact['source_url']})")
            st.divider()

    return recommendations


def render_action_recommendation(
    company: pd.Series, profile: dict, learning_state: dict
) -> dict:
    st.markdown("#### Next action")
    action = ensure_recommendation(company.to_dict(), profile, learning_state)
    st.metric("Recommended action", action["recommended_action"])
    st.metric("Confidence", f"{action['confidence_score']}/100")
    st.write(action["opportunity_summary"])
    st.markdown("**Why this action**")
    for reason in action["why_recommended"]:
        st.write(f"- {reason}")
    target_contact = action.get("target_contact")
    if target_contact:
        st.markdown("**Outreach contact**")
        st.write(
            f"**{target_contact['name']}** · {target_contact['title']} "
            f"(priority {target_contact['priority_score']}/100)"
        )
        st.caption(target_contact["why_they_matter"])
    if st.button(
        "Refresh recommendation",
        key=f"refresh-action-{company['company']}",
        use_container_width=True,
        help="Generate a new recommendation when context has changed.",
    ):
        refresh_recommendation(company.to_dict(), profile, learning_state)
        st.rerun()
    return action


def render_outreach_draft(company: pd.Series, action: dict) -> None:
    st.markdown("#### Email draft")
    st.caption("Tap the button below to open your mail app with this draft.")
    target_contact = action.get("target_contact")
    if target_contact:
        st.info(
            f"Drafts are addressed to **{target_contact['name']}** "
            f"({target_contact['title']}) for action: "
            f"**{action['recommended_action']}**."
        )
    else:
        st.warning("No curated contact linked. Drafts use a generic greeting.")

    email_draft = action["drafts"]["email"]
    linkedin_draft = action["drafts"]["linkedin"]
    recipient = resolve_draft_recipient(action)
    mailto_url, mailto_warning = build_mailto_link(action)

    mail_label = "Open in Mail app"
    if recipient:
        mail_label = f"Open in Mail app → {recipient}"
    elif target_contact:
        mail_label = f"Open in Mail app → {target_contact['name']}"

    st.link_button(
        mail_label,
        mailto_url,
        type="primary",
        use_container_width=True,
        help="Opens your phone's mail app with subject and body pre-filled.",
    )
    if mailto_warning:
        st.warning(mailto_warning)
    if not recipient:
        st.caption(
            "Add a recipient email below and save drafts before opening the mail app, "
            "or pick the contact manually inside your mail app."
        )
    st.caption("After sending, go to the Track tab and mark the action as Sent.")

    with st.form(f"drafts-{action['action_id']}"):
        email_to = st.text_input(
            "To (email)",
            value=email_draft.get("to", ""),
            placeholder="name@company.com",
        )
        email_subject = st.text_input(
            "Email subject",
            value=email_draft["subject"],
        )
        email_body = st.text_area(
            "Email draft",
            value=email_draft["body"],
            height=220,
        )
        linkedin_body = st.text_area(
            "LinkedIn draft",
            value=linkedin_draft["body"],
            height=160,
            help="Long-press to copy on mobile, then paste into LinkedIn.",
        )
        if st.form_submit_button("Save drafts", use_container_width=True):
            update_action_drafts(
                company["company"],
                action["action_id"],
                email_to=email_to,
                email_subject=email_subject,
                email_body=email_body,
                linkedin_body=linkedin_body,
            )
            st.success("Drafts saved. Tap Open in Mail app when ready.")
            st.rerun()


def render_action_history(company_name: str) -> None:
    st.markdown("#### Action history")
    history = get_all_action_history(company_name)
    if not history:
        st.caption("No action history yet.")
        return
    for item in history:
        with st.expander(
            f"{item['recommended_action']} · {item['status']} · "
            f"{item.get('updated_at', item.get('generated_at', ''))}",
            expanded=False,
        ):
            st.write(item.get("opportunity_summary", ""))
            st.caption(f"Confidence: {item.get('confidence_score', '—')}/100")
            for event in reversed(item.get("status_history", [])):
                note = f" — {event['note']}" if event.get("note") else ""
                st.write(f"- {event['status']} · {event['timestamp']}{note}")


def render_outcome_tracking(
    company: pd.Series, action: dict, learning_state: dict
) -> None:
    st.markdown("#### Outcome")
    st.write(f"Current status: **{action['status']}**")
    with st.form(f"action-status-{action['action_id']}"):
        status = st.selectbox("Update action status", ACTION_STATUSES, index=ACTION_STATUSES.index(action["status"]))
        note = st.text_input("Note (optional)")
        if st.form_submit_button("Save outcome", use_container_width=True):
            update_action_status(
                company["company"],
                action["action_id"],
                status,
                note.strip(),
            )
            learning_outcome = map_action_status_to_learning_outcome(status)
            if learning_outcome:
                record_outcome(learning_state, company.to_dict(), learning_outcome)
            st.rerun()

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
            f"Feedback: {latest_feedback['rating']}"
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
        if st.form_submit_button("Save feedback", use_container_width=True):
            record_feedback(learning_state, company.to_dict(), rating, reason)
            st.rerun()


def render_alignment_score(company: pd.Series) -> None:
    with st.expander(f"Alignment score · {int(company['final_score'])}/100"):
        render_score(company)
        st.metric("Base score", f"{int(company['base_score'])}/100")
        st.metric("Learned adjustment", f"{int(company['learned_adjustment']):+d}")
        st.metric("Theme", f"{int(company['theme_score'])}/100")
        st.metric("Capability", f"{int(company['capability_score'])}/100")
        st.metric("Role emergence", f"{int(company['role_score'])}/100")
        st.metric("Geography", f"{int(company['geography_score'])}/100")
        for reason in company["adjustment_reasons"]:
            st.write(f"- {reason}")


def get_company_action(
    company: pd.Series, profile: dict, learning_state: dict
) -> dict:
    return ensure_recommendation(company.to_dict(), profile, learning_state)


def render_question_engine(
    learning_state: dict, questions: list[dict]
) -> None:
    st.markdown("#### Learning question")
    st.caption("One question at a time. Answers improve future recommendations.")
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

    with st.expander("What AJOS has learned", expanded=False):
        render_list(insights["learned"], "No learning evidence yet.")
    with st.expander("Hypotheses", expanded=False):
        render_list(insights["hypotheses"], "No evidence-backed hypotheses yet.")
    with st.expander("Positive signals", expanded=False):
        render_list(insights["positive_signals"], "No positive signals yet.")
    with st.expander("Negative signals", expanded=False):
        render_list(insights["negative_signals"], "No negative signals yet.")
    with st.expander("Open questions", expanded=False):
        render_list(insights["open_questions"], "No open questions.")

    st.divider()
    st.markdown("#### AJOS proposals")
    st.caption(proposals["notice"])
    labels = {
        "opportunity_source_suggestions": "Sources",
        "scoring_suggestions": "Scoring",
        "roadmap_suggestions": "Roadmap",
        "feature_suggestions": "Features",
    }
    for key, label in labels.items():
        with st.expander(label, expanded=False):
            render_list(proposals[key], "No proposal yet.")


st.set_page_config(
    page_title="AJOS",
    page_icon="✦",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        .stApp { background: #f7f7f3; }
        .block-container {
            max-width: 720px;
            padding-top: 1rem;
            padding-bottom: 2rem;
        }
        h1 { font-size: 1.55rem; }
        h2 { font-size: 1.25rem; }
        h3, h4 { color: #18251f; font-size: 1.05rem; }
        [data-testid="stTabs"] button {
            font-size: 0.92rem;
            padding-left: 0.55rem;
            padding-right: 0.55rem;
        }
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e4ebe6;
            border-radius: 10px;
            padding: 0.55rem 0.7rem;
        }
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
        .intel-badge {
            border-radius: 999px;
            display: inline-block;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            margin: 0.35rem 0 0.65rem;
            padding: 0.2rem 0.55rem;
            text-transform: uppercase;
        }
        .intel-badge-fact {
            background: #dbeafe;
            color: #1e3a8a;
        }
        .intel-badge-observation {
            background: #fef3c7;
            color: #92400e;
        }
        .intel-badge-hypothesis {
            background: #d1fae5;
            color: #065f46;
        }
        a[data-testid="stLinkButton"][kind="primary"] {
            min-height: 3rem;
            font-size: 1.05rem;
            font-weight: 700;
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

st.markdown('<div class="eyebrow">AJOS</div>', unsafe_allow_html=True)
st.title("Opportunity Creation")
st.caption("Research, act, and track — optimized for mobile.")

with st.expander("Filters", expanded=False):
    selected_geographies = st.multiselect(
        "Geography",
        TARGET_GEOGRAPHIES,
        default=TARGET_GEOGRAPHIES,
    )
    selected_themes = st.multiselect(
        "Theme",
        PRIORITY_THEMES,
        default=PRIORITY_THEMES,
    )

filtered = companies_df[
    companies_df["country"].isin(selected_geographies)
    & companies_df["theme"].isin(selected_themes)
].copy()

if filtered.empty:
    st.warning("No environments match these filters. Broaden a geography or theme.")
    st.stop()

company_labels = {
    row["company"]: f"{row['company']} · {int(row['final_score'])}/100"
    for _, row in filtered.iterrows()
}
selected_company = st.selectbox(
    "Company",
    list(company_labels.keys()),
    format_func=lambda name: company_labels[name],
)
selected = filtered.loc[filtered["company"] == selected_company].iloc[0]

tab_discover, tab_research, tab_act, tab_track, tab_learn = st.tabs(
    ["Discover", "Research", "Act", "Track", "Learn"]
)

with tab_discover:
    render_company_header(selected)
    st.divider()
    render_opportunity_intelligence(selected)
    render_alignment_score(selected)
    st.metric("Opportunities in view", len(filtered))
    st.caption(
        f"Top match: {filtered.iloc[0]['company']} · "
        f"{int(filtered.iloc[0]['final_score'])}/100"
    )

with tab_research:
    render_company_header(selected)
    st.divider()
    render_company_intelligence(selected["company"])
    st.divider()
    render_contact_recommendations(selected["company"])

with tab_act:
    render_company_header(selected)
    st.divider()
    action = render_action_recommendation(selected, ankit_profile, learning_state)
    st.divider()
    render_outreach_draft(selected, action)

with tab_track:
    render_company_header(selected)
    st.divider()
    action = get_company_action(selected, ankit_profile, learning_state)
    render_outcome_tracking(selected, action, learning_state)
    st.divider()
    render_action_history(selected["company"])

with tab_learn:
    render_question_engine(learning_state, learning_questions)
    st.divider()
    render_insights_and_proposals(learning_state, learning_questions)

st.caption(
    "Curated hypotheses for exploration. Not a job board."
)
