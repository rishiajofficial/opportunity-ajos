import json
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from company_intelligence import (
    company_to_slug,
    get_current_report,
    intelligence_status,
    load_company_intelligence,
)
from contact_discovery import contact_summary, get_contact_recommendations


ACTIONS_DIR = Path(__file__).parent / "data" / "actions"
COMPANIES_ACTIONS_DIR = ACTIONS_DIR / "companies"
PATTERNS_PATH = ACTIONS_DIR / "patterns.json"

ACTION_TYPES = (
    "Send introduction email",
    "Send LinkedIn message",
    "Request conversation",
    "Offer workshop",
    "Offer pilot project",
    "Offer advisory support",
    "Share insight",
    "Do nothing yet",
)

ACTION_STATUSES = (
    "Suggested",
    "Drafted",
    "Sent",
    "Replied",
    "Meeting Scheduled",
    "Opportunity Created",
    "Closed",
)

STATUS_SIGNAL_WEIGHTS = {
    "Suggested": 0,
    "Drafted": 1,
    "Sent": 8,
    "Replied": 12,
    "Meeting Scheduled": 15,
    "Opportunity Created": 20,
    "Closed": -2,
}

TERMINAL_STATUSES = {"Closed", "Opportunity Created"}
MAX_MAILTO_URL_LENGTH = 2048

ENTRY_POINT_ACTION_MAP = (
    (("workshop",), "Offer workshop"),
    (("pilot",), "Offer pilot project"),
    (("advisor", "advisory"), "Offer advisory support"),
    (("product feedback", "share insight", "educator-in-residence"), "Share insight"),
    (("strategic collaboration", "partnership"), "Request conversation"),
    (("fractional", "in residence", "innovation partner"), "Request conversation"),
    (("introduction", "intro"), "Send introduction email"),
    (("community", "talk", "playbook"), "Share insight"),
)

ROLE_ACTION_MAP = (
    (("advisor", "advisory"), "Offer advisory support"),
    (("founder in residence", "entrepreneur in residence", "innovation partner"), "Request conversation"),
    (("workshop",), "Offer workshop"),
    (("lead", "head", "director"), "Request conversation"),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def entity_actions_path(entity_id: str) -> Path:
    return COMPANIES_ACTIONS_DIR / f"{company_to_slug(entity_id)}.json"


def default_patterns() -> dict[str, Any]:
    return {
        "updated_at": now_iso(),
        "theme_action_counts": {},
        "action_type_outcomes": {},
        "channel_counts": {},
        "successful_themes": {},
    }


def load_action_patterns() -> dict[str, Any]:
    patterns = load_json(PATTERNS_PATH, default_patterns())
    patterns.setdefault("theme_action_counts", {})
    patterns.setdefault("action_type_outcomes", {})
    patterns.setdefault("channel_counts", {})
    patterns.setdefault("successful_themes", {})
    return patterns


def save_action_patterns(patterns: dict[str, Any]) -> None:
    patterns["updated_at"] = now_iso()
    save_json(PATTERNS_PATH, patterns)


def default_entity_actions(entity_id: str) -> dict[str, Any]:
    return {
        "entity_type": "company",
        "entity_id": entity_id,
        "actions": [],
    }


def load_entity_actions(entity_id: str) -> dict[str, Any]:
    entity = load_json(entity_actions_path(entity_id), default_entity_actions(entity_id))
    entity.setdefault("actions", [])
    entity["entity_type"] = "company"
    entity["entity_id"] = entity_id
    return entity


def save_entity_actions(entity: dict[str, Any]) -> None:
    save_json(entity_actions_path(entity["entity_id"]), entity)


def get_active_action(entity: dict[str, Any]) -> dict[str, Any] | None:
    for action in reversed(entity["actions"]):
        if action["status"] not in TERMINAL_STATUSES:
            return action
    return None


def get_section(report: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    for section in report.get("sections", []):
        if section["id"] == section_id:
            return section
    return None


def map_text_to_action(text: str, mapping: tuple) -> str | None:
    lowered = text.lower()
    for keywords, action in mapping:
        if any(keyword in lowered for keyword in keywords):
            return action
    return None


def pick_action_from_intelligence(report: dict[str, Any]) -> str | None:
    entry_points = get_section(report, "potential_entry_points")
    if entry_points:
        for item in entry_points.get("items", []):
            action = map_text_to_action(item, ENTRY_POINT_ACTION_MAP)
            if action:
                return action
    return None


def pick_action_from_role(role: str) -> str | None:
    return map_text_to_action(role, ROLE_ACTION_MAP)


def latest_feedback_for_company(
    learning_state: dict[str, Any], company_name: str
) -> dict[str, Any] | None:
    for item in reversed(learning_state.get("feedback", [])):
        if item["company"] == company_name:
            return item
    return None


def pattern_action_boost(theme: str, patterns: dict[str, Any]) -> tuple[str | None, int]:
    theme_actions = patterns.get("theme_action_counts", {}).get(theme, {})
    if not theme_actions:
        return None, 0
    best_action = max(theme_actions, key=theme_actions.get)
    weight = theme_actions[best_action]
    if weight >= 2:
        return best_action, min(15, weight * 3)
    return None, 0


def build_opportunity_summary(
    company: dict[str, Any], report: dict[str, Any] | None
) -> str:
    if report:
        value_section = get_section(report, "value_for_aj")
        if value_section and value_section.get("content"):
            return value_section["content"]
    return (
        f"Explore a {company['suggested_role']} path at {company['company']} "
        f"in {company['theme']}."
    )


def build_why_recommended(
    company: dict[str, Any],
    action: str,
    report: dict[str, Any] | None,
    learning_state: dict[str, Any],
    patterns: dict[str, Any],
    confidence: int,
) -> list[str]:
    reasons = []
    feedback = latest_feedback_for_company(learning_state, company["company"])
    if feedback and feedback["rating"] == "Like":
        reasons.append("AJ previously liked this opportunity.")
    if report:
        reasons.append("Company intelligence brief is available to ground outreach.")
        entry_points = get_section(report, "potential_entry_points")
        if entry_points and entry_points.get("items"):
            reasons.append(
                "Intelligence entry points suggest a concrete collaboration path."
            )
    pattern_action, _ = pattern_action_boost(company["theme"], patterns)
    if pattern_action == action:
        reasons.append(
            f"Past actions in {company['theme']} suggest this action type works for AJ."
        )
    if company["theme"] in patterns.get("successful_themes", {}):
        reasons.append(
            f"{company['theme']} has produced positive action outcomes before."
        )
    if action == "Share insight" and feedback and feedback.get("reason"):
        if any(
            word in feedback["reason"].lower()
            for word in ("used the product", "teacher", "understand")
        ):
            reasons.append(
                "AJ has firsthand product experience that supports a insight-led opening."
            )
    if action == "Do nothing yet":
        reasons.append(
            "More research or intelligence may be needed before outreach is worthwhile."
        )
    if not reasons:
        reasons.append(
            f"Alignment with {company['theme']} and role pattern "
            f"{company['suggested_role']} supports this next step."
        )
    reasons.append(f"Confidence score: {confidence}/100.")
    return reasons


def calculate_confidence(
    company: dict[str, Any],
    action: str,
    report: dict[str, Any] | None,
    learning_state: dict[str, Any],
    patterns: dict[str, Any],
) -> int:
    score = 40
    if report:
        score += 15
    feedback = latest_feedback_for_company(learning_state, company["company"])
    if feedback:
        if feedback["rating"] == "Like":
            score += 12
        elif feedback["rating"] == "Not Interested":
            score -= 20
    score += min(15, int(company.get("final_score", company.get("base_score", 0)) / 10))
    pattern_action, pattern_boost = pattern_action_boost(company["theme"], patterns)
    if pattern_action == action:
        score += pattern_boost
    if company["theme"] in patterns.get("successful_themes", {}):
        score += 8
    if action == "Do nothing yet":
        score = max(20, min(score, 55))
    return max(0, min(100, score))


def choose_recommended_action(
    company: dict[str, Any],
    learning_state: dict[str, Any],
    patterns: dict[str, Any],
    report: dict[str, Any] | None,
) -> str:
    feedback = latest_feedback_for_company(learning_state, company["company"])
    if feedback and feedback["rating"] == "Not Interested":
        return "Do nothing yet"
    if not report and int(company.get("final_score", 0)) < 70:
        return "Do nothing yet"

    pattern_action, boost = pattern_action_boost(company["theme"], patterns)
    if pattern_action and boost >= 6:
        return pattern_action

    if report:
        intelligence_action = pick_action_from_intelligence(report)
        if intelligence_action:
            return intelligence_action

    role_action = pick_action_from_role(company["suggested_role"])
    if role_action:
        return role_action

    if feedback and feedback["rating"] == "Like":
        return "Request conversation"

    return "Send LinkedIn message"


def resolve_draft_recipient(action: dict[str, Any]) -> str:
    email_draft = action.get("drafts", {}).get("email", {})
    if email_draft.get("to"):
        return email_draft["to"].strip()
    target_contact = action.get("target_contact") or {}
    if target_contact.get("email"):
        return target_contact["email"].strip()
    return ""


def build_mailto_url(*, to: str = "", subject: str = "", body: str = "") -> str:
    address = quote(to.strip(), safe="") if to.strip() else ""
    base = f"mailto:{address}" if address else "mailto:"
    params = []
    if subject.strip():
        params.append(f"subject={quote(subject.strip(), safe='')}")
    if body.strip():
        params.append(f"body={quote(body.strip(), safe='')}")
    if not params:
        return base
    return f"{base}?{'&'.join(params)}"


def build_mailto_link(action: dict[str, Any]) -> tuple[str, str | None]:
    email_draft = action.get("drafts", {}).get("email", {})
    to = resolve_draft_recipient(action)
    subject = email_draft.get("subject", "")
    body = email_draft.get("body", "")
    warning = None
    url = build_mailto_url(to=to, subject=subject, body=body)
    if len(url) <= MAX_MAILTO_URL_LENGTH:
        return url, warning

    trimmed_body = body
    while len(url) > MAX_MAILTO_URL_LENGTH and len(trimmed_body) > 120:
        trimmed_body = trimmed_body[:-120].rstrip() + "\n\n[...]"
        url = build_mailto_url(to=to, subject=subject, body=trimmed_body)
    if len(url) > MAX_MAILTO_URL_LENGTH:
        trimmed_body = trimmed_body[:600].rstrip() + "\n\n[...]"
        url = build_mailto_url(to=to, subject=subject, body=trimmed_body)
    warning = "Email body was shortened so the mobile mail app can open reliably."
    return url, warning


def email_draft_payload(
    *,
    subject: str,
    body: str,
    to: str = "",
    timestamp: str | None = None,
) -> dict[str, str]:
    return {
        "to": to.strip(),
        "subject": subject.strip(),
        "body": body.strip(),
        "updated_at": timestamp or now_iso(),
    }


def generate_email_draft(
    company: dict[str, Any],
    action: str,
    profile: dict[str, Any],
    report: dict[str, Any] | None,
    contact: dict[str, Any] | None = None,
) -> tuple[str, str]:
    company_name = company["company"]
    role = company["suggested_role"]
    greeting = f"Hello {contact['name']}," if contact else "Hello,"
    opener = (
        f"I have been following {company_name}'s work in {company['theme']} "
        f"and see a meaningful opportunity to create value together."
    )
    if report:
        what_they_do = get_section(report, "what_they_do")
        if what_they_do and what_they_do.get("content"):
            opener = (
                f"I have been following {company_name}'s work — "
                f"{what_they_do['content'][:180].rstrip('.')}."
            )

    action_lines = {
        "Offer workshop": (
            f"I would like to explore a focused workshop on {company['theme']} "
            f"innovation that connects strategy, systems thinking, and practical execution."
        ),
        "Offer pilot project": (
            f"I would like to propose a short pilot project where I help shape "
            f"a {role.lower()} initiative with clear outcomes in 4-8 weeks."
        ),
        "Offer advisory support": (
            f"I would like to explore advisory support around {role.lower()} "
            f"and how AJ can help connect product, AI, and organizational change."
        ),
        "Share insight": (
            "As someone with direct experience in this space, I would like to share "
            "a few practical insights that may be useful to your team."
        ),
        "Request conversation": (
            f"I would welcome a short conversation about how a {role.lower()} "
            f"collaboration could create value for {company_name}."
        ),
        "Send introduction email": (
            f"I would appreciate an introduction to the right person at {company_name} "
            f"to explore a potential collaboration."
        ),
        "Send LinkedIn message": (
            f"I would welcome a brief conversation about opportunity creation in "
            f"{company['theme']} at {company_name}."
        ),
        "Do nothing yet": (
            "I am continuing research before outreach, but wanted to note this "
            "opportunity for future follow-up."
        ),
    }
    body_action = action_lines.get(
        action,
        f"I would welcome a conversation about how I might contribute as "
        f"{role}.",
    )
    subject = f"Opportunity to explore {role} with {company_name}"
    if contact:
        subject = f"{contact['name']} — opportunity to explore {role} with {company_name}"
    body = (
        f"{greeting}\n\n"
        f"{opener}\n\n"
        f"{body_action}\n\n"
        f"My background spans {', '.join(profile['capabilities'][:4]).lower()}, "
        f"and I am especially interested in founder-led environments where "
        f"multipotentialite operators can connect ideas, products, and systems.\n\n"
        f"Would you be open to a short conversation?\n\n"
        f"Best,\n{profile['name']}"
    )
    return subject, body


def generate_linkedin_draft(
    company: dict[str, Any],
    action: str,
    profile: dict[str, Any],
    report: dict[str, Any] | None,
    contact: dict[str, Any] | None = None,
) -> str:
    _, email_body = generate_email_draft(company, action, profile, report, contact)
    paragraphs = [part.strip() for part in email_body.split("\n\n") if part.strip()]
    compact = " ".join(paragraphs[:3])
    if len(compact) > 520:
        compact = compact[:517] + "..."
    return compact


def build_action_record(
    company: dict[str, Any],
    profile: dict[str, Any],
    learning_state: dict[str, Any],
) -> dict[str, Any]:
    patterns = load_action_patterns()
    report = None
    if intelligence_status(company["company"])["exists"]:
        report = get_current_report(load_company_intelligence(company["company"]))

    recommended_action = choose_recommended_action(
        company, learning_state, patterns, report
    )
    confidence = calculate_confidence(
        company, recommended_action, report, learning_state, patterns
    )
    why_recommended = build_why_recommended(
        company, recommended_action, report, learning_state, patterns, confidence
    )
    opportunity_summary = build_opportunity_summary(company, report)
    contact_recs = get_contact_recommendations(
        company["company"], recommended_action
    )
    target_contact = contact_summary(contact_recs["primary"])
    if target_contact:
        why_recommended.append(
            f"Primary outreach contact: {target_contact['name']} "
            f"({target_contact['title']})."
        )
    timestamp = now_iso()
    action_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"
    email_subject, email_body = generate_email_draft(
        company, recommended_action, profile, report, target_contact
    )
    linkedin_body = generate_linkedin_draft(
        company, recommended_action, profile, report, target_contact
    )
    recipient_email = (target_contact or {}).get("email", "")

    return {
        "action_id": action_id,
        "opportunity_summary": opportunity_summary,
        "recommended_action": recommended_action,
        "confidence_score": confidence,
        "why_recommended": why_recommended,
        "target_contact": target_contact,
        "theme": company["theme"],
        "country": company["country"],
        "suggested_role": company["suggested_role"],
        "status": "Suggested",
        "status_history": [
            {
                "status": "Suggested",
                "timestamp": timestamp,
                "note": "AJOS generated this action recommendation.",
            }
        ],
        "drafts": {
            "email": email_draft_payload(
                to=recipient_email,
                subject=email_subject,
                body=email_body,
                timestamp=timestamp,
            ),
            "linkedin": {
                "body": linkedin_body,
                "updated_at": timestamp,
            },
        },
        "generated_at": timestamp,
        "updated_at": timestamp,
    }


def enrich_action_with_contact(
    entity: dict[str, Any],
    action: dict[str, Any],
    company: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    if action.get("target_contact"):
        return action
    contact_recs = get_contact_recommendations(
        entity["entity_id"], action.get("recommended_action")
    )
    target_contact = contact_summary(contact_recs["primary"])
    if not target_contact:
        return action

    report = None
    if intelligence_status(company["company"])["exists"]:
        report = get_current_report(load_company_intelligence(company["company"]))

    timestamp = now_iso()
    email_subject, email_body = generate_email_draft(
        company,
        action["recommended_action"],
        profile,
        report,
        target_contact,
    )
    linkedin_body = generate_linkedin_draft(
        company,
        action["recommended_action"],
        profile,
        report,
        target_contact,
    )
    action["target_contact"] = target_contact
    previous_to = action.get("drafts", {}).get("email", {}).get("to", "")
    action["drafts"] = {
        "email": email_draft_payload(
            to=(target_contact or {}).get("email", previous_to),
            subject=email_subject,
            body=email_body,
            timestamp=timestamp,
        ),
        "linkedin": {
            "body": linkedin_body,
            "updated_at": timestamp,
        },
    }
    action["updated_at"] = timestamp
    save_entity_actions(entity)
    return action


def ensure_recommendation(
    company: dict[str, Any],
    profile: dict[str, Any],
    learning_state: dict[str, Any],
) -> dict[str, Any]:
    entity = load_entity_actions(company["company"])
    active = get_active_action(entity)
    if active:
        return enrich_action_with_contact(entity, active, company, profile)
    action = build_action_record(company, profile, learning_state)
    entity["actions"].append(action)
    save_entity_actions(entity)
    return action


def refresh_recommendation(
    company: dict[str, Any],
    profile: dict[str, Any],
    learning_state: dict[str, Any],
) -> dict[str, Any]:
    entity = load_entity_actions(company["company"])
    active = get_active_action(entity)
    if active and active["status"] == "Suggested":
        entity["actions"].remove(active)
    action = build_action_record(company, profile, learning_state)
    entity["actions"].append(action)
    save_entity_actions(entity)
    return action


def update_action_drafts(
    entity_id: str,
    action_id: str,
    *,
    email_to: str,
    email_subject: str,
    email_body: str,
    linkedin_body: str,
) -> dict[str, Any]:
    entity = load_entity_actions(entity_id)
    action = _find_action(entity, action_id)
    timestamp = now_iso()
    action["drafts"]["email"] = email_draft_payload(
        to=email_to,
        subject=email_subject,
        body=email_body,
        timestamp=timestamp,
    )
    action["drafts"]["linkedin"] = {
        "body": linkedin_body.strip(),
        "updated_at": timestamp,
    }
    action["updated_at"] = timestamp
    if action["status"] == "Suggested":
        _append_status(action, "Drafted", "Outreach drafts saved for review.")
    save_entity_actions(entity)
    rebuild_action_patterns()
    return action


def update_action_status(
    entity_id: str,
    action_id: str,
    status: str,
    note: str = "",
) -> dict[str, Any]:
    if status not in ACTION_STATUSES:
        raise ValueError(f"Invalid action status: {status}")
    entity = load_entity_actions(entity_id)
    action = _find_action(entity, action_id)
    _append_status(action, status, note or f"Status updated to {status}.")
    save_entity_actions(entity)
    rebuild_action_patterns()
    return action


def _find_action(entity: dict[str, Any], action_id: str) -> dict[str, Any]:
    for action in entity["actions"]:
        if action["action_id"] == action_id:
            return action
    raise ValueError(f"Action not found: {action_id}")


def _append_status(action: dict[str, Any], status: str, note: str) -> None:
    action["status"] = status
    action["updated_at"] = now_iso()
    action.setdefault("status_history", []).append(
        {
            "status": status,
            "timestamp": action["updated_at"],
            "note": note,
        }
    )


def rebuild_action_patterns() -> dict[str, Any]:
    patterns = default_patterns()
    if not COMPANIES_ACTIONS_DIR.exists():
        save_action_patterns(patterns)
        return patterns

    theme_action_counts: dict[str, Counter] = defaultdict(Counter)
    action_type_outcomes: dict[str, Counter] = defaultdict(Counter)
    channel_counts: Counter = Counter()
    successful_themes: Counter = Counter()

    for path in COMPANIES_ACTIONS_DIR.glob("*.json"):
        entity = load_json(path, default_entity_actions(""))
        for action in entity.get("actions", []):
            theme = action.get("theme", "Unknown")
            action_type = action.get("recommended_action", "Unknown")
            for event in action.get("status_history", []):
                weight = STATUS_SIGNAL_WEIGHTS.get(event["status"], 0)
                if weight <= 0:
                    continue
                theme_action_counts[theme][action_type] += weight
                action_type_outcomes[action_type][event["status"]] += 1
                if event["status"] in {"Sent", "Replied", "Meeting Scheduled", "Opportunity Created"}:
                    if "LinkedIn" in action_type:
                        channel_counts["LinkedIn"] += weight
                    if "email" in action_type.lower() or "introduction" in action_type.lower():
                        channel_counts["Email"] += weight
                if event["status"] in {"Meeting Scheduled", "Opportunity Created"}:
                    successful_themes[theme] += weight

    patterns["theme_action_counts"] = {
        theme: dict(counter) for theme, counter in theme_action_counts.items()
    }
    patterns["action_type_outcomes"] = {
        action_type: dict(counter)
        for action_type, counter in action_type_outcomes.items()
    }
    patterns["channel_counts"] = dict(channel_counts)
    patterns["successful_themes"] = dict(successful_themes)
    save_action_patterns(patterns)
    return patterns


def get_action_signals_for_memory() -> list[dict[str, Any]]:
    signals = []
    if not COMPANIES_ACTIONS_DIR.exists():
        return signals
    for path in COMPANIES_ACTIONS_DIR.glob("*.json"):
        entity = load_json(path, default_entity_actions(""))
        for action in entity.get("actions", []):
            for event in action.get("status_history", []):
                weight = STATUS_SIGNAL_WEIGHTS.get(event["status"], 0)
                if weight == 0:
                    continue
                signals.append(
                    {
                        "entity_id": entity.get("entity_id", ""),
                        "theme": action.get("theme", ""),
                        "recommended_action": action.get("recommended_action", ""),
                        "status": event["status"],
                        "weight": weight,
                        "timestamp": event.get("timestamp", ""),
                        "note": event.get("note", ""),
                    }
                )
    return signals


def get_action_pattern_adjustment(
    company: dict[str, Any], patterns: dict[str, Any] | None = None
) -> tuple[int, list[str]]:
    patterns = patterns or load_action_patterns()
    reasons = []
    score = 0

    pattern_action, boost = pattern_action_boost(company["theme"], patterns)
    if pattern_action:
        score += min(8, boost // 2)
        reasons.append(
            f"Action history in {company['theme']} favors '{pattern_action}' (+{min(8, boost // 2)})"
        )

    theme_success = patterns.get("successful_themes", {}).get(company["theme"], 0)
    if theme_success:
        addition = min(10, theme_success)
        score += addition
        reasons.append(
            f"Prior meetings or opportunities in {company['theme']} (+{addition})"
        )

    return min(12, score), reasons


def map_action_status_to_learning_outcome(status: str) -> str | None:
    mapping = {
        "Sent": "Reached Out",
        "Replied": "Conversation Started",
        "Meeting Scheduled": "Ongoing Discussion",
        "Opportunity Created": "Opportunity Created",
        "Closed": "Not Pursued",
    }
    return mapping.get(status)


def get_all_action_history(entity_id: str) -> list[dict[str, Any]]:
    entity = load_entity_actions(entity_id)
    return list(reversed(entity.get("actions", [])))
