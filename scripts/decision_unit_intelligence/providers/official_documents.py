"""Tier 2: public official documents. Additive evidence only; never EMAIL_VALIDATED."""

from __future__ import annotations

from scripts.decision_unit_intelligence.contact_discovery.public_documents import (
    DocumentBudget,
    mine_public_documents,
    query_from_context,
    to_provider_result,
)
from scripts.decision_unit_intelligence.providers.base import InvestigationContext, ProviderResult
from scripts.decision_unit_intelligence.web_discovery import SearchBackend, SearchBudget


class OfficialDocumentsProvider:
    provider_id = "official_documents"
    tier = 2
    first_class = False

    def __init__(
        self,
        *,
        backend: SearchBackend | None = None,
        budget: SearchBudget | DocumentBudget | None = None,
        fetcher=None,
        documents=None,
        enrich_campaign: bool = True,
    ) -> None:
        self.backend = backend
        self.fetcher = fetcher
        self.documents = documents
        self.enrich_campaign = enrich_campaign
        if isinstance(budget, DocumentBudget):
            self.doc_budget = budget
        elif isinstance(budget, SearchBudget):
            self.doc_budget = DocumentBudget(
                max_queries=budget.max_queries,
                max_results_per_query=budget.max_results_per_query,
                max_documents=budget.max_pages,
                max_bytes=budget.max_bytes,
                timeout_seconds=budget.timeout_seconds,
            )
        else:
            self.doc_budget = DocumentBudget()

    def collect(self, context: InvestigationContext) -> ProviderResult:
        query = query_from_context(context, budget=self.doc_budget)
        mined = mine_public_documents(
            query,
            backend=self.backend,
            fetcher=self.fetcher,
            documents=self.documents,
            enrich_campaign=self.enrich_campaign,
        )
        return to_provider_result(mined)
