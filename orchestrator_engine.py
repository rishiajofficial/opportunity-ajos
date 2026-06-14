"""Unified work queue for AJOS cloud agents."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ORCHESTRATOR_DIR = Path(__file__).parent / "data" / "orchestrator"
QUEUE_PATH = ORCHESTRATOR_DIR / "queue.json"
CONFIG_PATH = ORCHESTRATOR_DIR / "config.json"

WORK_TYPES = (
    "outreach_pipeline",
    "dev_implement",
    "outreach_improve",
    "discovery_run",
    "content_refine",
    "sync_check",
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


def default_config() -> dict[str, Any]:
    return {
        "auto_approve_dev_feedback": True,
        "max_items_per_run": 3,
        "webhook_enabled": True,
    }


def load_config() -> dict[str, Any]:
    return {**default_config(), **load_json(CONFIG_PATH, {})}


def load_queue() -> dict[str, list]:
    return load_json(QUEUE_PATH, {"items": []})


def save_queue(store: dict[str, list]) -> None:
    save_json(QUEUE_PATH, store)


def item_id() -> str:
    return f"orch_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')[:17]}"


def enqueue(
    work_type: str,
    *,
    company: str | None = None,
    feedback_id: str | None = None,
    notes: str = "",
    source: str = "app",
    priority: int = 5,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if work_type not in WORK_TYPES:
        raise ValueError(f"Unknown work type: {work_type}")
    store = load_queue()
    item = {
        "id": item_id(),
        "type": work_type,
        "company": company,
        "feedback_id": feedback_id,
        "notes": notes,
        "source": source,
        "priority": priority,
        "status": "queued",
        "created_at": now_iso(),
        "payload": payload or {},
    }
    store["items"].append(item)
    save_queue(store)
    try:
        from github_sync import schedule_sync

        schedule_sync("orchestrator/queue.json")
    except ImportError:
        pass
    return item


def get_queued(*, limit: int | None = None) -> list[dict[str, Any]]:
    config = load_config()
    cap = limit or config["max_items_per_run"]
    items = [item for item in load_queue().get("items", []) if item.get("status") == "queued"]
    items.sort(key=lambda item: (item.get("priority", 5), item.get("created_at", "")))
    return items[:cap]


def mark_done(item_id_value: str, *, result: str = "") -> dict[str, Any] | None:
    store = load_queue()
    item = next((i for i in store["items"] if i["id"] == item_id_value), None)
    if not item:
        return None
    item["status"] = "done"
    item["completed_at"] = now_iso()
    if result:
        item["result"] = result
    save_queue(store)
    try:
        from github_sync import schedule_sync

        schedule_sync("orchestrator/queue.json")
    except ImportError:
        pass
    return item


def mark_failed(item_id_value: str, error: str) -> dict[str, Any] | None:
    store = load_queue()
    item = next((i for i in store["items"] if i["id"] == item_id_value), None)
    if not item:
        return None
    item["status"] = "failed"
    item["error"] = error
    item["completed_at"] = now_iso()
    save_queue(store)
    return item
