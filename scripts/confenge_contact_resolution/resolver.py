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
from scripts.confenge_contact_resolution.merge import (
    account_block_from_observations,
    observations_to_candidates,
)
from scripts.confenge_contact_resolution.models import (
    AccountContactResolution,
    ServiceContext,
)
from scripts.confenge_contact_resolution.ranking import select_recommended
from scripts.confenge_contact_resolution.role_map import is_small_firm_porte


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
    return [
        RegistryAdapter(prefer_network=registry_prefer_network),
        SiteAdapter(),
        PublicDocsAdapter(),
        ContactPageAdapter(),
        WebSearchAdapter(
            provider=web_search_provider or NoOpWebSearchProvider(),
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


class ContactResolver:
    def __init__(self, config: ResolverConfig | None = None) -> None:
        self.config = config or ResolverConfig()

    def _adapters_sig(self) -> str:
        # Include network mode so offline empty results never poison online re-runs.
        names = ",".join(getattr(a, "name", type(a).__name__) for a in self.config.adapters)
        net = "1" if self.config.allow_network else "0"
        prefer = "1" if any(getattr(a, "prefer_network", False) for a in self.config.adapters) else "0"
        return f"{names}|net={net}|prefer={prefer}"

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

        observations = []
        used: list[str] = []
        skipped: list[str] = []
        razao = None
        porte = None
        mei = None

        for adapter in self.config.adapters:
            name = getattr(adapter, "name", type(adapter).__name__)
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
        ranked, rec_id = select_recommended(
            candidates,
            service_context=self.config.service_context,
            small_firm=small,
            account_dnc=account_dnc,
            account_bounce=account_bounce,
        )

        base.razao_social = razao
        base.small_firm = small
        base.candidates = ranked
        base.recommended_candidate_id = rec_id
        base.adapters_used = used
        base.adapters_skipped = skipped
        if account_dnc or account_bounce:
            base.limitations.append(
                f"account_block:{account_block_reason or ('DNC' if account_dnc else 'bounce')}"
            )
        if not ranked:
            base.absence_reason = "no_public_business_contact_found"
            base.limitations.append("Absence remains absence — no fabricated contacts")
        if self.config.cache:
            self.config.cache.set(ck, base.as_dict())
        return base

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
                source=SourceProvenance(**{k: src.get(k) for k in (
                    "source_type", "source_url", "source_document", "source_date", "observed_at", "notes"
                ) if k in src or k == "source_type"}),
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
                limitations=list(cd.get("limitations") or []),
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
        service_context=d.get("service_context") or ServiceContext.GENERIC.value,
        small_firm=bool(d.get("small_firm")),
        candidates=cands,
        recommended_candidate_id=d.get("recommended_candidate_id"),
        absence_reason=d.get("absence_reason"),
        adapters_used=list(d.get("adapters_used") or []),
        adapters_skipped=list(d.get("adapters_skipped") or []),
        cache_hit=bool(d.get("cache_hit")),
        resolved_at=d.get("resolved_at"),
        limitations=list(d.get("limitations") or []),
    )
