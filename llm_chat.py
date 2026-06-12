"""LLM-powered company chat via OpenAI gpt-4o-mini, grounded in CSV + intelligence briefs."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

PROFILE_PATH = Path(__file__).parent / "data" / "ankit_profile.json"
MODEL = "gpt-4o-mini"
MAX_HISTORY_TURNS = 4
MAX_BULLETS = 4

logger = logging.getLogger(__name__)


class LLMChatError(Exception):
    """Raised when the LLM call fails."""


def get_api_key() -> str:
    try:
        import streamlit as st

        key = st.secrets.get("OPENAI_API_KEY", "")
        if key:
            return str(key).strip()
    except Exception:
        pass
    return os.environ.get("OPENAI_API_KEY", "").strip()


def is_llm_enabled() -> bool:
    return bool(get_api_key())


def load_profile() -> dict[str, Any]:
    if not PROFILE_PATH.exists():
        return {}
    with PROFILE_PATH.open(encoding="utf-8") as source:
        return json.load(source)


def _compact_company(company: dict[str, Any]) -> dict[str, Any]:
    keys = (
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
    )
    return {key: company.get(key, "") for key in keys if company.get(key)}


def _compact_report(report: dict[str, Any] | None) -> list[dict[str, str]]:
    if not report:
        return []
    sections: list[dict[str, str]] = []
    for section in report.get("sections", []):
        content = str(section.get("content", "")).strip()
        if not content:
            continue
        sections.append(
            {
                "id": str(section.get("id", "")),
                "kind": str(section.get("kind", "observation")),
                "content": content[:500],
            }
        )
    return sections


def _compact_action(action: dict[str, Any] | None) -> dict[str, Any] | None:
    if not action:
        return None
    draft = action.get("drafts", {}).get("email", {})
    contact = action.get("target_contact") or {}
    return {
        "recommended_action": action.get("recommended_action", ""),
        "why_recommended": (action.get("why_recommended") or [])[:3],
        "target_contact": {
            "name": contact.get("name", ""),
            "title": contact.get("title", ""),
        },
        "email_draft": {
            "subject": draft.get("subject", ""),
            "body_preview": str(draft.get("body", ""))[:400],
        },
    }


def build_chat_context(
    company: dict[str, Any],
    report: dict[str, Any] | None,
    profile: dict[str, Any] | None,
    action: dict[str, Any] | None,
) -> str:
    payload: dict[str, Any] = {
        "company": _compact_company(company),
        "intelligence_sections": _compact_report(report),
        "has_intelligence_brief": bool(report),
    }
    if profile:
        payload["ankit_profile"] = {
            "positioning": profile.get("positioning", ""),
            "capabilities": profile.get("capabilities", []),
            "priority_themes": profile.get("priority_themes", []),
            "role_patterns": profile.get("role_patterns", []),
        }
    action_context = _compact_action(action)
    if action_context:
        payload["action_context"] = action_context
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_system_prompt(profile: dict[str, Any]) -> str:
    voice = profile.get("content_voice", {})
    avoid = ", ".join(voice.get("avoid", []))
    examples = "\n".join(f"- {item}" for item in voice.get("example_bullets", [])[:3])
    return f"""You are the AJOS Opportunity Engine assistant for Ankit.

Mission: opportunity creation — not job matching. Help Ankit understand founders, companies, and how he could create disproportionate value through conversation, collaboration, advisory work, or leadership.

Voice: Roman Hinglish, tum/tera tone. Short bullets — generic corporate copy nahi.
Return exactly 3-4 bullet points as a JSON array of strings, e.g. ["bullet 1", "bullet 2"].

Rules:
- Answer ONLY from the provided company data and intelligence brief. Do not invent facts.
- Intelligence sections marked kind "hypothesis" are hypotheses — say so briefly if you cite them.
- Intelligence sections marked kind "fact" or "observation" are stronger ground.
- If context lacks detail for the question, say "detail kam hai" and suggest what to ask next.
- Focus on fit, problems Ankit can solve, and potential entry points — not generic praise.
- Avoid these phrases: {avoid or "synergy, great fit, leverage"}.

Example tone:
{examples or "- Tum yahan systems + product dono chala sakte ho"}"""


def _history_messages(history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    if not history:
        return []
    messages: list[dict[str, str]] = []
    for turn in history[-MAX_HISTORY_TURNS * 2 :]:
        role = turn.get("role", "")
        if role not in {"user", "assistant"}:
            continue
        bullets = turn.get("bullets") or []
        content = "\n".join(f"- {b}" for b in bullets) if bullets else ""
        if content:
            messages.append({"role": role, "content": content})
    return messages


def parse_bullets(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []

    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                bullets = [str(item).strip() for item in parsed if str(item).strip()]
                if bullets:
                    return bullets[:MAX_BULLETS]
        except json.JSONDecodeError:
            pass

    match = re.search(r"\[[\s\S]*\]", stripped)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                bullets = [str(item).strip() for item in parsed if str(item).strip()]
                if bullets:
                    return bullets[:MAX_BULLETS]
        except json.JSONDecodeError:
            pass

    lines: list[str] = []
    for line in stripped.splitlines():
        cleaned = re.sub(r"^[-*•]\s*", "", line.strip())
        if cleaned:
            lines.append(cleaned)
    return lines[:MAX_BULLETS] if lines else [stripped[:280]]


def answer_with_llm(
    question: str,
    company: dict[str, Any],
    report: dict[str, Any] | None,
    *,
    profile: dict[str, Any] | None = None,
    action: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> list[str]:
    api_key = get_api_key()
    if not api_key:
        raise LLMChatError("OPENAI_API_KEY not configured")

    profile = profile or load_profile()
    context = build_chat_context(company, report, profile, action)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _build_system_prompt(profile)},
        {
            "role": "user",
            "content": f"Company context (ground truth — do not invent beyond this):\n{context}",
        },
    ]
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "content": question.strip()})

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.4,
            max_tokens=400,
        )
        content = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("LLM chat failed: %s", exc)
        raise LLMChatError(str(exc)) from exc

    bullets = parse_bullets(content)
    if not bullets:
        raise LLMChatError("Empty LLM response")
    return bullets[:MAX_BULLETS]
