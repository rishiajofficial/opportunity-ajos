"""Slack notifications for AJOS pipeline events."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from app_secrets import get_secret

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(get_secret("SLACK_WEBHOOK_URL"))


def post_message(text: str, *, blocks: list[dict[str, Any]] | None = None) -> bool:
    url = get_secret("SLACK_WEBHOOK_URL")
    if not url:
        return False
    payload: dict[str, Any] = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.warning("Slack notify failed: %s", exc)
        return False


def notify_discovery_match(name: str, country: str, theme: str, score: int) -> bool:
    return post_message(
        f"AJOS: New opportunity — {name} ({country}, {theme}) score {score}/100. Open review queue."
    )


def notify_contact_found(company: str, contact_name: str, contact_count: int) -> bool:
    return post_message(
        f"AJOS: Found {contact_count} contact(s) for {company}. Primary: {contact_name}."
    )


def notify_draft_ready(company: str, subject: str) -> bool:
    return post_message(f"AJOS: Draft ready for {company}. Subject: {subject}")


def notify_dev_feedback(feedback: str) -> bool:
    preview = feedback[:120] + ("…" if len(feedback) > 120 else "")
    return post_message(f"AJOS: Dev feedback queued — {preview}")


def notify_orchestrator_run(processed: int, summary: str) -> bool:
    return post_message(f"AJOS orchestrator: processed {processed} item(s). {summary}")
