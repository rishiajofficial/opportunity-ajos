"""LLM-powered company chat — Claude (preferred) or OpenAI, grounded in CSV + intel briefs."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Literal

from openai import OpenAI

PROFILE_PATH = Path(__file__).parent / "data" / "ankit_profile.json"
OPENAI_MODEL = "gpt-4o-mini"
ANTHROPIC_MODEL = "claude-haiku-4-5"
MAX_HISTORY_TURNS = 4
MAX_BULLETS = 4

logger = logging.getLogger(__name__)

Provider = Literal["anthropic", "openai"]


class LLMChatError(Exception):
    """Raised when the LLM call fails."""


def _get_secret(name: str) -> str:
    # Streamlit Cloud injects root-level secrets as env vars too.
    env_value = os.environ.get(name, "").strip()
    if env_value:
        return env_value
    try:
        import streamlit as st

        try:
            return str(st.secrets[name]).strip()
        except (KeyError, TypeError):
            pass
        attr = getattr(st.secrets, name, None)
        if attr is not None and not callable(attr):
            return str(attr).strip()
    except Exception:
        pass
    return ""


def get_anthropic_api_key() -> str:
    return _get_secret("ANTHROPIC_API_KEY")


def get_openai_api_key() -> str:
    return _get_secret("OPENAI_API_KEY")


def get_active_provider() -> Provider | None:
    if get_anthropic_api_key():
        return "anthropic"
    if get_openai_api_key():
        return "openai"
    return None


def is_llm_enabled() -> bool:
    return get_active_provider() is not None


def get_llm_mode_label() -> str:
    provider = get_active_provider()
    if provider == "anthropic":
        return "Claude answers"
    if provider == "openai":
        return "AI answers"
    return "Research snippets"


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
        "why_recommended": (action.get("why_recommended", []))[:3],
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


def _build_messages(
    context: str,
    history: list[dict[str, Any]] | None,
    question: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {
            "role": "user",
            "content": f"Company context (ground truth — do not invent beyond this):\n{context}",
        },
    ]
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "content": question.strip()})
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


def _anthropic_model() -> str:
    return _get_secret("ANTHROPIC_MODEL") or ANTHROPIC_MODEL


def _call_anthropic(
    api_key: str,
    system_prompt: str,
    messages: list[dict[str, str]],
) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=_anthropic_model(),
        max_tokens=400,
        temperature=0.4,
        system=system_prompt,
        messages=messages,
    )
    parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(parts).strip()


def _call_openai(
    api_key: str,
    system_prompt: str,
    messages: list[dict[str, str]],
) -> str:
    client = OpenAI(api_key=api_key)
    openai_messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        *messages,
    ]
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=openai_messages,
        temperature=0.4,
        max_tokens=400,
    )
    return (response.choices[0].message.content or "").strip()


def answer_with_llm(
    question: str,
    company: dict[str, Any],
    report: dict[str, Any] | None,
    *,
    profile: dict[str, Any] | None = None,
    action: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> list[str]:
    provider = get_active_provider()
    if not provider:
        raise LLMChatError("No LLM API key configured (ANTHROPIC_API_KEY or OPENAI_API_KEY)")

    profile = profile or load_profile()
    context = build_chat_context(company, report, profile, action)
    system_prompt = _build_system_prompt(profile)
    messages = _build_messages(context, history, question)

    try:
        if provider == "anthropic":
            content = _call_anthropic(get_anthropic_api_key(), system_prompt, messages)
        else:
            content = _call_openai(get_openai_api_key(), system_prompt, messages)
    except Exception as exc:
        logger.warning("LLM chat failed (%s): %s", provider, exc)
        raise LLMChatError(str(exc)) from exc

    bullets = parse_bullets(content)
    if not bullets:
        raise LLMChatError("Empty LLM response")
    return bullets[:MAX_BULLETS]
