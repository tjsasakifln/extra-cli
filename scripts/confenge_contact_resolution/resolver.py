"""Orchestrate adapters → merge → rank for one or many CNPJs."""

from __future__ import annotations

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_contact_resolution.adapters.base import AdapterContext, ContactAdapter
from scripts.confenge_contact_resolution.adapters.contact_pages import ContactPageAdapter
from scripts.confenge_contact_resolution.adapters.public_docs import PublicDocsAdapter
from scripts.confenge_contact_resolution.adapters.registry import RegistryAdapter
from scripts.confenge_contact_resolution.adapters.site import SiteAdapter
from scripts.confenge_contact_resolution.adapters.web_search import NoOpWebSearchProvider, WebSearchAdapter
from scripts.confenge_contact_resolution.cache import ResolutionCache, cache_key
from scripts.confenge_contact_resolution.email_policy import domain_of
from scripts.confenge_contact_resolution.merge import (
    account_block_from_observations,
    observations_to_candidates,
)
from scripts.confenge_contact_resolution.models import (
    SCHEMA_VERSION,
    AccountContactResolution,
    CommercialContactState,
    CompanyProcessingState,
    OwnershipStatus,
    ServiceContext,
)
from scripts.confenge_contact_resolution.ownership import (
    OwnershipContext,
    apply_ownership_to_candidate,
    commercial_state_for_resolution,
    domain_from_url,
    rejected_contact_dict,
    resolve_ownership,
)
from scripts.confenge_contact_resolution.ranking import select_recommended
from scripts.confenge_contact_resolution.reuse_graph import ContactReuseGraph
from scripts.confenge_contact_resolution.role_map import is_small_firm_porte
from scripts.confenge_contact_resolution.third_party_registry import ThirdPartyRegistry


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")[:14]


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_adapters(
    *,
    web_search_enabled: bool = False,
    web_search_provider=None,
    registry_prefer_network: bool = False,
) -> list[ContactAdapter]:
    provider = web_search_provider
    if web_search_enabled and provider is None:
        try:
            from scripts.confenge_contact_resolution.discovery.web_search_providers import (
                build_web_search_provider,
            )

            provider = build_web_search_provider()
        except Exception:  # noqa: BLE001
            provider = NoOpWebSearchProvider()
    return [
        RegistryAdapter(prefer_network=registry_prefer_network),
        SiteAdapter(),
        PublicDocsAdapter(),
        ContactPageAdapter(),
        WebSearchAdapter(
            provider=provider or NoOpWebSearchProvider(),
            enabled=web_search_enabled,
        ),
    ]


@dataclass
class ResolverConfig:
    service_context: str = ServiceContext.GENERIC.value
    adapters: list[ContactAdapter] = field(default_factory=default_adapters)
    cache: ResolutionCache | None = None
    check_mx: bool = False
    mx_resolver: Callable[[str], bool] | None = None
    allow_network: bool = False
    fixtures_dir: Path | None = None
    max_workers: int = 4
    # Injected per-CNPJ context builders for tests
    context_builder: Callable[[str], AdapterContext] | None = None
    # Ownership / anti-false-positive infrastructure (shared across batch)
    reuse_graph: ContactReuseGraph | None = None
    third_party_registry: ThirdPartyRegistry | None = None
    # When False, skip ownership gate (legacy tests only; production always True)
    apply_ownership: bool = True
    # Optional discovery cascade (production enrich-batch wires this)
    discovery_cascade: Any | None = None
    # Job metadata lookup: cnpj14 → {razao_social, economic_group_id, ...}
    job_meta: dict[str, dict[str, Any]] = field(default_factory=dict)


class ContactResolver:
    def __init__(self, config: ResolverConfig | None = None) -> None:
        self.config = config or ResolverConfig()
        self.reuse_graph = self.config.reuse_graph or ContactReuseGraph()
        self.third_party_registry = self.config.third_party_registry or ThirdPartyRegistry()

    def _adapters_sig(self) -> str:
        # Include every result-shaping input so stale evidence or a smaller
        # discovery budget can never poison a later authoritative run.
        names = ",".join(getattr(a, "name", type(a).__name__) for a in self.config.adapters)
        net = "1" if self.config.allow_network else "0"
        prefer = "1" if any(getattr(a, "prefer_network", False) for a in self.config.adapters) else "0"
        cascade = self.config.discovery_cascade
        budget = getattr(cascade, "budget", None)
        budget_sig = ",".join(
            str(getattr(budget, key, ""))
            for key in (
                "max_search_queries",
                "max_pages",
                "max_total_requests",
                "max_seconds",
                "max_bytes_per_page",
                "max_pages_per_domain",
            )
        )
        return (
            f"schema={SCHEMA_VERSION}|{names}|net={net}|prefer={prefer}"
            f"|mx={int(self.config.check_mx)}|budget={budget_sig}"
        )

    def resolve_one(
        self,
        cnpj: str,
        *,
        account_key: str | None = None,
        ctx: AdapterContext | None = None,
    ) -> AccountContactResolution:
        cnpj14 = _digits(cnpj)
        key = account_key or cnpj14
        resolved_at = _now()
        base = AccountContactResolution(
            cnpj14=cnpj14,
            account_key=key,
            service_context=self.config.service_context,
            resolved_at=resolved_at,
        )
        if len(cnpj14) != 14:
            base.absence_reason = "invalid_cnpj"
            base.limitations.append("CNPJ must have 14 digits")
            return base

        ck = cache_key(cnpj14, self.config.service_context, self._adapters_sig())
        if self.config.cache:
            hit = self.config.cache.get(ck)
            if hit is not None:
                hit["cache_hit"] = True
                # rebuild lightly from dict
                return _resolution_from_dict(hit)

        job_meta = (self.config.job_meta or {}).get(cnpj14) or {}
        economic_group_id = job_meta.get("economic_group_id") or job_meta.get("grupo_economico_id")
        razao_hint = job_meta.get("razao_social") or job_meta.get("company_name")
        fantasia_hint = job_meta.get("nome_fantasia") or job_meta.get("trade_name")

        if ctx is None and self.config.context_builder:
            ctx = self.config.context_builder(cnpj14)
        if ctx is None:
            ctx = AdapterContext(
                cnpj14=cnpj14,
                fixtures_dir=self.config.fixtures_dir,
                allow_network=self.config.allow_network,
            )
        else:
            ctx.cnpj14 = cnpj14
            if self.config.fixtures_dir and ctx.fixtures_dir is None:
                ctx.fixtures_dir = self.config.fixtures_dir
            ctx.allow_network = self.config.allow_network or ctx.allow_network

        # Production cascade: auto-fill site/docs/web before adapters (no manual injection)
        discovery_meta: dict[str, Any] = {}
        if self.config.discovery_cascade is not None and not self.config.fixtures_dir:
            try:
                cres = self.config.discovery_cascade.run(
                    cnpj14=cnpj14,
                    razao_social=razao_hint,
                    nome_fantasia=fantasia_hint,
                    registry_record=ctx.registry_record,
                    existing_ctx=ctx,
                    economic_group_id=str(economic_group_id) if economic_group_id else None,
                )
                ctx = cres.ctx
                discovery_meta = cres.as_meta()
                base.investigation_outcome = cres.stats.outcome
                base.discovery_stats = cres.stats.as_dict()
                base.domain_class = cres.domain.domain_class
                if cres.domain.domain and cres.domain.is_company_owned_eligible():
                    base.official_domain = cres.domain.domain
            except Exception as exc:  # noqa: BLE001 — discovery soft-fail
                base.limitations.append(f"discovery_error:{type(exc).__name__}")
                base.investigation_outcome = "ERROR"

        if economic_group_id:
            base.economic_group_id = str(economic_group_id)
            ctx.extra["economic_group_id"] = str(economic_group_id)

        observations = []
        used: list[str] = []
        skipped: list[str] = []
        razao = None
        porte = None
        mei = None
        cascade_stage = CompanyProcessingState.LOCAL_SEARCH.value
        base.processing_state = cascade_stage

        # Cascade layers: local/registry → official pages/docs → public web
        local_adapters = {"registry"}
        official_adapters = {"site", "public_docs", "contact_page"}
        public_adapters = {"web_search"}

        for adapter in self.config.adapters:
            name = getattr(adapter, "name", type(adapter).__name__)
            if name in local_adapters:
                cascade_stage = CompanyProcessingState.LOCAL_SEARCH.value
            elif name in official_adapters:
                cascade_stage = CompanyProcessingState.OFFICIAL_WEB_SEARCH.value
            elif name in public_adapters:
                cascade_stage = CompanyProcessingState.PUBLIC_WEB_SEARCH.value
            base.processing_state = cascade_stage
            try:
                obs = adapter.collect(ctx)
            except Exception as exc:  # noqa: BLE001 — fail soft per adapter
                skipped.append(f"{name}:error:{type(exc).__name__}")
                continue
            if obs:
                used.append(name)
                observations.extend(obs)
                for o in obs:
                    if o.razao_social and not razao:
                        razao = o.razao_social
                    if o.company_size and not porte:
                        porte = o.company_size
            else:
                skipped.append(f"{name}:empty")

        # Registry record porte for small firm
        if ctx.registry_record:
            porte = porte or ctx.registry_record.get("company_size") or ctx.registry_record.get("porte")
            mei = ctx.registry_record.get("mei")
            razao = razao or ctx.registry_record.get("legal_name") or ctx.registry_record.get("razao_social")

        small = is_small_firm_porte(str(porte) if porte else None, mei=mei if isinstance(mei, bool) else None)
        account_dnc, account_bounce, account_block_reason = account_block_from_observations(observations)
        candidates = observations_to_candidates(
            observations,
            cnpj14=cnpj14,
            account_key=key,
            check_mx=self.config.check_mx,
            mx_resolver=self.config.mx_resolver,
        )

        fantasia = None
        official_domain = base.official_domain  # may be set by discovery cascade
        if ctx.extra.get("official_domain") and not official_domain:
            official_domain = str(ctx.extra["official_domain"])
        if ctx.registry_record:
            fantasia = ctx.registry_record.get("nome_fantasia") or ctx.registry_record.get("trade_name")
            site_raw = ctx.registry_record.get("site") or ctx.registry_record.get("website")
            if not official_domain:
                official_domain = domain_from_url(str(site_raw) if site_raw else None)
        for o in observations:
            if o.nome_fantasia and not fantasia:
                fantasia = o.nome_fantasia
        if not razao and razao_hint:
            razao = str(razao_hint)
        # official_domain only from company-aligned hosts — never from an arbitrary
        # observation.site (third-party accounting pages must not become "official").
        company_label = " ".join(x for x in (razao or "", str(fantasia) if fantasia else "") if x)
        if not official_domain:
            from scripts.confenge_contact_resolution.ownership import (
                detect_third_party_type,
                domain_token_overlap,
            )

            for o in observations:
                if not o.site:
                    continue
                host = domain_from_url(o.site)
                if not host:
                    continue
                tp, _ = detect_third_party_type(host)
                if tp:
                    continue  # never promote third-party host to official_domain
                if company_label and domain_token_overlap(host, company_label) >= 0.35:
                    official_domain = host
                    break

        if self.config.apply_ownership:
            candidates, rejected = self._apply_ownership_pass(
                candidates,
                cnpj14=cnpj14,
                razao_social=razao,
                nome_fantasia=str(fantasia) if fantasia else None,
                official_domain=official_domain,
                observations=observations,
                economic_group_id=str(economic_group_id) if economic_group_id else None,
            )
        else:
            rejected = []

        ranked, rec_id = select_recommended(
            candidates,
            service_context=self.config.service_context,
            small_firm=small,
            account_dnc=account_dnc,
            account_bounce=account_bounce,
        )

        # Prefer enrollable recommended; if ranker picked non-enrollable and an
        # enrollable exists, re-point recommendation for Warmbly feed safety.
        if rec_id and self.config.apply_ownership:
            rec_c = next((c for c in ranked if c.candidate_id == rec_id), None)
            if rec_c and not rec_c.enrollable:
                alt = next((c for c in ranked if c.enrollable and not c.dnc and not c.bounce), None)
                if alt:
                    if rec_c:
                        rec_c.recommended = False
                        rec_c.recommendation_reason = None
                    alt.recommended = True
                    alt.recommendation_reason = (
                        f"Enrollable COMPANY_OWNED preferred over non-enrollable; "
                        f"role_class={alt.role_class}; ownership={alt.ownership_status}"
                    )
                    rec_id = alt.candidate_id
                else:
                    # No enrollable: keep ranking for human review but mark limitation
                    pass

        proc_state, comm_state = commercial_state_for_resolution(ranked, rejected)

        base.razao_social = razao
        base.nome_fantasia = str(fantasia) if fantasia else None
        base.official_domain = official_domain
        base.small_firm = small
        base.candidates = ranked
        base.rejected_contacts = rejected
        base.recommended_candidate_id = rec_id
        base.processing_state = proc_state
        base.commercial_contact_state = comm_state
        base.adapters_used = used
        base.adapters_skipped = skipped
        if account_dnc or account_bounce:
            base.limitations.append(f"account_block:{account_block_reason or ('DNC' if account_dnc else 'bounce')}")
        if not ranked and not rejected:
            base.absence_reason = "no_public_business_contact_found"
            # Budget/search exhausted must stay NO_CONTACT_YET commercially, not discard
            inv = base.investigation_outcome or ""
            if inv in {"BUDGET_EXHAUSTED", "SEARCH_EXHAUSTED", "RETRY_LATER", "ERROR"}:
                base.processing_state = (
                    CompanyProcessingState.RETRY_LATER.value
                    if inv in {"BUDGET_EXHAUSTED", "RETRY_LATER", "ERROR"}
                    else CompanyProcessingState.NO_CONTACT.value
                )
                base.commercial_contact_state = CommercialContactState.NO_CONTACT_YET.value
                base.limitations.append(f"investigation_outcome:{inv}")
            else:
                base.processing_state = CompanyProcessingState.NO_CONTACT.value
                base.commercial_contact_state = CommercialContactState.NO_CONTACT_YET.value
            base.limitations.append("Absence remains absence — no fabricated contacts")
            if not base.investigation_outcome:
                base.investigation_outcome = "NO_CONTACT_YET"
        elif not any(c.enrollable for c in ranked):
            if not base.absence_reason and not ranked:
                base.absence_reason = "no_public_business_contact_found"
            elif ranked and not any(c.enrollable for c in ranked):
                base.limitations.append("candidates_present_but_none_enrollable_after_ownership_resolution")
            if not base.investigation_outcome:
                base.investigation_outcome = "CONTACT_FOUND"
        else:
            if not base.investigation_outcome:
                base.investigation_outcome = "CONTACT_FOUND"
        if discovery_meta:
            base.discovery_stats = {**(base.discovery_stats or {}), **(discovery_meta.get("discovery_stats") or {})}
        if self.config.cache:
            self.config.cache.set(ck, base.as_dict())
        return base

    def _apply_ownership_pass(
        self,
        candidates: list,
        *,
        cnpj14: str,
        razao_social: str | None,
        nome_fantasia: str | None,
        official_domain: str | None,
        observations: list,
        economic_group_id: str | None = None,
    ) -> tuple[list, list[dict]]:
        """Run ownership resolver + reuse graph; split rejected third-party contacts."""
        from scripts.confenge_contact_resolution.models import ContactCandidate

        # Seed graph with this company's channels first (for same-company multi-cand)
        self.reuse_graph.register_company(
            cnpj14,
            razao_social=razao_social,
            economic_group_id=economic_group_id,
        )
        for c in candidates:
            self.reuse_graph.observe_candidate(
                cnpj14,
                email=c.email,
                phone=c.phone_e164 or c.phone_raw,
                domain=domain_of(c.email) if c.email else None,
                razao_social=razao_social,
                economic_group_id=economic_group_id,
            )

        # Context text from observations (pages/docs) for third-party lexicon
        context_blob = " ".join(
            filter(
                None,
                [getattr(o, "context_text", None) or (o.source.notes if o.source else None) for o in observations],
            )
        )
        art_flags = {(o.email or "").lower(): bool(getattr(o, "art_crea_only", False)) for o in observations}

        octx = OwnershipContext(
            cnpj14=cnpj14,
            razao_social=razao_social,
            nome_fantasia=nome_fantasia,
            official_domain=official_domain,
            economic_group_id=economic_group_id,
        )

        kept: list[ContactCandidate] = []
        rejected: list[dict] = []

        for c in candidates:
            reuse = self.reuse_graph.best_signal(
                cnpj14,
                email=c.email,
                phone=c.phone_e164 or c.phone_raw,
                domain=domain_of(c.email) if c.email else None,
            )
            reg_hit = self.third_party_registry.lookup(
                domain=domain_of(c.email) if c.email else None,
                email=c.email,
                phone=c.phone_e164 or c.phone_raw,
            )
            art_only = bool(art_flags.get((c.email or "").lower())) or ("art_crea_only" in (c.limitations or []))
            result = resolve_ownership(
                c,
                ctx=octx,
                reuse=reuse,
                registry_hit=reg_hit,
                context_text=context_blob,
                art_crea_only=art_only,
                independent_sources_count=c.independent_sources_count,
            )
            apply_ownership_to_candidate(
                c,
                result,
                independent_sources_count=c.independent_sources_count,
                source_urls=list(c.source_urls or []),
                source_types=list(c.source_types or []),
            )

            # Grow third-party registry from hard rejects
            if c.ownership_status in {
                OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value,
                OwnershipStatus.SHARED_EXTERNAL_CONTACT.value,
            }:
                self.third_party_registry.register_from_rejection(
                    email=c.email,
                    phone=c.phone_e164 or c.phone_raw,
                    third_party_type=c.third_party_type
                    or ("OTHER" if c.ownership_status == OwnershipStatus.SHARED_EXTERNAL_CONTACT.value else None),
                    reason=c.ownership_reason,
                    cnpj14=cnpj14,
                )
                rejected.append(rejected_contact_dict(c))
                # Keep third-party out of primary candidates list when hard reject
                if c.ownership_status == OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value:
                    continue
                if c.ownership_status == OwnershipStatus.SHARED_EXTERNAL_CONTACT.value and not c.enrollable:
                    # Keep visibility for audit but not as positive candidate
                    continue

            kept.append(c)

        return kept, rejected

    def resolve_batch(
        self,
        cnpjs: list[str],
        *,
        max_workers: int | None = None,
    ) -> list[AccountContactResolution]:
        workers = max_workers if max_workers is not None else self.config.max_workers
        workers = max(1, min(workers, 16))
        results: dict[int, AccountContactResolution] = {}
        if workers == 1 or len(cnpjs) <= 1:
            return [self.resolve_one(c) for c in cnpjs]

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(self.resolve_one, c): i for i, c in enumerate(cnpjs)}
            for fut in as_completed(futs):
                i = futs[fut]
                try:
                    results[i] = fut.result()
                except Exception as exc:  # noqa: BLE001
                    c = cnpjs[i]
                    results[i] = AccountContactResolution(
                        cnpj14=_digits(c),
                        account_key=_digits(c),
                        absence_reason=f"resolver_error:{type(exc).__name__}",
                        resolved_at=_now(),
                        limitations=[str(exc)],
                    )
        return [results[i] for i in range(len(cnpjs))]


def _resolution_from_dict(d: dict[str, Any]) -> AccountContactResolution:
    """Best-effort rebuild for cache hits (ranking already applied)."""
    from scripts.confenge_contact_resolution.models import (
        ContactCandidate,
        EmailVerificationLayers,
        OwnershipStatus,
        SourceProvenance,
        WhatsAppBlock,
    )

    cands = []
    for cd in d.get("candidates") or []:
        src = cd.get("source") or {}
        layers = cd.get("email_layers") or {}
        wa = cd.get("whatsapp") or {}
        cands.append(
            ContactCandidate(
                candidate_id=cd.get("candidate_id") or "",
                cnpj14=cd.get("cnpj14") or d.get("cnpj14") or "",
                account_key=cd.get("account_key") or d.get("account_key") or "",
                name=cd.get("name"),
                cargo=cd.get("cargo"),
                role_class=cd.get("role_class") or "generic",
                email=cd.get("email"),
                email_display=cd.get("email_display"),
                phone_raw=cd.get("phone_raw"),
                phone_e164=cd.get("phone_e164"),
                phone_type=cd.get("phone_type") or "unknown",
                site=cd.get("site"),
                linkedin_public=cd.get("linkedin_public"),
                source=SourceProvenance(
                    **{
                        k: src.get(k)
                        for k in (
                            "source_type",
                            "source_url",
                            "source_document",
                            "source_date",
                            "source_published_at",
                            "observed_at",
                            "verified_at",
                            "evidence_sha256",
                            "notes",
                        )
                        if k in src or k == "source_type"
                    }
                ),
                verification_status=cd.get("verification_status") or "NOT_AVAILABLE",
                email_layers=EmailVerificationLayers(
                    syntactic_ok=layers.get("syntactic_ok"),
                    domain_ok=layers.get("domain_ok"),
                    mx_ok=layers.get("mx_ok"),
                    mx_checked=bool(layers.get("mx_checked")),
                    pattern_guessed=bool(layers.get("pattern_guessed")),
                ),
                confidence=float(cd.get("confidence") or 0),
                recommended=bool(cd.get("recommended")),
                recommendation_reason=cd.get("recommendation_reason"),
                freshness=float(cd.get("freshness") or 0.7),
                freshness_days=cd.get("freshness_days"),
                freshness_class=cd.get("freshness_class") or "UNKNOWN_DATE",
                dnc=bool(cd.get("dnc")),
                bounce=bool(cd.get("bounce")),
                dnc_reason=cd.get("dnc_reason"),
                whatsapp=WhatsAppBlock(
                    consent_status=wa.get("consent_status") or "UNKNOWN",
                    consent_provenance=wa.get("consent_provenance"),
                    e164=wa.get("e164"),
                ),
                rank_score=float(cd.get("rank_score") or 0),
                rank_explain=list(cd.get("rank_explain") or []),
                enrollable=bool(cd.get("enrollable")),
                epistemic_class=cd.get("epistemic_class") or "OBSERVED_PUBLIC",
                ownership_status=cd.get("ownership_status") or OwnershipStatus.UNRESOLVED.value,
                ownership_reason=cd.get("ownership_reason"),
                verification_reason=cd.get("verification_reason"),
                third_party_type=cd.get("third_party_type"),
                associated_company_count=int(cd.get("associated_company_count") or 1),
                independent_sources_count=int(cd.get("independent_sources_count") or 1),
                domain_matches_company=cd.get("domain_matches_company"),
                found_on_official_source=bool(cd.get("found_on_official_source")),
                found_on_company_document=bool(cd.get("found_on_company_document")),
                source_urls=list(cd.get("source_urls") or []),
                source_types=list(cd.get("source_types") or []),
                contact_type=cd.get("contact_type") or "UNKNOWN",
                limitations=list(cd.get("limitations") or []),
                email_explicitly_published=bool(cd.get("email_explicitly_published")),
                name_explicitly_published=bool(cd.get("name_explicitly_published")),
                role_explicitly_published=bool(cd.get("role_explicitly_published")),
                human_identity_evidence_valid=bool(cd.get("human_identity_evidence_valid")),
                identity_evidence_urls=list(cd.get("identity_evidence_urls") or []),
                evidence_sha256=cd.get("evidence_sha256"),
            )
        )
    # fix source default if empty
    for c in cands:
        if not c.source.source_type:
            c.source.source_type = "unknown"

    return AccountContactResolution(
        cnpj14=d.get("cnpj14") or "",
        account_key=d.get("account_key") or "",
        razao_social=d.get("razao_social"),
        nome_fantasia=d.get("nome_fantasia"),
        official_domain=d.get("official_domain"),
        service_context=d.get("service_context") or ServiceContext.GENERIC.value,
        small_firm=bool(d.get("small_firm")),
        candidates=cands,
        rejected_contacts=list(d.get("rejected_contacts") or []),
        recommended_candidate_id=d.get("recommended_candidate_id"),
        absence_reason=d.get("absence_reason"),
        processing_state=d.get("processing_state") or CompanyProcessingState.NOT_STARTED.value,
        commercial_contact_state=d.get("commercial_contact_state") or CommercialContactState.NO_CONTACT_YET.value,
        next_contact_resolution_at=d.get("next_contact_resolution_at"),
        adapters_used=list(d.get("adapters_used") or []),
        adapters_skipped=list(d.get("adapters_skipped") or []),
        cache_hit=bool(d.get("cache_hit")),
        resolved_at=d.get("resolved_at"),
        limitations=list(d.get("limitations") or []),
        investigation_outcome=d.get("investigation_outcome"),
        economic_group_id=d.get("economic_group_id"),
        domain_class=d.get("domain_class"),
        discovery_stats=dict(d.get("discovery_stats") or {}),
    )
