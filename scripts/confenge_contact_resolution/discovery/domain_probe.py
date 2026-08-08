"""Cheap official-domain candidates from razão/fantasia (no search engine).

Strict alignment only: never promote a live host to official just because DNS
answers. Short/generic SLDs (wh.com, bar.com.br) stay UNRESOLVED.
"""

from __future__ import annotations

import re
import socket
import unicodedata
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.confenge_contact_resolution.discovery.official_domain import (
    DomainClass,
    DomainResolution,
    classify_host,
    is_blocked_host,
    is_credible_company_domain,
)

# Legal + industry generics that must not form a solo brand host.
_STOP = {
    "ltda",
    "eireli",
    "me",
    "epp",
    "sa",
    "s/a",
    "s.a",
    "de",
    "da",
    "do",
    "das",
    "dos",
    "e",
    "em",
    "com",
    "para",
    "construtora",
    "construcoes",
    "construções",
    "construcao",
    "construção",
    "engenharia",
    "servicos",
    "serviços",
    "servico",
    "serviço",
    "comercio",
    "comércio",
    "industria",
    "indústria",
    "incorporadora",
    "incorporacao",
    "incorporação",
    "empreendimentos",
    "participacoes",
    "participações",
    "grupo",
    "holding",
    "transportadora",
    "transportes",
    "mineracao",
    "mineração",
    "pavimentacao",
    "pavimentação",
    "instalacoes",
    "instalações",
    "locacao",
    "locação",
    "obras",
    "infraestrutura",
    "saneamento",
    "companhia",
    "empresa",
    "brasil",
    "nacional",
}


def _strip_accents(s: str) -> str:
    nk = unicodedata.normalize("NFKD", s or "")
    return "".join(ch for ch in nk if not unicodedata.combining(ch))


def name_tokens(name: str | None) -> list[str]:
    raw = _strip_accents(name or "").lower()
    raw = re.sub(r"[^a-z0-9\s]", " ", raw)
    # Brand tokens must be reasonably distinctive (len >= 4)
    return [t for t in raw.split() if t and t not in _STOP and len(t) >= 4]


def _sld(host: str) -> str:
    h = (host or "").lower().removeprefix("www.")
    parts = h.split(".")
    if len(parts) >= 2 and parts[-1] == "br" and len(parts) >= 3:
        return parts[-3]  # foo.com.br → foo
    if len(parts) >= 2:
        return parts[-2]
    return parts[0] if parts else ""


def candidate_domains(
    *,
    razao_social: str | None = None,
    nome_fantasia: str | None = None,
    max_candidates: int = 12,
) -> list[str]:
    """Generate plausible .com.br / .com hosts from distinctive company tokens only."""
    hosts: list[str] = []
    seen: set[str] = set()

    def add(h: str) -> None:
        h = h.lower().strip(".-")
        if not h or h in seen or is_blocked_host(h):
            return
        sld = _sld(h)
        # Ultra-short SLD only when explicitly allowed by caller path (acronym brands)
        if len(sld) < 3:
            return
        if sld in _STOP:
            return
        if len(h) < 7:
            return
        seen.add(h)
        hosts.append(h)

    for label in (nome_fantasia, razao_social):
        toks = name_tokens(label)
        # Also allow exact 3-letter leading acronym from raw name (AMF, LMA)
        raw = _strip_accents(label or "").lower()
        raw_words = [w for w in re.split(r"[^a-z0-9]+", raw) if w and w not in _STOP]
        if raw_words and len(raw_words[0]) == 3 and raw_words[0].isalpha():
            acr = raw_words[0]
            add(f"{acr}.com.br")
            add(f"{acr}.com")
        if not toks:
            continue
        # Prefer multi-token brands when available
        if len(toks) >= 2:
            add(f"{toks[0]}{toks[1]}.com.br")
            add(f"{toks[0]}-{toks[1]}.com.br")
            add(f"{''.join(toks[:3])}.com.br")
            add(f"{'-'.join(toks[:3])}.com.br")
        # Single distinctive brand token only if long enough (avoid WH, FTS as probes
        # unless they are exact leading acronym handled above)
        brand = toks[0]
        if len(brand) >= 5:
            add(f"{brand}.com.br")
            add(f"{brand}.com")
            add(f"{brand}engenharia.com.br")
            add(f"{brand}construtora.com.br")
            add(f"{brand}construcoes.com.br")

    return hosts[:max_candidates]


def probe_host(host: str, *, timeout: float = 3.0) -> dict[str, Any] | None:
    """Return live probe info if host resolves and answers HTTP(S)."""
    host = (host or "").lower().removeprefix("www.")
    if not host or is_blocked_host(host):
        return None
    if len(_sld(host)) < 4:
        return None
    prev_to = socket.getdefaulttimeout()
    socket.setdefaulttimeout(min(2.0, timeout))
    try:
        try:
            socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except OSError:
            try:
                socket.getaddrinfo(host, 80, type=socket.SOCK_STREAM)
            except OSError:
                return None
    finally:
        socket.setdefaulttimeout(prev_to)

    for scheme in ("https", "http"):
        url = f"{scheme}://{host}/"
        req = Request(  # noqa: S310
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; extra-cli-confenge-contact/1.0)"},
        )
        try:
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310
                status = int(getattr(resp, "status", 200) or 200)
                final = resp.geturl() or url
                if status >= 400:
                    continue
                return {"host": host, "url": final, "status": status, "scheme": scheme}
        except HTTPError as exc:
            if int(exc.code) in {401, 403}:
                return {"host": host, "url": url, "status": int(exc.code), "scheme": scheme}
            continue
        except (URLError, TimeoutError, OSError):
            continue
    return None


def probe_official_domain(
    *,
    razao_social: str | None,
    nome_fantasia: str | None = None,
    max_probes: int = 8,
    timeout: float = 5.0,
) -> DomainResolution:
    """Probe name-derived hosts; only return company-aligned official domains.

    Live + UNRESOLVED is NEVER promoted to OFFICIAL_LIKELY (that caused wh.com
    style false positives). Alignment must come from classify_host / credibility.
    """
    label = " ".join(x for x in (razao_social or "", nome_fantasia or "") if x)
    best: DomainResolution | None = None
    for host in candidate_domains(razao_social=razao_social, nome_fantasia=nome_fantasia)[:max_probes]:
        live = probe_host(host, timeout=timeout)
        if not live:
            continue
        res = classify_host(live["host"], company_label=label)
        res.provenance = list(res.provenance or []) + ["domain_probe"]
        res.source_url = live["url"]
        res.evidence = list(res.evidence or []) + [f"http_{live['status']}"]
        # Hard gate: only company-aligned classes may become official
        if not res.is_company_owned_eligible():
            continue
        if not is_credible_company_domain(res.domain, label):
            continue
        if best is None or res.confidence > best.confidence:
            best = res
        if res.domain_class == DomainClass.OFFICIAL_CONFIRMED.value:
            break
    return best or DomainResolution(domain_class=DomainClass.UNRESOLVED.value)
