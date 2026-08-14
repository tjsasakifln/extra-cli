"""Bounded cascade runner used by the CLI."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from scripts.decision_unit_intelligence.models import SearchLedger, normalize_cnpj
from scripts.decision_unit_intelligence.orchestrator import investigate_account
from scripts.decision_unit_intelligence.providers.administrative_process import AdministrativeProcessProvider
from scripts.decision_unit_intelligence.providers.base import InvestigationContext
from scripts.decision_unit_intelligence.providers.company_website import CompanyWebsiteProvider
from scripts.decision_unit_intelligence.providers.existing_datalake import ExistingDatalakeProvider
from scripts.decision_unit_intelligence.providers.external_enrichment import ExternalEnrichmentProvider
from scripts.decision_unit_intelligence.providers.historical_campaign import HistoricalCampaignProvider
from scripts.decision_unit_intelligence.providers.official_documents import OfficialDocumentsProvider
from scripts.decision_unit_intelligence.providers.public_search import PublicSearchProvider

_SHARED_HISTORICAL: HistoricalCampaignProvider | None = None


def default_providers(*, external_enabled: bool = False) -> list[Any]:
    global _SHARED_HISTORICAL
    if _SHARED_HISTORICAL is None:
        _SHARED_HISTORICAL = HistoricalCampaignProvider()
    return [
        _SHARED_HISTORICAL,
        ExistingDatalakeProvider(),
        AdministrativeProcessProvider(),
        OfficialDocumentsProvider(),
        CompanyWebsiteProvider(),
        PublicSearchProvider(),
        ExternalEnrichmentProvider(enabled=external_enabled),
    ]


def run_account(
    cnpj: str,
    *,
    service: str = "reajuste_14133",
    providers: list[Any] | None = None,
    infer_email: bool = True,
) -> Any:
    started = perf_counter()
    ctx = InvestigationContext(cnpj=normalize_cnpj(cnpj), service=service)
    providers = providers or default_providers()
    people = []
    channels = []
    ledger = SearchLedger()
    legal_name = None
    why_now = None
    site = None
    blocked = False
    for provider in providers:
        try:
            result = provider.collect(ctx)
        except Exception as exc:
            ledger.blocked_sources.append(f"{provider.provider_id}:{type(exc).__name__}")
            ledger.provider_attempts += 1
            continue
        people.extend(result.people)
        channels.extend(result.channels)
        ledger.attempts.extend(result.attempts)
        ledger.provider_attempts += len(result.attempts)
        ledger.documents_checked += sum(a.documents_checked for a in result.attempts)
        ledger.search_queries.extend([q for a in result.attempts for q in a.queries])
        if any(a.blocked for a in result.attempts):
            ledger.blocked_sources.append(provider.provider_id)
            # A blocked source is not R0 and not exhaustion.
            if provider.tier <= 1 and not people and not channels:
                blocked = True
        if result.legal_name:
            legal_name = result.legal_name
        if result.why_now:
            why_now = result.why_now
        if result.company_site:
            site = result.company_site
        ledger.tiers_completed.append(provider.tier)
        ledger.known_evidence_checked += len(result.people) + len(result.channels)
        # Positive stop: we already have a named person and a channel.
        if people and channels:
            break
    ledger.duration_ms = int((perf_counter() - started) * 1000)
    return investigate_account(
        cnpj=cnpj,
        legal_name=legal_name,
        service=ctx.service,
        why_now=why_now,
        people=people,
        channels=channels,
        ledger=ledger,
        company_site=site,
        infer_email=infer_email,
        blocked=blocked,
    )
