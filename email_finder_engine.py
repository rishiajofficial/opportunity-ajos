import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from action_engine import enrich_action_with_contact, get_active_action, load_entity_actions, save_entity_actions
from apollo_client import ApolloClientError, ApolloResult, match_by_id, match_person, search_people
from company_intelligence import save_json
from contact_discovery import load_company_contacts, save_company_contacts, validate_entity
from discovery_engine import website_host
from hunter_client import HunterClientError, HunterResult, domain_search as hunter_domain_search
from hunter_client import email_finder as hunter_email_finder
from learning import get_interested_companies, load_state


EMAIL_FINDER_DIR = Path(__file__).parent / "data" / "email_finder"
CONFIG_PATH = EMAIL_FINDER_DIR / "config.json"
RUNS_PATH = EMAIL_FINDER_DIR / "runs.json"
COMPANIES_PATH = Path(__file__).parent / "data" / "companies.csv"
PROFILE_PATH = Path(__file__).parent / "data" / "ankit_profile.json"

GENERIC_EMAIL_PREFIXES = ("info@", "hello@", "support@", "contact@", "sales@", "admin@")

ROLE_TAG_TITLES: dict[str, list[str]] = {
    "founder": ["Founder", "Co-Founder", "Co-founder"],
    "ceo": ["CEO", "Chief Executive Officer"],
    "head_of_product": ["Head of Product", "VP Product", "Chief Product Officer"],
    "head_of_innovation": ["Head of Innovation", "Innovation Director", "Chief Innovation Officer"],
    "head_of_partnerships": ["Head of Partnerships", "VP Partnerships"],
    "head_of_growth": ["Head of Growth", "VP Growth"],
    "head_of_education": ["Head of Education", "Head of Creator Success"],
}

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
        "max_companies_per_run": 3,
        "max_contacts_per_company": 2,
        "require_verified_email": False,
        "allow_generic_emails": False,
        "max_credits_per_run": 10,
        "updated_at": now_iso(),
    }


def validate_config(config: dict[str, Any]) -> None:
    required = (
        "enabled",
        "provider",
        "max_companies_per_run",
        "max_contacts_per_company",
        "require_verified_email",
        "allow_generic_emails",
        "max_credits_per_run",
    )
    for field in required:
        if field not in config:
            raise ValueError(f"Email finder config missing required field: {field}")
    if config["provider"] not in ("apollo", "hunter"):
        raise ValueError("config.provider must be 'apollo' or 'hunter'.")
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


def is_email_finder_enabled() -> bool:
    return bool(load_config()["enabled"])


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


def split_name(name: str) -> tuple[str, str] | None:
    cleaned = name.strip()
    if not cleaned or VAGUE_NAME_PATTERN.search(cleaned):
        return None
    parts = cleaned.split()
    if len(parts) < 2:
        return None
    return parts[0], " ".join(parts[1:])


def titles_for_contact(contact: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    if contact.get("title"):
        titles.append(contact["title"])
    for tag in contact.get("role_tags", []):
        titles.extend(ROLE_TAG_TITLES.get(tag, []))
    deduped: list[str] = []
    seen = set()
    for title in titles:
        key = title.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(title)
    return deduped[:8]


def is_generic_email(email: str, *, allow_generic: bool) -> bool:
    if allow_generic:
        return False
    lowered = email.strip().lower()
    return any(lowered.startswith(prefix) for prefix in GENERIC_EMAIL_PREFIXES)


def accept_result(result: ApolloResult | HunterResult, config: dict[str, Any]) -> bool:
    if not result.email:
        return False
    status = (result.email_status or "").lower()
    if status in ("unavailable", "invalid"):
        return False
    if config["require_verified_email"] and status not in ("verified", "valid"):
        return False
    if is_generic_email(result.email, allow_generic=config["allow_generic_emails"]):
        return False
    return True


def names_match(contact_name: str, first_name: str | None, last_name: str | None) -> bool:
    parsed = split_name(contact_name)
    if not parsed:
        return False
    contact_first, contact_last = parsed
    if not first_name:
        return False
    if first_name.lower() != contact_first.lower():
        return False
    if not last_name or last_name.endswith("***"):
        return True
    return last_name.split()[0].lower() == contact_last.split()[0].lower()


def find_via_search(
    *,
    contact: dict[str, Any],
    domain: str,
) -> ApolloResult | None:
    titles = titles_for_contact(contact)
    if not titles:
        return None
    candidates = [item for item in search_people(domain=domain, titles=titles) if item.has_email]
    for candidate in candidates:
        if names_match(contact["name"], candidate.first_name, candidate.last_name):
            return match_by_id(candidate.person_id)
    if len(candidates) == 1:
        return match_by_id(candidates[0].person_id)
    return None


def find_via_hunter_search(
    *,
    contact: dict[str, Any],
    domain: str,
) -> HunterResult | None:
    titles = titles_for_contact(contact)
    candidates = hunter_domain_search(domain=domain, limit=10)
    if titles:
        title_keys = {title.lower() for title in titles}
        filtered = [
            item
            for item in candidates
            if item.title and any(key in item.title.lower() for key in title_keys)
        ]
        if filtered:
            candidates = filtered
    for candidate in candidates:
        if names_match(contact["name"], candidate.first_name, candidate.last_name):
            return candidate
    if len(candidates) == 1:
        return candidates[0]
    return None


def find_email_for_contact_apollo(
    *,
    contact: dict[str, Any],
    company_name: str,
    domain: str,
    config: dict[str, Any],
) -> tuple[ApolloResult | None, str | None]:
    parsed = split_name(contact["name"])
    result: ApolloResult | None = None
    if parsed:
        first_name, last_name = parsed
        try:
            result = match_person(
                first_name=first_name,
                last_name=last_name,
                domain=domain,
                organization_name=company_name,
            )
        except ApolloClientError as error:
            return None, str(error)
        if accept_result(result, config):
            return result, None

    try:
        fallback = find_via_search(contact=contact, domain=domain)
    except ApolloClientError as error:
        return None, str(error)
    if fallback and accept_result(fallback, config):
        return fallback, None
    if result and result.email and not accept_result(result, config):
        return None, f"Rejected email for {contact['name']}: status={result.email_status}"
    return None, f"No acceptable email found for {contact['name']}"


def find_email_for_contact_hunter(
    *,
    contact: dict[str, Any],
    domain: str,
    config: dict[str, Any],
) -> tuple[HunterResult | None, str | None]:
    parsed = split_name(contact["name"])
    result: HunterResult | None = None
    if parsed:
        first_name, last_name = parsed
        try:
            result = hunter_email_finder(
                first_name=first_name,
                last_name=last_name,
                domain=domain,
            )
        except HunterClientError as error:
            return None, str(error)
        if accept_result(result, config):
            return result, None

    try:
        fallback = find_via_hunter_search(contact=contact, domain=domain)
    except HunterClientError as error:
        return None, str(error)
    if fallback and accept_result(fallback, config):
        return fallback, None
    if result and result.email and not accept_result(result, config):
        return None, f"Rejected email for {contact['name']}: status={result.email_status}"
    return None, f"No acceptable email found for {contact['name']}"


def find_email_for_contact(
    *,
    contact: dict[str, Any],
    company_name: str,
    domain: str,
    config: dict[str, Any],
) -> tuple[ApolloResult | HunterResult | None, str | None]:
    primary = config["provider"]
    secondary = "apollo" if primary == "hunter" else "hunter"

    for provider in (primary, secondary):
        try:
            if provider == "hunter":
                result, err = find_email_for_contact_hunter(
                    contact=contact, domain=domain, config=config
                )
            else:
                result, err = find_email_for_contact_apollo(
                    contact=contact,
                    company_name=company_name,
                    domain=domain,
                    config=config,
                )
            if result and result.email:
                return result, None
        except Exception as exc:
            err = str(exc)
            continue

    parsed = split_name(contact["name"])
    if not parsed and contact.get("title"):
        try:
            titles = titles_for_contact(contact)
            if config["provider"] == "hunter":
                from hunter_client import domain_search

                results = domain_search(domain=domain, limit=5)
                for item in results:
                    if titles and item.title:
                        if not any(t.lower() in item.title.lower() for t in titles):
                            continue
                    if item.email and accept_result(item, config):
                        return item, None
        except Exception:
            pass

    return None, f"No acceptable email found for {contact['name']}"


def apply_email_to_contact(
    contact: dict[str, Any],
    result: ApolloResult | HunterResult,
    *,
    provider: str,
) -> None:
    contact["email"] = result.email
    contact["email_status"] = result.email_status or "unknown"
    contact["email_source"] = provider
    contact["email_source_url"] = result.linkedin_url or contact.get("source_url", "")
    contact["email_found_at"] = now_iso()


def contacts_missing_email(entity: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    missing = [
        contact
        for contact in entity["contacts"]
        if not (contact.get("email") or "").strip()
    ]
    missing.sort(key=lambda item: item["priority_score"], reverse=True)
    return missing[:limit]


def build_queue(companies: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    config = load_config()
    interested = get_interested_companies(companies, state)
    queue: list[dict[str, Any]] = []
    for company in interested:
        entity = load_company_contacts(company["company"])
        if entity is None:
            queue.append(
                {
                    "company": company["company"],
                    "website": company.get("website", ""),
                    "domain": website_host(company.get("website", "")),
                    "contacts_file": False,
                    "missing_contacts": 0,
                    "contacts": [],
                }
            )
            continue
        missing = contacts_missing_email(
            entity, limit=config["max_contacts_per_company"]
        )
        if not missing:
            continue
        queue.append(
            {
                "company": company["company"],
                "website": company.get("website", ""),
                "domain": website_host(company.get("website", "")),
                "contacts_file": True,
                "missing_contacts": len(missing),
                "contacts": [
                    {
                        "contact_id": contact["contact_id"],
                        "name": contact["name"],
                        "title": contact["title"],
                        "priority_score": contact["priority_score"],
                    }
                    for contact in missing
                ],
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


def run_email_finder(
    *,
    max_companies: int | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    config = load_config()
    if not config["enabled"]:
        return {"processed": 0, "emails_found": 0, "credits_used": 0, "errors": ["disabled"]}

    companies = load_companies()
    state = load_state()
    profile = load_profile()
    queue = build_queue(companies, state)
    limit = max_companies if max_companies is not None else config["max_companies_per_run"]
    queue = queue[:limit]

    summary = {
        "processed": 0,
        "emails_found": 0,
        "credits_used": 0,
        "dry_run": dry_run,
        "results": [],
        "errors": [],
    }

    for item in queue:
        if summary["credits_used"] >= config["max_credits_per_run"]:
            summary["errors"].append("Stopped: max_credits_per_run reached")
            break

        company_name = item["company"]
        domain = item["domain"]
        if not domain:
            summary["errors"].append(f"{company_name}: missing website domain")
            continue
        if not item["contacts_file"]:
            summary["errors"].append(f"{company_name}: no contacts file")
            continue

        entity = load_company_contacts(company_name)
        if entity is None:
            continue

        company_result = {
            "company": company_name,
            "contacts_updated": [],
            "skipped": [],
        }
        missing = contacts_missing_email(
            entity, limit=config["max_contacts_per_company"]
        )

        for contact in missing:
            if summary["credits_used"] >= config["max_credits_per_run"]:
                company_result["skipped"].append(
                    {"contact_id": contact["contact_id"], "reason": "credit cap"}
                )
                break
            if contact.get("email") and not force:
                company_result["skipped"].append(
                    {"contact_id": contact["contact_id"], "reason": "already has email"}
                )
                continue

            try:
                result, error = find_email_for_contact(
                    contact=contact,
                    company_name=company_name,
                    domain=domain,
                    config=config,
                )
            except (ApolloClientError, HunterClientError) as error:
                summary["errors"].append(f"{company_name}/{contact['contact_id']}: {error}")
                break

            if result is None:
                company_result["skipped"].append(
                    {"contact_id": contact["contact_id"], "reason": error or "not found"}
                )
                continue

            summary["credits_used"] += result.credits_used
            if dry_run:
                company_result["contacts_updated"].append(
                    {
                        "contact_id": contact["contact_id"],
                        "email": result.email,
                        "dry_run": True,
                    }
                )
                summary["emails_found"] += 1
                continue

            apply_email_to_contact(contact, result, provider=config["provider"])
            company_result["contacts_updated"].append(
                {
                    "contact_id": contact["contact_id"],
                    "email": result.email,
                    "email_status": result.email_status,
                }
            )
            summary["emails_found"] += 1

        if company_result["contacts_updated"] and not dry_run:
            entity["updated_at"] = now_iso()
            validate_entity(entity)
            save_company_contacts(entity)
            sync_company_actions(company_name, profile, companies)

        if company_result["contacts_updated"] or company_result["skipped"]:
            summary["processed"] += 1
            summary["results"].append(company_result)

    return summary


def record_run(
    *,
    processed: int,
    emails_found: int,
    credits_used: int,
    errors: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    store = load_json(RUNS_PATH, {"runs": []})
    entry = {
        "timestamp": now_iso(),
        "processed": processed,
        "emails_found": emails_found,
        "credits_used": credits_used,
        "dry_run": dry_run,
        "errors": errors or [],
    }
    store.setdefault("runs", []).append(entry)
    save_json(RUNS_PATH, store)
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="AJOS email finder utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("show-config", help="Print email finder config JSON")
    subparsers.add_parser("list-queue", help="List interested companies missing emails")

    run_parser = subparsers.add_parser("run", help="Find emails via configured provider (hunter or apollo)")
    run_parser.add_argument("--max", type=int, default=None, help="Max companies this run")
    run_parser.add_argument("--dry-run", action="store_true", help="Call API but do not write JSON")
    run_parser.add_argument("--force", action="store_true", help="Overwrite existing contact emails")

    record_parser = subparsers.add_parser("record-run", help="Record an email finder run")
    record_parser.add_argument("--processed", type=int, default=0)
    record_parser.add_argument("--emails-found", type=int, default=0)
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

    if args.command == "run":
        summary = run_email_finder(
            max_companies=args.max,
            dry_run=args.dry_run,
            force=args.force,
        )
        print(json.dumps(summary, indent=2))
        if not args.dry_run:
            record_run(
                processed=summary["processed"],
                emails_found=summary["emails_found"],
                credits_used=summary["credits_used"],
                errors=summary["errors"],
            )
        return

    if args.command == "record-run":
        entry = record_run(
            processed=args.processed,
            emails_found=args.emails_found,
            credits_used=args.credits_used,
            errors=args.errors,
            dry_run=args.dry_run,
        )
        print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
