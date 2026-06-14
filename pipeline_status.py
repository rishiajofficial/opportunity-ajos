"""Pipeline status helpers for UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONTACT_RUNS = Path(__file__).parent / "data" / "contact_discovery" / "runs.json"
EMAIL_RUNS = Path(__file__).parent / "data" / "email_finder" / "runs.json"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def latest_run_for_company(path: Path, company: str) -> dict[str, Any] | None:
    runs = load_json(path, {"runs": []}).get("runs", [])
    for run in reversed(runs):
        for detail in run.get("companies", []):
            if detail.get("company") == company:
                return {"run": run, "detail": detail}
    return None


def pipeline_status(company: str, action: dict[str, Any] | None = None) -> dict[str, str]:
    from contact_discovery import contacts_status

    contact = contacts_status(company)
    cd = latest_run_for_company(CONTACT_RUNS, company)
    ef = latest_run_for_company(EMAIL_RUNS, company)

    contact_line = "Not started"
    if contact.get("contact_count", 0) > 0:
        contact_line = f"Found {contact['contact_count']} contact(s)"
    elif cd:
        detail = cd["detail"]
        if detail.get("contacts_added"):
            contact_line = f"Added {len(detail['contacts_added'])} contact(s)"
        elif detail.get("skipped"):
            contact_line = f"Skipped: {detail['skipped'][0].get('reason', 'unknown')}"

    email_line = "Not started"
    if ef:
        detail = ef["detail"]
        if detail.get("emails_found", 0) > 0:
            email_line = f"Found {detail['emails_found']} email(s)"
        elif detail.get("errors"):
            email_line = f"No email: {detail['errors'][0][:80]}"

    draft = (action or {}).get("drafts", {}).get("email", {})
    draft_line = "No draft"
    if draft.get("body"):
        draft_line = "AI conversation opener" if "?" in draft.get("subject", "") else "Draft ready"

    return {
        "contacts": contact_line,
        "email": email_line,
        "draft": draft_line,
    }
