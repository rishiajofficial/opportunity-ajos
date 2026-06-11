import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


INTELLIGENCE_DIR = Path(__file__).parent / "data" / "intelligence" / "companies"
STALE_AFTER_DAYS = 90

REQUIRED_SECTION_IDS = (
    "what_they_do",
    "customers",
    "products_and_services",
    "business_model",
    "recent_developments",
    "hiring_patterns",
    "strategic_challenges",
    "value_for_aj",
    "potential_entry_points",
)

SECTION_TITLES = {
    "what_they_do": "What does this company do?",
    "customers": "Who are its customers?",
    "products_and_services": "What products or services does it offer?",
    "business_model": "What is its business model?",
    "recent_developments": "What recent developments matter?",
    "hiring_patterns": "What hiring patterns are visible?",
    "strategic_challenges": "What strategic challenges may exist?",
    "value_for_aj": "Why might AJ create value here?",
    "potential_entry_points": "Potential entry points",
}

VALID_KINDS = {"fact", "observation", "hypothesis"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def company_to_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = slug.replace("&", "and")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


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


def intelligence_path(company_name: str) -> Path:
    return INTELLIGENCE_DIR / f"{company_to_slug(company_name)}.json"


def list_intelligence_companies() -> list[str]:
    if not INTELLIGENCE_DIR.exists():
        return []
    return sorted(
        path.stem
        for path in INTELLIGENCE_DIR.glob("*.json")
        if path.is_file()
    )


def validate_source(source: dict[str, Any]) -> None:
    if not source.get("url"):
        raise ValueError("Each source must include a url.")
    if not source.get("label"):
        raise ValueError("Each source must include a label.")


def validate_section(section: dict[str, Any]) -> None:
    section_id = section.get("id")
    if section_id not in REQUIRED_SECTION_IDS:
        raise ValueError(f"Unknown intelligence section id: {section_id}")
    if section.get("kind") not in VALID_KINDS:
        raise ValueError(f"Section {section_id} has invalid kind.")
    content = section.get("content", "").strip()
    items = section.get("items", [])
    if not content and not items:
        raise ValueError(f"Section {section_id} must include content or items.")
    if items and not isinstance(items, list):
        raise ValueError(f"Section {section_id} items must be a list.")


def validate_report(report: dict[str, Any]) -> None:
    required_fields = ("report_id", "researched_at", "refresh_method", "sections")
    for field in required_fields:
        if field not in report:
            raise ValueError(f"Intelligence report missing required field: {field}")

    section_ids = [section["id"] for section in report["sections"]]
    missing_sections = set(REQUIRED_SECTION_IDS) - set(section_ids)
    if missing_sections:
        missing = ", ".join(sorted(missing_sections))
        raise ValueError(f"Intelligence report missing sections: {missing}")

    for section in report["sections"]:
        validate_section(section)

    for source in report.get("sources", []):
        validate_source(source)


def validate_entity(entity: dict[str, Any]) -> None:
    if entity.get("entity_type") != "company":
        raise ValueError("Only company intelligence is supported in V1.")
    if not entity.get("entity_id"):
        raise ValueError("Intelligence entity must include entity_id.")
    if not entity.get("reports"):
        raise ValueError("Intelligence entity must include at least one report.")
    if not entity.get("current_report_id"):
        raise ValueError("Intelligence entity must include current_report_id.")

    report_ids = {report["report_id"] for report in entity["reports"]}
    if entity["current_report_id"] not in report_ids:
        raise ValueError("current_report_id does not match any report.")

    for report in entity["reports"]:
        validate_report(report)


def load_company_intelligence(company_name: str) -> dict[str, Any] | None:
    path = intelligence_path(company_name)
    if not path.exists():
        return None

    entity = load_json(path, None)
    if entity is None:
        return None

    validate_entity(entity)
    if entity["entity_id"] != company_name:
        raise ValueError(
            f"Intelligence entity_id '{entity['entity_id']}' does not match "
            f"company '{company_name}'."
        )
    return entity


def get_current_report(entity: dict[str, Any]) -> dict[str, Any]:
    current_report_id = entity["current_report_id"]
    for report in entity["reports"]:
        if report["report_id"] == current_report_id:
            return report
    raise ValueError(f"Report not found for id: {current_report_id}")


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def intelligence_status(company_name: str) -> dict[str, Any]:
    entity = load_company_intelligence(company_name)
    if entity is None:
        return {
            "exists": False,
            "company": company_name,
            "researched_at": None,
            "is_stale": False,
            "refresh_method": None,
        }

    report = get_current_report(entity)
    researched_at = report["researched_at"]
    researched_time = parse_timestamp(researched_at)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_AFTER_DAYS)
    return {
        "exists": True,
        "company": company_name,
        "researched_at": researched_at,
        "is_stale": researched_time < stale_cutoff,
        "refresh_method": report.get("refresh_method"),
    }


def save_company_report(
    company_name: str,
    report: dict[str, Any],
    *,
    website: str = "",
) -> dict[str, Any]:
    validate_report(report)
    path = intelligence_path(company_name)
    entity = load_json(
        path,
        {
            "entity_type": "company",
            "entity_id": company_name,
            "website": website,
            "current_report_id": report["report_id"],
            "reports": [],
        },
    )

    entity["entity_type"] = "company"
    entity["entity_id"] = company_name
    if website:
        entity["website"] = website
    entity["reports"].append(report)
    entity["current_report_id"] = report["report_id"]
    validate_entity(entity)
    save_json(path, entity)
    return entity
