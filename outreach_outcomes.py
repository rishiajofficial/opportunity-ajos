"""Track sent outreach emails and queue self-improvement."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OUTREACH_DIR = Path(__file__).parent / "data" / "outreach"
OUTCOMES_PATH = OUTREACH_DIR / "outcomes.json"


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


def load_outcomes() -> dict[str, list]:
    return load_json(OUTCOMES_PATH, {"items": []})


def record_sent(
    *,
    company: str,
    contact: str = "",
    subject: str = "",
    body: str = "",
    angle: str = "",
) -> dict[str, Any]:
    store = load_outcomes()
    item = {
        "company": company,
        "contact": contact,
        "subject": subject,
        "body": body,
        "angle": angle,
        "sent_at": now_iso(),
        "replied": None,
        "notes": "",
    }
    store["items"].append(item)
    save_json(OUTCOMES_PATH, store)

    try:
        from orchestrator_engine import enqueue

        enqueue(
            "outreach_improve",
            company=company,
            notes=f"Learn from sent email: {subject[:60]}",
            source="email_sent",
            priority=3,
            payload={"subject": subject, "angle": angle},
        )
    except ImportError:
        pass

    try:
        from github_sync import schedule_sync

        schedule_sync("outreach/outcomes.json")
    except ImportError:
        pass

    return item


def mark_replied(company: str, *, notes: str = "") -> dict[str, Any] | None:
    store = load_outcomes()
    for item in reversed(store.get("items", [])):
        if item["company"] == company and item.get("replied") is None:
            item["replied"] = True
            item["notes"] = notes
            item["replied_at"] = now_iso()
            save_json(OUTCOMES_PATH, store)
            return item
    return None


def gold_examples() -> list[dict[str, Any]]:
    return [
        item
        for item in load_outcomes().get("items", [])
        if item.get("replied") is True and item.get("subject") and item.get("body")
    ]
