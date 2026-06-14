"""Run outreach pipeline for a single company: contacts → email → draft."""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def run_outreach_pipeline(company_name: str, *, force: bool = False) -> dict[str, Any]:
    from action_engine import enrich_action_with_contact, ensure_recommendation, get_active_action, load_entity_actions, save_entity_actions
    from contact_discovery_engine import bootstrap_company, load_companies, load_config as load_cd_config, load_profile, company_row, website_host
    from email_finder_engine import find_email_for_contact, load_config as load_ef_config, apply_email_to_contact, sync_company_actions as ef_sync
    from contact_discovery import load_company_contacts, save_company_contacts
    from learning import load_state

    result: dict[str, Any] = {
        "company": company_name,
        "contacts_added": 0,
        "emails_found": 0,
        "draft_updated": False,
        "errors": [],
    }

    companies = load_companies()
    row = company_row(companies, company_name)
    if not row:
        result["errors"].append("company not in CSV")
        return result

    profile = load_profile()
    domain = website_host(row.get("website", ""))
    if not domain:
        result["errors"].append("missing website domain")
        return result

    cd_config = load_cd_config()
    entity = load_company_contacts(company_name)
    if entity is None or not entity.get("contacts") or force:
        try:
            bootstrap_result, _credits = bootstrap_company(
                company_name=company_name,
                domain=domain,
                website=row.get("website", ""),
                config=cd_config,
                credits_remaining=cd_config["max_credits_per_run"],
            )
            result["contacts_added"] = len(bootstrap_result.get("contacts_added", []))
            if bootstrap_result.get("skipped"):
                result["errors"].extend(bootstrap_result["skipped"])
        except Exception as exc:
            logger.exception("Contact discovery failed")
            result["errors"].append(f"contact discovery: {exc}")

    entity = load_company_contacts(company_name)
    if entity and entity.get("contacts"):
        ef_config = load_ef_config()
        provider = ef_config.get("provider", "hunter")
        for contact in entity["contacts"]:
            if contact.get("email") and not force:
                continue
            email_result, err = find_email_for_contact(
                contact=contact,
                company_name=company_name,
                domain=domain,
                config=ef_config,
            )
            if email_result and email_result.email:
                apply_email_to_contact(contact, email_result, provider=provider)
                result["emails_found"] += 1
            elif err:
                result["errors"].append(err)
        save_company_contacts(entity)
        ef_sync(company_name, profile, companies)

    state = load_state()
    action_record = ensure_recommendation(row, profile, state)
    entity_actions = load_entity_actions(company_name)
    active = get_active_action(entity_actions)
    if active:
        enrich_action_with_contact(entity_actions, active, row, profile)
        save_entity_actions(entity_actions)
        result["draft_updated"] = True

    try:
        from slack_notify import notify_contact_found, notify_draft_ready

        if entity and entity.get("contacts"):
            primary = entity["contacts"][0]
            notify_contact_found(company_name, primary.get("name", "—"), len(entity["contacts"]))
        if active:
            draft = active.get("drafts", {}).get("email", {})
            if draft.get("subject"):
                notify_draft_ready(company_name, draft["subject"])
    except ImportError:
        pass

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AJOS outreach pipeline")
    parser.add_argument("--company", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run_outreach_pipeline(args.company, force=args.force)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
