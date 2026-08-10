"""Process-first harvest source types must count as company-document ownership proof."""

from __future__ import annotations

from scripts.confenge_contact_resolution.models import (
    ContactCandidate,
    SourceProvenance,
    VerificationStatus,
)
from scripts.confenge_contact_resolution.ownership import OwnershipContext, resolve_ownership


def test_public_process_document_with_brand_domain_is_company_owned() -> None:
    cand = ContactCandidate(
        candidate_id="t1",
        cnpj14="32475769000100",
        account_key="cnpj_root:32475769",
        email="contato@construtoraalvorada.com.br",
        source=SourceProvenance(
            source_type="public_process_document",
            source_url="https://pncp.gov.br/pncp-api/v1/orgaos/x/arquivos/1",
        ),
        verification_status=VerificationStatus.OBSERVED.value,
        found_on_company_document=True,
    )
    ctx = OwnershipContext(
        cnpj14="32475769000100",
        razao_social="CONSTRUTORA ALVORADA LTDA",
    )
    result = resolve_ownership(cand, ctx=ctx)
    assert result.ownership_status == "COMPANY_OWNED"
    assert result.enrollable is True
