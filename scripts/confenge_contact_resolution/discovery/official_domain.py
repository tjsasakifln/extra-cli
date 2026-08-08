"""Official company domain discovery and classification."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from scripts.confenge_contact_resolution.ownership import (
    detect_third_party_type,
    domain_from_url,
    domain_token_overlap,
)

# Hosts that must never be treated as company official sites
_BLOCKED_HOST_SUFFIXES = (
    "jusbrasil.com.br",
    "linkedin.com",
    "instagram.com",
    "facebook.com",
    "fb.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "tiktok.com",
    "gov.br",
    "transparencia.gov.br",
    "pncp.gov.br",
    "comprasnet.gov.br",
    "bcb.gov.br",
    "receita.fazenda.gov.br",
    "wikipedia.org",
    "reclameaqui.com.br",
    "glassdoor.com",
    "indeed.com",
    "catalogo.me",
    "econodata.com.br",
    "cnpj.biz",
    "casadosdados.com.br",
    "empresascnpj.com",
    "consultacnpj.com",
    "cnpja.com",
    "brasilcnpj.com",
    "solutudo.com.br",
    "telelistas.net",
    "guiamais.com.br",
    "apontador.com.br",
    "google.com",
    "bing.com",
    "duckduckgo.com",
    "yahoo.com",
    "apollo.io",
    "zoominfo.com",
    "crunchbase.com",
    "wix.com",
    "wixsite.com",
    "lojavirtual.com.br",
    "mercadoshops.com.br",
    "shopee.com.br",
    "mercadolivre.com.br",
    "olx.com.br",
)

_DIRECTORY_HINTS = (
    "diretorio",
    "directory",
    "guia",
    "catalogo",
    "catálogo",
    "lista",
    "empresas",
    "cnpj",
    "yellowpages",
    "telelistas",
    "solutudo",
    "econodata",
    "casadosdados",
)

_ASSOCIATION_HINTS = (
    "sindicato",
    "associacao",
    "associação",
    "federacao",
    "federação",
    "confederacao",
    "confederação",
    "camara",
    "câmara",
    "sebrae",
    "senai",
    "sesi",
)

# Industry generics: alone they never prove company identity in a host SLD.
_GENERIC_BRAND_TOKENS = frozenset(
    {
        "construtora",
        "construcoes",
        "construcao",
        "engenharia",
        "servicos",
        "servico",
        "comercio",
        "industria",
        "incorporadora",
        "empreendimentos",
        "participacoes",
        "transportadora",
        "transportes",
        "mineracao",
        "pavimentacao",
        "instalacoes",
        "locacao",
        "obras",
        "infraestrutura",
        "saneamento",
        "companhia",
        "empresa",
        "brasil",
        "nacional",
        "grupo",
        "holding",
        "bar",
        "cafe",
        "hotel",
        "cooper",
        "alpha",
        "beta",
        "delta",
        "omega",
    }
)


class DomainClass(StrEnum):
    OFFICIAL_CONFIRMED = "OFFICIAL_CONFIRMED"
    OFFICIAL_LIKELY = "OFFICIAL_LIKELY"
    THIRD_PARTY = "THIRD_PARTY"
    DIRECTORY = "DIRECTORY"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class DomainResolution:
    domain: str | None = None
    domain_class: str = DomainClass.UNRESOLVED.value
    confidence: float = 0.0
    provenance: list[str] = field(default_factory=list)
    source_url: str | None = None
    evidence: list[str] = field(default_factory=list)

    def is_company_owned_eligible(self) -> bool:
        return self.domain_class in {
            DomainClass.OFFICIAL_CONFIRMED.value,
            DomainClass.OFFICIAL_LIKELY.value,
        } and bool(self.domain)

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "domain_class": self.domain_class,
            "confidence": self.confidence,
            "provenance": list(self.provenance),
            "source_url": self.source_url,
            "evidence": list(self.evidence),
        }


def _host(url_or_domain: str | None) -> str | None:
    if not url_or_domain:
        return None
    h = domain_from_url(url_or_domain) if "://" in url_or_domain or "/" in url_or_domain else url_or_domain
    if not h:
        return None
    return h.lower().removeprefix("www.")


def is_blocked_host(host: str | None) -> bool:
    h = _host(host)
    if not h:
        return True
    for suffix in _BLOCKED_HOST_SUFFIXES:
        if h == suffix or h.endswith("." + suffix):
            return True
    if h.endswith(".gov.br") or h.endswith(".jus.br") or h.endswith(".mil.br"):
        return True
    return False


def classify_host(
    host: str | None,
    *,
    company_label: str | None = None,
    page_title: str | None = None,
    snippet: str | None = None,
) -> DomainResolution:
    h = _host(host)
    if not h:
        return DomainResolution(domain_class=DomainClass.UNRESOLVED.value)

    if is_blocked_host(h):
        # refine directory vs gov vs social
        blob = f"{h} {page_title or ''} {snippet or ''}".lower()
        directory_hosts = (
            "cnpj",
            "econodata",
            "casadosdados",
            "jusbrasil",
            "solutudo",
            "telelistas",
            "guiamais",
            "apontador",
            "reclameaqui",
            "empresascnpj",
            "consultacnpj",
            "cnpja",
            "brasilcnpj",
        )
        if any(x in blob for x in _DIRECTORY_HINTS) or any(s in h for s in directory_hosts):
            return DomainResolution(
                domain=h,
                domain_class=DomainClass.DIRECTORY.value,
                confidence=0.9,
                evidence=["blocked_directory_or_social"],
            )
        if h.endswith(".gov.br") or "licita" in h or "pncp" in h:
            return DomainResolution(
                domain=h,
                domain_class=DomainClass.DIRECTORY.value,
                confidence=0.95,
                evidence=["public_portal_or_gov"],
            )
        return DomainResolution(
            domain=h,
            domain_class=DomainClass.THIRD_PARTY.value,
            confidence=0.9,
            evidence=["blocked_host"],
        )

    tp, tp_ev = detect_third_party_type(h)
    if tp:
        return DomainResolution(
            domain=h,
            domain_class=DomainClass.THIRD_PARTY.value,
            confidence=0.85,
            evidence=list(tp_ev or []) + [f"third_party_type:{tp}"],
        )

    blob = f"{page_title or ''} {snippet or ''}".lower()
    if any(x in blob for x in _ASSOCIATION_HINTS):
        return DomainResolution(
            domain=h,
            domain_class=DomainClass.THIRD_PARTY.value,
            confidence=0.7,
            evidence=["association_or_union_hint"],
        )
    if any(x in blob for x in _DIRECTORY_HINTS):
        return DomainResolution(
            domain=h,
            domain_class=DomainClass.DIRECTORY.value,
            confidence=0.75,
            evidence=["directory_hint_in_text"],
        )

    label = (company_label or "").strip()
    if not is_credible_company_domain(h, label):
        return DomainResolution(
            domain=h,
            domain_class=DomainClass.UNRESOLVED.value,
            confidence=0.15,
            evidence=["host_not_credible_for_company"],
        )

    overlap = domain_token_overlap(h, label) if label else 0.0
    if overlap >= 0.55:
        return DomainResolution(
            domain=h,
            domain_class=DomainClass.OFFICIAL_CONFIRMED.value,
            confidence=min(0.95, 0.55 + overlap),
            evidence=[f"token_overlap:{overlap:.2f}"],
        )
    # Stricter than before (was 0.35): weak Jaccard on short hosts caused bar.com.br FPs
    if overlap >= 0.45:
        return DomainResolution(
            domain=h,
            domain_class=DomainClass.OFFICIAL_LIKELY.value,
            confidence=min(0.8, 0.4 + overlap),
            evidence=[f"token_overlap:{overlap:.2f}"],
        )

    # Brand token in host: distinctive only (len>=6, not industry generic)
    if label:
        tokens = [
            t
            for t in re.split(r"[^a-z0-9]+", label.lower())
            if len(t) >= 6 and t not in _GENERIC_BRAND_TOKENS
        ]
        host_compact = h.replace(".", "").replace("-", "")
        sld = _second_level_label(h)
        for t in tokens:
            if t == sld or (t in host_compact and len(t) >= 6):
                return DomainResolution(
                    domain=h,
                    domain_class=DomainClass.OFFICIAL_LIKELY.value,
                    confidence=0.6,
                    evidence=[f"distinctive_token_in_host:{t}"],
                )

    return DomainResolution(
        domain=h,
        domain_class=DomainClass.UNRESOLVED.value,
        confidence=0.2,
        evidence=["no_company_alignment"],
    )


def _second_level_label(host: str | None) -> str:
    h = (host or "").lower().removeprefix("www.")
    parts = [p for p in h.split(".") if p]
    if len(parts) >= 3 and parts[-1] == "br":
        return parts[-3]
    if len(parts) >= 2:
        return parts[-2]
    return parts[0] if parts else ""


def is_credible_company_domain(domain: str | None, company_label: str | None) -> bool:
    """Hard gate before a host may be treated as official for COMPANY_OWNED.

    Rejects short SLDs (wh.com, fts.com) unless the company name starts with that
    exact acronym, generic industry-only hosts, and hosts with no distinctive
    token shared with the company name.
    """
    h = _host(domain)
    if not h or is_blocked_host(h):
        return False
    sld = _second_level_label(h)
    if len(sld) < 3:
        return False
    if sld in _GENERIC_BRAND_TOKENS:
        return False
    label = (company_label or "").strip()
    if not label:
        return False
    # Fold label to tokens (keep short acronyms)
    raw_parts = [t for t in re.split(r"[^a-z0-9]+", re.sub(r"[^a-z0-9\s]", " ", label.lower())) if t]
    # Drop legal form tokens only
    legal = {"ltda", "limitada", "sa", "me", "epp", "eireli", "s", "a", "e"}
    words = [t for t in raw_parts if t not in legal and t not in _GENERIC_BRAND_TOKENS]
    if not words:
        return False

    # 3-char SLD: only if it is the leading brand acronym of the company name
    if len(sld) == 3:
        return words[0] == sld

    # Must share a distinctive token (len>=4) with company name
    label_tokens = {t for t in words if len(t) >= 4}
    if not label_tokens and words[0] != sld:
        return False
    host_flat = h.replace(".", "").replace("-", "")
    for t in label_tokens:
        if t == sld or t in host_flat:
            return True
    if words[0] == sld and len(sld) >= 4:
        return True
    return domain_token_overlap(h, label) >= 0.45


def resolve_official_domain(
    *,
    razao_social: str | None = None,
    nome_fantasia: str | None = None,
    registry_site: str | None = None,
    candidate_urls: list[str] | None = None,
    search_results: list[dict[str, Any]] | None = None,
) -> DomainResolution:
    """Pick the best official domain from registry + search candidates."""
    label = " ".join(x for x in (razao_social or "", nome_fantasia or "") if x).strip()
    best: DomainResolution | None = None

    def _consider(res: DomainResolution, provenance: str, source_url: str | None = None) -> None:
        nonlocal best
        if not res.domain:
            return
        res.provenance = list(res.provenance or []) + [provenance]
        if source_url:
            res.source_url = source_url
        if best is None:
            best = res
            return
        rank = {
            DomainClass.OFFICIAL_CONFIRMED.value: 4,
            DomainClass.OFFICIAL_LIKELY.value: 3,
            DomainClass.UNRESOLVED.value: 1,
            DomainClass.DIRECTORY.value: 0,
            DomainClass.THIRD_PARTY.value: 0,
        }
        if rank.get(res.domain_class, 0) > rank.get(best.domain_class, 0):
            best = res
        elif rank.get(res.domain_class, 0) == rank.get(best.domain_class, 0) and res.confidence > best.confidence:
            best = res

    if registry_site:
        host = _host(registry_site)
        res = classify_host(host, company_label=label)
        if res.is_company_owned_eligible():
            # Registry website is strong when not third-party
            if res.domain_class == DomainClass.OFFICIAL_LIKELY.value:
                res.domain_class = DomainClass.OFFICIAL_CONFIRMED.value
                res.confidence = max(res.confidence, 0.85)
            res.evidence.append("registry_website")
        _consider(res, "registry", registry_site)

    for url in candidate_urls or []:
        host = _host(url)
        res = classify_host(host, company_label=label)
        _consider(res, "candidate_url", url)

    for r in search_results or []:
        url = r.get("url") or r.get("link")
        host = _host(str(url) if url else None) or _host(r.get("domain"))
        res = classify_host(
            host,
            company_label=label,
            page_title=r.get("title"),
            snippet=r.get("snippet") or r.get("body"),
        )
        _consider(res, "web_search", str(url) if url else None)

    if best is None:
        return DomainResolution(domain_class=DomainClass.UNRESOLVED.value, confidence=0.0)
    return best


def seed_paths_for_domain(domain: str) -> list[str]:
    """Conservative contactish paths to try on an official domain."""
    d = domain.lower().removeprefix("www.")
    base = f"https://{d}"
    paths = [
        "/",
        "/contato",
        "/fale-conosco",
        "/fale_conosco",
        "/empresa",
        "/sobre",
        "/quem-somos",
        "/equipe",
        "/licitacoes",
        "/licitações",
        "/comercial",
        "/orcamentos",
        "/orçamentos",
        "/engenharia",
        "/contratos",
        "/contato.html",
        "/contact",
    ]
    return [base + p for p in paths]


def same_registrable_host(url: str, domain: str) -> bool:
    h = _host(url)
    d = _host(domain)
    if not h or not d:
        return False
    return h == d or h.endswith("." + d)
