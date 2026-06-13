import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from action_engine import enrich_action_with_contact, get_active_action, load_entity_actions, save_entity_actions
from company_intelligence import company_to_slug, save_json
from contact_discovery import (
    load_company_contacts,
    save_company_contacts,
    validate_contact,
    validate_entity,
)
from discovery_engine import website_host
from hunter_client import HunterClientError, HunterResult, domain_search
from learning import get_interested_companies, load_state


CONTACT_DISCOVERY_DIR = Path(__file__).parent / "data" / "contact_discovery"
CONFIG_PATH = CONTACT_DISCOVERY_DIR / "config.json"
RUNS_PATH = CONTACT_DISCOVERY_DIR / "runs.json"
COMPANIES_PATH = Path(__file__).parent / "data" / "companies.csv"
PROFILE_PATH = Path(__file__).parent / "data" / "ankit_profile.json"

GENERIC_EMAIL_PREFIXES = ("info@", "hello@", "support@", "contact@", "sales@", "admin@")

TITLE_ROLE_RULES: list[tuple[tuple[str, ...], tuple[str, ...], int]] = [
    (("founder", "co-founder", "cofounder"), ("founder",), 96),
    (("chief executive", " ceo", "ceo ", "ceo&"), ("founder", "ceo"), 95),
    (("head of product", "vp product", "chief product"), ("head_of_product",), 90),
    (("head of innovation", "innovation director", "chief innovation"), ("head_of_innovation",), 88),
    (("head of partnership", "vp partnership"), ("head_of_partnerships",), 85),
    (("head of growth", "vp growth"), ("head_of_growth",), 83),
    (("head of education", "creator success"), ("head_of_education",), 82),
    (("president", "managing director", "general manager"), ("ceo",), 84),
]

VAGUE_NAME_PATTERN = re.compile(
    r"\b(contact|leadership|lead)\b",
    re.IGNORECASE,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def default_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "provider": "hunter",
        "max_companies_per_run": 2,
        "max_contacts_per_company": 5,
        "max_credits_per_run": 15,
        "allow_generic_emails": False,
        "updated_at": now_iso(),
    }


def validate_config(config: dict[str, Any]) -> None:
    required = (
        "enabled",
        "provider",
        "max_companies_per_run",
        "max_contacts_per_company",
        "max_credits_per_run",
        "allow_generic_emails",
    )
    for field in required:
        if field not in config:
            raise ValueError(f"Contact discovery config missing required field: {field}")
    if config["provider"] != "hunter":
        raise ValueError("Only provider 'hunter' is supported in V1.")
    for int_field in ("max_companies_per_run", "max_contacts_per_company", "max_credits_per_run"):
        value = config[int_field]
        if not isinstance(value, int) or value < 0 or value > 25:
            raise ValueError(f"config.{int_field} must be an integer from 0 to 25.")


def load_config() -> dict[str, Any]:
    stored = load_json(CONFIG_PATH, default_config())
    merged = default_config()
    merged.update(stored)
    validate_config(merged)
    return merged


def load_companies() -> list[dict[str, Any]]:
    with COMPANIES_PATH.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def load_profile() -> dict[str, Any]:
    return load_json(PROFILE_PATH, {})


def company_row(companies: list[dict[str, Any]], company_name: str) -> dict[str, Any] | None:
    for row in companies:
        if row["company"] == company_name:
            return row
    return None


def is_generic_email(email: str, *, allow_generic: bool) -> bool:
    if allow_generic:
        return False
    lowered = email.strip().lower()
    return any(lowered.startswith(prefix) for prefix in GENERIC_EMAIL_PREFIXES)


def infer_role_tags(title: str) -> list[str]:
    lowered = f" {title.lower()} "
    for keywords, tags, _score in TITLE_ROLE_RULES:
        if any(keyword in lowered for keyword in keywords):
            return list(tags)
    return ["head_of_product"]


def title_priority(title: str) -> int:
    lowered = f" {title.lower()} "
    best = 0
    for keywords, _tags, score in TITLE_ROLE_RULES:
        if any(keyword in lowered for keyword in keywords):
            best = max(best, score)
    return best


def display_name(result: HunterResult) -> str | None:
    parts = [part for part in (result.first_name, result.last_name) if part]
    if len(parts) >= 2:
        return " ".join(parts)
    if result.email:
        local = result.email.split("@", 1)[0]
        cleaned = local.replace(".", " ").replace("_", " ").replace("-", " ")
        tokens = [token for token in cleaned.split() if token.isalpha()]
        if len(tokens) >= 2:
            return " ".join(token.title() for token in tokens[:3])
    return None


def contact_id_for(company_slug: str, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{company_slug}-{slug}"[:80]


def why_they_matter(title: str, company_name: str) -> str:
    return (
        f"{title} — key decision-maker at {company_name}; "
        "outreach on product, partnerships, or advisory fit."
    )


def hunter_result_to_contact(
    result: HunterResult,
    *,
    company_name: str,
    website: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    if not result.email or is_generic_email(result.email, allow_generic=config["allow_generic_emails"]):
        return None
    name = display_name(result)
    if not name or VAGUE_NAME_PATTERN.search(name):
        return None
    title = (result.title or "Leadership").strip()
    role_tags = infer_role_tags(title)
    priority = min(100, title_priority(title) + (4 if "founder" in role_tags else 0))
    slug = company_to_slug(company_name)
    contact: dict[str, Any] = {
        "contact_id": contact_id_for(slug, name),
        "name": name,
        "title": title,
        "why_they_matter": why_they_matter(title, company_name),
        "priority_score": priority or 80,
        "source_url": website or f"https://{result.email.split('@')[-1]}",
        "role_tags": role_tags,
        "email": result.email,
        "email_status": result.email_status or "unknown",
        "email_source": "hunter",
        "email_source_url": result.linkedin_url or website,
        "email_found_at": now_iso(),
    }
    validate_contact(contact)
    return contact


def build_queue(companies: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    interested = get_interested_companies(companies, state)
    queue: list[dict[str, Any]] = []
    for company in interested:
        entity = load_company_contacts(company["company"])
        if entity is None or not entity.get("contacts"):
            queue.append(
                {
                    "company": company["company"],
                    "website": company.get("website", ""),
                    "domain": website_host(company.get("website", "")),
                    "contacts_file": entity is not None,
                    "contact_count": len(entity["contacts"]) if entity else 0,
                    "reason": "missing contacts file" if entity is None else "empty contacts",
                }
            )
    return queue


def sync_company_actions(company_name: str, profile: dict[str, Any], companies: list[dict[str, Any]]) -> None:
    row = company_row(companies, company_name)
    if row is None:
        return
    entity = load_entity_actions(company_name)
    active = get_active_action(entity)
    if not active:
        return
    enrich_action_with_contact(entity, active, row, profile)
    save_entity_actions(entity)


def add_contacts(payload: dict[str, Any]) -> dict[str, Any]:
    entity_id = payload["entity_id"].strip()
    contacts = payload.get("contacts") or []
    if not contacts:
        raise ValueError("contacts list must not be empty")

    existing = load_company_contacts(entity_id)
    entity = existing or {
        "entity_type": "company",
        "entity_id": entity_id,
        "contacts": [],
    }
    known_ids = {contact["contact_id"] for contact in entity["contacts"]}
    added: list[str] = []
    for contact in contacts:
        validate_contact(contact)
        if contact["contact_id"] in known_ids:
            continue
        entity["contacts"].append(contact)
        known_ids.add(contact["contact_id"])
        added.append(contact["contact_id"])

    validate_entity(entity)
    save_company_contacts(entity)
    profile = load_profile()
    companies = load_companies()
    sync_company_actions(entity_id, profile, companies)
    return {"entity_id": entity_id, "added": added, "contact_count": len(entity["contacts"])}


def bootstrap_company(
    *,
    company_name: str,
    domain: str,
    website: str,
    config: dict[str, Any],
    credits_remaining: int,
) -> tuple[dict[str, Any], int]:
    company_result = {
        "company": company_name,
        "contacts_added": [],
        "skipped": [],
        "credits_used": 0,
    }
    if credits_remaining <= 0:
        company_result["skipped"].append({"reason": "credit cap"})
        return company_result, 0

    limit = min(config["max_contacts_per_company"], credits_remaining, 10)
    try:
        results = domain_search(domain=domain, limit=limit)
    except HunterClientError as error:
        company_result["skipped"].append({"reason": str(error)})
        return company_result, 0

    ranked = sorted(results, key=lambda item: title_priority(item.title or ""), reverse=True)
    contacts: list[dict[str, Any]] = []
    credits_used = 0
    seen_emails: set[str] = set()

    for result in ranked:
        if len(contacts) >= config["max_contacts_per_company"]:
            break
        if credits_used >= credits_remaining:
            break
        email_key = (result.email or "").lower()
        if not email_key or email_key in seen_emails:
            continue
        contact = hunter_result_to_contact(
            result,
            company_name=company_name,
            website=website,
            config=config,
        )
        if contact is None:
            company_result["skipped"].append(
                {"email": result.email, "reason": "generic or incomplete name"}
            )
            continue
        if any(existing["contact_id"] == contact["contact_id"] for existing in contacts):
            continue
        contacts.append(contact)
        seen_emails.add(email_key)
        credits_used += result.credits_used

    if not contacts:
        company_result["skipped"].append({"reason": "no acceptable contacts from domain search"})
        return company_result, credits_used

    entity = load_company_contacts(company_name)
    if entity is None:
        entity = {
            "entity_type": "company",
            "entity_id": company_name,
            "contacts": [],
        }
    known_ids = {contact["contact_id"] for contact in entity["contacts"]}
    for contact in contacts:
        if contact["contact_id"] in known_ids:
            continue
        entity["contacts"].append(contact)
        company_result["contacts_added"].append(
            {
                "contact_id": contact["contact_id"],
                "name": contact["name"],
                "email": contact.get("email"),
            }
        )

    validate_entity(entity)
    save_company_contacts(entity)
    profile = load_profile()
    companies = load_companies()
    sync_company_actions(company_name, profile, companies)
    company_result["credits_used"] = credits_used
    return company_result, credits_used


def run_contact_discovery(
    *,
    max_companies: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    config = load_config()
    if not config["enabled"]:
        return {"processed": 0, "contacts_added": 0, "credits_used": 0, "errors": ["disabled"]}

    companies = load_companies()
    state = load_state()
    queue = build_queue(companies, state)
    limit = max_companies if max_companies is not None else config["max_companies_per_run"]
    queue = queue[:limit]

    summary = {
        "processed": 0,
        "contacts_added": 0,
        "credits_used": 0,
        "dry_run": dry_run,
        "results": [],
        "errors": [],
    }
    credits_left = config["max_credits_per_run"]

    for item in queue:
        if credits_left <= 0:
            summary["errors"].append("Stopped: max_credits_per_run reached")
            break

        company_name = item["company"]
        domain = item["domain"]
        website = item.get("website", "")
        if not domain:
            summary["errors"].append(f"{company_name}: missing website domain")
            continue

        if dry_run:
            summary["results"].append(
                {
                    "company": company_name,
                    "domain": domain,
                    "dry_run": True,
                    "would_bootstrap": True,
                }
            )
            summary["processed"] += 1
            continue

        company_result, used = bootstrap_company(
            company_name=company_name,
            domain=domain,
            website=website,
            config=config,
            credits_remaining=credits_left,
        )
        credits_left -= used
        summary["credits_used"] += used
        if company_result["contacts_added"]:
            summary["contacts_added"] += len(company_result["contacts_added"])
            summary["processed"] += 1
        summary["results"].append(company_result)

    return summary


def record_run(
    *,
    processed: int,
    contacts_added: int,
    credits_used: int,
    errors: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    store = load_json(RUNS_PATH, {"runs": []})
    entry = {
        "timestamp": now_iso(),
        "processed": processed,
        "contacts_added": contacts_added,
        "credits_used": credits_used,
        "dry_run": dry_run,
        "errors": errors or [],
    }
    store.setdefault("runs", []).append(entry)
    save_json(RUNS_PATH, store)
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="AJOS contact discovery utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("show-config", help="Print contact discovery config JSON")
    subparsers.add_parser("list-queue", help="List interested companies missing contacts")

    add_parser = subparsers.add_parser("add", help="Add researched contacts from JSON")
    add_parser.add_argument("--json", required=True, help="Entity JSON string or @file path")

    run_parser = subparsers.add_parser("run", help="Bootstrap contacts via Hunter domain search")
    run_parser.add_argument("--max", type=int, default=None, help="Max companies this run")
    run_parser.add_argument("--dry-run", action="store_true", help="List targets without API calls")

    record_parser = subparsers.add_parser("record-run", help="Record a contact discovery run")
    record_parser.add_argument("--processed", type=int, default=0)
    record_parser.add_argument("--contacts-added", type=int, default=0)
    record_parser.add_argument("--credits-used", type=int, default=0)
    record_parser.add_argument("--dry-run", action="store_true")
    record_parser.add_argument("--errors", nargs="*", default=[])

    args = parser.parse_args()

    if args.command == "show-config":
        print(json.dumps(load_config(), indent=2))
        return

    if args.command == "list-queue":
        companies = load_companies()
        state = load_state()
        print(json.dumps(build_queue(companies, state), indent=2))
        return

    if args.command == "add":
        payload = args.json
        if payload.startswith("@"):
            payload = Path(payload[1:]).read_text(encoding="utf-8")
        created = add_contacts(json.loads(payload))
        print(json.dumps(created, indent=2))
        return

    if args.command == "run":
        summary = run_contact_discovery(max_companies=args.max, dry_run=args.dry_run)
        print(json.dumps(summary, indent=2))
        if not args.dry_run:
            record_run(
                processed=summary["processed"],
                contacts_added=summary["contacts_added"],
                credits_used=summary["credits_used"],
                errors=summary["errors"],
            )
        return

    if args.command == "record-run":
        entry = record_run(
            processed=args.processed,
            contacts_added=args.contacts_added,
            credits_used=args.credits_used,
            errors=args.errors,
            dry_run=args.dry_run,
        )
        print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
