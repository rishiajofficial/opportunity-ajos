import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from company_intelligence import company_to_slug, save_json, load_json


DISCOVERY_DIR = Path(__file__).parent / "data" / "discovery"
CANDIDATES_PATH = DISCOVERY_DIR / "candidates.json"
RUNS_PATH = DISCOVERY_DIR / "runs.json"
COMPANIES_PATH = Path(__file__).parent / "data" / "companies.csv"

NOTIFY_THRESHOLD = 85
VALID_STATUSES = {"pending", "approved", "rejected", "merged"}
SCORE_WEIGHTS = {
    "theme": 0.30,
    "capability": 0.30,
    "role": 0.25,
    "geography": 0.15,
}
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_candidates_store() -> dict[str, Any]:
    return {"candidates": []}


def default_runs_store() -> dict[str, Any]:
    return {"runs": []}


def website_host(website: str) -> str:
    parsed = urlparse(website.strip())
    host = parsed.netloc or parsed.path
    return host.lower().removeprefix("www.")


def join_field(value: str | list[str]) -> str:
    if isinstance(value, list):
        return "; ".join(item.strip() for item in value if str(item).strip())
    return str(value).strip()


def weighted_base_score(base_scores: dict[str, Any]) -> int:
    total = 0.0
    for key, weight in SCORE_WEIGHTS.items():
        total += float(base_scores[key]) * weight
    return round(total)


def validate_source(source: dict[str, Any]) -> None:
    if not source.get("url"):
        raise ValueError("Each source must include a url.")
    if not source.get("label"):
        raise ValueError("Each source must include a label.")


def validate_candidate(candidate: dict[str, Any]) -> None:
    required = (
        "candidate_id",
        "name",
        "country",
        "theme",
        "website",
        "one_liner",
        "why_ankit_fits",
        "problems_to_solve",
        "suggested_role",
        "base_scores",
        "source_urls",
        "discovered_at",
        "status",
    )
    for field in required:
        if field not in candidate:
            raise ValueError(f"Candidate missing required field: {field}")

    if candidate["status"] not in VALID_STATUSES:
        raise ValueError(f"Invalid candidate status: {candidate['status']}")

    for score_key in SCORE_WEIGHTS:
        score = candidate["base_scores"][score_key]
        if not isinstance(score, (int, float)):
            raise ValueError(f"base_scores.{score_key} must be numeric.")
        if score < 0 or score > 100:
            raise ValueError(f"base_scores.{score_key} must be 0-100.")

    if not candidate["source_urls"]:
        raise ValueError("Candidate must include at least one source_url.")

    for source in candidate["source_urls"]:
        validate_source(source)


def load_candidates() -> dict[str, Any]:
    return load_json(CANDIDATES_PATH, default_candidates_store())


def save_candidates(store: dict[str, Any]) -> dict[str, Any]:
    for candidate in store["candidates"]:
        validate_candidate(candidate)
    save_json(CANDIDATES_PATH, store)
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


def record_run(
    *,
    themes_searched: list[str],
    candidates_added: int,
    errors: list[str] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    store = load_runs()
    entry = {
        "run_id": run_id or str(uuid.uuid4()),
        "completed_at": now_iso(),
        "themes_searched": themes_searched,
        "candidates_added": candidates_added,
        "errors": errors or [],
    }
    store["runs"].append(entry)
    save_runs(store)
    return entry


def load_existing_company_names() -> set[str]:
    if not COMPANIES_PATH.exists():
        return set()
    with COMPANIES_PATH.open(encoding="utf-8") as source:
        reader = csv.DictReader(source)
        return {row["company"].strip().lower() for row in reader}


def load_existing_website_hosts() -> set[str]:
    if not COMPANIES_PATH.exists():
        return set()
    with COMPANIES_PATH.open(encoding="utf-8") as source:
        reader = csv.DictReader(source)
        return {website_host(row["website"]) for row in reader if row.get("website")}


def find_candidate(store: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for candidate in store["candidates"]:
        if candidate["candidate_id"] == candidate_id:
            return candidate
    raise ValueError(f"Candidate not found: {candidate_id}")


def is_duplicate_candidate(
    name: str,
    website: str,
    *,
    store: dict[str, Any] | None = None,
) -> str | None:
    name_key = name.strip().lower()
    host = website_host(website)
    slug = company_to_slug(name)

    if name_key in load_existing_company_names():
        return f"Company already exists in companies.csv: {name}"

    if host in load_existing_website_hosts():
        return f"Website already exists in companies.csv: {website}"

    store = store or load_candidates()
    for candidate in store["candidates"]:
        if candidate["status"] == "rejected":
            continue
        if candidate["name"].strip().lower() == name_key:
            return f"Candidate already exists: {name}"
        if website_host(candidate["website"]) == host:
            return f"Candidate website already exists: {website}"
        if candidate["candidate_id"] == slug:
            return f"Candidate slug already exists: {slug}"

    rejected = get_rejected_slugs(store)
    if slug in rejected:
        return f"Candidate was previously rejected: {name}"

    return None


def get_rejected_slugs(store: dict[str, Any] | None = None) -> set[str]:
    store = store or load_candidates()
    return {
        company_to_slug(candidate["name"])
        for candidate in store["candidates"]
        if candidate["status"] == "rejected"
    }


def get_pending_candidates() -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in load_candidates()["candidates"]
        if candidate["status"] == "pending"
    ]


def should_notify(candidate: dict[str, Any]) -> bool:
    return weighted_base_score(candidate["base_scores"]) >= NOTIFY_THRESHOLD


def candidate_to_company_row(candidate: dict[str, Any]) -> dict[str, str]:
    scores = candidate["base_scores"]
    return {
        "company": candidate["name"],
        "country": candidate["country"],
        "theme": candidate["theme"],
        "description": candidate["one_liner"],
        "website": candidate["website"],
        "theme_score": str(int(scores["theme"])),
        "capability_score": str(int(scores["capability"])),
        "role_score": str(int(scores["role"])),
        "geography_score": str(int(scores["geography"])),
        "why_fit": join_field(candidate["why_ankit_fits"]),
        "problems_to_solve": join_field(candidate["problems_to_solve"]),
        "suggested_role": candidate["suggested_role"],
    }


def candidate_to_review_dict(candidate: dict[str, Any]) -> dict[str, Any]:
    row = candidate_to_company_row(candidate)
    base_score = weighted_base_score(candidate["base_scores"])
    row.update(
        {
            "theme_score": int(row["theme_score"]),
            "capability_score": int(row["capability_score"]),
            "role_score": int(row["role_score"]),
            "geography_score": int(row["geography_score"]),
            "base_score": base_score,
            "learned_adjustment": 0,
            "adjustment_reasons": [],
            "final_score": base_score,
            "is_discovered": True,
            "candidate_id": candidate["candidate_id"],
            "discovery_run_id": candidate.get("discovery_run_id", ""),
            "source_urls": candidate.get("source_urls", []),
        }
    )
    return row


def append_company_to_csv(company_row: dict[str, str]) -> None:
    fieldnames = [
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
    with COMPANIES_PATH.open("a", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames)
        writer.writerow({field: company_row[field] for field in fieldnames})


def add_candidate(
    candidate: dict[str, Any],
    *,
    discovery_run_id: str | None = None,
) -> dict[str, Any]:
    store = load_candidates()
    name = candidate["name"].strip()
    website = candidate["website"].strip()
    duplicate_reason = is_duplicate_candidate(name, website, store=store)
    if duplicate_reason:
        raise ValueError(duplicate_reason)

    slug = company_to_slug(name)
    base_scores = candidate["base_scores"]
    for score_key in SCORE_WEIGHTS:
        if score_key not in base_scores:
            raise ValueError(f"base_scores missing key: {score_key}")

    record = {
        "candidate_id": candidate.get("candidate_id") or slug,
        "name": name,
        "country": candidate["country"].strip(),
        "theme": candidate["theme"].strip(),
        "website": website,
        "one_liner": candidate["one_liner"].strip(),
        "why_ankit_fits": candidate["why_ankit_fits"],
        "problems_to_solve": candidate["problems_to_solve"],
        "suggested_role": candidate["suggested_role"].strip(),
        "base_scores": {key: int(base_scores[key]) for key in SCORE_WEIGHTS},
        "source_urls": candidate["source_urls"],
        "discovered_at": candidate.get("discovered_at") or now_iso(),
        "status": "pending",
        "discovery_run_id": discovery_run_id or candidate.get("discovery_run_id", ""),
    }
    validate_candidate(record)
    store["candidates"].append(record)
    save_candidates(store)
    return record


def approve_candidate(candidate_id: str) -> dict[str, Any]:
    store = load_candidates()
    candidate = find_candidate(store, candidate_id)
    if candidate["status"] == "merged":
        return candidate_to_review_dict(candidate)

    company_row = candidate_to_company_row(candidate)
    append_company_to_csv(company_row)
    candidate["status"] = "merged"
    save_candidates(store)
    return candidate_to_review_dict(candidate)


def reject_candidate(candidate_id: str, reason: str = "") -> dict[str, Any]:
    store = load_candidates()
    candidate = find_candidate(store, candidate_id)
    candidate["status"] = "rejected"
    if reason.strip():
        candidate["rejection_reason"] = reason.strip()
    candidate["rejected_at"] = now_iso()
    save_candidates(store)
    return candidate


def build_review_queue(
    company_dicts: list[dict[str, Any]],
    learning_state: dict[str, Any],
    *,
    geographies: list[str] | None = None,
    themes: list[str] | None = None,
) -> list[dict[str, Any]]:
    from learning import get_review_queue

    csv_queue = get_review_queue(company_dicts, learning_state)
    discovery_queue = []
    for candidate in get_pending_candidates():
        review_item = candidate_to_review_dict(candidate)
        if geographies and review_item["country"] not in geographies:
            continue
        if themes and review_item["theme"] not in themes:
            continue
        discovery_queue.append(review_item)

    discovery_queue.sort(
        key=lambda item: (-item["final_score"], item["company"].lower())
    )
    return discovery_queue + csv_queue


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="AJOS discovery candidate utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add a discovery candidate")
    add_parser.add_argument("--json", required=True, help="Candidate JSON string or @file path")

    subparsers.add_parser("list-pending", help="List pending discovery candidates")
    subparsers.add_parser("list-rejected", help="List rejected candidate slugs")

    record_parser = subparsers.add_parser("record-run", help="Record a discovery run")
    record_parser.add_argument("--themes", nargs="+", required=True)
    record_parser.add_argument("--added", type=int, default=0)
    record_parser.add_argument("--errors", nargs="*", default=[])

    args = parser.parse_args()

    if args.command == "add":
        payload = args.json
        if payload.startswith("@"):
            payload = Path(payload[1:]).read_text(encoding="utf-8")
        candidate = json.loads(payload)
        created = add_candidate(candidate)
        print(json.dumps(created, indent=2))
        if should_notify(created):
            print("NOTIFY", file=sys.stderr)
        return

    if args.command == "list-pending":
        print(json.dumps(get_pending_candidates(), indent=2))
        return

    if args.command == "list-rejected":
        print(json.dumps(sorted(get_rejected_slugs()), indent=2))
        return

    if args.command == "record-run":
        entry = record_run(
            themes_searched=args.themes,
            candidates_added=args.added,
            errors=args.errors,
        )
        print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
