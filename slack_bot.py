"""Slack Bolt bot for /ajos slash commands."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def trigger_cursor_webhook(payload: dict[str, Any] | None = None) -> bool:
    url = os.environ.get("CURSOR_WEBHOOK_URL", "")
    token = os.environ.get("CURSOR_WEBHOOK_TOKEN", "")
    if not url or not token:
        return False
    data = json.dumps(payload or {"event": "ajos.slash_command"}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.warning("Cursor webhook failed: %s", exc)
        return False


def handle_slash_command(command: str, text: str) -> str:
    parts = text.strip().split(maxsplit=1)
    sub = parts[0].lower() if parts else "status"
    arg = parts[1] if len(parts) > 1 else ""

    if sub == "run":
        ok = trigger_cursor_webhook({"event": "ajos.run"})
        return "Orchestrator triggered." if ok else "Webhook not configured."

    if sub == "status":
        from orchestrator_engine import get_queued, load_queue

        queued = get_queued(limit=10)
        total = len([i for i in load_queue().get("items", []) if i.get("status") == "queued"])
        return f"Queue: {total} item(s). Next: {', '.join(i['type'] for i in queued[:3]) or 'empty'}"

    if sub == "draft" and arg:
        return f"Draft mode for {arg} — open AJOS Focus tab or use in-app chat."

    if sub == "improve" and arg:
        from learning import submit_dev_feedback

        submit_dev_feedback(arg)
        trigger_cursor_webhook({"event": "ajos.dev_feedback"})
        return "Feedback queued for dev agent."

    if sub == "sent" and arg:
        from outreach_outcomes import record_sent

        record_sent(company=arg)
        trigger_cursor_webhook({"event": "ajos.email_sent", "company": arg})
        return f"Marked sent for {arg}. Learning queued."

    return "Usage: /ajos status | run | draft <company> | improve <text> | sent <company>"


def create_app():
    """Create Slack Bolt app if dependencies and tokens are configured."""
    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
    except ImportError as exc:
        raise RuntimeError("Install slack-bolt to run slack_bot.py") from exc

    app = App(token=os.environ["SLACK_BOT_TOKEN"])

    @app.command("/ajos")
    def ajos_command(ack, command, respond):
        ack()
        respond(handle_slash_command("/ajos", command.get("text", "")))

    return app, SocketModeHandler


if __name__ == "__main__":
    app, handler = create_app()
    handler.start()
