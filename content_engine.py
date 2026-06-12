"""Content refinement utilities for AJOS — Hinglish copy aligned to Ankit's profile."""

from __future__ import annotations

import argparse
import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from company_intelligence import company_to_slug, load_json, save_json
from learning import UNCLEAR_RATING, load_state, record_feedback


CONTENT_DIR = Path(__file__).parent / "data" / "content"
QUEUE_PATH = CONTENT_DIR / "refinement_queue.json"
RUNS_PATH = CONTENT_DIR / "runs.json"
CONFIG_PATH = CONTENT_DIR / "config.json"
COMPANIES_PATH = Path(__file__).parent / "data" / "companies.csv"
PROFILE_PATH = Path(__file__).parent / "data" / "ankit_profile.json"
STATE_PATH = Path(__file__).parent / "data" / "learning" / "state.json"

COMPANY_FIELDS = (
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
COPY_FIELDS = ("description", "why_fit", "problems_to_solve", "suggested_role")
VALID_STATUSES = {"pending", "refined", "skipped"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_queue_store() -> dict[str, Any]:
    return {"items": []}


def default_runs_store() -> dict[str, Any]:
    return {"runs": []}


def default_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "max_companies_per_run": 3,
        "requeue_after_refine": True,
        "updated_at": now_iso(),
    }


def validate_config(config: dict[str, Any]) -> None:
    if not isinstance(config.get("enabled"), bool):
        raise ValueError("config.enabled must be a boolean.")
    max_per_run = config.get("max_companies_per_run")
    if not isinstance(max_per_run, int) or max_per_run < 0 or max_per_run > 12:
        raise ValueError("config.max_companies_per_run must be an integer from 0 to 12.")
    if not isinstance(config.get("requeue_after_refine"), bool):
        raise ValueError("config.requeue_after_refine must be a boolean.")


def load_config() -> dict[str, Any]:
    stored = load_json(CONFIG_PATH, default_config())
    merged = default_config()
    merged.update(stored)
    validate_config(merged)
    return merged


def save_config(config: dict[str, Any]) -> dict[str, Any]:
    record = default_config()
    record.update(config)
    record["updated_at"] = now_iso()
    validate_config(record)
    save_json(CONFIG_PATH, record)
    return record


def load_queue() -> dict[str, Any]:
    return load_json(QUEUE_PATH, default_queue_store())


def save_queue(store: dict[str, Any]) -> dict[str, Any]:
    save_json(QUEUE_PATH, store)
    return store


def load_runs() -> dict[str, Any]:
    return load_json(RUNS_PATH, default_runs_store())


def save_runs(store: dict[str, Any]) -> dict[str, Any]:
    save_json(RUNS_PATH, store)
    return store


def get_last_run() -> dict[str, Any] | None:
    runs = load_runs()["runs"]
    if not runs:
        return None
    return runs[-1]


def find_queue_item(store: dict[str, Any], company: str) -> dict[str, Any] | None:
    company_key = company.strip().lower()
    for item in store["items"]:
        if item["company"].strip().lower() == company_key:
            return item
    return None


def queue_for_refinement(
    company: dict[str, Any],
    reason: str = "",
    *,
    source: str = "review",
) -> dict[str, Any]:
    store = load_queue()
    name = company["company"].strip()
    existing = find_queue_item(store, name)
    if existing and existing["status"] == "pending":
        if reason.strip():
            existing["reason"] = reason.strip()
            existing["updated_at"] = now_iso()
        save_queue(store)
        return existing

    item = {
        "item_id": company_to_slug(name),
        "company": name,
        "country": company.get("country", ""),
        "theme": company.get("theme", ""),
        "reason": reason.strip(),
        "source": source,
        "status": "pending",
        "queued_at": now_iso(),
        "updated_at": now_iso(),
        "refined_at": "",
    }
    if existing:
        existing.update(item)
        existing["status"] = "pending"
    else:
        store["items"].append(item)
    save_queue(store)
    return item


def get_pending_refinements() -> list[dict[str, Any]]:
    return [
        item for item in load_queue()["items"] if item["status"] == "pending"
    ]


def load_companies() -> list[dict[str, str]]:
    if not COMPANIES_PATH.exists():
        return []
    with COMPANIES_PATH.open(encoding="utf-8") as source:
        return list(csv.DictReader(source))


def load_company_row(company_name: str) -> dict[str, str]:
    company_key = company_name.strip().lower()
    for row in load_companies():
        if row["company"].strip().lower() == company_key:
            return row
    raise ValueError(f"Company not found in companies.csv: {company_name}")


def update_company_copy(
    company_name: str,
    *,
    description: str | None = None,
    why_fit: str | None = None,
    problems_to_solve: str | None = None,
    suggested_role: str | None = None,
) -> dict[str, str]:
    updates = {
        "description": description,
        "why_fit": why_fit,
        "problems_to_solve": problems_to_solve,
        "suggested_role": suggested_role,
    }
    if not any(value is not None for value in updates.values()):
        raise ValueError("At least one copy field must be provided.")

    rows = load_companies()
    company_key = company_name.strip().lower()
    updated_row: dict[str, str] | None = None
    for row in rows:
        if row["company"].strip().lower() != company_key:
            continue
        for field, value in updates.items():
            if value is not None:
                row[field] = value.strip()
        updated_row = row
        break

    if updated_row is None:
        raise ValueError(f"Company not found in companies.csv: {company_name}")

    with COMPANIES_PATH.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=COMPANY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return updated_row


def mark_refined(
    company_name: str,
    *,
    requeue: bool | None = None,
) -> dict[str, Any]:
    store = load_queue()
    item = find_queue_item(store, company_name)
    if not item:
        raise ValueError(f"No refinement queue item for: {company_name}")

    item["status"] = "refined"
    item["refined_at"] = now_iso()
    item["updated_at"] = now_iso()
    save_queue(store)

    should_requeue = load_config()["requeue_after_refine"] if requeue is None else requeue
    if should_requeue:
        state = load_state()
        row = load_company_row(company_name)
        record_feedback(
            state,
            row,
            "Neutral",
            "Content agent ne copy refine ki — dubara review ke liye.",
        )
    return item


def record_run(
    *,
    companies_refined: int,
    companies_skipped: int = 0,
    errors: list[str] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    store = load_runs()
    entry = {
        "run_id": run_id or str(uuid.uuid4()),
        "completed_at": now_iso(),
        "companies_refined": companies_refined,
        "companies_skipped": companies_skipped,
        "errors": errors or [],
    }
    store["runs"].append(entry)
    save_runs(store)
    return entry


def build_refinement_brief(company_name: str) -> dict[str, Any]:
    row = load_company_row(company_name)
    profile = load_json(PROFILE_PATH, {})
    state = load_state()
    queue_item = find_queue_item(load_queue(), company_name) or {}
    unclear = [
        item
        for item in state["feedback"]
        if item["company"] == company_name and item["rating"] == UNCLEAR_RATING
    ]
    return {
        "company": company_name,
        "current_copy": {field: row.get(field, "") for field in COPY_FIELDS},
        "profile": profile,
        "unclear_feedback": unclear,
        "refinement_reason": queue_item.get("reason", ""),
        "voice": profile.get("content_voice", {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AJOS content refinement utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("show-config", help="Print content agent config JSON")
    subparsers.add_parser("list-pending", help="List companies awaiting copy refinement")

    brief_parser = subparsers.add_parser("brief", help="Print refinement brief for a company")
    brief_parser.add_argument("--company", required=True)

    update_parser = subparsers.add_parser("update", help="Update company copy in companies.csv")
    update_parser.add_argument("--company", required=True)
    update_parser.add_argument("--json", required=True, help="JSON with copy fields or @file")

    refined_parser = subparsers.add_parser(
        "mark-refined", help="Mark queue item refined and optionally re-queue"
    )
    refined_parser.add_argument("--company", required=True)
    refined_parser.add_argument("--no-requeue", action="store_true")

    record_parser = subparsers.add_parser("record-run", help="Record a content agent run")
    record_parser.add_argument("--refined", type=int, default=0)
    record_parser.add_argument("--skipped", type=int, default=0)
    record_parser.add_argument("--errors", nargs="*", default=[])

    args = parser.parse_args()

    if args.command == "show-config":
        print(json.dumps(load_config(), indent=2))
        return

    if args.command == "list-pending":
        print(json.dumps(get_pending_refinements(), indent=2))
        return

    if args.command == "brief":
        print(json.dumps(build_refinement_brief(args.company), indent=2, ensure_ascii=False))
        return

    if args.command == "update":
        payload = args.json
        if payload.startswith("@"):
            payload = Path(payload[1:]).read_text(encoding="utf-8")
        copy = json.loads(payload)
        updated = update_company_copy(args.company, **copy)
        print(json.dumps(updated, indent=2, ensure_ascii=False))
        return

    if args.command == "mark-refined":
        item = mark_refined(args.company, requeue=not args.no_requeue)
        print(json.dumps(item, indent=2, ensure_ascii=False))
        return

    if args.command == "record-run":
        entry = record_run(
            companies_refined=args.refined,
            companies_skipped=args.skipped,
            errors=args.errors,
        )
        print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
