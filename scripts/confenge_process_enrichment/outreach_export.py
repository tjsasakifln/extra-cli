"""Map process-first contacts into confenge.outreach.v1 compatible fields.

Privacy: no CPF, residential address, or raw process documents.
"""

from __future__ import annotations

from typing import Any

from scripts.confenge_process_enrichment.attribution import is_exportable_to_warmbly
from scripts.confenge_process_enrichment.contact_graph import select_best_for_service
from scripts.confenge_process_enrichment.contact_extract import is_functional_mailbox
from scripts.confenge_process_enrichment.models import (
    AccountContactGraph,
    AccountEnrichmentResult,
    ContactObservation,
    EpistemicClass,
)


FORBIDDEN_EXPORT_KEYS = frozenset(
    {
        "cpf",
        "cpf_internal",
        "rg",
        "residential_address",
        "endereco_residencial",
        "data_nascimento",
        "birth_date",
        "bank_account",
        "dados_bancarios",
        "signature_image",
        "raw_document",
        "extracted_full_text",
    }
)


def _safe_contact_payload(
    *,
    person_name: str | None,
    role_observed: str | None,
    normalized_role: str | None,
    email: str | None,
    phone: str | None,
    contact_class: str,
    contact_confidence: float,
    freshness: float,
    source_type: str,
    source_document_type: str | None,
    source_observed_at: str | None,
    provenance_id: str | None,
    referral_route: bool,
    contact_priority_by_service: dict[str, float] | None = None,
    epistemic_class: str | None = None,
) -> dict[str, Any]:
    payload = {
        "person_name": person_name,
        "role_observed": role_observed,
        "normalized_role": normalized_role,
        "role_confidence": contact_confidence,
        "email": email,
        "phone": phone,
        "contact_class": contact_class,
        "contact_confidence": contact_confidence,
        "freshness": freshness,
        "source_type": source_type,
        "source_document_type": source_document_type,
        "source_observed_at": source_observed_at,
        "provenance_id": provenance_id,
        "referral_route": referral_route,
        "contact_priority_by_service": contact_priority_by_service or {},
        "epistemic_class": epistemic_class,
    }
    # Strip forbidden keys if any slipped in
    for k in list(payload.keys()):
        if k in FORBIDDEN_EXPORT_KEYS:
            del payload[k]
    return payload


def observation_to_outreach(obs: ContactObservation) -> dict[str, Any] | None:
    if obs.pattern_guessed:
        return None
    if not is_exportable_to_warmbly(obs.epistemic_class):
        return None
    if not obs.email and not obs.phone:
        return None
    return _safe_contact_payload(
        person_name=obs.person_name,
        role_observed=obs.role_observed,
        normalized_role=obs.role_observed,
        email=obs.email,
        phone=obs.phone,
        contact_class="functional_mailbox"
        if obs.email and is_functional_mailbox(obs.email) and not obs.person_name
        else "named_or_channel",
        contact_confidence=0.7 if obs.epistemic_class == EpistemicClass.COMPANY_DECLARED else 0.6,
        freshness=1.0,
        source_type="public_process_document",
        source_document_type=obs.document_type,
        source_observed_at=obs.observation_date,
        provenance_id=obs.evidence_text_hash or obs.source_document_id,
        referral_route=bool(obs.email and is_functional_mailbox(obs.email) and not obs.person_name),
        epistemic_class=obs.epistemic_class.value,
    )


def graph_to_outreach_contacts(graph: AccountContactGraph) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for person in graph.people:
        if not person.emails and not person.phones:
            continue
        if person.epistemic_best and not is_exportable_to_warmbly(person.epistemic_best):
            continue
        email = person.emails[0] if person.emails else None
        # DNC/bounce already filtered at graph build for rejected; double-check extra flags
        if any(o.extra.get("dnc") or o.extra.get("bounce") for o in person.observations):
            continue
        out.append(
            _safe_contact_payload(
                person_name=person.name,
                role_observed=person.roles[0] if person.roles else None,
                normalized_role=person.roles[0] if person.roles else None,
                email=email,
                phone=person.phones[0] if person.phones else None,
                contact_class="named_person",
                contact_confidence=person.confidence,
                freshness=person.role_freshness,
                source_type="public_process_document",
                source_document_type=(person.observations[0].document_type if person.observations else None),
                source_observed_at=person.newest_source_date,
                provenance_id=person.person_key,
                referral_route=False,
                contact_priority_by_service={
                    svc: (select_best_for_service(graph, svc) or {}).get("confidence", 0)
                    for svc in ("reajuste", "orcamento", "diretoria_b2g", "generic")
                },
                epistemic_class=person.epistemic_best,
            )
        )
    for m in graph.functional_mailboxes:
        row = observation_to_outreach(m)
        if row:
            out.append(row)
    return out


def assert_no_forbidden_pii(payload: dict[str, Any]) -> None:
    """Raise if forbidden PII keys appear anywhere in a nested payload."""

    def walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k).lower()
                if key in FORBIDDEN_EXPORT_KEYS or key.endswith("_cpf") or key == "cpf":
                    raise AssertionError(f"Forbidden PII key at {path}.{k}")
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")

    walk(payload)


def enrich_outreach_record(
    base: dict[str, Any],
    result: AccountEnrichmentResult,
) -> dict[str, Any]:
    """Backward-compatible enrichment of a confenge.outreach.v1 account record."""
    out = dict(base)
    contacts = result.outreach_contacts or (
        graph_to_outreach_contacts(result.contact_graph) if result.contact_graph else []
    )
    out["process_first"] = {
        "investigation_state": result.investigation_state.value,
        "terminal_state": result.terminal_state.value,
        "funnel_flags": result.funnel_flags,
        "blockers": result.blockers,
        "research_gaps": result.research_gaps,
        "best_contacts_by_service": result.best_contacts_by_service,
        "referral_routes": result.referral_routes,
    }
    out["contacts"] = contacts
    out["contact_lineage_schema"] = "confenge.process_first_contact.v1"
    assert_no_forbidden_pii(out)
    return out
