"""Multi-step LLM outreach: strategic angle → conversation opener."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from llm_chat import LLMChatError, get_active_provider, get_anthropic_api_key, get_openai_api_key
from openai import OpenAI

logger = logging.getLogger(__name__)

PROFILE_PATH = Path(__file__).parent / "data" / "ankit_profile.json"
OUTREACH_DIR = Path(__file__).parent / "data" / "outreach"
ANGLES_PATH = OUTREACH_DIR / "angles.json"
OUTCOMES_PATH = OUTREACH_DIR / "outcomes.json"
CONFIG_PATH = OUTREACH_DIR / "config.json"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as destination:
        json.dump(data, destination, indent=2, ensure_ascii=True)
        destination.write("\n")


def load_profile() -> dict[str, Any]:
    return load_json(PROFILE_PATH, {})


def load_config() -> dict[str, Any]:
    defaults = {"draft_mode": "llm", "auto_research": True}
    stored = load_json(CONFIG_PATH, defaults)
    return {**defaults, **stored}


def load_angles() -> dict[str, list]:
    return load_json(ANGLES_PATH, {"items": []})


def save_angle(company: str, angle: str, hook: str) -> None:
    store = load_angles()
    store["items"] = [
        item for item in store.get("items", []) if item.get("company") != company
    ]
    store["items"].append({"company": company, "angle": angle, "hook": hook})
    save_json(ANGLES_PATH, store)


def prior_angles(exclude_company: str | None = None) -> list[str]:
    return [
        item["angle"]
        for item in load_angles().get("items", [])
        if item.get("company") != exclude_company and item.get("angle")
    ]


def _call_llm(system: str, user: str, *, max_tokens: int = 600) -> str:
    provider = get_active_provider()
    if not provider:
        raise LLMChatError("No LLM API key configured")

    if provider == "anthropic":
        from anthropic import Anthropic

        client = Anthropic(api_key=get_anthropic_api_key())
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=max_tokens,
            temperature=0.4,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "\n".join(block.text for block in response.content if block.type == "text")

    client = OpenAI(api_key=get_openai_api_key())
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or "").strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[\s\S]*\}", stripped)
    if match:
        return json.loads(match.group())
    raise LLMChatError("Could not parse LLM JSON response")


def derive_strategic_angle(
    company: dict[str, Any],
    report: dict[str, Any] | None,
    profile: dict[str, Any] | None = None,
) -> dict[str, str]:
    profile = profile or load_profile()
    outreach = profile.get("outreach_voice", {})
    avoid_repeat = prior_angles(exclude_company=company.get("company"))

    intel = ""
    if report:
        for section in report.get("sections", [])[:6]:
            intel += f"\n{section.get('id', '')}: {str(section.get('content', ''))[:300]}"

    system = f"""You identify a unique strategic tension for founder outreach.
Style: crisp, Elon-style observation — not compliments, not job asks.
Avoid repeating these prior angles: {avoid_repeat[:5]}
Return JSON: {{"tension": "...", "hook_question": "...", "avoid_repeating": "..."}}"""

    user = f"""Company: {company.get('company')}
Theme: {company.get('theme')}
Role: {company.get('suggested_role')}
Why fit: {company.get('why_fit', '')[:400]}
Problems: {company.get('problems_to_solve', '')[:300]}
Intel:{intel or ' limited'}

Find the company-specific strategic question a founder would want to answer — not generic wellbeing/fit praise."""

    result = _parse_json_object(_call_llm(system, user, max_tokens=400))
    angle = str(result.get("tension", "")).strip()
    hook = str(result.get("hook_question", "")).strip()
    if angle:
        save_angle(company["company"], angle, hook)
    return {"tension": angle, "hook_question": hook, "avoid_repeating": str(result.get("avoid_repeating", ""))}


def generate_conversation_opener(
    company: dict[str, Any],
    contact: dict[str, Any] | None,
    angle: dict[str, str],
    profile: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    """Return (subject, body, reasoning)."""
    profile = profile or load_profile()
    outreach = profile.get("outreach_voice", {})
    signature_name = outreach.get("signature_name", "A. Zen")
    tagline = outreach.get("tagline", "AI Product & Systems Builder, figuring out my next engagement")
    agent_mention = outreach.get("agent_mention", "(My AI agent identifies companies aligned with me. {company} came up.)")
    avoid = ", ".join(outreach.get("avoid", []))
    examples = json.dumps(outreach.get("example_emails", [])[:2], ensure_ascii=False)

    contact_name = ""
    if contact and contact.get("name"):
        first = contact["name"].split()[0]
        contact_name = first

    system = f"""Write a founder conversation opener email for Ankit.
Style: {outreach.get('style', 'Crisp founder-to-founder. Observation + implication + one question. No job ask.')}
Max {outreach.get('max_body_lines', 6)} lines in body. No exclamation marks.
Avoid: {avoid}
Sign as:
—
{signature_name}
{tagline}
{agent_mention.format(company=company.get('company', ''))}

Few-shot examples:
{examples}

Return JSON: {{"subject": "...", "body": "...", "reasoning": "..."}}"""

    user = f"""Company: {company.get('company')}
Contact first name: {contact_name or 'unknown — use no greeting name'}
Strategic tension: {angle.get('tension', '')}
Hook question: {angle.get('hook_question', '')}

Write subject (provocative, ~5 words) and body (observation → implication → curious question). Do NOT ask for a job."""

    result = _parse_json_object(_call_llm(system, user, max_tokens=500))
    subject = str(result.get("subject", "")).strip()
    body = str(result.get("body", "")).strip()
    reasoning = str(result.get("reasoning", "")).strip()
    return subject, body, reasoning


def validate_draft(subject: str, body: str, profile: dict[str, Any] | None = None) -> list[str]:
    profile = profile or load_profile()
    outreach = profile.get("outreach_voice", {})
    issues: list[str] = []
    combined = f"{subject} {body}".lower()
    for phrase in outreach.get("avoid", []):
        if phrase.lower() in combined:
            issues.append(f"Contains avoid phrase: {phrase}")
    if "?" not in body and "curious" not in combined:
        issues.append("Body should include a founder-level question")
    if len(body.split("\n")) > outreach.get("max_body_lines", 6) + 2:
        issues.append("Body too long")
    job_phrases = ("hire me", "open role", "job opportunity", "i need a role")
    if any(p in combined for p in job_phrases):
        issues.append("Sounds like a job ask")
    return issues


def generate_email_draft_llm(
    company: dict[str, Any],
    report: dict[str, Any] | None,
    contact: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    """Return (subject, body, reasoning). Raises LLMChatError on failure."""
    angle = derive_strategic_angle(company, report, profile)
    subject, body, reasoning = generate_conversation_opener(company, contact, angle, profile)
    issues = validate_draft(subject, body, profile)
    if issues:
        reasoning += " | Validation: " + "; ".join(issues)
    return subject, body, reasoning
