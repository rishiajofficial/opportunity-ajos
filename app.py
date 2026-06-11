import html
import json
import os
import textwrap
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
from company_chat import (
    answer_company_question,
    load_report,
    suggested_questions,
)
from company_intelligence import (
    get_current_report,
    intelligence_status,
    load_company_intelligence,
)
from contact_discovery import contacts_status, get_contact_recommendations
from discovery_engine import (
    approve_candidate,
    build_review_queue,
    get_last_run,
    reject_candidate,
)
from learning import (
    answer_question,
    calculate_personalization,
    generate_insights,
    generate_proposals,
    get_interested_companies,
    get_open_questions,
    get_saved_companies,
    load_questions,
    load_state,
    persist_learning,
    record_feedback,
    record_outcome,
    record_review_decision,
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

APP_CSS = """
<style>
    #MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; }
    .stApp { background: #eef2ef; }
    .block-container {
        max-width: 480px;
        padding: 0.35rem 0.85rem 5rem;
    }
    [data-testid="stTabs"] {
        background: #fff;
        border: 1px solid #dde5df;
        border-radius: 16px;
        padding: 0.35rem 0.35rem 0.75rem;
        box-shadow: 0 8px 24px rgba(23, 63, 52, 0.06);
    }
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 0.15rem;
    }
    [data-testid="stTabs"] button {
        border-radius: 10px;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 0.45rem 0.35rem;
    }
    [data-testid="stMetric"] {
        background: #f8faf9;
        border: 1px solid #e4ebe6;
        border-radius: 12px;
        padding: 0.45rem 0.55rem;
    }
    .app-shell-title {
        color: #28705a;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.14em;
        margin: 0 0 0.15rem;
        text-transform: uppercase;
    }
    .company-card {
        background: linear-gradient(135deg, #173f34 0%, #215745 100%);
        border-radius: 18px;
        color: #fff;
        margin: 0.35rem 0 0.75rem;
        padding: 1rem 1.05rem;
    }
    .company-card h2 {
        color: #fff;
        font-size: 1.35rem;
        line-height: 1.2;
        margin: 0 0 0.35rem;
    }
    .company-meta {
        color: rgba(255,255,255,0.82);
        font-size: 0.82rem;
        margin-bottom: 0.65rem;
    }
    .score-pill {
        background: rgba(255,255,255,0.16);
        border-radius: 999px;
        display: inline-block;
        font-size: 0.78rem;
        font-weight: 700;
        margin-right: 0.35rem;
        padding: 0.2rem 0.55rem;
    }
    .app-card {
        background: #fff;
        border: 1px solid #e4ebe6;
        border-radius: 14px;
        margin-bottom: 0.65rem;
        padding: 0.85rem 0.95rem;
    }
    .app-card-label {
        color: #6b7a73;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        margin-bottom: 0.25rem;
        text-transform: uppercase;
    }
    .app-card-title {
        color: #173f34;
        font-size: 1rem;
        font-weight: 700;
        line-height: 1.35;
        margin: 0 0 0.35rem;
    }
    .app-card-body {
        color: #425049;
        font-size: 0.92rem;
        line-height: 1.5;
        margin: 0;
    }
    .role-chip {
        background: #e7efe9;
        border-radius: 10px;
        color: #173f34;
        display: inline-block;
        font-size: 0.84rem;
        font-weight: 650;
        margin-top: 0.35rem;
        padding: 0.35rem 0.55rem;
    }
    .intel-badge {
        border-radius: 999px;
        display: inline-block;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        margin-bottom: 0.45rem;
        padding: 0.15rem 0.5rem;
        text-transform: uppercase;
    }
    .intel-badge-fact { background: #dbeafe; color: #1e3a8a; }
    .intel-badge-observation { background: #fef3c7; color: #92400e; }
    .intel-badge-hypothesis { background: #d1fae5; color: #065f46; }
    .discovered-badge {
        background: #fce7f3;
        border-radius: 999px;
        color: #9d174d;
        display: inline-block;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        margin-bottom: 0.45rem;
        padding: 0.15rem 0.5rem;
        text-transform: uppercase;
    }
    a[data-testid="stLinkButton"][kind="primary"] {
        border-radius: 14px;
        font-size: 1rem;
        font-weight: 800;
        min-height: 3.2rem;
    }
    div[data-testid="stExpander"] {
        background: #fff;
        border: 1px solid #e8eeea;
        border-radius: 12px;
        margin-bottom: 0.45rem;
    }
    .bullet-card {
        background: #fff;
        border: 1px solid #e4ebe6;
        border-radius: 14px;
        margin-bottom: 0.65rem;
        padding: 0.85rem 0.95rem;
    }
    .bullet-card li {
        color: #425049;
        font-size: 0.92rem;
        line-height: 1.45;
        margin-bottom: 0.35rem;
    }
    .company-card .app-shell-title {
        color: rgba(255,255,255,0.75);
    }
    div[data-testid="stButton"]:has(button[kind="primary"]) button {
        background: linear-gradient(135deg, #173f34 0%, #28705a 100%) !important;
        border: none !important;
        color: #fff !important;
        font-weight: 800 !important;
        min-height: 2.75rem;
    }
    #review-actions-letgo ~ div[data-testid="stButton"] > button {
        background: #f4f6f5 !important;
        border: 1px solid #c5d0ca !important;
        color: #5f6f67 !important;
        font-weight: 700 !important;
    }
    #review-actions-save ~ div[data-testid="stButton"] > button {
        background: #fff8eb !important;
        border: 1px solid #e8c878 !important;
        color: #8a6a1e !important;
        font-weight: 700 !important;
    }
</style>
"""


def render_html(markup: str) -> None:
    lines = [
        line.strip()
        for line in textwrap.dedent(markup).splitlines()
        if line.strip()
    ]
    st.html("".join(lines))


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


def truncate(text: str, limit: int = 140) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def shorten_bullet(text: str, max_words: int = 12) -> str:
    words = str(text).split()
    if len(words) <= max_words:
        return str(text).strip()
    return " ".join(words[:max_words]).rstrip(",;.") + "…"


def split_bullets(text: str, max_items: int = 4) -> list[str]:
    cleaned = str(text).strip()
    if not cleaned:
        return []
    for separator in (";", "\n"):
        if separator in cleaned:
            parts = [
                shorten_bullet(part.strip())
                for part in cleaned.split(separator)
                if part.strip()
            ]
            if len(parts) > 1:
                return parts[:max_items]
    sentences = [
        part.strip()
        for part in cleaned.replace("?", ".").split(".")
        if part.strip()
    ]
    if len(sentences) > 1:
        return [shorten_bullet(sentence) for sentence in sentences[:max_items]]
    if len(cleaned) > 100:
        return [shorten_bullet(truncate(cleaned, 95))]
    return [shorten_bullet(cleaned)]


def preview_bullets_from_text(text: str, max_items: int = 3) -> list[str]:
    return split_bullets(text, max_items=max_items)


def render_bullet_list(items: list[str], max_items: int = 4) -> None:
    bullets = [item for item in items if item][:max_items]
    if not bullets:
        return
    items_html = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in bullets
    )
    st.html(f'<div class="bullet-card"><ul>{items_html}</ul></div>')


def companies_as_dicts(companies_df: pd.DataFrame) -> list[dict]:
    return [row.to_dict() for _, row in companies_df.iterrows()]


def find_company_row(companies_df: pd.DataFrame, company_name: str) -> pd.Series:
    return companies_df.loc[companies_df["company"] == company_name].iloc[0]


def init_session_view() -> None:
    st.session_state.setdefault("ajos_view", "review")
    st.session_state.setdefault("ajos_focus_company", None)
    st.session_state.setdefault("company_chats", {})


def chat_history(company_name: str) -> list[dict]:
    chats = st.session_state.company_chats
    return chats.setdefault(company_name, [])


def append_chat_message(company_name: str, role: str, bullets: list[str]) -> None:
    chat_history(company_name).append({"role": role, "bullets": bullets})


def render_chat_messages(company_name: str) -> None:
    for message in chat_history(company_name):
        with st.chat_message(message["role"]):
            for bullet in message["bullets"]:
                st.write(f"- {bullet}")


def render_company_chat(
    company: pd.Series,
    *,
    mode: str = "explore",
    action: dict | None = None,
) -> None:
    company_name = company["company"]
    report = load_report(company_name)
    has_intel = report is not None

    st.caption("Ask anything — answers come from research on file.")
    render_chat_messages(company_name)

    suggest_cols = st.columns(min(3, len(suggested_questions(has_intel))))
    for index, (col, prompt) in enumerate(
        zip(suggest_cols, suggested_questions(has_intel))
    ):
        with col:
            if st.button(
                prompt,
                key=f"chat-suggest-{mode}-{company_name}-{index}",
                use_container_width=True,
            ):
                append_chat_message(company_name, "user", [prompt])
                bullets = answer_company_question(
                    prompt,
                    company.to_dict(),
                    report,
                    action=action,
                )
                append_chat_message(company_name, "assistant", bullets)
                st.rerun()

    placeholder = (
        "Ask about next steps or the draft…"
        if mode == "action"
        else "Ask about this company…"
    )
    question = st.chat_input(placeholder, key=f"chat-input-{mode}-{company_name}")
    if question:
        append_chat_message(company_name, "user", [question])
        bullets = answer_company_question(
            question,
            company.to_dict(),
            report,
            action=action,
        )
        append_chat_message(company_name, "assistant", bullets)
        st.rerun()


def render_occasional_feedback(
    learning_state: dict,
    questions: list[dict],
    company_name: str,
) -> None:
    history = chat_history(company_name)
    if len(history) < 2 or len(history) % 4 != 0:
        return
    open_questions = get_open_questions(learning_state, questions)
    if not open_questions:
        return
    question = open_questions[0]
    st.markdown("**Quick check-in**")
    st.caption(truncate(question["prompt"], 120))
    with st.form(f"inline-learn-{company_name}-{question['id']}"):
        if question["type"] == "multiselect":
            answer = st.multiselect(
                "Your answer",
                question["options"],
                label_visibility="collapsed",
            )
        else:
            answer = st.text_input("Your answer", label_visibility="collapsed")
        if st.form_submit_button("Save", use_container_width=True):
            has_answer = (
                bool(answer) if isinstance(answer, list) else bool(str(answer).strip())
            )
            if has_answer:
                answer_question(learning_state, question, answer)
                st.rerun()


def open_focus_view(company_name: str) -> None:
    st.session_state.ajos_view = "focus"
    st.session_state.ajos_focus_company = company_name


def render_kind_badge(kind: str) -> None:
    labels = {
        "fact": "Fact",
        "observation": "Observation",
        "hypothesis": "Hypothesis",
    }
    st.markdown(
        f'<span class="intel-badge intel-badge-{kind}">{labels[kind]}</span>',
        unsafe_allow_html=True,
    )


def review_item_to_series(item: dict) -> pd.Series:
    return pd.Series(item)


def render_company_card(
    company: pd.Series,
    *,
    label: str = "Opportunity",
    is_discovered: bool = False,
) -> None:
    name = html.escape(str(company["company"]))
    country = html.escape(str(company["country"]))
    theme = html.escape(str(company["theme"]))
    role = html.escape(str(company["suggested_role"]))
    label_safe = html.escape(label)
    discovered_badge = (
        '<span class="discovered-badge">Discovered</span>' if is_discovered else ""
    )
    render_html(
        f'<div class="company-card">'
        f'<div class="app-shell-title">{label_safe}</div>'
        f"{discovered_badge}"
        f"<h2>{name}</h2>"
        f'<div class="company-meta">{country} · {theme}</div>'
        f'<span class="score-pill">{int(company["final_score"])}/100 score</span>'
        f'<span class="score-pill">{role}</span>'
        f"</div>"
    )


def render_info_card(label: str, title: str, body: str = "") -> None:
    label_safe = html.escape(label)
    title_safe = html.escape(str(title))
    body_html = (
        f'<p class="app-card-body">{html.escape(str(body))}</p>' if body else ""
    )
    render_html(
        f'<div class="app-card">'
        f'<div class="app-card-label">{label_safe}</div>'
        f'<div class="app-card-title">{title_safe}</div>'
        f"{body_html}"
        f"</div>"
    )


def render_discover_tab(company: pd.Series, filtered: pd.DataFrame) -> None:
    bullets = split_bullets(company["why_fit"], 3) + split_bullets(
        company["problems_to_solve"], 2
    )
    render_info_card("The opportunity", company["company"])
    render_bullet_list(bullets, max_items=4)
    with st.expander("Full picture", expanded=False):
        st.markdown("**Why you fit**")
        for item in split_bullets(company["why_fit"], 10):
            st.write(f"- {item}")
        st.markdown("**Problems you could solve**")
        for item in split_bullets(company["problems_to_solve"], 10):
            st.write(f"- {item}")
        st.markdown(
            f'<span class="role-chip">{company["suggested_role"]}</span>',
            unsafe_allow_html=True,
        )
    with st.expander("About company", expanded=False):
        st.write(company["description"])
        st.link_button("Open website", company["website"], use_container_width=True)
    with st.expander(f"Score detail · {int(company['final_score'])}/100", expanded=False):
        st.metric("Base score", f"{int(company['base_score'])}/100")
        st.metric("From learning", f"{int(company['learned_adjustment']):+d}")
        st.metric("Theme fit", f"{int(company['theme_score'])}/100")
        st.caption(f"{len(filtered)} companies in filter")


def render_company_intelligence(company_name: str) -> bool:
    status = intelligence_status(company_name)
    if not status["exists"]:
        return False

    entity = load_company_intelligence(company_name)
    report = get_current_report(entity)
    value_section = next(
        (section for section in report["sections"] if section["id"] == "value_for_aj"),
        None,
    )
    if value_section:
        preview_items = value_section.get("preview") or preview_bullets_from_text(
            value_section.get("content", ""), max_items=3
        )
    else:
        preview_items = ["Research brief ready."]
    render_info_card("Research", company_name, f"Updated {report['researched_at'][:10]}")
    render_bullet_list(preview_items, max_items=3)

    with st.expander("Full company research", expanded=False):
        if status["is_stale"]:
            st.warning("This brief may be stale — consider refreshing.")
        for section in report["sections"]:
            st.markdown(f"**{section['title']}**")
            render_kind_badge(section["kind"])
            if section.get("content"):
                st.write(section["content"])
            for item in section.get("items", []):
                st.write(f"- {item}")
    return True


def render_contact_recommendations(company_name: str) -> dict:
    recommendations = get_contact_recommendations(company_name)
    primary = recommendations["primary"]
    if not primary:
        st.info("No contacts added for this company yet.")
        return recommendations

    render_info_card(
        "Try first",
        primary["name"],
        f"{primary['title']} · priority {primary['priority_score']}/100",
    )
    render_bullet_list([shorten_bullet(primary["why_they_matter"])], max_items=1)

    with st.expander("Contact details", expanded=False):
        st.write(primary["why_they_matter"])
        st.markdown(f"[Source]({primary['source_url']})")
        secondary = recommendations["secondary"]
        if secondary:
            st.markdown(f"**Plan B:** {secondary['name']} · {secondary['title']}")
            st.write(secondary["why_they_matter"])
        if recommendations["why_primary"]:
            st.caption(recommendations["why_primary"])
        for contact in recommendations["all_contacts"]:
            st.markdown(
                f"**{contact['name']}** · {contact['title']} · "
                f"{contact['priority_score']}/100"
            )
    return recommendations


def render_research_tab(company: pd.Series) -> None:
    has_intel = render_company_intelligence(company["company"])
    if not has_intel and not contacts_status(company["company"])["exists"]:
        render_info_card(
            "Research",
            "No deep research yet",
            "Basic opportunity detail is on the review card.",
        )
    render_contact_recommendations(company["company"])


def render_action_surface(action: dict) -> None:
    target_contact = action.get("target_contact")
    contact_line = (
        f"{target_contact['name']} · {target_contact['title']}"
        if target_contact
        else "No contact linked yet"
    )
    render_info_card(
        "Next step",
        action["recommended_action"],
        f"{action['confidence_score']}/100 confidence · {contact_line}",
    )
    why_preview = [
        shorten_bullet(reason)
        for reason in action.get("why_recommended", [])
        if not reason.lower().startswith("confidence:")
    ][:2]
    render_bullet_list(why_preview, max_items=2)


def render_action_details(
    company: pd.Series,
    profile: dict,
    learning_state: dict,
    action: dict,
    *,
    inline_draft: bool = False,
) -> None:
    email_draft = action["drafts"]["email"]
    recipient = resolve_draft_recipient(action)
    target_contact = action.get("target_contact")
    mailto_url, mailto_warning = build_mailto_link(action)
    mail_label = "Open mail app"
    if recipient:
        mail_label = f"Send mail → {recipient}"
    elif target_contact:
        mail_label = f"Send mail → {target_contact['name']}"

    st.link_button(mail_label, mailto_url, type="primary", use_container_width=True)
    if mailto_warning:
        st.caption("Draft shortened so the mobile mail app can open reliably.")
    if not recipient:
        st.caption("Add email below, save, then open mail.")

    draft_expander = not inline_draft
    draft_block = (
        st.expander("Edit draft", expanded=False)
        if draft_expander
        else st.container()
    )
    with draft_block:
        if inline_draft:
            st.markdown("**Email draft**")
        with st.form(f"drafts-{action['action_id']}"):
            email_to = st.text_input("To (email)", value=email_draft.get("to", ""))
            email_subject = st.text_input("Subject", value=email_draft["subject"])
            email_body = st.text_area("Email draft", value=email_draft["body"], height=160)
            linkedin_body = st.text_area(
                "LinkedIn draft",
                value=action["drafts"]["linkedin"]["body"],
                height=100,
            )
            if st.form_submit_button("Save draft", use_container_width=True):
                update_action_drafts(
                    company["company"],
                    action["action_id"],
                    email_to=email_to,
                    email_subject=email_subject,
                    email_body=email_body,
                    linkedin_body=linkedin_body,
                )
                st.rerun()

    with st.expander("Why this step?", expanded=False):
        st.write(action["opportunity_summary"])
        for reason in action["why_recommended"]:
            st.write(f"- {reason}")

    if st.button(
        "Get new suggestion",
        key=f"refresh-action-{company['company']}",
        use_container_width=True,
    ):
        refresh_recommendation(company.to_dict(), profile, learning_state)
        st.rerun()


def render_act_tab(company: pd.Series, profile: dict, learning_state: dict) -> dict:
    action = ensure_recommendation(company.to_dict(), profile, learning_state)
    render_action_surface(action)
    render_action_details(company, profile, learning_state, action)
    return action


def render_track_tab(
    company: pd.Series, profile: dict, learning_state: dict
) -> None:
    action = ensure_recommendation(company.to_dict(), profile, learning_state)
    render_info_card("Status", action["status"], action["recommended_action"])

    with st.form(f"action-status-{action['action_id']}"):
        status = st.selectbox(
            "Status update",
            ACTION_STATUSES,
            index=ACTION_STATUSES.index(action["status"]),
            label_visibility="collapsed",
        )
        note = st.text_input("Note (optional)")
        if st.form_submit_button("Save", use_container_width=True):
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

    history = get_all_action_history(company["company"])
    with st.expander(f"Action history ({len(history)})", expanded=False):
        if not history:
            st.caption("Nothing tracked yet.")
        for item in history:
            st.markdown(
                f"**{item['recommended_action']}** · {item['status']}"
            )
            st.caption(item.get("updated_at", item.get("generated_at", "")))


def render_learn_tab(learning_state: dict, questions: list[dict]) -> None:
    open_questions = get_open_questions(learning_state, questions)
    if open_questions:
        question = open_questions[0]
        render_info_card("Question", truncate(question["prompt"], 90))
    else:
        st.caption("All questions answered. Reopen one below.")
        question_labels = {item["prompt"]: item for item in questions}
        selected_prompt = st.selectbox(
            "Reopen question",
            question_labels,
            label_visibility="collapsed",
        )
        question = question_labels[selected_prompt]

    if questions:
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
                    question["prompt"],
                    question["options"],
                    default=previous_answer,
                    label_visibility="collapsed",
                )
            else:
                answer = st.text_area(
                    question["prompt"],
                    value=previous_answer,
                    label_visibility="collapsed",
                )
            if st.form_submit_button("Save answer", use_container_width=True):
                has_answer = (
                    bool(answer) if isinstance(answer, list) else bool(answer.strip())
                )
                if has_answer:
                    answer_question(learning_state, question, answer)
                    st.rerun()
                else:
                    st.warning("Write something first.")

    insights = generate_insights(learning_state, questions)
    proposals = generate_proposals(learning_state, questions)
    with st.expander("What AJOS learned", expanded=False):
        render_list(insights["learned"], "Nothing learned yet.")
        render_list(insights["hypotheses"], "No hypotheses yet.")
    with st.expander("Future ideas", expanded=False):
        for key, label in {
            "opportunity_source_suggestions": "New sources",
            "scoring_suggestions": "Scoring",
            "roadmap_suggestions": "Roadmap",
            "feature_suggestions": "Features",
        }.items():
            st.markdown(f"**{label}**")
            render_list(proposals[key], "Nothing yet.")


def render_list(items: list[str], empty_message: str) -> None:
    if not items:
        st.caption(empty_message)
        return
    for item in items:
        st.write(f"- {item}")


def render_review_bullets(company: pd.Series) -> None:
    bullets = split_bullets(company["why_fit"], 3) + split_bullets(
        company["problems_to_solve"], 2
    )
    render_bullet_list(bullets, max_items=4)


def _handle_review_decision(
    company: pd.Series,
    learning_state: dict,
    decision: str,
    *,
    is_discovered: bool = False,
    candidate_id: str | None = None,
) -> None:
    company_dict = company.to_dict()
    if decision == "pass":
        if is_discovered and candidate_id:
            reject_candidate(candidate_id)
        else:
            record_review_decision(learning_state, company_dict, "pass")
    elif decision == "saved":
        if is_discovered and candidate_id:
            merged = approve_candidate(candidate_id)
            load_data.clear()
            record_review_decision(learning_state, merged, "saved")
        else:
            record_review_decision(learning_state, company_dict, "saved")
    elif decision == "interested":
        if is_discovered and candidate_id:
            merged = approve_candidate(candidate_id)
            load_data.clear()
            record_review_decision(learning_state, merged, "interested")
            open_focus_view(merged["company"])
        else:
            record_review_decision(learning_state, company_dict, "interested")
            open_focus_view(company["company"])
    else:
        st.session_state.ajos_view = "review"
        st.session_state.ajos_focus_company = None
    st.rerun()


def render_review_actions(
    company: pd.Series,
    learning_state: dict,
    *,
    is_discovered: bool = False,
    candidate_id: str | None = None,
) -> None:
    st.markdown("---")
    if st.button(
        "Interested",
        key="review-interested",
        type="primary",
        use_container_width=True,
    ):
        _handle_review_decision(
            company,
            learning_state,
            "interested",
            is_discovered=is_discovered,
            candidate_id=candidate_id,
        )

    letgo_col, save_col = st.columns(2)
    with letgo_col:
        st.markdown('<div id="review-actions-letgo"></div>', unsafe_allow_html=True)
        if st.button("Let go", key="review-pass", use_container_width=True):
            _handle_review_decision(
                company,
                learning_state,
                "pass",
                is_discovered=is_discovered,
                candidate_id=candidate_id,
            )
    with save_col:
        st.markdown('<div id="review-actions-save"></div>', unsafe_allow_html=True)
        if st.button("Save for later", key="review-save", use_container_width=True):
            _handle_review_decision(
                company,
                learning_state,
                "saved",
                is_discovered=is_discovered,
                candidate_id=candidate_id,
            )


def render_review_header(
    queue_size: int,
    saved_count: int,
    interested_count: int,
) -> None:
    if interested_count:
        if st.button(
            f"Interested ({interested_count})",
            key="open-interested",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.ajos_view = "interested"
            st.rerun()

    header_left, header_saved = st.columns([2, 1])
    with header_left:
        if queue_size:
            st.caption(f"1 of {queue_size} in queue")
        else:
            st.caption("Queue empty")
    with header_saved:
        if saved_count and st.button(f"Saved ({saved_count})", key="open-saved"):
            st.session_state.ajos_view = "saved"
            st.rerun()


def render_discovery_footer() -> None:
    last_run = get_last_run()
    if not last_run:
        return
    themes = ", ".join(last_run.get("themes_searched", []))
    completed_at = last_run.get("completed_at", "")
    st.caption(
        f"Last discovery run: {completed_at} · themes: {themes} · "
        f"added {last_run.get('candidates_added', 0)}"
    )


def render_review_screen(
    filtered: pd.DataFrame,
    learning_state: dict,
    learning_questions: list[dict],
    *,
    selected_geographies: list[str],
    selected_themes: list[str],
) -> None:
    company_dicts = companies_as_dicts(filtered)
    queue = build_review_queue(
        company_dicts,
        learning_state,
        geographies=selected_geographies,
        themes=selected_themes,
    )
    saved = get_saved_companies(company_dicts, learning_state)
    interested = get_interested_companies(company_dicts, learning_state)

    render_review_header(len(queue), len(saved), len(interested))

    if not queue:
        st.info("You're through the list.")
        if saved:
            st.caption("Open Saved to revisit bookmarked opportunities.")
        if interested:
            st.caption("Open Interested to continue with liked opportunities.")
        render_discovery_footer()
        with st.expander("AJOS learning", expanded=False):
            render_learn_tab(learning_state, learning_questions)
        return

    current_item = queue[0]
    is_discovered = bool(current_item.get("is_discovered"))
    if is_discovered:
        current = review_item_to_series(current_item)
    else:
        current = find_company_row(filtered, current_item["company"])
    render_company_card(current, is_discovered=is_discovered)
    render_review_bullets(current)
    render_occasional_feedback(learning_state, learning_questions, current["company"])
    render_company_chat(current, mode="explore")
    render_review_actions(
        current,
        learning_state,
        is_discovered=is_discovered,
        candidate_id=current_item.get("candidate_id"),
    )
    render_discovery_footer()

    with st.expander("AJOS learning", expanded=False):
        render_learn_tab(learning_state, learning_questions)


def render_company_picker(
    companies: list[dict],
    filtered: pd.DataFrame,
    *,
    title: str,
    list_key: str,
) -> None:
    st.markdown(f"### {title}")
    if not companies:
        st.caption("Nothing here yet.")
    for company in companies:
        row = find_company_row(filtered, company["company"])
        if st.button(
            f"{row['company']} · {int(row['final_score'])}/100",
            key=f"{list_key}-{row['company']}",
            use_container_width=True,
        ):
            open_focus_view(row["company"])
            st.rerun()
    if st.button("← Back to queue", key=f"back-{list_key}", use_container_width=True):
        st.session_state.ajos_view = "review"
        st.rerun()


def render_focus_view(
    company: pd.Series,
    filtered: pd.DataFrame,
    profile: dict,
    learning_state: dict,
) -> None:
    if st.button("← Back to queue", key="focus-back", use_container_width=True):
        st.session_state.ajos_view = "review"
        st.session_state.ajos_focus_company = None
        st.rerun()

    render_company_card(company, label="Next steps")
    action = ensure_recommendation(company.to_dict(), profile, learning_state)
    render_action_surface(action)
    render_action_details(
        company,
        profile,
        learning_state,
        action,
        inline_draft=True,
    )
    st.markdown("---")
    st.caption("Questions? Ask here — draft edit upar hai.")
    render_company_chat(company, mode="action", action=action)
    with st.expander("Track progress", expanded=False):
        render_track_tab(company, profile, learning_state)
    st.link_button("Open website", company["website"], use_container_width=True)


def get_app_password() -> str:
    try:
        return st.secrets["AJOS_PASSWORD"]
    except (KeyError, AttributeError, FileNotFoundError):
        return os.environ.get("AJOS_PASSWORD", "")


def render_login_gate() -> None:
    if st.session_state.get("ajos_authenticated"):
        return

    expected_password = get_app_password()
    if not expected_password:
        st.error("Password not configured.")
        st.caption(
            "Local: create `.streamlit/secrets.toml`. "
            "Cloud: set `AJOS_PASSWORD` in Streamlit secrets."
        )
        st.stop()

    st.markdown('<div class="app-shell-title">AJOS</div>', unsafe_allow_html=True)
    st.subheader("Log in")

    def password_entered() -> None:
        if st.session_state.get("ajos_password_input") == expected_password:
            st.session_state.ajos_authenticated = True
            st.session_state.pop("ajos_login_error", None)
        else:
            st.session_state.ajos_login_error = True

    st.text_input(
        "Password",
        type="password",
        key="ajos_password_input",
        on_change=password_entered,
        label_visibility="collapsed",
        placeholder="Enter password",
    )
    if st.session_state.get("ajos_login_error"):
        st.error("Wrong password")
    if st.button("Enter", use_container_width=True):
        password_entered()
        if st.session_state.get("ajos_authenticated"):
            st.rerun()
    st.stop()


st.set_page_config(
    page_title="AJOS",
    page_icon="✦",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(APP_CSS, unsafe_allow_html=True)
render_login_gate()

try:
    companies_df, ankit_profile = load_data()
    learning_questions = load_questions()
    learning_state = persist_learning(load_state())
except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
    st.error(f"Could not load data: {error}")
    st.stop()

personalization = companies_df.apply(
    lambda company: calculate_personalization(company.to_dict(), learning_state),
    axis=1,
)
companies_df["learned_adjustment"] = [result[0] for result in personalization]
companies_df["adjustment_reasons"] = [result[1] for result in personalization]
companies_df["final_score"] = (
    companies_df["base_score"] + companies_df["learned_adjustment"]
).clip(0, 100)
companies_df = companies_df.sort_values(
    ["final_score", "base_score", "company"], ascending=[False, False, True]
)

init_session_view()

with st.expander("Filters", expanded=False):
    selected_geographies = st.multiselect(
        "Country", TARGET_GEOGRAPHIES, default=TARGET_GEOGRAPHIES
    )
    selected_themes = st.multiselect(
        "Theme", PRIORITY_THEMES, default=PRIORITY_THEMES
    )

filtered = companies_df[
    companies_df["country"].isin(selected_geographies)
    & companies_df["theme"].isin(selected_themes)
].copy()

if filtered.empty:
    st.warning("No matches — try broader filters.")
    st.stop()

company_dicts = companies_as_dicts(filtered)
view = st.session_state.ajos_view
focus_company = st.session_state.ajos_focus_company

if view == "saved":
    render_company_picker(
        get_saved_companies(company_dicts, learning_state),
        filtered,
        title="Saved for later",
        list_key="saved",
    )
elif view == "interested":
    render_company_picker(
        get_interested_companies(company_dicts, learning_state),
        filtered,
        title="Interested",
        list_key="interested",
    )
elif view == "focus" and focus_company:
    try:
        focus_row = find_company_row(companies_df, focus_company)
    except IndexError:
        st.session_state.ajos_view = "review"
        st.session_state.ajos_focus_company = None
        st.rerun()
    render_focus_view(focus_row, filtered, ankit_profile, learning_state)
else:
    render_review_screen(
        filtered,
        learning_state,
        learning_questions,
        selected_geographies=selected_geographies,
        selected_themes=selected_themes,
    )
