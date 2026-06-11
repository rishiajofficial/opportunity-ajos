import json
from pathlib import Path
from typing import Any

from company_intelligence import company_to_slug


CONTACTS_DIR = Path(__file__).parent / "data" / "contacts" / "companies"

VALID_ROLE_TAGS = {
    "founder",
    "ceo",
    "head_of_product",
    "head_of_innovation",
    "head_of_partnerships",
    "head_of_growth",
    "head_of_education",
}

ACTION_CONTACT_TAGS: dict[str, tuple[str, ...]] = {
    "Send introduction email": ("founder", "ceo"),
    "Send LinkedIn message": ("founder", "ceo", "head_of_product"),
    "Request conversation": ("founder", "ceo", "head_of_innovation"),
    "Offer workshop": ("head_of_innovation", "head_of_product", "head_of_education"),
    "Offer pilot project": ("head_of_innovation", "head_of_product"),
    "Offer advisory support": ("founder", "ceo", "head_of_innovation"),
    "Share insight": ("head_of_product", "head_of_education", "head_of_innovation"),
    "Do nothing yet": (),
}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def contacts_path(entity_id: str) -> Path:
    return CONTACTS_DIR / f"{company_to_slug(entity_id)}.json"


def default_entity_contacts(entity_id: str) -> dict[str, Any]:
    return {
        "entity_type": "company",
        "entity_id": entity_id,
        "contacts": [],
    }


def validate_contact(contact: dict[str, Any]) -> None:
    required = ("contact_id", "name", "title", "why_they_matter", "priority_score", "source_url")
    for field in required:
        if not contact.get(field) and field != "priority_score":
            raise ValueError(f"Contact missing required field: {field}")
    if not isinstance(contact["priority_score"], int):
        raise ValueError(f"Contact {contact.get('contact_id')} priority_score must be an integer.")
    if contact["priority_score"] < 0 or contact["priority_score"] > 100:
        raise ValueError(f"Contact {contact.get('contact_id')} priority_score must be 0-100.")
    role_tags = contact.get("role_tags", [])
    if not role_tags:
        raise ValueError(f"Contact {contact.get('contact_id')} must include role_tags.")
    unknown_tags = set(role_tags) - VALID_ROLE_TAGS
    if unknown_tags:
        raise ValueError(f"Contact {contact.get('contact_id')} has unknown role_tags: {unknown_tags}")


def validate_entity(entity: dict[str, Any]) -> None:
    if entity.get("entity_type") != "company":
        raise ValueError("Only company contacts are supported in V1.")
    if not entity.get("entity_id"):
        raise ValueError("Contact entity must include entity_id.")
    entity.setdefault("contacts", [])
    contact_ids = set()
    for contact in entity["contacts"]:
        validate_contact(contact)
        if contact["contact_id"] in contact_ids:
            raise ValueError(f"Duplicate contact_id: {contact['contact_id']}")
        contact_ids.add(contact["contact_id"])


def load_company_contacts(entity_id: str) -> dict[str, Any] | None:
    path = contacts_path(entity_id)
    if not path.exists():
        return None
    entity = load_json(path, default_entity_contacts(entity_id))
    validate_entity(entity)
    if entity["entity_id"] != entity_id:
        raise ValueError(
            f"Contact entity_id '{entity['entity_id']}' does not match '{entity_id}'."
        )
    return entity


def contacts_status(entity_id: str) -> dict[str, Any]:
    entity = load_company_contacts(entity_id)
    if entity is None:
        return {"exists": False, "company": entity_id, "contact_count": 0}
    return {
        "exists": True,
        "company": entity_id,
        "contact_count": len(entity["contacts"]),
    }


def _contact_action_score(contact: dict[str, Any], action_type: str) -> int:
    preferred_tags = ACTION_CONTACT_TAGS.get(action_type, ())
    overlap = len(set(contact.get("role_tags", [])) & set(preferred_tags))
    return contact["priority_score"] + overlap * 12


def select_contact_for_action(
    contacts: list[dict[str, Any]], action_type: str
) -> dict[str, Any] | None:
    if not contacts or action_type == "Do nothing yet":
        return None
    ranked = sorted(
        contacts,
        key=lambda contact: _contact_action_score(contact, action_type),
        reverse=True,
    )
    return ranked[0]


def select_secondary_contact(
    contacts: list[dict[str, Any]],
    primary: dict[str, Any] | None,
    action_type: str | None = None,
) -> dict[str, Any] | None:
    if not contacts:
        return None
    excluded_id = primary["contact_id"] if primary else None
    candidates = [contact for contact in contacts if contact["contact_id"] != excluded_id]
    if not candidates:
        return None
    if action_type:
        ranked = sorted(
            candidates,
            key=lambda contact: _contact_action_score(contact, action_type),
            reverse=True,
        )
        return ranked[0]
    ranked = sorted(candidates, key=lambda contact: contact["priority_score"], reverse=True)
    return ranked[0]


def build_selection_reason(
    contact: dict[str, Any], action_type: str | None, *, rank: str
) -> str:
    tags = ", ".join(tag.replace("_", " ") for tag in contact.get("role_tags", []))
    base = (
        f"{rank} contact with priority {contact['priority_score']}/100. "
        f"{contact['why_they_matter']}"
    )
    if action_type and action_type != "Do nothing yet":
        preferred = ACTION_CONTACT_TAGS.get(action_type, ())
        if preferred and set(contact.get("role_tags", [])) & set(preferred):
            preferred_labels = ", ".join(tag.replace("_", " ") for tag in preferred)
            return (
                f"{base} Selected because '{action_type}' typically routes to "
                f"roles such as {preferred_labels}."
            )
    return base


def get_contact_recommendations(
    entity_id: str, action_type: str | None = None
) -> dict[str, Any]:
    entity = load_company_contacts(entity_id)
    if entity is None or not entity["contacts"]:
        return {
            "exists": False,
            "company": entity_id,
            "primary": None,
            "secondary": None,
            "why_primary": None,
            "why_secondary": None,
            "all_contacts": [],
        }

    contacts = entity["contacts"]
    if action_type:
        primary = select_contact_for_action(contacts, action_type)
        secondary = select_secondary_contact(contacts, primary, action_type)
    else:
        ranked = sorted(contacts, key=lambda contact: contact["priority_score"], reverse=True)
        primary = ranked[0]
        secondary = select_secondary_contact(contacts, primary)

    return {
        "exists": True,
        "company": entity_id,
        "primary": primary,
        "secondary": secondary,
        "why_primary": (
            build_selection_reason(primary, action_type, rank="Primary")
            if primary
            else None
        ),
        "why_secondary": (
            build_selection_reason(secondary, action_type, rank="Secondary")
            if secondary
            else None
        ),
        "all_contacts": sorted(
            contacts, key=lambda contact: contact["priority_score"], reverse=True
        ),
    }


def contact_summary(contact: dict[str, Any] | None) -> dict[str, Any] | None:
    if contact is None:
        return None
    summary = {
        "contact_id": contact["contact_id"],
        "name": contact["name"],
        "title": contact["title"],
        "why_they_matter": contact["why_they_matter"],
        "priority_score": contact["priority_score"],
        "source_url": contact["source_url"],
        "role_tags": contact.get("role_tags", []),
    }
    if contact.get("email"):
        summary["email"] = contact["email"].strip()
    return summary
