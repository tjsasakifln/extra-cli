"""Builders for cryptographically self-consistent recipient evidence fixtures."""

from __future__ import annotations

from scripts.decision_unit_intelligence.evidence import make_evidence
from scripts.decision_unit_intelligence.models import EpistemicClass


def exact_page_attestation(
    *,
    account: str,
    mailbox: str,
    source_url: str,
    observed_at: str,
    page_sha256: str,
    binding_context: str = "official_domain_mailbox",
) -> dict:
    """Return the exact fields emitted by an official-site evidence producer."""

    email_snippet = f"Contato: {mailbox}"
    email_evidence = make_evidence(
        field="email",
        value=mailbox,
        epistemic_class=EpistemicClass.OBSERVED,
        source_type="company_website",
        source_url=source_url,
        document_sha256=page_sha256,
        evidence_snippet=email_snippet,
        observed_at=observed_at,
        extraction_method="public_page_exact_text",
    )
    binding_evidence = make_evidence(
        field="account_mailbox_binding",
        value=f"{account}|{mailbox}",
        epistemic_class=EpistemicClass.OBSERVED,
        source_type="company_website",
        source_url=source_url,
        document_sha256=page_sha256,
        evidence_snippet=f"CNPJ {account} | {email_snippet}",
        observed_at=observed_at,
        extraction_method=f"official_page_exact_cnpj_and_email:{binding_context}",
        extra={
            "page_cnpj14": account,
            "page_content_sha256": page_sha256,
            "email_evidence_id": email_evidence.evidence_id,
        },
    )
    return {
        "evidence_ids": [binding_evidence.evidence_id],
        "page_cnpj14": account,
        "page_cnpj_evidence_id": binding_evidence.evidence_id,
        "page_cnpj_evidence_sha256": page_sha256,
        "account_mailbox_binding_evidence": binding_evidence.to_dict(),
        "mailbox_observation_evidence": email_evidence.to_dict(),
    }
