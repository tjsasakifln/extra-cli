"""Administrative process resolution: contract → process → portal → doc index.

Lazy discovery + registry cache. Web search only as identifier discovery tool.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus, urljoin

from scripts.confenge_process_enrichment.adapters.municipal_portal import MunicipalPortalAdapter
from scripts.confenge_process_enrichment.adapters.sei_public import (
    SeiPublicAdapter,
    is_sei_url,
    research_url,
)
from scripts.confenge_process_enrichment.identifiers import (
    digits_only,
    normalize_process_number,
    process_number_variants,
)
from scripts.confenge_process_enrichment.models import ContractNode, ProvenanceEdge, _now_iso
from scripts.confenge_process_enrichment.source_registry import (
    ProcessSourceEntry,
    ProcessSourceRegistry,
    seed_pncp_family,
)

SearchFn = Callable[[str, int], list[dict[str, Any]]]
FetchFn = Callable[[str], tuple[int | None, str | None, str | None]]  # status, body, err


@dataclass
class ProcessResolution:
    contract_id: str
    process_number: str | None = None
    process_number_normalized: str | None = None
    orgao_cnpj: str | None = None
    process_system_family: str | None = None
    process_url: str | None = None
    document_index: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    discovery_queries: list[str] = field(default_factory=list)
    provenance: list[ProvenanceEdge] = field(default_factory=list)
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "process_number": self.process_number,
            "process_number_normalized": self.process_number_normalized,
            "orgao_cnpj": self.orgao_cnpj,
            "process_system_family": self.process_system_family,
            "process_url": self.process_url,
            "document_index": self.document_index,
            "blockers": self.blockers,
            "discovery_queries": self.discovery_queries,
            "provenance": [p.to_dict() for p in self.provenance],
            "resolved": self.resolved,
        }


def build_discovery_queries(
    *,
    process_number: str | None,
    company_name: str | None,
    company_cnpj: str | None,
    contract_number: str | None,
) -> list[str]:
    """Strong-identifier web queries only (never email promotion from snippets)."""
    q: list[str] = []
    variants = process_number_variants(process_number)
    for v in variants[:3]:
        q.append(f'"{v}"')
        if company_name:
            q.append(f'"{v}" "{company_name}"')
        if company_cnpj:
            q.append(f'"{v}" "{company_cnpj}"')
    if contract_number and company_name:
        q.append(f'"{contract_number}" "{company_name}"')
    if company_cnpj:
        for term in ("proposta", "contrato", "licitação", "habilitação", "representante"):
            q.append(f'"{company_cnpj}" {term}')
    if company_name and contract_number:
        q.append(f'"{company_name}" "{contract_number}"')
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for item in q:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out[:12]


def _guess_family_from_url(url: str) -> str:
    u = url.lower()
    if "pncp.gov.br" in u:
        return "pncp"
    if "sei." in u or "/sei/" in u:
        return "sei"
    if "compras" in u and (".gov.br" in u or "prefeitura" in u):
        return "procurement_portal"
    if "transparencia" in u:
        return "transparency_portal"
    if "processo" in u or "protocolo" in u:
        return "state_electronic_process"
    return "generic_html_index"


def resolve_process_for_contract(
    contract: ContractNode,
    *,
    registry: ProcessSourceRegistry | None = None,
    company_name: str | None = None,
    company_cnpj: str | None = None,
    search_fn: SearchFn | None = None,
    fetch_fn: FetchFn | None = None,
    allow_network: bool = False,
    max_search_queries: int = 4,
) -> ProcessResolution:
    """Resolve process portal and optional document index for one contract."""
    reg = registry or ProcessSourceRegistry()
    res = ProcessResolution(
        contract_id=contract.contract_id,
        process_number=contract.administrative_process_number,
        process_number_normalized=normalize_process_number(contract.administrative_process_number),
        orgao_cnpj=contract.contracting_authority_cnpj,
    )

    orgao = contract.contracting_authority_cnpj
    if orgao:
        seed_pncp_family(reg, orgao, uf=contract.uf)
        # PNCP document listing via orgao/ano/seq is always a first-class path
        if contract.year and contract.sequential:
            res.process_system_family = "pncp"
            res.process_url = (
                f"https://pncp.gov.br/app/contratos/{orgao}/{contract.year}/{contract.sequential}"
            )
            res.provenance.append(
                ProvenanceEdge(
                    source="pncp",
                    source_url=res.process_url,
                    source_identifier=contract.pncp_control_number,
                    join_method="orgao_ano_sequencial",
                    confidence=0.95,
                )
            )
            res.resolved = True

    known = reg.get(orgao) if orgao else None
    if known and known.search_base_url and known.supports_process_number and res.process_number_normalized:
        # Construct portal URL from known query pattern
        if known.query_mechanism == "query_param":
            res.process_url = f"{known.search_base_url}?processo={quote_plus(res.process_number_normalized)}"
        elif known.query_mechanism == "process_number_path":
            res.process_url = urljoin(known.search_base_url.rstrip("/") + "/", quote_plus(res.process_number_normalized))
        else:
            res.process_url = known.search_base_url
        res.process_system_family = known.process_system_family
        res.resolved = True
        if known.captcha_required:
            res.blockers.append("CAPTCHA_REQUIRED")
        if known.authentication_required:
            res.blockers.append("AUTH_REQUIRED")

    # Municipal / short process portals (non-NUP)
    # Optional sample cap for national batch runs (env CONFENGE_MUNI_MAX_PROBES).
    import os as _os

    _muni_max = int(_os.environ.get("CONFENGE_MUNI_MAX_PROBES") or "0")  # 0 = unlimited
    if not hasattr(resolve_process_for_contract, "_muni_probe_count"):
        resolve_process_for_contract._muni_probe_count = 0  # type: ignore[attr-defined]

    if allow_network and res.process_number and len(digits_only(res.process_number)) < 15:
        known = reg.get(orgao) if orgao else None
        known_base = (
            known.search_base_url
            if known
            and known.process_system_family
            in {
                "municipal_html",
                "municipal_multi24h",
                "municipal_portal_php",
                "transparency_portal",
                "procurement_portal",
                "municipal_process",
            }
            and known.search_base_url
            else None
        )
        skip_muni = bool(
            known
            and known.failure_count >= 2
            and "MUNICIPAL_PORTAL_NOT_FOUND" in (known.notes or "")
            and not known_base
        )
        if skip_muni:
            res.blockers.append("MUNICIPAL_PORTAL_NOT_FOUND")
        elif _muni_max > 0 and resolve_process_for_contract._muni_probe_count >= _muni_max:  # type: ignore[attr-defined]
            res.blockers.append("MUNICIPAL_PROBE_BUDGET_EXCEEDED")
        else:
            try:
                resolve_process_for_contract._muni_probe_count += 1  # type: ignore[attr-defined]
                muni = MunicipalPortalAdapter(max_bases=5, max_pages=5, request_delay=0.15)
                mres = muni.resolve(
                    process_number=res.process_number,
                    municipality=contract.municipality,
                    uf=contract.uf,
                    orgao_cnpj=orgao,
                    entity_name=contract.contracting_authority_name,
                    supplier_cnpj=company_cnpj or contract.supplier_cnpj,
                    known_base_url=known_base,
                )
                res.blockers.extend(mres.blockers)
                if not mres.resolved and orgao:
                    reg.upsert(
                        ProcessSourceEntry(
                            contracting_entity_cnpj=orgao,
                            entity_name=contract.contracting_authority_name,
                            uf=contract.uf,
                            municipality=contract.municipality,
                            process_system_family="municipal_html",
                            search_base_url=None,
                            query_mechanism="html_discovery",
                            supports_process_number=True,
                            failure_count=(known.failure_count if known else 0) + 1,
                            notes="MUNICIPAL_PORTAL_NOT_FOUND",
                            confidence=0.2,
                            last_verified_at=_now_iso(),
                        )
                    )
                if mres.resolved:
                    res.process_system_family = mres.process_system_family
                    res.process_url = mres.portal_url
                    res.resolved = True
                    if mres.document_index:
                        res.document_index.extend(mres.document_index)
                    res.provenance.append(
                        ProvenanceEdge(
                            source="municipal_portal",
                            source_url=mres.portal_url,
                            source_identifier=res.process_number_normalized or res.process_number,
                            confidence=0.65 if mres.document_index else 0.5,
                            join_method="process_number",
                            notes=";".join(mres.notes) if mres.notes else "municipal_html_discovery",
                            observed_at=_now_iso(),
                        )
                    )
                    if orgao and mres.portal_url:
                        reg.upsert(
                            ProcessSourceEntry(
                                contracting_entity_cnpj=orgao,
                                entity_name=contract.contracting_authority_name,
                                uf=contract.uf,
                                municipality=contract.municipality,
                                process_system_family=mres.process_system_family,
                                search_base_url=mres.portal_url,
                                query_mechanism="html_discovery",
                                supports_process_number=True,
                                supports_document_listing=bool(mres.document_index),
                                supports_direct_download=bool(mres.document_index),
                                captcha_required=False,
                                confidence=0.6 if mres.document_index else 0.45,
                                notes="Lazy municipal portal discovery",
                                last_verified_at=_now_iso(),
                            )
                        )
                        if mres.document_index:
                            reg.record_success(
                                orgao,
                                process_system_family=mres.process_system_family,
                                search_base_url=mres.portal_url,
                                supports_document_listing=True,
                            )
            except Exception as exc:  # noqa: BLE001
                res.blockers.append(f"MUNICIPAL_ERROR:{type(exc).__name__}")

    # SEI public consultation (highest-yield family after PNCP for federal NUPs)
    sei_docs: list[dict[str, Any]] = []
    is_nup = bool(res.process_number and len(digits_only(res.process_number)) >= 15)
    if allow_network and res.process_number and is_nup:
        known = reg.get(orgao) if orgao else None
        known_base = (
            known.search_base_url
            if known and known.process_system_family == "sei" and known.search_base_url
            else None
        )
        # Cache short-circuit: do not re-hit SEI when organ already captcha-blocked
        if known and known.captcha_required and known.process_system_family == "sei":
            res.blockers.append("CAPTCHA_BLOCKED")
            res.process_system_family = "sei"
            if known.search_base_url:
                res.process_url = research_url(known.search_base_url)
                res.resolved = True
            res.provenance.append(
                ProvenanceEdge(
                    source="sei_public",
                    source_url=res.process_url,
                    source_identifier=res.process_number_normalized,
                    confidence=0.4,
                    join_method="process_number",
                    notes="SEI base known; captcha required (cached)",
                    observed_at=_now_iso(),
                )
            )
        else:
            try:
                sei = SeiPublicAdapter()
                sei_res = sei.resolve_and_list_docs(
                    res.process_number,
                    orgao_cnpj=orgao,
                    known_base=known_base,
                )
                if sei_res.blocker:
                    res.blockers.append(sei_res.blocker)
                if sei_res.captcha_required:
                    res.blockers.append("CAPTCHA_BLOCKED")
                if sei_res.base_url and orgao:
                    reg.upsert(
                        ProcessSourceEntry(
                            contracting_entity_cnpj=orgao,
                            entity_name=contract.contracting_authority_name,
                            uf=contract.uf,
                            municipality=contract.municipality,
                            process_system_family="sei",
                            search_base_url=sei_res.base_url,
                            query_mechanism="sei_public_form",
                            supports_process_number=True,
                            supports_document_listing=bool(sei_res.document_index),
                            supports_direct_download=False,
                            captcha_required=bool(sei_res.captcha_required or sei_res.blocker == "CAPTCHA_BLOCKED"),
                            authentication_required=False,
                            confidence=0.7 if sei_res.matched_protocol else 0.45,
                            notes="; ".join(sei_res.notes) if sei_res.notes else "SEI public research",
                            last_verified_at=_now_iso(),
                        )
                    )
                if sei_res.matched_protocol or sei_res.document_index:
                    res.process_system_family = "sei"
                    if sei_res.process_urls:
                        res.process_url = sei_res.process_urls[0]
                    else:
                        res.process_url = research_url(sei_res.base_url)
                    res.resolved = True
                    sei_docs = list(sei_res.document_index)
                    res.document_index.extend(sei_docs)
                    res.provenance.append(
                        ProvenanceEdge(
                            source="sei_public",
                            source_url=res.process_url,
                            source_identifier=sei_res.protocol_tried,
                            confidence=0.85 if sei_res.matched_protocol else 0.5,
                            join_method="process_number",
                            notes=sei_res.blocker or "sei_public_search",
                            observed_at=_now_iso(),
                        )
                    )
                    if orgao and sei_res.matched_protocol:
                        reg.record_success(
                            orgao,
                            process_system_family="sei",
                            search_base_url=sei_res.base_url,
                            supports_process_number=True,
                            captcha_required=sei_res.captcha_required,
                        )
                elif sei_res.blocker == "CAPTCHA_BLOCKED" and orgao:
                    reg.record_failure(orgao, note="SEI captcha blocked public search")
            except Exception as exc:  # noqa: BLE001
                res.blockers.append(f"SEI_ERROR:{type(exc).__name__}")

    # Discovery via web search only when no portal path is known yet.
    # Skip when PNCP already resolved the process portal (avoid slow/blocked search
    # engines after every SEI captcha — captcha is recorded as blocker already).
    need_discovery = (
        bool(res.process_number)
        and allow_network
        and not res.resolved
        and not res.document_index
    )
    if need_discovery:
        queries = build_discovery_queries(
            process_number=res.process_number,
            company_name=company_name,
            company_cnpj=company_cnpj or contract.supplier_cnpj,
            contract_number=contract.contract_number,
        )
        res.discovery_queries = queries[:max_search_queries]
        hits: list[dict[str, Any]] = []
        if search_fn is not None:
            for q in res.discovery_queries:
                try:
                    batch = search_fn(q, 5)
                except Exception as exc:  # noqa: BLE001
                    res.blockers.append(f"SEARCH_ERROR:{exc}")
                    break
                hits.extend(batch or [])
        else:
            # Built-in identifier discovery (Bing HTML)
            try:
                from scripts.confenge_process_enrichment.adapters.web_discovery import (
                    discover_process_urls,
                )

                hits = discover_process_urls(
                    process_number=res.process_number,
                    company_name=company_name,
                    company_cnpj=company_cnpj or contract.supplier_cnpj,
                    max_queries=max_search_queries,
                )
            except Exception as exc:  # noqa: BLE001
                res.blockers.append(f"SEARCH_ERROR:{type(exc).__name__}")
                hits = []

        for hit in hits:
            url = (hit.get("url") or hit.get("link") or "").strip()
            if not url.startswith("http"):
                continue
            if not any(x in url.lower() for x in (".gov.br", "pncp.", "transparencia", "sei.")):
                continue
            # Prefer SEI URLs when process path still thin
            if not res.process_url or is_sei_url(url):
                res.process_url = url
            fam = _guess_family_from_url(url)
            if fam == "sei" or not res.process_system_family:
                res.process_system_family = fam
            res.resolved = True
            res.provenance.append(
                ProvenanceEdge(
                    source="web_discovery",
                    source_url=url,
                    source_identifier=res.process_number_normalized,
                    confidence=0.6,
                    join_method="process_number_search",
                    notes=f"query={(hit.get('query') or '')[:80]}",
                    observed_at=_now_iso(),
                )
            )
            if orgao:
                reg.upsert(
                    ProcessSourceEntry(
                        contracting_entity_cnpj=orgao,
                        entity_name=contract.contracting_authority_name,
                        uf=contract.uf,
                        municipality=contract.municipality,
                        process_system_family=res.process_system_family or "unknown",
                        search_base_url=url,
                        query_mechanism="html_search",
                        supports_process_number=True,
                        confidence=0.55,
                        notes="Discovered via identifier web search",
                    )
                )
            if is_sei_url(url):
                break

    # Optional fetch of process page for document index (HTML links)
    if res.resolved and res.process_url and allow_network and fetch_fn and not res.document_index:
        try:
            status, body, err = fetch_fn(res.process_url)
        except Exception as exc:  # noqa: BLE001
            res.blockers.append(f"FETCH_ERROR:{exc}")
            status, body, err = None, None, str(exc)
        if status in (401, 403):
            res.blockers.append("AUTH_REQUIRED")
        elif status == 429:
            res.blockers.append("SOURCE_BLOCKED")
        elif err and not body:
            res.blockers.append(f"SOURCE_BLOCKED:{err[:120]}")
        elif body:
            res.document_index = _extract_doc_links(body, base_url=res.process_url)
            if orgao:
                reg.record_success(orgao, supports_document_listing=bool(res.document_index))

    if not res.process_number and not (contract.year and contract.sequential):
        res.blockers.append("PROCESS_NUMBER_MISSING")
    return res


def _extract_doc_links(html: str, *, base_url: str) -> list[dict[str, Any]]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html or "", flags=re.I)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for href in hrefs:
        low = href.lower()
        if not any(ext in low for ext in (".pdf", ".doc", ".docx", ".zip", "arquivo", "download")):
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        title = href.rsplit("/", 1)[-1]
        out.append({"url": url, "title": title, "source": "process_html_index"})
    return out[:100]
