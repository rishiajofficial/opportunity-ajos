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
from llm_chat import get_llm_mode_label, is_llm_enabled
from company_intelligence import (
    get_current_report,
    intelligence_status,
    load_company_intelligence,
)
from contact_discovery import contacts_status, get_contact_recommendations
from content_engine import (
    get_last_run as get_content_last_run,
    get_pending_refinements,
    load_config as load_content_config,
    queue_for_refinement,
)
from discovery_engine import (
    approve_candidate,
    build_review_queue,
    get_last_run,
    load_config,
    reject_candidate,
    save_config,
)
from learning import (
    answer_question,
    approve_dev_feedback,
    calculate_personalization,
    dismiss_dev_feedback,
    generate_insights,
    generate_proposals,
    get_interested_companies,
    get_open_questions,
    get_saved_companies,
    is_question_answered,
    latest_answer_for,
    load_dev_agent_queue,
    load_dev_feedback,
    load_questions,
    load_state,
    persist_learning,
    record_feedback,
    record_outcome,
    record_review_decision,
    skip_question,
    submit_dev_feedback,
)
from ui_preferences import geography_options, load_preferences, save_preferences
from chat_store import load_chat, save_chat
from pipeline_status import pipeline_status


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
DISCOVERY_THEME_OPTIONS = PRIORITY_THEMES + ["Human Potential"]
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
    .dashboard-header {
        display: none;
    }
    .sidebar-brand {
        color: #173f34;
        font-size: 1.35rem;
        font-weight: 800;
        letter-spacing: 0.04em;
        margin: 0 0 0.15rem;
    }
    .sidebar-tagline {
        color: #6b7a73;
        font-size: 0.78rem;
        margin: 0 0 1rem;
    }
    .main-nav-wrap {
        background: #fff;
        border: 1px solid #e4ebe6;
        border-radius: 14px;
        margin-bottom: 0.85rem;
        padding: 0.45rem 0.5rem;
        position: sticky;
        top: 0.35rem;
        z-index: 30;
    }
    .main-nav-wrap [data-testid="column"] button {
        font-size: 0.78rem !important;
        min-height: 2.35rem;
        padding: 0.35rem 0.5rem !important;
        white-space: normal;
    }
    .queue-preview-item {
        color: #425049;
        font-size: 0.82rem;
        line-height: 1.5;
        margin: 0.1rem 0;
    }
    .queue-preview-active {
        color: #173f34;
        font-weight: 700;
    }
    @media (max-width: 768px) {
        div[data-testid="stHorizontalBlock"] {
            flex-direction: column !important;
            gap: 0.5rem !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            width: 100% !important;
            min-width: 100% !important;
            flex: 1 1 100% !important;
        }
    }
    @media (min-width: 1024px) {
        .block-container {
            max-width: 1280px;
            padding: 1rem 2rem 3rem;
        }
        section[data-testid="stSidebar"] {
            min-width: 300px !important;
            max-width: 320px !important;
            background: #f8faf9;
            border-right: 1px solid #dde5df;
        }
        section[data-testid="stSidebar"] .block-container {
            max-width: 100%;
            padding: 1rem 0.85rem 2rem;
        }
        .dashboard-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #fff;
            border: 1px solid #e4ebe6;
            border-radius: 16px;
            margin-bottom: 1rem;
            padding: 0.85rem 1.15rem;
        }
        .dashboard-header h1 {
            color: #173f34;
            font-size: 1.1rem;
            font-weight: 800;
            margin: 0;
        }
        .dashboard-header p {
            color: #6b7a73;
            font-size: 0.82rem;
            margin: 0;
        }
        .dashboard-metrics {
            display: flex;
            gap: 0.65rem;
            flex-wrap: wrap;
        }
        .dashboard-metric {
            background: #f4f7f5;
            border: 1px solid #e4ebe6;
            border-radius: 12px;
            font-size: 0.78rem;
            font-weight: 700;
            padding: 0.35rem 0.65rem;
            white-space: nowrap;
        }
        .dashboard-metric strong {
            color: #173f34;
        }
        .review-layout [data-testid="column"]:first-child .company-card {
            margin-top: 0;
        }
        .review-chat-column [data-testid="stChatMessage"] {
            padding: 0.35rem 0;
        }
        .review-chat-column [data-testid="stChatMessage"] p {
            font-size: 0.86rem;
            line-height: 1.35;
            margin: 0.15rem 0;
        }
        .review-chat-column [data-testid="stChatMessage"] ul {
            font-size: 0.86rem;
            line-height: 1.35;
            margin: 0.15rem 0 0.35rem;
            padding-left: 1.1rem;
        }
        .review-chat-column [data-testid="stChatMessage"] li {
            margin-bottom: 0.2rem;
        }
        .review-chat-column [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid #e4ebe6;
            border-radius: 12px;
            margin-bottom: 0.5rem;
        }
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
    #review-actions-unclear ~ div[data-testid="stButton"] > button {
        background: #f8f4f4 !important;
        border: 1px solid #d8c8c8 !important;
        color: #7a5a5a !important;
        font-weight: 700 !important;
    }
    .focus-steps {
        display: flex;
        gap: 0.4rem;
        flex-wrap: wrap;
        margin: 0.5rem 0 0.85rem;
    }
    .focus-step {
        background: #f4f7f5;
        border: 1px solid #e4ebe6;
        border-radius: 999px;
        color: #8a9a92;
        font-size: 0.76rem;
        font-weight: 700;
        padding: 0.28rem 0.7rem;
    }
    .focus-step.active {
        background: #e7efe9;
        border-color: #28705a;
        color: #173f34;
    }
    .focus-step.done {
        color: #28705a;
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


def shorten_bullet(text: str, max_words: int = 16) -> str:
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


FOCUS_STEPS = ("overview", "draft", "send")
MAIN_VIEWS = ("review", "interested", "saved", "learning", "proposals", "settings")


def init_session_view() -> None:
    st.session_state.setdefault("ajos_view", "review")
    st.session_state.setdefault("ajos_focus_company", None)
    st.session_state.setdefault("ajos_focus_return_view", "review")
    st.session_state.setdefault("company_chats", {})
    prefs = load_preferences()
    st.session_state.setdefault("sidebar_geographies", prefs["sidebar_geographies"])
    st.session_state.setdefault("sidebar_themes", prefs["sidebar_themes"])


def _focus_step_key(company_name: str) -> str:
    return f"ajos_focus_step::{company_name}"


def get_focus_step(company_name: str) -> str:
    step = st.session_state.get(_focus_step_key(company_name), "overview")
    return step if step in FOCUS_STEPS else "overview"


def set_focus_step(company_name: str, step: str) -> None:
    st.session_state[_focus_step_key(company_name)] = step


def chat_history(company_name: str) -> list[dict]:
    chats = st.session_state.company_chats
    if company_name not in chats:
        chats[company_name] = load_chat(company_name)
    return chats.setdefault(company_name, [])


MAX_CHAT_TURNS = 8


def append_chat_message(company_name: str, role: str, bullets: list[str]) -> None:
    history = chat_history(company_name)
    history.append({"role": role, "bullets": bullets})
    if len(history) > MAX_CHAT_TURNS * 2:
        del history[: -MAX_CHAT_TURNS * 2]
    save_chat(company_name, history)


def render_chat_messages(company_name: str, *, height: int = 300) -> None:
    messages = chat_history(company_name)
    if not messages:
        return
    with st.container(height=height, border=False):
        for message in messages:
            with st.chat_message(message["role"]):
                bullets = message.get("bullets") or []
                if len(bullets) == 1:
                    st.markdown(bullets[0])
                else:
                    st.markdown("\n".join(f"- {bullet}" for bullet in bullets))


def _answer_chat_question(
    question: str,
    company: pd.Series,
    report: dict | None,
    *,
    action: dict | None = None,
    profile: dict | None = None,
    chat_mode: str = "explore",
) -> list[str]:
    company_name = company["company"]
    history = chat_history(company_name)[:-1]
    with st.spinner("Soch raha hoon…"):
        return answer_company_question(
            question,
            company.to_dict(),
            report,
            action=action,
            history=history,
            profile=profile,
            chat_mode=chat_mode,
        )


def render_company_chat(
    company: pd.Series,
    *,
    mode: str = "explore",
    action: dict | None = None,
    profile: dict | None = None,
) -> None:
    company_name = company["company"]
    report = load_report(company_name)
    has_intel = report is not None
    chat_mode = "draft" if mode == "action" else mode

    mode_label = get_llm_mode_label()
    st.caption(f"Short answers · {mode_label}")
    render_chat_messages(company_name, height=450 if mode == "action" else 300)

    prompts = suggested_questions(has_intel, chat_mode=chat_mode)
    suggest_cols = st.columns(min(3, len(prompts)))
    for index, (col, prompt) in enumerate(zip(suggest_cols, prompts)):
        with col:
            if st.button(
                prompt,
                key=f"chat-suggest-{mode}-{company_name}-{index}",
                use_container_width=True,
            ):
                append_chat_message(company_name, "user", [prompt])
                bullets = _answer_chat_question(
                    prompt,
                    company,
                    report,
                    action=action,
                    profile=profile,
                    chat_mode=chat_mode,
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
        bullets = _answer_chat_question(
            question,
            company,
            report,
            action=action,
            profile=profile,
            chat_mode=chat_mode,
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
        save_col, skip_col = st.columns(2)
        with save_col:
            save_clicked = st.form_submit_button("Save", use_container_width=True)
        with skip_col:
            skip_clicked = st.form_submit_button("Skip", use_container_width=True)
        if save_clicked:
            has_answer = (
                bool(answer) if isinstance(answer, list) else bool(str(answer).strip())
            )
            if has_answer:
                answer_question(learning_state, question, answer)
                st.rerun()
        elif skip_clicked:
            skip_question(learning_state, question)
            st.rerun()


def open_focus_view(company_name: str, *, return_view: str = "review") -> None:
    st.session_state.ajos_view = "focus"
    st.session_state.ajos_focus_company = company_name
    st.session_state.ajos_focus_return_view = return_view
    st.session_state[_focus_step_key(company_name)] = "overview"


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

    email_line = ""
    if primary.get("email"):
        status = primary.get("email_status", "")
        status_label = f" · {status}" if status else ""
        email_line = f" · {primary['email']}{status_label}"
    render_info_card(
        "Try first",
        primary["name"],
        f"{primary['title']} · priority {primary['priority_score']}/100{email_line}",
    )
    render_bullet_list([shorten_bullet(primary["why_they_matter"])], max_items=1)
    if not primary.get("email"):
        st.caption("Email finder agent will look this up for interested companies.")

    with st.expander("Contact details", expanded=False):
        st.write(primary["why_they_matter"])
        st.markdown(f"[Source]({primary['source_url']})")
        if primary.get("email"):
            st.markdown(f"**Email:** {primary['email']}")
            if primary.get("email_status"):
                st.caption(f"Status: {primary['email_status']}")
            if primary.get("email_source_url"):
                st.markdown(f"[Email source]({primary['email_source_url']})")
        secondary = recommendations["secondary"]
        if secondary:
            st.markdown(f"**Plan B:** {secondary['name']} · {secondary['title']}")
            st.write(secondary["why_they_matter"])
            if secondary.get("email"):
                st.markdown(f"**Email:** {secondary['email']}")
        if recommendations["why_primary"]:
            st.caption(recommendations["why_primary"])
        for contact in recommendations["all_contacts"]:
            contact_email = f" · {contact['email']}" if contact.get("email") else ""
            st.markdown(
                f"**{contact['name']}** · {contact['title']} · "
                f"{contact['priority_score']}/100{contact_email}"
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
            email_body = st.text_area("Email draft", value=email_draft["body"], height=320)
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


def render_answered_questions_summary(
    learning_state: dict, questions: list[dict]
) -> None:
    answered = [
        question
        for question in questions
        if is_question_answered(learning_state, question["id"])
    ]
    if not answered:
        return
    for question in answered:
        record = latest_answer_for(learning_state, question["id"])
        if not record:
            continue
        answer_text = record["answer"]
        if isinstance(answer_text, list):
            answer_text = ", ".join(answer_text)
        st.caption(f"**{truncate(question['prompt'], 70)}** — {answer_text}")


def render_question_form(
    learning_state: dict,
    question: dict,
    *,
    form_key_suffix: str = "",
) -> None:
    previous_answer = latest_answer_for(learning_state, question["id"])
    default_value = (
        previous_answer["answer"]
        if previous_answer
        else ([] if question["type"] == "multiselect" else "")
    )
    with st.form(f"question-{question['id']}{form_key_suffix}"):
        if question["type"] == "multiselect":
            answer = st.multiselect(
                question["prompt"],
                question["options"],
                default=default_value,
                label_visibility="collapsed",
            )
        else:
            answer = st.text_area(
                question["prompt"],
                value=default_value,
                label_visibility="collapsed",
            )
        save_col, skip_col = st.columns(2)
        with save_col:
            save_clicked = st.form_submit_button("Save answer", use_container_width=True)
        with skip_col:
            skip_clicked = st.form_submit_button("Skip for now", use_container_width=True)
        if save_clicked:
            has_answer = (
                bool(answer) if isinstance(answer, list) else bool(str(answer).strip())
            )
            if has_answer:
                answer_question(learning_state, question, answer)
                st.rerun()
            else:
                st.warning("Write something first.")
        elif skip_clicked:
            skip_question(learning_state, question)
            st.rerun()


def render_dev_proposals(proposals: dict) -> None:
    dev_proposals = proposals.get("dev_proposals", [])
    if not dev_proposals:
        st.caption("No pending dev feedback proposals.")
        return
    for item in dev_proposals:
        st.markdown(f"**{item['feedback']}**")
        st.caption(item["suggested_action"])
        approve_col, dismiss_col = st.columns(2)
        with approve_col:
            if st.button(
                "Approve",
                key=f"dev-approve-{item['id']}",
                use_container_width=True,
                type="primary",
            ):
                approve_dev_feedback(item["id"])
                st.success(
                    "Queued for dev agent — push to GitHub or automation will pick up."
                )
                st.rerun()
        with dismiss_col:
            if st.button(
                "Dismiss",
                key=f"dev-dismiss-{item['id']}",
                use_container_width=True,
            ):
                dismiss_dev_feedback(item["id"])
                st.rerun()


def render_dev_feedback_panel(*, use_expander: bool = True) -> None:
    if use_expander:
        with st.expander("Dev feedback", expanded=False):
            _render_dev_feedback_form()
    else:
        st.markdown("#### Dev feedback")
        _render_dev_feedback_form()


def _render_dev_feedback_form() -> None:
    st.caption(
        "Product or code feedback. Approved items queue for the development agent."
    )
    feedback_text = st.text_area(
        "What should we build or fix?",
        height=100,
        key="dev-feedback-input",
        label_visibility="collapsed",
        placeholder="e.g. Learning questions keep repeating after I answer them",
    )
    if st.button("Submit feedback", key="dev-feedback-submit", type="primary"):
        try:
            item = submit_dev_feedback(feedback_text)
            st.success("Feedback saved and queued for dev agent.")
            st.rerun()
        except ValueError as error:
            st.warning(str(error))

    queue = load_dev_agent_queue()
    queued = [item for item in queue.get("items", []) if item.get("status") == "queued"]
    if queued:
        st.caption(f"{len(queued)} item(s) queued for dev agent.")

    store = load_dev_feedback()
    recent = list(reversed(store.get("items", [])))[:5]
    if recent:
        st.markdown("**Recent feedback**")
        for item in recent:
            status = item.get("status", "pending")
            st.caption(f"{status}: {item['feedback'][:100]}")


def render_learning_questions(learning_state: dict, questions: list[dict]) -> None:
    open_questions = get_open_questions(learning_state, questions)
    if open_questions:
        question = open_questions[0]
        render_info_card("Question", truncate(question["prompt"], 90))
        render_question_form(learning_state, question)
    else:
        st.caption("Core questions complete.")
        render_answered_questions_summary(learning_state, questions)
        with st.expander("Update an answer", expanded=False):
            question_labels = {item["prompt"]: item for item in questions}
            selected_prompt = st.selectbox(
                "Choose question",
                question_labels,
                label_visibility="collapsed",
            )
            render_question_form(
                learning_state,
                question_labels[selected_prompt],
                form_key_suffix="-reopen",
            )


def render_learning_screen(learning_state: dict, questions: list[dict]) -> None:
    st.markdown("### Learning")
    st.caption("One question at a time — answers shape scoring and recommendations.")
    render_learning_questions(learning_state, questions)

    insights = generate_insights(learning_state, questions)
    st.markdown("#### What AJOS learned")
    render_list(insights["learned"], "Nothing learned yet.")
    st.markdown("#### Hypotheses")
    render_list(insights["hypotheses"], "No hypotheses yet.")
    if insights["positive_signals"]:
        st.markdown("#### Positive signals")
        render_list(insights["positive_signals"], "")
    if insights["negative_signals"]:
        st.markdown("#### Negative signals")
        render_list(insights["negative_signals"], "")
    if insights["open_questions"]:
        st.markdown("#### Still open")
        render_list(insights["open_questions"], "All core questions answered.")


def render_proposals_screen(learning_state: dict, questions: list[dict]) -> None:
    proposals = generate_proposals(learning_state, questions)
    st.markdown("### Proposals")
    st.caption(proposals.get("notice", ""))

    st.markdown("#### Dev proposals")
    render_dev_proposals(proposals)

    st.markdown("#### Future ideas")
    for key, label in {
        "opportunity_source_suggestions": "New sources",
        "scoring_suggestions": "Scoring",
        "roadmap_suggestions": "Roadmap",
        "feature_suggestions": "Features",
        "content_suggestions": "Copy to refine",
    }.items():
        st.markdown(f"**{label}**")
        render_list(proposals.get(key, []), "Nothing yet.")


def render_settings_screen() -> None:
    st.markdown("### Settings")
    st.caption("Discovery, agents, and product feedback — always here in the main view.")
    render_discovery_panel(use_expander=False)
    render_dev_feedback_panel(use_expander=False)
    try:
        from orchestrator_engine import enqueue, get_queued

        st.markdown("#### Orchestrator")
        queued = get_queued(limit=10)
        st.caption(f"{len(queued)} queued orchestrator item(s).")
        if st.button("Test orchestrator sync", key="orchestrator-sync-test"):
            item = enqueue(
                "sync_check",
                notes="Manual sync check from Settings",
                source="settings_sync_test",
                priority=1,
            )
            st.success(
                "Queued sync check "
                f"{item['id']} — GitHub sync will push the orchestrator queue when configured."
            )
    except ImportError:
        pass
    try:
        from github_sync import is_configured, load_status, sync_now

        st.markdown("#### GitHub sync")
        if is_configured():
            status = load_status()
            if status.get("pending"):
                st.caption("Pending sync to GitHub…")
                if st.button("Sync now", key="github-sync-now"):
                    result = sync_now()
                    if result.get("ok"):
                        st.success("Synced to GitHub.")
                    else:
                        st.error(result.get("error", "Sync failed"))
            elif status.get("last_sync"):
                st.caption(f"Last synced: {status['last_sync']}")
            else:
                st.caption("Auto-sync enabled when data changes.")
        else:
            st.caption("Set GITHUB_TOKEN to auto-sync data/ to GitHub.")
    except ImportError:
        pass


def render_list(items: list[str], empty_message: str) -> None:
    if not items:
        st.caption(empty_message)
        return
    for item in items:
        st.write(f"- {item}")


def render_review_bullets(company: pd.Series) -> None:
    bullets = (
        split_bullets(company.get("description", ""), 1)
        + split_bullets(company["why_fit"], 2)
        + split_bullets(company["problems_to_solve"], 1)
    )
    render_bullet_list(bullets, max_items=4)


def _trigger_outreach_pipeline(company_name: str) -> None:
    try:
        from orchestrator_engine import enqueue

        enqueue(
            "outreach_pipeline",
            company=company_name,
            source="interested_click",
            priority=1,
        )
    except ImportError:
        pass
    try:
        from pipeline_runner import run_outreach_pipeline

        run_outreach_pipeline(company_name)
    except Exception:
        pass


def _handle_review_decision(
    company: pd.Series,
    learning_state: dict,
    decision: str,
    *,
    is_discovered: bool = False,
    candidate_id: str | None = None,
    reason: str = "",
) -> None:
    company_dict = company.to_dict()
    rating_labels = {
        "pass": "Not Interested",
        "saved": "Saved",
        "interested": "Like",
        "unclear": "Didn't Understand",
    }
    if decision == "pass":
        if is_discovered and candidate_id:
            reject_candidate(candidate_id)
        record_review_decision(learning_state, company_dict, "pass")
        st.toast(f"Saved: {rating_labels['pass']}")
    elif decision == "saved":
        if is_discovered and candidate_id:
            merged = approve_candidate(candidate_id)
            load_data.clear()
            record_review_decision(learning_state, merged, "saved")
        else:
            record_review_decision(learning_state, company_dict, "saved")
        st.toast(f"Saved: {rating_labels['saved']}")
    elif decision == "interested":
        if is_discovered and candidate_id:
            merged = approve_candidate(candidate_id)
            load_data.clear()
            record_review_decision(learning_state, merged, "interested")
            _trigger_outreach_pipeline(merged["company"])
            open_focus_view(merged["company"], return_view="review")
        else:
            record_review_decision(learning_state, company_dict, "interested")
            _trigger_outreach_pipeline(company["company"])
            open_focus_view(company["company"], return_view="review")
        st.toast(f"Saved: {rating_labels['interested']}")
    elif decision == "unclear":
        if is_discovered and candidate_id:
            reject_candidate(candidate_id, reason=reason or "Copy unclear")
        record_review_decision(learning_state, company_dict, "unclear", reason)
        if not is_discovered:
            queue_for_refinement(company_dict, reason)
        st.session_state.pop("ajos_unclear_company", None)
        st.toast(f"Saved: {rating_labels['unclear']}")
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

    company_name = str(company["company"])
    if st.session_state.get("ajos_unclear_company") == company_name:
        reason = st.text_area(
            "Kya samajh nahi aaya? (optional — isse copy improve hogi)",
            key=f"unclear-reason-{company_name}",
            placeholder="e.g. company kya karti hai clear nahi thi, fit vague laga…",
        )
        confirm_col, cancel_col = st.columns(2)
        with confirm_col:
            st.markdown('<div id="review-actions-unclear"></div>', unsafe_allow_html=True)
            if st.button(
                "Hata do & improve karo",
                key="review-unclear-confirm",
                use_container_width=True,
            ):
                _handle_review_decision(
                    company,
                    learning_state,
                    "unclear",
                    is_discovered=is_discovered,
                    candidate_id=candidate_id,
                    reason=reason,
                )
        with cancel_col:
            if st.button("Cancel", key="review-unclear-cancel", use_container_width=True):
                st.session_state.pop("ajos_unclear_company", None)
                st.rerun()
    else:
        st.markdown('<div id="review-actions-unclear"></div>', unsafe_allow_html=True)
        if st.button(
            "Didn't understand",
            key="review-unclear",
            use_container_width=True,
        ):
            st.session_state["ajos_unclear_company"] = company_name
            st.rerun()


def switch_view(view: str) -> None:
    st.session_state.ajos_view = view
    if view != "focus":
        st.session_state.ajos_focus_company = None
    st.rerun()


def render_main_nav(
    current: str,
    *,
    queue_len: int,
    saved_count: int,
    interested_count: int,
    pending_dev_proposals: int = 0,
) -> None:
    st.markdown('<div class="main-nav-wrap">', unsafe_allow_html=True)
    cols = st.columns(len(MAIN_VIEWS))
    labels = {
        "review": f"Review ({queue_len})",
        "interested": f"Interested ({interested_count})",
        "saved": f"Saved ({saved_count})",
        "learning": "Learning",
        "proposals": (
            f"Proposals ({pending_dev_proposals})"
            if pending_dev_proposals
            else "Proposals"
        ),
        "settings": "Settings",
    }
    for col, view_key in zip(cols, MAIN_VIEWS):
        with col:
            if st.button(
                labels[view_key],
                key=f"main-nav-{view_key}",
                use_container_width=True,
                type="primary" if current == view_key else "secondary",
            ):
                if current != view_key:
                    switch_view(view_key)
    st.markdown("</div>", unsafe_allow_html=True)


def leave_focus_view() -> None:
    return_view = st.session_state.get("ajos_focus_return_view", "review")
    switch_view(return_view)


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
            switch_view("interested")

    header_left, header_saved = st.columns([2, 1])
    with header_left:
        if queue_size:
            st.caption(f"1 of {queue_size} in queue")
        else:
            st.caption("Queue empty")
    with header_saved:
        if saved_count and st.button(f"Saved ({saved_count})", key="open-saved"):
            switch_view("saved")


def render_dashboard_header(
    queue_size: int,
    saved_count: int,
    interested_count: int,
    *,
    current_company: str = "",
) -> None:
    current_line = (
        f"Reviewing <strong>{html.escape(current_company)}</strong>"
        if current_company
        else "Queue empty"
    )
    render_html(
        f'<div class="dashboard-header">'
        f"<div><h1>AJOS</h1><p>Opportunity review</p></div>"
        f'<div class="dashboard-metrics">'
        f'<span class="dashboard-metric">Queue <strong>{queue_size}</strong></span>'
        f'<span class="dashboard-metric">Saved <strong>{saved_count}</strong></span>'
        f'<span class="dashboard-metric">Interested <strong>{interested_count}</strong></span>'
        f'<span class="dashboard-metric">{current_line}</span>'
        f"</div></div>"
    )


def render_sidebar_dashboard(
    *,
    queue: list[dict],
    saved_count: int,
    interested_count: int,
    selected_geographies: list[str],
    selected_themes: list[str],
) -> tuple[list[str], list[str]]:
    with st.sidebar:
        st.markdown('<p class="sidebar-brand">AJOS</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="sidebar-tagline">Filters & queue</p>',
            unsafe_allow_html=True,
        )

        view = st.session_state.ajos_view
        if view == "focus":
            st.caption("Next steps open")
            if st.button("← Back to queue", key="sidebar-focus-back", use_container_width=True):
                leave_focus_view()
        else:
            st.caption(
                "Learning, Proposals, Settings — top tabs in main view "
                "(sidebar collapse safe)."
            )

        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        m1.metric("Queue", len(queue))
        m2.metric("Saved", saved_count)
        m3.metric("Interested", interested_count)

        if queue:
            st.caption("Up next")
            for index, item in enumerate(queue[:6]):
                name = html.escape(str(item["company"]))
                score = int(item.get("final_score", 0))
                active = " queue-preview-active" if index == 0 else ""
                badge = " · Discovered" if item.get("is_discovered") else ""
                st.markdown(
                    f'<p class="queue-preview-item{active}">'
                    f"{name} · {score}/100{badge}</p>",
                    unsafe_allow_html=True,
                )

        st.markdown("---")
        sidebar_country_options = geography_options(
            discovery_countries=load_config().get("active_countries", [])
        )
        selected_geographies = st.multiselect(
            "Country",
            sidebar_country_options,
            default=[g for g in selected_geographies if g in sidebar_country_options],
            key="sidebar-countries",
        )
        selected_themes = st.multiselect(
            "Theme",
            PRIORITY_THEMES,
            default=selected_themes,
            key="sidebar-themes",
        )

        render_discovery_footer()

    return selected_geographies, selected_themes


def _lines_to_list(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def render_discovery_panel(*, use_expander: bool = True) -> None:
    config = load_config()
    pending_country = st.session_state.get("discovery-new-country", "").strip()
    country_options = sorted(
        set(TARGET_GEOGRAPHIES)
        | set(config.get("active_countries", []))
        | ({pending_country} if pending_country else set())
    )
    theme_options = sorted(
        set(DISCOVERY_THEME_OPTIONS) | set(config.get("active_themes", []))
    )

    def _discovery_form() -> None:
        status = "on" if config["enabled"] else "paused"
        st.caption(
            f"Cloud agent searches from `data/discovery/config.json` · status: **{status}**"
        )
        if config.get("updated_at"):
            st.caption(f"Config updated: {config['updated_at']}")

        enabled = st.toggle(
            "Discovery enabled",
            value=bool(config["enabled"]),
            key="discovery-enabled",
        )
        active_countries = st.multiselect(
            "Search countries",
            country_options,
            default=[
                c for c in config.get("active_countries", []) if c in country_options
            ],
            key="discovery-countries",
        )
        new_country = st.text_input(
            "Add country",
            placeholder="e.g. Germany",
            key="discovery-new-country",
        )
        if new_country.strip():
            extra = new_country.strip()
            if extra not in active_countries:
                active_countries = active_countries + [extra]
                st.caption(f"Will include: {extra}")

        active_themes = st.multiselect(
            "Search themes",
            theme_options,
            default=[t for t in config.get("active_themes", []) if t in theme_options],
            key="discovery-themes",
        )
        industries_text = st.text_area(
            "Industries (one per line)",
            value="\n".join(config.get("active_industries", [])),
            height=80,
            key="discovery-industries",
            help="Extra search tags for the cloud agent, e.g. workplace wellbeing",
        )
        exclude_text = st.text_area(
            "Exclude keywords (one per line)",
            value="\n".join(config.get("exclude_keywords", [])),
            height=60,
            key="discovery-exclude",
        )
        limit_col, threshold_col = st.columns(2)
        with limit_col:
            max_candidates = st.number_input(
                "Max candidates per run",
                min_value=0,
                max_value=10,
                value=int(config.get("max_candidates_per_run", 3)),
                key="discovery-max-candidates",
            )
        with threshold_col:
            notify_threshold = st.slider(
                "Notify if score ≥",
                min_value=70,
                max_value=100,
                value=int(config.get("notify_threshold", 85)),
                key="discovery-notify-threshold",
            )

        if st.button("Save discovery settings", key="discovery-save", type="primary"):
            countries_to_save = list(active_countries)
            extra_country = new_country.strip()
            if extra_country and extra_country not in countries_to_save:
                countries_to_save.append(extra_country)
            saved = save_config(
                {
                    "enabled": enabled,
                    "active_countries": countries_to_save,
                    "active_themes": active_themes,
                    "active_industries": _lines_to_list(industries_text),
                    "exclude_keywords": _lines_to_list(exclude_text),
                    "max_candidates_per_run": int(max_candidates),
                    "notify_threshold": int(notify_threshold),
                }
            )
            st.session_state["discovery-countries"] = countries_to_save
            st.session_state["discovery-new-country"] = ""
            try:
                from github_sync import schedule_sync

                schedule_sync("discovery/config.json")
            except ImportError:
                pass
            st.success(
                f"Saved countries: {', '.join(saved.get('active_countries', countries_to_save))}"
            )
            st.rerun()

    if use_expander:
        with st.expander("Discovery", expanded=False):
            _discovery_form()
    else:
        st.markdown("#### Discovery")
        _discovery_form()


def render_discovery_footer() -> None:
    config = load_config()
    last_run = get_last_run()
    status = "on" if config["enabled"] else "paused"
    if last_run:
        themes = ", ".join(last_run.get("themes_searched", []))
        completed_at = last_run.get("completed_at", "")
        discovery_line = (
            f"Discovery {status} · last run: {completed_at} · themes: {themes} · "
            f"added {last_run.get('candidates_added', 0)}"
        )
    else:
        discovery_line = f"Discovery {status} · no runs logged yet"

    content_config = load_content_config()
    content_status = "on" if content_config["enabled"] else "paused"
    pending = len(get_pending_refinements())
    content_run = get_content_last_run()
    if content_run:
        content_line = (
            f"Content agent {content_status} · last run: {content_run.get('completed_at', '')} · "
            f"refined {content_run.get('companies_refined', 0)} · pending {pending}"
        )
    else:
        content_line = (
            f"Content agent {content_status} · pending {pending}"
            if pending
            else f"Content agent {content_status} · no runs yet"
        )
    st.caption(f"{discovery_line} · {content_line}")


def render_review_screen(
    filtered: pd.DataFrame,
    learning_state: dict,
    learning_questions: list[dict],
    *,
    selected_geographies: list[str],
    selected_themes: list[str],
    profile: dict | None = None,
    queue: list[dict] | None = None,
    saved_count: int | None = None,
    interested_count: int | None = None,
) -> None:
    company_dicts = companies_as_dicts(filtered)
    if queue is None:
        queue = build_review_queue(
            company_dicts,
            learning_state,
            geographies=selected_geographies,
            themes=selected_themes,
        )
    if saved_count is None:
        saved_count = len(get_saved_companies(company_dicts, learning_state))
    if interested_count is None:
        interested_count = len(get_interested_companies(company_dicts, learning_state))

    render_dashboard_header(
        len(queue),
        saved_count,
        interested_count,
        current_company=queue[0]["company"] if queue else "",
    )
    render_review_header(len(queue), saved_count, interested_count)

    if not queue:
        st.info("You're through the list.")
        if saved_count:
            st.caption("Open Saved to revisit bookmarked opportunities.")
        if interested_count:
            st.caption("Open Interested to continue with liked opportunities.")
        st.caption("Use the top tabs for Learning, Proposals, or Settings.")
        return

    current_item = queue[0]
    is_discovered = bool(current_item.get("is_discovered"))
    if is_discovered:
        current = review_item_to_series(current_item)
    else:
        current = find_company_row(filtered, current_item["company"])

    main_col, chat_col = st.columns([11, 9], gap="large")
    with main_col:
        render_company_card(current, is_discovered=is_discovered)
        render_review_bullets(current)
        render_review_actions(
            current,
            learning_state,
            is_discovered=is_discovered,
            candidate_id=current_item.get("candidate_id"),
        )
    with chat_col:
        st.markdown('<div class="review-layout review-chat-column"></div>', unsafe_allow_html=True)
        render_occasional_feedback(learning_state, learning_questions, current["company"])
        render_company_chat(current, mode="explore", profile=profile)


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
            open_focus_view(row["company"], return_view=list_key)
            st.rerun()
    if st.button("← Back to queue", key=f"back-{list_key}", use_container_width=True):
        st.session_state.ajos_view = "review"
        st.rerun()


def render_focus_step_indicator(current: str) -> None:
    labels = {"overview": "Next step", "draft": "Draft", "send": "Send"}
    current_idx = FOCUS_STEPS.index(current)
    parts: list[str] = []
    for index, step_id in enumerate(FOCUS_STEPS):
        if index < current_idx:
            css = "focus-step done"
        elif index == current_idx:
            css = "focus-step active"
        else:
            css = "focus-step"
        parts.append(f'<span class="{css}">{index + 1}. {labels[step_id]}</span>')
    st.markdown(f'<div class="focus-steps">{"".join(parts)}</div>', unsafe_allow_html=True)


def render_focus_nav(company_name: str, step: str) -> None:
    back_col, queue_col, _ = st.columns([1, 1, 2])
    with back_col:
        if step != "overview":
            previous = FOCUS_STEPS[FOCUS_STEPS.index(step) - 1]
            if st.button("← Back", key=f"focus-prev-{step}", use_container_width=True):
                set_focus_step(company_name, previous)
                st.rerun()
    with queue_col:
        if st.button("← Queue", key="focus-back-queue", use_container_width=True):
            leave_focus_view()


def render_focus_overview_step(
    company: pd.Series,
    profile: dict,
    learning_state: dict,
    action: dict,
) -> None:
    render_company_card(company, label="Next steps")
    status = pipeline_status(company["company"], action)
    st.caption(
        f"Contacts: {status['contacts']} · Email: {status['email']} · Draft: {status['draft']}"
    )
    render_action_surface(action)
    with st.expander("Why this step?", expanded=False):
        st.write(action["opportunity_summary"])
        for reason in action["why_recommended"][:4]:
            st.write(f"- {shorten_bullet(reason)}")
    if st.button(
        "Draft edit karo →",
        key=f"focus-to-draft-{company['company']}",
        type="primary",
        use_container_width=True,
    ):
        set_focus_step(company["company"], "draft")
        st.rerun()
    if st.button(
        "Naya suggestion",
        key=f"focus-refresh-{company['company']}",
        use_container_width=True,
    ):
        refresh_recommendation(company.to_dict(), profile, learning_state)
        set_focus_step(company["company"], "overview")
        st.rerun()


def render_focus_draft_step(company: pd.Series, action: dict) -> None:
    email_draft = action["drafts"]["email"]
    target_contact = action.get("target_contact")
    if target_contact:
        st.caption(f"To: {target_contact['name']} · {target_contact['title']}")
    with st.form(f"focus-draft-{action['action_id']}"):
        email_to = st.text_input("To (email)", value=email_draft.get("to", ""))
        email_subject = st.text_input("Subject", value=email_draft["subject"])
        email_body = st.text_area("Message", value=email_draft["body"], height=360)
        with st.expander("LinkedIn draft"):
            linkedin_body = st.text_area(
                "LinkedIn",
                value=action["drafts"]["linkedin"]["body"],
                height=140,
                label_visibility="collapsed",
            )
        if st.form_submit_button("Save & continue →", use_container_width=True, type="primary"):
            update_action_drafts(
                company["company"],
                action["action_id"],
                email_to=email_to,
                email_subject=email_subject,
                email_body=email_body,
                linkedin_body=linkedin_body,
            )
            set_focus_step(company["company"], "send")
            st.rerun()


def render_focus_send_step(
    company: pd.Series,
    profile: dict,
    learning_state: dict,
    action: dict,
) -> None:
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
        st.caption("Email missing? ← Back se draft mein add karo.")

    if st.button("Mark as sent", key=f"focus-sent-{company['company']}", use_container_width=True):
        from outreach_outcomes import record_sent

        draft = action.get("drafts", {}).get("email", {})
        contact = action.get("target_contact") or {}
        record_sent(
            company=company["company"],
            contact=contact.get("name", ""),
            subject=draft.get("subject", ""),
            body=draft.get("body", ""),
        )
        update_action_status(
            company["company"],
            action["action_id"],
            "Sent",
            "Marked sent from Focus view.",
        )
        st.toast("Email marked sent — learning queued.")
        st.rerun()

    with st.expander("Track progress", expanded=False):
        render_track_tab(company, profile, learning_state)
    st.link_button("Open website", company["website"], use_container_width=True)


def render_focus_view(
    company: pd.Series,
    filtered: pd.DataFrame,
    profile: dict,
    learning_state: dict,
) -> None:
    company_name = company["company"]
    step = get_focus_step(company_name)
    action = ensure_recommendation(company.to_dict(), profile, learning_state)

    main_col, chat_col = st.columns([11, 9], gap="large")
    with main_col:
        render_focus_nav(company_name, step)
        render_focus_step_indicator(step)
        if step == "overview":
            render_focus_overview_step(company, profile, learning_state, action)
        elif step == "draft":
            render_focus_draft_step(company, action)
        else:
            render_focus_send_step(company, profile, learning_state, action)
    with chat_col:
        st.markdown('<div class="review-chat-column"></div>', unsafe_allow_html=True)
        st.caption("Short answers · draft edit left side pe hai.")
        render_company_chat(company, mode="action", action=action, profile=profile)


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
    layout="wide",
    initial_sidebar_state="expanded",
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

company_dicts_all = companies_as_dicts(companies_df)
learning_state_for_sidebar = learning_state
queue_for_sidebar = build_review_queue(
    company_dicts_all,
    learning_state_for_sidebar,
    geographies=st.session_state.sidebar_geographies,
    themes=st.session_state.sidebar_themes,
)
saved_for_sidebar = get_saved_companies(company_dicts_all, learning_state_for_sidebar)
interested_for_sidebar = get_interested_companies(
    company_dicts_all, learning_state_for_sidebar
)

selected_geographies, selected_themes = render_sidebar_dashboard(
    queue=queue_for_sidebar,
    saved_count=len(saved_for_sidebar),
    interested_count=len(interested_for_sidebar),
    selected_geographies=st.session_state.sidebar_geographies,
    selected_themes=st.session_state.sidebar_themes,
)
pending_dev_proposals = len(
    generate_proposals(learning_state, learning_questions).get("dev_proposals", [])
)
st.session_state.sidebar_geographies = selected_geographies
st.session_state.sidebar_themes = selected_themes
save_preferences(geographies=selected_geographies, themes=selected_themes)

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

nav_view = (
    view
    if view in MAIN_VIEWS
    else st.session_state.get("ajos_focus_return_view", "review")
)
render_main_nav(
    nav_view,
    queue_len=len(queue_for_sidebar),
    saved_count=len(saved_for_sidebar),
    interested_count=len(interested_for_sidebar),
    pending_dev_proposals=pending_dev_proposals,
)

if view == "learning":
    render_learning_screen(learning_state, learning_questions)
elif view == "proposals":
    render_proposals_screen(learning_state, learning_questions)
elif view == "settings":
    render_settings_screen()
elif view == "saved":
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
        profile=ankit_profile,
        queue=build_review_queue(
            company_dicts,
            learning_state,
            geographies=selected_geographies,
            themes=selected_themes,
        ),
        saved_count=len(get_saved_companies(company_dicts, learning_state)),
        interested_count=len(get_interested_companies(company_dicts, learning_state)),
    )
