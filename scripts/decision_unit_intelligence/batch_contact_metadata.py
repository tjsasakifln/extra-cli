"""Join controlled-email classifications back to their durable route evidence."""

from __future__ import annotations

from typing import Any


def _route_index(account: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_mailbox: dict[str, dict[str, Any]] = {}
    for raw in account.get("routes") or []:
        if not isinstance(raw, dict):
            continue
        route = dict(raw)
        route_id = str(route.get("route_id") or "").strip()
        mailbox = str(route.get("channel_value") or "").strip().lower()
        if route_id:
            by_id[route_id] = route
        if mailbox and "@" in mailbox:
            by_mailbox[mailbox] = route
    return by_id, by_mailbox


def attach_route_evidence(
    contacts: list[dict[str, Any]],
    *,
    account: dict[str, Any],
) -> list[dict[str, Any]]:
    """Preserve route provenance without changing the frozen eligibility policy."""
    by_id, by_mailbox = _route_index(account)
    enriched: list[dict[str, Any]] = []
    for raw in contacts:
        contact = dict(raw)
        route_id = str(contact.get("source_contact_id") or contact.get("route_id") or "").strip()
        mailbox = str(contact.get("email") or contact.get("mailbox") or "").strip().lower()
        route = by_id.get(route_id) or by_mailbox.get(mailbox)
        if route is None:
            enriched.append(contact)
            continue

        source_type = str(route.get("source_type") or "").strip() or None
        source_url = str(route.get("source_url") or "").strip() or None
        observed_at = str(route.get("observed_at") or "").strip() or None
        evidence_ids = [str(item) for item in (route.get("evidence_ids") or []) if item]
        epistemic = str(route.get("epistemic_class") or "").strip() or None
        target_role = str(route.get("target_role") or "").strip() or None
        ownership = str(route.get("ownership") or "").strip() or None
        freshness = str(route.get("freshness") or "").strip() or None
        suppression = str(route.get("suppression") or "").strip() or None

        if source_type:
            contact["source"] = source_type
            contact["source_type"] = source_type
        if source_url:
            contact["source_url"] = source_url
        if observed_at:
            contact["observed_at"] = observed_at
        if evidence_ids:
            contact["evidence_ids"] = evidence_ids
        source_reference = source_url or (evidence_ids[0] if evidence_ids else None)
        if source_reference:
            contact["source_reference"] = source_reference
        if target_role:
            contact["mailbox_department"] = target_role
            contact.setdefault("role", target_role)
            contact.setdefault("role_class", target_role)
        if ownership:
            contact["ownership_status"] = ownership
        if freshness:
            contact["route_freshness"] = freshness
        if suppression:
            contact["route_suppression"] = suppression
        if epistemic:
            contact["provenance_class"] = epistemic

        raw_provenance = contact.get("provenance")
        provenance = dict(raw_provenance) if isinstance(raw_provenance, dict) else {}
        if source_type:
            provenance.setdefault("source_type", source_type)
        if source_url:
            provenance.setdefault("source_url", source_url)
        if observed_at:
            provenance.setdefault("observed_at", observed_at)
        if evidence_ids:
            provenance.setdefault("evidence_ids", evidence_ids)
        if epistemic:
            provenance.setdefault("epistemic_class", epistemic)
        if provenance:
            contact["provenance"] = provenance
        enriched.append(contact)
    return enriched


def attach_projection_evidence(
    projection: dict[str, Any],
    *,
    account: dict[str, Any],
) -> dict[str, Any]:
    """Return an auditable projection; safe to apply repeatedly."""
    result = dict(projection)
    result["contacts"] = attach_route_evidence(
        [dict(item) for item in (projection.get("contacts") or []) if isinstance(item, dict)],
        account=account,
    )
    preferred = projection.get("preferred_initial_route")
    if isinstance(preferred, dict):
        joined = attach_route_evidence(
            [{**preferred, "email": preferred.get("mailbox")}],
            account=account,
        )
        if joined:
            result["preferred_initial_route"] = joined[0]
    return result
