"""Grounded company Q&A from CSV + intelligence briefs (no LLM)."""

from __future__ import annotations

import re
from typing import Any

from company_intelligence import get_current_report, intelligence_status, load_company_intelligence
from contact_discovery import get_contact_recommendations


TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "what_they_do": ("what do", "what does", "kya kart", "company do", "about them", "business"),
    "customers": ("customer", "client", "who buy", "who use", "kaun use"),
    "products_and_services": ("product", "service", "offer", "feature", "platform"),
    "business_model": ("revenue", "business model", "monetiz", "pricing", "saas"),
    "recent_developments": ("recent", "news", "latest", "abhi kya", "development"),
    "hiring_patterns": ("hiring", "hire", "jobs", "roles", "recruit"),
    "strategic_challenges": ("challenge", "problem", "risk", "struggle", "issue"),
    "value_for_aj": ("why fit", "why me", "value", "kyun fit", "create value", "my fit"),
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
        "What do they do?",
        "Why might I fit here?",
        "What could I help solve?",
    ]
    if has_intel:
        base.extend(["Who are their customers?", "How could I approach them?"])
    return base[:5]


def answer_company_question(
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
        if topic == "why_fit_csv":
            why = str(company.get("why_fit", "")).strip()
            if why:
                parts = [part.strip() for part in why.split(";") if part.strip()]
                answers.extend(parts[:3])
            continue
        if topic == "problems":
            problems = str(company.get("problems_to_solve", "")).strip()
            if problems:
                parts = [part.strip() for part in problems.split(";") if part.strip()]
                answers.extend(parts[:3])
            continue
        if topic == "contacts":
            recs = get_contact_recommendations(company["company"])
            primary = recs.get("primary")
            if primary:
                answers.append(
                    f"Try first: {primary['name']} ({primary['title']})"
                )
                answers.append(primary["why_they_matter"])
            else:
                answers.append("Abhi contacts file mein nahi — website se explore karo.")
            continue
        if report:
            section = _section_by_id(report, topic)
            title = section.get("title", topic) if section else topic
            bullets = _bullets_from_section(section)
            if bullets:
                answers.append(f"{title}")
                answers.extend(bullets[:2])
        elif topic in {"what_they_do", "value_for_aj"}:
            desc = str(company.get("description", "")).strip()
            if desc:
                answers.append(desc)

    if not answers:
        if report:
            section = _section_by_id(report, "what_they_do")
            answers = _bullets_from_section(section, max_items=2)
        if not answers:
            answers = [
                str(company.get("description", "")).strip() or "Is company pe abhi limited detail hai.",
                "Try: what do they do / why fit / what problems / how to approach.",
            ]

    return answers[:4]
