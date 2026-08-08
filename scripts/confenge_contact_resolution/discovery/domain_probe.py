"""Cheap official-domain candidates from razão/fantasia (no search engine)."""

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
)

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
}


def _strip_accents(s: str) -> str:
    nk = unicodedata.normalize("NFKD", s or "")
    return "".join(ch for ch in nk if not unicodedata.combining(ch))


def name_tokens(name: str | None) -> list[str]:
    raw = _strip_accents(name or "").lower()
    raw = re.sub(r"[^a-z0-9\s]", " ", raw)
    return [t for t in raw.split() if t and t not in _STOP and len(t) >= 2]


def candidate_domains(
    *,
    razao_social: str | None = None,
    nome_fantasia: str | None = None,
    max_candidates: int = 12,
) -> list[str]:
    """Generate plausible .com.br / .com hosts from company names."""
    hosts: list[str] = []
    seen: set[str] = set()

    def add(h: str) -> None:
        h = h.lower().strip(".-")
        if not h or h in seen or is_blocked_host(h):
            return
        if len(h) < 4:
            return
        seen.add(h)
        hosts.append(h)

    for label in (nome_fantasia, razao_social):
        toks = name_tokens(label)
        if not toks:
            continue
        compact = "".join(toks[:3])
        add(f"{compact}.com.br")
        add(f"{compact}.com")
        add(f"{'-'.join(toks[:3])}.com.br")
        if len(toks) >= 1:
            add(f"{toks[0]}.com.br")
            add(f"{toks[0]}.com")
        if len(toks) >= 2:
            add(f"{toks[0]}{toks[1]}.com.br")
            add(f"{toks[0]}-{toks[1]}.com.br")
            add(f"{toks[0]}engenharia.com.br")
            add(f"{toks[0]}construtora.com.br")
            add(f"{toks[0]}construcoes.com.br")

    return hosts[:max_candidates]


def probe_host(host: str, *, timeout: float = 3.0) -> dict[str, Any] | None:
    """Return live probe info if host resolves and answers HTTP(S)."""
    host = (host or "").lower().removeprefix("www.")
    if not host or is_blocked_host(host):
        return None
    # Fail closed quickly on DNS (default getaddrinfo can hang on bad resolvers)
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
    """Probe name-derived hosts; return best company-aligned live domain."""
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
        if res.domain_class == DomainClass.UNRESOLVED.value:
            res.domain_class = DomainClass.OFFICIAL_LIKELY.value
            res.confidence = max(res.confidence, 0.6)
            res.evidence.append("live_name_derived_host")
        if best is None or res.confidence > best.confidence:
            best = res
        if res.domain_class == DomainClass.OFFICIAL_CONFIRMED.value:
            break
    return best or DomainResolution(domain_class=DomainClass.UNRESOLVED.value)
