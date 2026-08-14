"""Tier 2 stub: official documents. Live fetch is budgeted separately."""

from __future__ import annotations

from scripts.decision_unit_intelligence.models import SearchAttempt, normalize_cnpj, stable_id
from scripts.decision_unit_intelligence.providers.base import InvestigationContext, ProviderResult


class OfficialDocumentsProvider:
    provider_id = "official_documents"
    tier = 2

    def collect(self, context: InvestigationContext) -> ProviderResult:
        cnpj = normalize_cnpj(context.cnpj)
        return ProviderResult(
            attempts=[
                SearchAttempt(
                    attempt_id=stable_id("att", self.provider_id, cnpj),
                    company_entity_id=cnpj,
                    tier=2,
                    provider_id=self.provider_id,
                    source="pncp_documents",
                    status="skipped",
                    reason="track_a_uses_existing_cache_first",
                )
            ],
            terminal="skipped",
        )
