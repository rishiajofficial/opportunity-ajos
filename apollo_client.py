import os
import time
from dataclasses import dataclass
from typing import Any

import requests


APOLLO_BASE_URL = "https://api.apollo.io/api/v1"
REQUEST_INTERVAL_SECONDS = 1.0
_last_request_at = 0.0


@dataclass
class ApolloResult:
    person_id: str | None
    email: str | None
    email_status: str | None
    linkedin_url: str | None
    first_name: str | None
    last_name: str | None
    credits_used: int


@dataclass
class ApolloSearchResult:
    person_id: str
    first_name: str | None
    last_name: str | None
    title: str | None
    has_email: bool


class ApolloClientError(Exception):
    pass


def get_api_key() -> str:
    key = os.environ.get("APOLLO_API_KEY", "").strip()
    if not key:
        raise ApolloClientError(
            "APOLLO_API_KEY is not set. Export it locally or add it to Cursor Automation env."
        )
    return key


def _throttle() -> None:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < REQUEST_INTERVAL_SECONDS:
        time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
    _last_request_at = time.monotonic()


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": get_api_key(),
    }


def _request(method: str, path: str, *, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
    _throttle()
    response = requests.request(
        method,
        f"{APOLLO_BASE_URL}{path}",
        headers=_headers(),
        json=json_body,
        timeout=30,
    )
    if response.status_code == 401:
        raise ApolloClientError("Apollo API rejected the key (401). Check APOLLO_API_KEY.")
    if response.status_code == 403:
        raise ApolloClientError(
            f"Apollo API forbidden (403). Endpoint may not be on your plan: {path}"
        )
    if response.status_code == 429:
        raise ApolloClientError("Apollo rate limit hit (429). Retry later.")
    if not response.ok:
        raise ApolloClientError(
            f"Apollo API error {response.status_code} on {path}: {response.text[:300]}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise ApolloClientError(f"Unexpected Apollo response type from {path}")
    return payload


def _person_from_payload(payload: dict[str, Any], *, credits_used: int) -> ApolloResult:
    person = payload.get("person") or {}
    return ApolloResult(
        person_id=person.get("id"),
        email=(person.get("email") or "").strip() or None,
        email_status=(person.get("email_status") or "").strip() or None,
        linkedin_url=(person.get("linkedin_url") or "").strip() or None,
        first_name=(person.get("first_name") or "").strip() or None,
        last_name=(person.get("last_name") or "").strip() or None,
        credits_used=credits_used,
    )


def match_person(
    *,
    first_name: str,
    last_name: str,
    domain: str,
    organization_name: str | None = None,
) -> ApolloResult:
    body: dict[str, Any] = {
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "domain": domain.strip(),
    }
    if organization_name:
        body["organization_name"] = organization_name.strip()
    payload = _request("POST", "/people/match", json_body=body)
    return _person_from_payload(payload, credits_used=1)


def match_by_id(person_id: str) -> ApolloResult:
    payload = _request("POST", "/people/match", json_body={"id": person_id.strip()})
    return _person_from_payload(payload, credits_used=1)


def search_people(
    *,
    domain: str,
    titles: list[str] | None = None,
    per_page: int = 5,
) -> list[ApolloSearchResult]:
    body: dict[str, Any] = {
        "q_organization_domains": domain.strip(),
        "per_page": max(1, min(per_page, 25)),
        "page": 1,
    }
    if titles:
        body["person_titles"] = [title.strip() for title in titles if title.strip()]
    payload = _request("POST", "/mixed_people/api_search", json_body=body)
    people = payload.get("people") or []
    results: list[ApolloSearchResult] = []
    for person in people:
        if not person.get("id"):
            continue
        results.append(
            ApolloSearchResult(
                person_id=str(person["id"]),
                first_name=(person.get("first_name") or "").strip() or None,
                last_name=(person.get("last_name_obfuscated") or person.get("last_name") or "").strip()
                or None,
                title=(person.get("title") or "").strip() or None,
                has_email=bool(person.get("has_email")),
            )
        )
    return results
