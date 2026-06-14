"""Persist company chat history to disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from company_intelligence import company_to_slug

CHAT_DIR = Path(__file__).parent / "data" / "chat"


def chat_path(company_name: str) -> Path:
    return CHAT_DIR / f"{company_to_slug(company_name)}.json"


def load_chat(company_name: str) -> list[dict[str, Any]]:
    path = chat_path(company_name)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    return data.get("messages", [])


def save_chat(company_name: str, messages: list[dict[str, Any]]) -> None:
    path = chat_path(company_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as destination:
        json.dump({"company": company_name, "messages": messages}, destination, indent=2)
        destination.write("\n")
    try:
        from github_sync import schedule_sync

        schedule_sync(f"chat/{path.name}")
    except ImportError:
        pass
