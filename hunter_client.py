import time
from dataclasses import dataclass
from typing import Any

import requests

from app_secrets import get_secret


HUNTER_BASE_URL = "https://api.hunter.io/v2"
REQUEST_INTERVAL_SECONDS = 1.0
_last_request_at = 0.0


@dataclass
class HunterResult:
    person_id: str | None
    email: str | None
    email_status: str | None
    linkedin_url: str | None
    first_name: str | None
    last_name: str | None
    title: str | None
    credits_used: int


class HunterClientError(Exception):
    pass


def get_api_key() -> str:
    key = get_secret("HUNTER_API_KEY")
    if not key:
        raise HunterClientError(
            "HUNTER_API_KEY is not set. Add it to .streamlit/secrets.toml or export it."
        )
    return key


def _throttle() -> None:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < REQUEST_INTERVAL_SECONDS:
        time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
    _last_request_at = time.monotonic()


def _get(path: str, *, params: dict[str, Any]) -> dict[str, Any]:
    _throttle()
    query = dict(params)
    query["api_key"] = get_api_key()
    response = requests.get(
        f"{HUNTER_BASE_URL}{path}",
        params=query,
        timeout=30,
    )
    if response.status_code == 401:
        raise HunterClientError("Hunter API rejected the key (401). Check HUNTER_API_KEY.")
    if response.status_code == 403:
        raise HunterClientError(
            f"Hunter API forbidden (403). Check plan limits or endpoint access: {path}"
        )
    if response.status_code == 429:
        raise HunterClientError("Hunter rate limit hit (429). Retry later.")
    if not response.ok:
        raise HunterClientError(
            f"Hunter API error {response.status_code} on {path}: {response.text[:300]}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise HunterClientError(f"Unexpected Hunter response type from {path}")
    return payload


def _verification_status(verification: dict[str, Any] | None) -> str | None:
    if not verification:
        return None
    status = (verification.get("status") or "").strip()
    return status or None


def email_finder(
    *,
    first_name: str,
    last_name: str,
    domain: str,
) -> HunterResult:
    payload = _get(
        "/email-finder",
        params={
            "domain": domain.strip(),
            "first_name": first_name.strip(),
            "last_name": last_name.strip(),
        },
    )
    data = payload.get("data") or {}
    email = (data.get("email") or "").strip() or None
    credits_used = 1 if email else 0
    return HunterResult(
        person_id=None,
        email=email,
        email_status=_verification_status(data.get("verification")),
        linkedin_url=(data.get("linkedin_url") or "").strip() or None,
        first_name=(data.get("first_name") or first_name).strip() or None,
        last_name=(data.get("last_name") or last_name).strip() or None,
        title=(data.get("position") or "").strip() or None,
        credits_used=credits_used,
    )


def domain_search(*, domain: str, limit: int = 10) -> list[HunterResult]:
    payload = _get(
        "/domain-search",
        params={
            "domain": domain.strip(),
            "limit": max(1, min(limit, 10)),
        },
    )
    data = payload.get("data") or {}
    emails = data.get("emails") or []
    results: list[HunterResult] = []
    for item in emails:
        email = (item.get("value") or "").strip() or None
        if not email:
            continue
        first_name = (item.get("first_name") or "").strip() or None
        last_name = (item.get("last_name") or "").strip() or None
        results.append(
            HunterResult(
                person_id=None,
                email=email,
                email_status=_verification_status(item.get("verification")),
                linkedin_url=(item.get("linkedin") or "").strip() or None,
                first_name=first_name,
                last_name=last_name,
                title=(item.get("position") or "").strip() or None,
                credits_used=1,
            )
        )
    return results
