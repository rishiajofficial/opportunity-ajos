"""Grounded company Q&A from CSV + intelligence briefs, with optional LLM."""

from __future__ import annotations

import logging
import re
from typing import Any

from company_intelligence import get_current_report, intelligence_status, load_company_intelligence
from contact_discovery import get_contact_recommendations
from llm_chat import LLMChatError, answer_with_llm, get_active_provider, is_llm_enabled

logger = logging.getLogger(__name__)


TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "what_they_do": ("what do", "what does", "kya kart", "company do", "about them", "business"),
    "customers": ("customer", "client", "who buy", "who use", "kaun use"),
    "products_and_services": ("product", "service", "offer", "feature", "platform"),
    "business_model": ("revenue", "business model", "monetiz", "pricing", "saas"),
    "recent_developments": ("recent", "news", "latest", "abhi kya", "development"),
    "hiring_patterns": ("hiring", "hire", "jobs", "roles", "recruit"),
    "strategic_challenges": ("challenge", "problem", "risk", "struggle", "issue"),
    "value_for_aj": (
        "why fit",
        "why me",
        "value",
        "kyun fit",
        "kaise fit",
        "main fit",
        "create value",
        "my fit",
    ),
    "potential_entry_points": ("entry", "how to approach", "collaboration", "partnership", "start"),
    "contacts": ("contact", "who to reach", "email who", "founder", "ceo", "kisko"),
    "why_fit_csv": ("opportunity", "alignment", "score", "role"),
    "problems": ("solve", "help them", "problems", "kya solve"),
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _match_topics(question: str) -> list[str]:
    normalized = _normalize(question)
    matched = [
        topic
        for topic, keywords in TOPIC_KEYWORDS.items()
        if any(keyword in normalized for keyword in keywords)
    ]
    if not matched:
        if any(word in normalized for word in ("fit", "why", "value")):
            matched.append("value_for_aj")
        if any(word in normalized for word in ("do", "kya", "about")):
            matched.append("what_they_do")
    return matched or ["what_they_do", "value_for_aj"]


def _section_by_id(report: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    return next(
        (section for section in report.get("sections", []) if section.get("id") == section_id),
        None,
    )


def _bullets_from_section(section: dict[str, Any] | None, max_items: int = 3) -> list[str]:
    if not section:
        return []
    preview = section.get("preview") or []
    if preview:
        return preview[:max_items]
    items = section.get("items") or []
    if items:
        return [str(item) for item in items[:max_items]]
    content = section.get("content", "").strip()
    if not content:
        return []
    parts = [part.strip() for part in content.replace(";", ".").split(".") if part.strip()]
    return parts[:max_items] if parts else [content[:220]]


def load_report(company_name: str) -> dict[str, Any] | None:
    if not intelligence_status(company_name)["exists"]:
        return None
    return get_current_report(load_company_intelligence(company_name))


def suggested_questions(has_intel: bool) -> list[str]:
    base = [
        "Ye company kya karti hai?",
        "Main yahan kaise fit hoon?",
        "Main kya solve kar sakta hoon?",
    ]
    if has_intel:
        base.extend(["Customers kaun hain?", "Approach kaise karoon?"])
    return base[:5]


def _csv_bullets(field: str, max_items: int = 3) -> list[str]:
    text = str(field or "").strip()
    if not text:
        return []
    if ";" in text:
        return [part.strip() for part in text.split(";") if part.strip()][:max_items]
    return [text[:220]]


def _company_pitch(company: dict[str, Any]) -> list[str]:
    desc = str(company.get("description", "")).strip()
    return [desc] if desc else []


def answer_company_question(
    question: str,
    company: dict[str, Any],
    report: dict[str, Any] | None,
    *,
    action: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
    profile: dict[str, Any] | None = None,
) -> list[str]:
    if is_llm_enabled():
        try:
            return answer_with_llm(
                question,
                company,
                report,
                action=action,
                history=history,
                profile=profile,
            )
        except LLMChatError as exc:
            logger.warning("Falling back to rule-based chat: %s", exc)
            provider = get_active_provider() or "LLM"
            bullets = _answer_rule_based(
                question,
                company,
                report,
                action=action,
            )
            error_hint = str(exc).split("\n")[0][:100]
            return [
                f"{provider} abhi respond nahi kar paya ({error_hint}) — research snippets:"
            ] + bullets[:3]

    return _answer_rule_based(
        question,
        company,
        report,
        action=action,
    )


def _answer_rule_based(
    question: str,
    company: dict[str, Any],
    report: dict[str, Any] | None,
    *,
    action: dict[str, Any] | None = None,
) -> list[str]:
    normalized = _normalize(question)
    if not normalized:
        return ["Kuch likho — company ke baare mein pooch sakte ho."]

    if action and any(word in normalized for word in ("draft", "email", "mail", "linkedin")):
        draft = action.get("drafts", {}).get("email", {})
        contact = action.get("target_contact") or {}
        lines = [
            f"Suggested action: {action.get('recommended_action', '—')}",
            f"Draft to: {contact.get('name', '—')} ({contact.get('title', '—')})",
        ]
        if draft.get("subject"):
            lines.append(f"Subject: {draft['subject']}")
        if draft.get("body"):
            preview = draft["body"].split("\n\n")[0][:160]
            lines.append(f"Opener: {preview}…")
        lines.append("Neeche draft edit kar sakte ho, ya specific change batao.")
        return lines

    if action and any(word in normalized for word in ("next step", "what should", "kya kar")):
        lines = [f"Next step: {action.get('recommended_action', '—')}"]
        for reason in action.get("why_recommended", [])[:3]:
            lines.append(reason)
        return lines

    topics = _match_topics(question)
    answers: list[str] = []

    for topic in topics:
        if topic == "what_they_do":
            answers.extend(_company_pitch(company))
            if report:
                section = _section_by_id(report, "what_they_do")
                answers.extend(_bullets_from_section(section, max_items=1))
            continue
        if topic in {"value_for_aj", "why_fit_csv"}:
            answers.extend(_csv_bullets(company.get("why_fit", ""), max_items=3))
            if report and len(answers) < 3:
                section = _section_by_id(report, "value_for_aj")
                answers.extend(_bullets_from_section(section, max_items=2))
            continue
        if topic == "problems":
            answers.extend(_csv_bullets(company.get("problems_to_solve", ""), max_items=3))
            continue
        if topic == "contacts":
            recs = get_contact_recommendations(company["company"])
            primary = recs.get("primary")
            if primary:
                answers.append(
                    f"Pehle try karo: {primary['name']} ({primary['title']})"
                )
                answers.append(primary["why_they_matter"])
            else:
                answers.append("Abhi contacts file mein nahi — pehle fit samjho, phir reach.")
            continue
        if topic == "potential_entry_points" and report:
            section = _section_by_id(report, "potential_entry_points")
            answers.extend(_bullets_from_section(section, max_items=3))
            continue
        if report:
            section = _section_by_id(report, topic)
            answers.extend(_bullets_from_section(section, max_items=2))

    if not answers:
        answers = (
            _company_pitch(company)
            or _csv_bullets(company.get("why_fit", ""), max_items=2)
            or ["Is company pe detail kam hai — specific sawaal poocho."]
        )

    seen: set[str] = set()
    unique: list[str] = []
    for line in answers:
        key = line.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(line.strip())
    return unique[:4]
