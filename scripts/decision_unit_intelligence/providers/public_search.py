"""Tier 4 public search. Fail-fast when yield is structurally weak."""

from __future__ import annotations

from scripts.decision_unit_intelligence.models import SearchAttempt, normalize_cnpj, stable_id
from scripts.decision_unit_intelligence.providers.base import InvestigationContext, ProviderResult


class PublicSearchProvider:
    provider_id = "public_search"
    tier = 4

    def collect(self, context: InvestigationContext) -> ProviderResult:
        cnpj = normalize_cnpj(context.cnpj)
        return ProviderResult(
            attempts=[
                SearchAttempt(
                    attempt_id=stable_id("att", self.provider_id, cnpj),
                    company_entity_id=cnpj,
                    tier=4,
                    provider_id=self.provider_id,
                    source="public_search",
                    status="skipped",
                    reason="yield_fail_fast_aggregators_not_primary",
                    extra={"policy": "do_not_burn_budget_on_weak_aggregators"},
                )
            ],
            terminal="skipped",
        )
