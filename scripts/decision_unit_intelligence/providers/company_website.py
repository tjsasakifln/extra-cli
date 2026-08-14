"""Tier 3 stub: company website. Optional; never required for R3."""

from __future__ import annotations

from scripts.decision_unit_intelligence.models import SearchAttempt, normalize_cnpj, stable_id
from scripts.decision_unit_intelligence.providers.base import InvestigationContext, ProviderResult


class CompanyWebsiteProvider:
    provider_id = "company_website"
    tier = 3

    def collect(self, context: InvestigationContext) -> ProviderResult:
        cnpj = normalize_cnpj(context.cnpj)
        return ProviderResult(
            attempts=[
                SearchAttempt(
                    attempt_id=stable_id("att", self.provider_id, cnpj),
                    company_entity_id=cnpj,
                    tier=3,
                    provider_id=self.provider_id,
                    source="company_site",
                    status="skipped",
                    reason="site_already_in_tier0_when_known",
                )
            ],
            terminal="skipped",
        )
