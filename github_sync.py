"""Auto-commit and push data/ changes to GitHub from Streamlit Cloud."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_secrets import get_secret

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
STATUS_PATH = DATA_DIR / "github_sync_status.json"
DEBOUNCE_SECONDS = 30

_lock = threading.Lock()
_pending_paths: set[str] = set()
_timer: threading.Timer | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_status() -> dict[str, Any]:
    if not STATUS_PATH.exists():
        return {"last_sync": None, "last_error": None, "pending": False}
    with STATUS_PATH.open(encoding="utf-8") as source:
        return json.load(source)


def save_status(status: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATUS_PATH.open("w", encoding="utf-8") as destination:
        json.dump(status, destination, indent=2, ensure_ascii=True)
        destination.write("\n")


def is_configured() -> bool:
    return bool(get_secret("GITHUB_TOKEN"))


def data_relative_path(path_value: str | Path) -> Path | None:
    path = Path(path_value)
    if path.is_absolute():
        try:
            return path.relative_to(DATA_DIR)
        except ValueError:
            return None

    parts = path.parts
    rel = Path(*parts[1:]) if parts and parts[0] == "data" else path
    if not rel.parts or any(part == ".." for part in rel.parts):
        return None
    return rel


def schedule_sync(relative_path: str | Path) -> None:
    """Queue a data file for debounced git push."""
    if not is_configured():
        return
    rel = data_relative_path(relative_path)
    if rel is None:
        return
    with _lock:
        _pending_paths.add(str(rel))
        save_status({**load_status(), "pending": True, "queued_at": now_iso()})
        _schedule_timer()


def _schedule_timer() -> None:
    global _timer
    if _timer is not None:
        _timer.cancel()
    _timer = threading.Timer(DEBOUNCE_SECONDS, _run_sync)
    _timer.daemon = True
    _timer.start()


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {}
    token = get_secret("GITHUB_TOKEN")
    if token:
        env["GIT_ASKPASS"] = "echo"
        env["GIT_TERMINAL_PROMPT"] = "0"
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )
    return result


def sync_now(*, message: str | None = None) -> dict[str, Any]:
    """Commit and push pending data/ changes immediately."""
    if not is_configured():
        return {"ok": False, "error": "GITHUB_TOKEN not configured"}

    repo_root = Path(__file__).parent
    with _lock:
        paths = sorted(_pending_paths)
        _pending_paths.clear()

    if not paths:
        return {"ok": True, "skipped": True, "reason": "nothing pending"}

    try:
        for rel in paths:
            full = DATA_DIR / rel
            if full.exists():
                _run_git(["git", "add", str(Path("data") / rel)], cwd=repo_root)

        diff = _run_git(["git", "diff", "--cached", "--quiet"], cwd=repo_root)
        if diff.returncode == 0:
            save_status({"last_sync": now_iso(), "last_error": None, "pending": False})
            return {"ok": True, "skipped": True, "reason": "no changes"}

        commit_msg = message or f"data: sync {', '.join(paths[:3])}"
        commit = _run_git(["git", "commit", "-m", commit_msg], cwd=repo_root)
        if commit.returncode != 0:
            raise RuntimeError(commit.stderr.strip() or "git commit failed")

        token = get_secret("GITHUB_TOKEN")
        remote_url = _run_git(["git", "remote", "get-url", "origin"], cwd=repo_root)
        if remote_url.returncode == 0 and token and "@" not in remote_url.stdout:
            url = remote_url.stdout.strip()
            if url.startswith("https://github.com/"):
                auth_url = url.replace(
                    "https://github.com/",
                    f"https://x-access-token:{token}@github.com/",
                )
                _run_git(["git", "remote", "set-url", "origin", auth_url], cwd=repo_root)

        push = _run_git(["git", "push", "origin", "HEAD"], cwd=repo_root)
        if push.returncode != 0:
            raise RuntimeError(push.stderr.strip() or "git push failed")

        save_status({"last_sync": now_iso(), "last_error": None, "pending": False, "paths": paths})
        return {"ok": True, "paths": paths}
    except Exception as exc:
        logger.exception("GitHub sync failed")
        save_status({"last_sync": load_status().get("last_sync"), "last_error": str(exc), "pending": True})
        with _lock:
            _pending_paths.update(paths)
        return {"ok": False, "error": str(exc)}


def _run_sync() -> None:
    sync_now()


def sync_after_write(relative_path: str | Path, *, message: str | None = None) -> None:
    schedule_sync(relative_path)
    if message:
        with _lock:
            global _timer
            if _timer is not None:
                _timer.cancel()
            _timer = threading.Timer(DEBOUNCE_SECONDS, lambda: sync_now(message=message))
            _timer.daemon = True
            _timer.start()
