"""Tier 5 optional external provider. Off by default. Never structural."""

from __future__ import annotations

from scripts.decision_unit_intelligence.models import SearchAttempt, normalize_cnpj, stable_id
from scripts.decision_unit_intelligence.providers.base import InvestigationContext, ProviderResult


class ExternalEnrichmentProvider:
    provider_id = "external_enrichment"
    tier = 5

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def collect(self, context: InvestigationContext) -> ProviderResult:
        cnpj = normalize_cnpj(context.cnpj)
        if not self.enabled:
            return ProviderResult(
                attempts=[
                    SearchAttempt(
                        attempt_id=stable_id("att", self.provider_id, cnpj),
                        company_entity_id=cnpj,
                        tier=5,
                        provider_id=self.provider_id,
                        source="external",
                        status="skipped",
                        reason="provider_disabled",
                    )
                ],
                terminal="skipped",
            )
        return ProviderResult(
            attempts=[
                SearchAttempt(
                    attempt_id=stable_id("att", self.provider_id, cnpj, "on"),
                    company_entity_id=cnpj,
                    tier=5,
                    provider_id=self.provider_id,
                    source="external",
                    status="skipped",
                    reason="no_provider_configured",
                )
            ],
            terminal="skipped",
        )
