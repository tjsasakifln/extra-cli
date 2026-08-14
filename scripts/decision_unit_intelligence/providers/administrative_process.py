"""Optional wrapper around confenge_process_enrichment. Isolated import failure."""

from __future__ import annotations

from scripts.decision_unit_intelligence.models import SearchAttempt, normalize_cnpj, stable_id
from scripts.decision_unit_intelligence.providers.base import InvestigationContext, ProviderResult


class AdministrativeProcessProvider:
    provider_id = "administrative_process"
    tier = 1

    def collect(self, context: InvestigationContext) -> ProviderResult:
        cnpj = normalize_cnpj(context.cnpj)
        try:
            from scripts.confenge_process_enrichment import pipeline as _pe  # noqa: F401
        except Exception as exc:
            return ProviderResult(
                attempts=[
                    SearchAttempt(
                        attempt_id=stable_id("att", self.provider_id, cnpj),
                        company_entity_id=cnpj,
                        tier=1,
                        provider_id=self.provider_id,
                        source="confenge_process_enrichment",
                        status="skipped",
                        reason=f"module_unavailable:{type(exc).__name__}",
                    )
                ],
                terminal="skipped",
            )
        return ProviderResult(
            attempts=[
                SearchAttempt(
                    attempt_id=stable_id("att", self.provider_id, cnpj, "avail"),
                    company_entity_id=cnpj,
                    tier=1,
                    provider_id=self.provider_id,
                    source="confenge_process_enrichment",
                    status="skipped",
                    reason="live_fetch_not_in_track_a_budget",
                )
            ],
            terminal="skipped",
        )
