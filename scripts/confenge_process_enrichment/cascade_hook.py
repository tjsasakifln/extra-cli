"""Optional hook to feed process-first extracts into confenge_contact_resolution.

When confenge_contact_resolution is present (integration worktree / merge),
call ``public_docs_from_enrichment`` to populate AdapterContext.public_docs.
"""

from __future__ import annotations

from typing import Any

from scripts.confenge_process_enrichment.models import AccountEnrichmentResult, EpistemicClass
from scripts.confenge_process_enrichment.pipeline import ProcessFirstConfig, ProcessFirstEnricher


def public_docs_from_enrichment(result: AccountEnrichmentResult) -> list[dict[str, Any]]:
    """Shape process-first observations for PublicDocsAdapter / datalake_docs."""
    out: list[dict[str, Any]] = []
    graph = result.contact_graph
    if not graph:
        return out
    for person in graph.people:
        for obs in person.observations:
            if obs.epistemic_class in {
                EpistemicClass.PUBLIC_OFFICIAL,
                EpistemicClass.OTHER_BIDDER,
                EpistemicClass.UNKNOWN_ENTITY,
            }:
                continue
            if obs.pattern_guessed:
                continue
            if not obs.email and not obs.phone:
                continue
            out.append(
                {
                    "email": obs.email,
                    "phone": obs.phone,
                    "name": obs.person_name,
                    "cargo": obs.role_observed,
                    "url": obs.source_url,
                    "document_id": obs.source_document_id,
                    "doc_type": obs.document_type or "process_document",
                    "source_date": obs.observation_date,
                    "evidence_strength": "company_authored_document"
                    if obs.epistemic_class == EpistemicClass.COMPANY_DECLARED
                    else "document_contact",
                    "cnpj14": result.account_cnpj,
                    "epistemic_class": obs.epistemic_class.value,
                    "evidence_text_hash": obs.evidence_text_hash,
                }
            )
    for m in graph.functional_mailboxes:
        if m.email:
            out.append(
                {
                    "email": m.email,
                    "phone": m.phone,
                    "name": None,
                    "cargo": m.role_observed,
                    "url": m.source_url,
                    "document_id": m.source_document_id,
                    "doc_type": m.document_type or "process_document",
                    "source_date": m.observation_date,
                    "evidence_strength": "document_contact",
                    "cnpj14": result.account_cnpj,
                    "epistemic_class": m.epistemic_class.value,
                    "evidence_text_hash": m.evidence_text_hash,
                }
            )
    return out


def enrich_public_docs_for_cnpj(
    cnpj14: str,
    *,
    razao_social: str | None = None,
    contracts: list[dict[str, Any]] | None = None,
    allow_network: bool = False,
    dsn: str | None = None,
    document_texts: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], AccountEnrichmentResult]:
    """Run process-first enrichment and return PublicDocs-shaped extracts."""
    enricher = ProcessFirstEnricher(
        config=ProcessFirstConfig(allow_network=allow_network, dsn=dsn)
    )
    result = enricher.enrich(
        account_cnpj=cnpj14,
        razao_social=razao_social,
        contracts=contracts,
        document_texts=document_texts,
    )
    return public_docs_from_enrichment(result), result
