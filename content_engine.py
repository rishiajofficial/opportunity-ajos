import argparse
import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from company_intelligence import (
    get_current_report,
    load_company_intelligence,
    load_json,
    save_json,
)


BASE_DIR = Path(__file__).parent
CONTENT_DIR = BASE_DIR / "data" / "content"
CONFIG_PATH = CONTENT_DIR / "config.json"
QUEUE_PATH = CONTENT_DIR / "refinement_queue.json"
RUNS_PATH = CONTENT_DIR / "runs.json"
COMPANIES_PATH = BASE_DIR / "data" / "companies.csv"
LEARNING_STATE_PATH = BASE_DIR / "data" / "learning" / "state.json"

REFINED_FIELDS = ("description", "why_fit", "problems_to_solve")
COMPANY_FIELDNAMES = [
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
]
PENDING_FEEDBACK_RATINGS = {"Didn't understand", "Did not understand"}
PENDING_REASON_PHRASES = (
    "didn't understand",
    "did not understand",
    "dont understand",
    "don't understand",
    "need to understand",
    "needs more context",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "max_companies_per_run": 3,
        "updated_at": now_iso(),
    }


def default_queue() -> dict[str, Any]:
    return {"items": []}


def default_runs() -> dict[str, Any]:
    return {"runs": []}


def validate_config(config: dict[str, Any]) -> None:
    if not isinstance(config.get("enabled"), bool):
        raise ValueError("config.enabled must be a boolean.")
    max_companies = config.get("max_companies_per_run")
    if not isinstance(max_companies, int) or max_companies < 0 or max_companies > 10:
        raise ValueError("config.max_companies_per_run must be an integer from 0 to 10.")


def load_config() -> dict[str, Any]:
    config = default_config()
    config.update(load_json(CONFIG_PATH, {}))
    validate_config(config)
    return config


def load_queue(*, sync_feedback: bool = False) -> dict[str, Any]:
    queue = load_json(QUEUE_PATH, default_queue())
    queue.setdefault("items", [])
    if sync_feedback:
        queue = sync_queue_from_feedback(queue)
        save_queue(queue)
    return queue


def save_queue(queue: dict[str, Any]) -> dict[str, Any]:
    queue.setdefault("items", [])
    save_json(QUEUE_PATH, queue)
    return queue


def load_runs() -> dict[str, Any]:
    runs = load_json(RUNS_PATH, default_runs())
    runs.setdefault("runs", [])
    return runs


def save_runs(runs: dict[str, Any]) -> dict[str, Any]:
    runs.setdefault("runs", [])
    save_json(RUNS_PATH, runs)
    return runs


def load_companies() -> tuple[list[dict[str, str]], list[str]]:
    with COMPANIES_PATH.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = list(reader.fieldnames or [])
        missing = set(COMPANY_FIELDNAMES).difference(fieldnames)
        if missing:
            raise ValueError(f"Missing company CSV fields: {', '.join(sorted(missing))}")
        return list(reader), fieldnames


def save_companies(rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with COMPANIES_PATH.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def find_company(rows: list[dict[str, str]], company_name: str) -> dict[str, str]:
    target = company_name.strip().lower()
    for row in rows:
        if row["company"].strip().lower() == target:
            return row
    raise ValueError(f"Company not found: {company_name}")


def latest_feedback_by_company() -> dict[str, dict[str, Any]]:
    state = load_json(LEARNING_STATE_PATH, {})
    latest = {}
    for feedback in state.get("feedback", []):
        company = str(feedback.get("company", "")).strip()
        if company:
            latest[company.lower()] = feedback
    return latest


def feedback_needs_refinement(feedback: dict[str, Any]) -> bool:
    rating = str(feedback.get("rating", "")).strip()
    reason = str(feedback.get("reason", "")).strip().lower()
    return rating in PENDING_FEEDBACK_RATINGS or any(
        phrase in reason for phrase in PENDING_REASON_PHRASES
    )


def sync_queue_from_feedback(queue: dict[str, Any]) -> dict[str, Any]:
    known_pending = {
        item["company"].strip().lower()
        for item in queue.get("items", [])
        if item.get("status") == "pending"
    }
    known_done = {
        item["company"].strip().lower()
        for item in queue.get("items", [])
        if item.get("status") == "refined"
    }
    rows, _fieldnames = load_companies()
    company_names = {row["company"].strip().lower(): row["company"] for row in rows}

    for company_key, feedback in latest_feedback_by_company().items():
        if company_key not in company_names:
            continue
        if company_key in known_pending or company_key in known_done:
            continue
        if not feedback_needs_refinement(feedback):
            continue
        queue["items"].append(
            {
                "queue_id": str(uuid.uuid4()),
                "company": company_names[company_key],
                "reason": str(feedback.get("reason", "")).strip(),
                "source": "learning_feedback",
                "status": "pending",
                "created_at": now_iso(),
            }
        )
    return queue


def pending_items() -> list[dict[str, Any]]:
    queue = load_queue(sync_feedback=True)
    return [item for item in queue["items"] if item.get("status") == "pending"]


def build_brief(company_name: str) -> dict[str, Any]:
    rows, _fieldnames = load_companies()
    company = find_company(rows, company_name)
    feedback = latest_feedback_by_company().get(company["company"].strip().lower())
    entity = load_company_intelligence(company["company"])
    report = get_current_report(entity) if entity else None
    return {
        "company": company,
        "latest_feedback": feedback,
        "intelligence_report": report,
    }


def load_json_argument(raw: str) -> dict[str, Any]:
    payload = raw
    if raw.startswith("@"):
        payload = Path(raw[1:]).read_text(encoding="utf-8")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Update payload must be a JSON object.")
    return data


def update_company_copy(company_name: str, copy: dict[str, Any]) -> dict[str, str]:
    missing = [field for field in REFINED_FIELDS if not str(copy.get(field, "")).strip()]
    if missing:
        raise ValueError(f"Copy payload missing refined fields: {', '.join(missing)}")

    rows, fieldnames = load_companies()
    company = find_company(rows, company_name)
    for field in REFINED_FIELDS:
        company[field] = str(copy[field]).strip()
    save_companies(rows, fieldnames)
    return company


def mark_refined(company_name: str) -> dict[str, Any]:
    queue = load_queue(sync_feedback=True)
    target = company_name.strip().lower()
    marked: dict[str, Any] | None = None
    for item in queue["items"]:
        if item.get("company", "").strip().lower() != target:
            continue
        if item.get("status") == "refined":
            marked = item
            continue
        item["status"] = "refined"
        item["refined_at"] = now_iso()
        marked = item

    if marked is None:
        rows, _fieldnames = load_companies()
        company = find_company(rows, company_name)
        marked = {
            "queue_id": str(uuid.uuid4()),
            "company": company["company"],
            "reason": "Manual generic-copy refinement",
            "source": "manual_generic_refinement",
            "status": "refined",
            "created_at": now_iso(),
            "refined_at": now_iso(),
        }
        queue["items"].append(marked)

    save_queue(queue)
    return marked


def record_run(refined_count: int, errors: list[str] | None = None) -> dict[str, Any]:
    runs = load_runs()
    entry = {
        "run_id": str(uuid.uuid4()),
        "completed_at": now_iso(),
        "refined_count": refined_count,
        "pending_remaining": len(pending_items()),
        "errors": errors or [],
    }
    runs["runs"].append(entry)
    save_runs(runs)
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="AJOS content refinement utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("show-config", help="Print content config JSON")
    subparsers.add_parser("list-pending", help="List pending content refinements")

    brief_parser = subparsers.add_parser("brief", help="Print company refinement brief")
    brief_parser.add_argument("--company", required=True)

    update_parser = subparsers.add_parser("update", help="Update review-facing copy")
    update_parser.add_argument("--company", required=True)
    update_parser.add_argument("--json", required=True, help="Copy JSON string or @file path")

    mark_parser = subparsers.add_parser("mark-refined", help="Mark company as refined")
    mark_parser.add_argument("--company", required=True)

    run_parser = subparsers.add_parser("record-run", help="Record a content run")
    run_parser.add_argument("--refined", type=int, required=True)
    run_parser.add_argument("--errors", nargs="*", default=[])

    args = parser.parse_args()

    if args.command == "show-config":
        print(json.dumps(load_config(), indent=2))
        return

    if args.command == "list-pending":
        print(json.dumps(pending_items(), indent=2))
        return

    if args.command == "brief":
        print(json.dumps(build_brief(args.company), indent=2))
        return

    if args.command == "update":
        updated = update_company_copy(args.company, load_json_argument(args.json))
        print(json.dumps(updated, indent=2))
        return

    if args.command == "mark-refined":
        print(json.dumps(mark_refined(args.company), indent=2))
        return

    if args.command == "record-run":
        print(json.dumps(record_run(args.refined, args.errors), indent=2))


if __name__ == "__main__":
    main()
