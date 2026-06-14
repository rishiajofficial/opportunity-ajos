"""Persist sidebar filter preferences across sessions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PREFS_PATH = Path(__file__).parent / "data" / "ui_preferences.json"

DEFAULT_GEOGRAPHIES = [
    "UAE",
    "Singapore",
    "India",
    "Netherlands",
    "Finland",
    "Switzerland",
]
DEFAULT_THEMES = [
    "Future of Work",
    "Creator Economy",
    "Education",
    "Wellness & Mental Wellbeing",
]


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


def default_preferences(
    *,
    geographies: list[str] | None = None,
    themes: list[str] | None = None,
) -> dict[str, list[str]]:
    return {
        "sidebar_geographies": list(geographies or DEFAULT_GEOGRAPHIES),
        "sidebar_themes": list(themes or DEFAULT_THEMES),
    }


def load_preferences() -> dict[str, list[str]]:
    stored = load_json(PREFS_PATH, {})
    defaults = default_preferences()
    return {
        "sidebar_geographies": stored.get("sidebar_geographies") or defaults["sidebar_geographies"],
        "sidebar_themes": stored.get("sidebar_themes") or defaults["sidebar_themes"],
    }


def save_preferences(*, geographies: list[str], themes: list[str]) -> dict[str, list[str]]:
    prefs = {
        "sidebar_geographies": geographies,
        "sidebar_themes": themes,
    }
    save_json(PREFS_PATH, prefs)
    return prefs


def geography_options(*, discovery_countries: list[str] | None = None) -> list[str]:
    return sorted(set(DEFAULT_GEOGRAPHIES) | set(discovery_countries or []))
