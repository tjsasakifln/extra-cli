"""Bounded public-web discovery primitives for CONFENGE accounts.

Search, crawl, extraction, and domain resolution are replaceable adapters. The
module never turns a search hit, an email pattern, or a reachable mailbox into
proof of a person's identity or permission to contact them.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from scripts.decision_unit_intelligence.decision_policy import normalize_observed_role
from scripts.decision_unit_intelligence.email_discovery import (
    associate_person_to_email,
    build_email_job_queries,
    classify_email_discovery,
    extract_mailto_addresses,
    plausible_person_name,
    score_internal_url,
)
from scripts.decision_unit_intelligence.evidence import make_evidence, make_page_document_witness
from scripts.decision_unit_intelligence.models import (
    ChannelObservation,
    ChannelType,
    EpistemicClass,
    FieldEvidence,
    OwnershipStatus,
    PersonObservation,
    PersonRelation,
    fold_text,
    normalize_cnpj,
    normalize_email,
    normalize_name,
    normalize_phone,
    now_iso,
    stable_id,
)
from scripts.decision_unit_intelligence.providers.base import InvestigationContext
from scripts.decision_unit_intelligence.reachability import classify_observed_email_channel, is_freemail

USER_AGENT = "CONFENGE-Public-Discovery/1.0 (+https://github.com/tjsasakifln/extra-cli)"

_ROLE_PATTERN = (
    r"diretor(?:a)?(?:\s+(?:de\s+)?(?:engenharia|comercial|opera(?:ç|c)[oõ]es))?"
    r"|gerente(?:\s+(?:de\s+)?(?:engenharia|comercial|contratos|licita(?:ç|c)[oõ]es|suprimentos))?"
    r"|s[oó]ci[oa](?:[-\s]+administrador(?:a)?)?|propriet[aá]ri[oa]|presidente"
    r"|respons[aá]vel\s+t[eé]cnico|representante\s+legal|preposto|signat[aá]rio"
)
_NAME_WORD = r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÀ-ÖØ-öø-ÿ'’-]+"
_NAME_PATTERN = rf"{_NAME_WORD}(?:\s+(?:(?:d[aeo]s?|e)\s+)?{_NAME_WORD}){{1,4}}"
_ROLE_THEN_NAME = re.compile(rf"(?P<role>{_ROLE_PATTERN})\s*[:|,\-–]\s*(?P<name>{_NAME_PATTERN})", re.I)
_NAME_THEN_ROLE = re.compile(rf"(?P<name>{_NAME_PATTERN})\s*[:|,\-–]\s*(?P<role>{_ROLE_PATTERN})", re.I)
_NAME_THEN_ROLE_LOOSE = re.compile(rf"(?P<name>{_NAME_PATTERN})\s+(?P<role>{_ROLE_PATTERN})", re.I)
_EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w-])", re.I)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?55\s*)?(?:\(?\d{2}\)?[\s.-]*)?\d{4,5}[\s.-]*\d{4}(?!\d)")
_CNPJ_TEXT_RE = re.compile(
    r"(?<!\d)(\d{2}[.\s]?\d{3}[.\s]?\d{3}[\/\s]?\d{4}[-\s]?\d{2})(?!\d)"
)

_COUNTERPARTY_CONTEXT_MARKERS = (
    "agente publico",
    "agente de contratacao",
    "assessoria contabil",
    "buyer",
    "comprador",
    "comissao de contratacao",
    "contratante",
    "contabilidade",
    "escritorio contabil",
    "fiscal do contrato",
    "equipe de apoio",
    "gestor do contrato",
    "oab ",
    "orgao comprador",
    "orgao licitante",
    "orgao publico",
    "prefeitura",
    "pregoeiro",
    "leiloeiro",
    "procurador do cliente",
    "tomador",
    "responsavel pela contratacao",
)

_COMPANY_CONTACT_CONTEXT_MARKERS = (
    "administrativo",
    "atendimento",
    "comercial",
    "contato",
    "e-mail",
    "email",
    "engenharia",
    "fale conosco",
    "financeiro",
    "licitacao",
    "orcamento",
)


def account_mailbox_binding_context(
    *,
    email: str,
    snippet: str,
    page_text: str,
    cnpj_span: tuple[int, int],
    canonical_domain: str,
) -> tuple[bool, str]:
    """Require mailbox context that identifies the target, not a counterparty.

    A corporate-domain mailbox is attributable on the exact-CNPJ official page
    unless its local context explicitly identifies a buyer/third party.  A
    public freemail additionally has to be near the target CNPJ *and* appear in
    an explicit company-contact context.  Mere proximity is negative evidence
    at best: procurement pages often co-locate a supplier CNPJ with a buyer or
    auctioneer's freemail.  Foreign corporate domains never inherit the page's
    CNPJ merely by co-occurrence.
    """

    local = fold_text(snippet)
    if any(marker in local for marker in _COUNTERPARTY_CONTEXT_MARKERS):
        return False, "COUNTERPARTY_MAILBOX_CONTEXT"
    mailbox_domain = email.rsplit("@", 1)[-1].lower().removeprefix("www.")
    official = canonical_domain.lower().removeprefix("www.")
    if mailbox_domain == official or mailbox_domain.endswith(f".{official}"):
        return True, "OFFICIAL_DOMAIN_MAILBOX"
    if not is_freemail(email):
        return False, "FOREIGN_DOMAIN_MAILBOX"

    page_lower = page_text.lower()
    cnpj_start, cnpj_end = cnpj_span
    for match in re.finditer(re.escape(email.lower()), page_lower):
        distance = min(abs(match.start() - cnpj_end), abs(cnpj_start - match.end()))
        if distance > 800:
            continue
        window_start = max(0, min(match.start(), cnpj_start) - 240)
        window_end = min(len(page_text), max(match.end(), cnpj_end) + 240)
        window = fold_text(page_text[window_start:window_end])
        if any(marker in window for marker in _COUNTERPARTY_CONTEXT_MARKERS):
            return False, "COUNTERPARTY_MAILBOX_CONTEXT"
        email_start = max(0, match.start() - 180)
        email_end = min(len(page_text), match.end() + 180)
        email_context = fold_text(page_text[email_start:email_end])
        if not any(marker in email_context for marker in _COMPANY_CONTACT_CONTEXT_MARKERS):
            return False, "FREEMAIL_WITHOUT_COMPANY_CONTACT_CONTEXT"
        return True, "FREEMAIL_EXACT_CNPJ_WITH_COMPANY_CONTACT_CONTEXT"
    return False, "FREEMAIL_NOT_LOCALLY_BOUND_TO_CNPJ"


def source_publication_timestamp(html: str) -> str | None:
    """Extract a page-declared publication/modification timestamp, if present."""

    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    time_node = soup.find("time", datetime=True)
    if time_node:
        value = str(time_node.get("datetime") or "").strip()
        if value:
            return value
    for attrs in (
        {"property": "article:modified_time"},
        {"property": "article:published_time"},
        {"name": "dateModified"},
        {"name": "datePublished"},
    ):
        node = soup.find("meta", attrs=attrs)
        value = str(node.get("content") or "").strip() if node else ""
        if value:
            return value
    return None

_EXCLUDED_HOST_SUFFIXES = (
    "bing.com",
    "checkpj.app",
    "duckduckgo.com",
    "facebook.com",
    "glassdoor.com.br",
    "google.com",
    "guiapj.com.br",
    "instagram.com",
    "jusbrasil.com.br",
    "linkedin.com",
    "maps.google.com",
    "youtube.com",
)
_THIRD_PARTY_HOST_MARKERS = (
    "cnpj",
    "econodata",
    "empresadois",
    "escavador",
    "guiamais",
    "solutudo",
)


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str = ""
    snippet: str = ""
    engine: str | None = None


@dataclass(frozen=True)
class CrawlDocument:
    url: str
    text: str
    content_type: str
    retrieved_at: str
    links: tuple[str, ...] = ()
    bytes_touched: int = 0
    html: str = ""


@dataclass(frozen=True)
class SearchBudget:
    max_queries: int = 4
    max_results_per_query: int = 5
    max_pages: int = 4
    max_bytes: int = 1_500_000
    timeout_seconds: float = 12.0
    min_query_interval_seconds: float = 1.0
    cache_ttl_days: int = 7

    def __post_init__(self) -> None:
        for value in (self.max_queries, self.max_results_per_query, self.max_pages, self.max_bytes):
            if value <= 0:
                raise ValueError("web discovery budgets must be positive")


@dataclass(frozen=True)
class DomainCandidate:
    domain: str
    score: int
    reason_codes: tuple[str, ...]
    evidence_urls: tuple[str, ...]


@dataclass(frozen=True)
class DomainResolution:
    canonical_domain: str | None
    confidence: str
    alternatives: tuple[DomainCandidate, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_domain": self.canonical_domain,
            "confidence": self.confidence,
            "alternatives": [asdict(candidate) for candidate in self.alternatives],
            "reason_codes": list(self.reason_codes),
        }


@dataclass
class ExtractedWebEvidence:
    people: list[PersonObservation] = field(default_factory=list)
    channels: list[ChannelObservation] = field(default_factory=list)
    evidence: list[FieldEvidence] = field(default_factory=list)


class SearchBackend(Protocol):
    backend_id: str

    def search(self, query: str, *, limit: int) -> list[SearchHit]: ...


class WebCrawler(Protocol):
    def fetch(self, url: str, *, max_bytes: int) -> CrawlDocument: ...


class JsonDiscoveryCache:
    """Small replaceable disk cache. Raw pages remain local runtime assets."""

    def __init__(self, root: Path, *, ttl_days: int = 7) -> None:
        self.root = root
        self.ttl = timedelta(days=ttl_days)

    def _path(self, namespace: str, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / namespace / f"{digest}.json"

    def get(self, namespace: str, key: str) -> Any | None:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            stored_at = datetime.fromisoformat(payload["stored_at"].replace("Z", "+00:00"))
            if datetime.now(UTC) - stored_at > self.ttl:
                return None
            return payload.get("value")
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def set(self, namespace: str, key: str, value: Any) -> None:
        path = self._path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"stored_at": now_iso(), "value": value}
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


class SearxngSearchBackend:
    """HTTP adapter only; no SearXNG code is linked into extra-cli."""

    backend_id = "searxng"

    def __init__(self, base_url: str, *, timeout_seconds: float = 12.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, *, limit: int) -> list[SearchHit]:
        response = httpx.get(
            f"{self.base_url}/search",
            params={"q": query, "format": "json", "language": "pt-BR", "safesearch": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=self.timeout_seconds,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
        return [
            SearchHit(
                url=str(row.get("url") or ""),
                title=str(row.get("title") or ""),
                snippet=str(row.get("content") or ""),
                engine=str(row.get("engine") or "") or None,
            )
            for row in (payload.get("results") or [])[:limit]
            if row.get("url")
        ]


class DdgsSearchBackend:
    """Optional MIT-licensed local canary adapter; import stays lazy."""

    backend_id = "ddgs"

    def __init__(self, *, timeout_seconds: float = 12.0) -> None:
        try:
            from ddgs import DDGS
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("ddgs backend requires the optional 'ddgs' package") from exc
        self._ddgs = DDGS(timeout=timeout_seconds)

    def search(self, query: str, *, limit: int) -> list[SearchHit]:
        rows = self._ddgs.text(query, region="br-pt", safesearch="moderate", max_results=limit)
        return [
            SearchHit(
                url=str(row.get("href") or row.get("url") or ""),
                title=str(row.get("title") or ""),
                snippet=str(row.get("body") or row.get("snippet") or ""),
                engine=str(row.get("source") or "") or None,
            )
            for row in rows
            if row.get("href") or row.get("url")
        ]


class CachedRateLimitedSearchBackend:
    def __init__(
        self,
        backend: SearchBackend,
        *,
        cache: JsonDiscoveryCache,
        min_interval_seconds: float,
        policy_version: str = "query-policy.v2",
    ) -> None:
        self.backend = backend
        self.backend_id = backend.backend_id
        self.cache = cache
        self.min_interval_seconds = min_interval_seconds
        self.policy_version = policy_version
        self._last_query_at = 0.0
        self.cache_hits = 0
        self.cache_misses = 0

    def search(self, query: str, *, limit: int) -> list[SearchHit]:
        key = f"{self.backend_id}|{self.policy_version}|{limit}|{query}"
        cached = self.cache.get("search", key)
        if cached is not None:
            self.cache_hits += 1
            return [SearchHit(**row) for row in cached]
        self.cache_misses += 1
        wait = self.min_interval_seconds - (monotonic() - self._last_query_at)
        if wait > 0:
            sleep(wait)
        hits = self.backend.search(query, limit=limit)
        self._last_query_at = monotonic()
        self.cache.set("search", key, [asdict(hit) for hit in hits])
        return hits


class CachedPublicCrawler:
    def __init__(self, crawler: WebCrawler, *, cache: JsonDiscoveryCache) -> None:
        self.crawler = crawler
        self.cache = cache
        self.cache_hits = 0
        self.cache_misses = 0

    def fetch(self, url: str, *, max_bytes: int) -> CrawlDocument:
        key = f"{max_bytes}|{url}"
        cached = self.cache.get("crawl", key)
        if cached is not None:
            self.cache_hits += 1
            return CrawlDocument(
                url=cached["url"],
                text=cached["text"],
                content_type=cached["content_type"],
                retrieved_at=cached["retrieved_at"],
                links=tuple(cached.get("links") or []),
                bytes_touched=int(cached.get("bytes_touched") or 0),
                html=str(cached.get("html") or ""),
            )
        self.cache_misses += 1
        document = self.crawler.fetch(url, max_bytes=max_bytes)
        self.cache.set("crawl", key, asdict(document))
        return document


def _public_http_url(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    try:
        addresses = {row[4][0] for row in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except OSError:
        return False
    for raw in addresses:
        ip = ipaddress.ip_address(raw)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return False
    return True


class HttpxPublicCrawler:
    def __init__(self, *, timeout_seconds: float = 12.0, retries: int = 1) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self._robots: dict[str, RobotFileParser] = {}

    def _robots_allowed(self, url: str) -> bool:
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        robot = self._robots.get(origin)
        if robot is None:
            robot = RobotFileParser(urljoin(origin, "/robots.txt"))
            try:
                robot.read()
            except OSError:
                return False
            self._robots[origin] = robot
        return robot.can_fetch(USER_AGENT, url)

    def fetch(self, url: str, *, max_bytes: int) -> CrawlDocument:
        if not _public_http_url(url):
            raise ValueError("crawler only accepts public HTTP(S) URLs")
        if not self._robots_allowed(url):
            raise PermissionError("robots policy does not allow this crawl")
        last_error: Exception | None = None
        for _attempt in range(self.retries + 1):
            try:
                with httpx.stream(
                    "GET",
                    url,
                    headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.8"},
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                ) as response:
                    response.raise_for_status()
                    if not _public_http_url(str(response.url)):
                        raise ValueError("redirected outside public HTTP(S)")
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if content_type not in {
                        "text/html",
                        "text/plain",
                        "application/xml",
                        "text/xml",
                        "application/rss+xml",
                        "application/xhtml+xml",
                    }:
                        raise ValueError(f"unsupported crawl content type: {content_type}")
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise ValueError("crawl byte budget exceeded")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    html, text, links = _html_to_text_and_links(raw, str(response.url), content_type)
                    return CrawlDocument(
                        url=str(response.url),
                        text=text,
                        content_type=content_type,
                        retrieved_at=now_iso(),
                        links=tuple(links),
                        bytes_touched=len(raw),
                        html=html,
                    )
            except (httpx.HTTPError, OSError, ValueError, PermissionError) as exc:
                last_error = exc
        if last_error is None:  # pragma: no cover - loop always runs at least once
            raise RuntimeError("crawler failed without an exception")
        raise last_error


def _html_to_text_and_links(raw: bytes, url: str, content_type: str) -> tuple[str, str, list[str]]:
    decoded = raw.decode("utf-8", errors="replace")
    if content_type == "text/plain":
        return "", decoded, []
    soup = BeautifulSoup(raw, "lxml")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if href.lower().startswith("mailto:"):
            address = href.split(":", 1)[1].split("?", 1)[0]
            visible = anchor.get_text(" ", strip=True)
            if address and address.lower() not in visible.lower():
                anchor.string = f"{visible} {address}".strip()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    links: list[str] = []
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    for anchor in soup.find_all("a", href=True):
        target = urljoin(url, str(anchor["href"]))
        parsed = urlsplit(target)
        target_host = (parsed.hostname or "").lower().removeprefix("www.")
        if parsed.scheme in {"http", "https"} and target_host == host:
            links.append(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")))
    return decoded, text, list(dict.fromkeys(links))


def build_query_plan(
    context: InvestigationContext,
    *,
    known_domain: str | None = None,
    known_people: list[str] | None = None,
) -> list[str]:
    company = (context.legal_name or "").strip()
    cnpj = normalize_cnpj(context.cnpj)
    role_terms = {
        "reajuste_14133": ["diretor de engenharia", "contratos", "financeiro"],
        "acompanhamento_contratual": ["contratos", "diretor de engenharia", "jurídico contratual"],
        "licitacoes_propostas": ["licitações", "comercial", "suprimentos"],
        "orcamento_bdi": ["orçamento", "engenharia", "diretor de engenharia"],
    }.get(context.service, ["diretor", "engenharia", "comercial"])
    people = known_people if known_people is not None else list(context.extra.get("known_people") or [])
    queries = build_email_job_queries(
        company=company or None,
        cnpj=cnpj or None,
        domain=known_domain,
        known_people=people,
        role_terms=role_terms,
    )
    if company:
        queries.extend(f'"{company}" {term}' for term in role_terms)
        queries.extend(
            [
                f'"{company}" diretoria',
                f'"{company}" sócio',
                f'"{company}" contato',
                f'"{company}" telefone',
            ]
        )
    if cnpj:
        queries.append(f'"{cnpj}" telefone')
    if known_domain:
        queries.extend(
            [
                f"site:{known_domain} diretor",
                f"site:{known_domain} filetype:pdf",
            ]
        )
    return list(dict.fromkeys(query for query in queries if query.strip()))


def _host(url: str) -> str | None:
    try:
        host = (urlsplit(url).hostname or "").lower().strip(".")
    except ValueError:
        return None
    return host[4:] if host.startswith("www.") else host or None


def _candidate_allowed(host: str) -> bool:
    if host.endswith(".gov.br") or host == "gov.br":
        return False
    if any(host == suffix or host.endswith(f".{suffix}") for suffix in _EXCLUDED_HOST_SUFFIXES):
        return False
    return not any(marker in host for marker in _THIRD_PARTY_HOST_MARKERS)


def resolve_corporate_domain(
    context: InvestigationContext,
    hits: list[SearchHit],
    *,
    known_site: str | None = None,
) -> DomainResolution:
    cnpj = normalize_cnpj(context.cnpj)
    name_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", (context.legal_name or "").lower())
        if len(token) >= 4 and token not in {"ltda", "eireli", "engenharia", "construtora", "servicos"}
    ]
    grouped: dict[str, dict[str, Any]] = {}
    if known_site:
        known_host = _host(known_site)
        if known_host and _candidate_allowed(known_host):
            grouped[known_host] = {"score": 7, "reasons": {"KNOWN_SITE_OBSERVED"}, "urls": {known_site}}
    for hit in hits:
        host = _host(hit.url)
        if not host or not _candidate_allowed(host):
            continue
        row = grouped.setdefault(host, {"score": 0, "reasons": set(), "urls": set()})
        haystack = f"{hit.title} {hit.snippet}".lower()
        row["urls"].add(hit.url)
        if cnpj and cnpj in re.sub(r"\D", "", haystack):
            row["score"] += 4
            row["reasons"].add("CNPJ_EXACT_ON_RESULT")
        result_overlap = sum(1 for token in name_tokens if token in haystack)
        if result_overlap:
            row["score"] += min(3, result_overlap)
            row["reasons"].add("LEGAL_NAME_TOKEN_MATCH")
        host_overlap = sum(1 for token in name_tokens if token in host)
        if host_overlap:
            row["score"] += min(6, host_overlap * 3)
            row["reasons"].add("DOMAIN_NAME_TOKEN_MATCH")
        if host.endswith(".com.br"):
            row["score"] += 1
            row["reasons"].add("BRAZIL_CORPORATE_TLD")
        if any(word in haystack for word in ("site oficial", "institucional", "quem somos")):
            row["score"] += 2
            row["reasons"].add("OFFICIAL_SITE_LANGUAGE")
    candidates = sorted(
        (
            DomainCandidate(
                domain=host,
                score=int(row["score"]),
                reason_codes=tuple(sorted(row["reasons"])),
                evidence_urls=tuple(sorted(row["urls"])),
            )
            for host, row in grouped.items()
        ),
        key=lambda candidate: (-candidate.score, candidate.domain),
    )
    candidates = [
        candidate
        for candidate in candidates
        if "KNOWN_SITE_OBSERVED" in candidate.reason_codes or "DOMAIN_NAME_TOKEN_MATCH" in candidate.reason_codes
    ]
    if not candidates or candidates[0].score < 4:
        return DomainResolution(None, "UNKNOWN", tuple(candidates[:5]), ("NO_DEFENSIBLE_DOMAIN",))
    top = candidates[0]
    ambiguous = len(candidates) > 1 and candidates[1].score >= top.score - 1
    if ambiguous:
        return DomainResolution(None, "LOW", tuple(candidates[:5]), ("AMBIGUOUS_TOP_DOMAINS",))
    confidence = "HIGH" if top.score >= 8 else "MEDIUM"
    return DomainResolution(top.domain, confidence, tuple(candidates[:5]), top.reason_codes)


def rank_crawl_urls(
    hits: list[SearchHit],
    canonical_domain: str,
    *,
    limit: int,
    extra_urls: list[str] | tuple[str, ...] = (),
) -> list[str]:
    scored: list[tuple[int, str]] = []
    for hit in hits:
        if _host(hit.url) != canonical_domain:
            continue
        path = urlsplit(hit.url).path.lower()
        score = score_internal_url(hit.url, f"{hit.title} {hit.snippet}")
        if path in {"", "/"}:
            score += 3
        scored.append((-score, hit.url))
    for url in extra_urls:
        if _host(url) != canonical_domain:
            continue
        scored.append((-score_internal_url(url), url))
    ranked = list(dict.fromkeys(url for _score, url in sorted(scored)))
    homepage = f"https://{canonical_domain}/"
    if homepage not in ranked:
        if len(ranked) >= limit:
            ranked = ranked[: max(0, limit - 1)]
        ranked.append(homepage)
    return ranked[:limit]


def _context_snippet(text: str, start: int, end: int, *, radius: int = 140) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)].strip()


def _match_person_to_email(email: str, people: list[PersonObservation]) -> str | None:
    """Local-part signal only. Identity uses associate_person_to_email."""
    from scripts.decision_unit_intelligence.email_discovery import local_part_name_signal

    matches = [
        name
        for person in people
        if (name := normalize_name(person.person_name)) and local_part_name_signal(email, name)
    ]
    return matches[0] if len(set(matches)) == 1 else None


def extract_public_evidence(
    context: InvestigationContext,
    document: CrawlDocument,
    *,
    canonical_domain: str | None = None,
) -> ExtractedWebEvidence:
    cnpj = normalize_cnpj(context.cnpj)
    extracted = ExtractedWebEvidence()
    official_host = (canonical_domain or "").lower().removeprefix("www.")
    document_host = (_host(document.url) or "").lower().removeprefix("www.")
    cnpj_match = next(
        (
            match
            for match in _CNPJ_TEXT_RE.finditer(document.text or "")
            if normalize_cnpj(match.group(1)) == cnpj
        ),
        None,
    )
    page_cnpj_attested = bool(cnpj_match and official_host and document_host == official_host)
    page_content = document.html or document.text or ""
    page_document_witness = make_page_document_witness(page_content)
    page_content_sha256 = hashlib.sha256(page_content.encode("utf-8")).hexdigest()
    source_published_at = source_publication_timestamp(document.html)
    seen_people: set[tuple[str, str]] = set()
    for pattern in (_ROLE_THEN_NAME, _NAME_THEN_ROLE, _NAME_THEN_ROLE_LOOSE):
        for match in pattern.finditer(document.text):
            name = normalize_name(match.group("name"))
            role = match.group("role").strip()
            if not name or not plausible_person_name(name) or (name, role.lower()) in seen_people:
                continue
            seen_people.add((name, role.lower()))
            snippet = _context_snippet(document.text, match.start(), match.end())
            evidence = make_evidence(
                field="person_role",
                value=f"{name}|{role}",
                epistemic_class=EpistemicClass.OBSERVED,
                source_type="company_website",
                source_url=document.url,
                evidence_snippet=snippet,
                observed_at=document.retrieved_at,
                extraction_method="public_page_exact_text",
            )
            extracted.evidence.append(evidence)
            extracted.people.append(
                PersonObservation(
                    observation_id=stable_id("web-person", cnpj, name, role, document.url),
                    company_entity_id=cnpj,
                    person_name=name,
                    observed_role=role,
                    normalized_role_class=normalize_observed_role(role),
                    relation=PersonRelation.COMPANY_MEMBER,
                    source_type="company_website",
                    source_url=document.url,
                    snippet=snippet,
                    observed_at=document.retrieved_at,
                    epistemic_class=EpistemicClass.OBSERVED,
                    evidence_id=evidence.evidence_id,
                )
            )
    emails = list(
        dict.fromkeys(
            [
                *(normalize_email(match.group(1)) for match in _EMAIL_RE.finditer(document.text)),
                *extract_mailto_addresses(document.html),
            ]
        )
    )
    known_people = list(extracted.people)
    for extra_name in context.extra.get("known_people") or []:
        name = normalize_name(str(extra_name))
        if name and not any(normalize_name(person.person_name) == name for person in known_people):
            known_people.append(
                PersonObservation(
                    observation_id=stable_id("ctx-person", cnpj, name),
                    company_entity_id=cnpj,
                    person_name=name,
                    observed_role=None,
                    relation=PersonRelation.COMPANY_MEMBER,
                    source_type="investigation_context",
                    source_url=document.url,
                    epistemic_class=EpistemicClass.OBSERVED,
                )
            )
    for email in emails:
        if not email:
            continue
        association = associate_person_to_email(
            email,
            people=known_people,
            html=document.html,
            text=document.text,
            source_url=document.url,
            canonical_domain=canonical_domain or _host(document.url),
        )
        if association.associated and association.person_name:
            if not any(normalize_name(person.person_name) == association.person_name for person in extracted.people):
                person_evidence = make_evidence(
                    field="person_role",
                    value=association.person_name,
                    epistemic_class=EpistemicClass.OBSERVED,
                    source_type="company_website",
                    source_url=document.url,
                    evidence_snippet=association.snippet,
                    observed_at=document.retrieved_at,
                    extraction_method=association.extraction_method,
                )
                extracted.evidence.append(person_evidence)
                extracted.people.append(
                    PersonObservation(
                        observation_id=stable_id("web-person", cnpj, association.person_name, document.url),
                        company_entity_id=cnpj,
                        person_name=association.person_name,
                        observed_role=None,
                        relation=PersonRelation.COMPANY_MEMBER,
                        source_type="company_website",
                        source_url=document.url,
                        snippet=association.snippet,
                        observed_at=document.retrieved_at,
                        epistemic_class=EpistemicClass.OBSERVED,
                        evidence_id=person_evidence.evidence_id,
                    )
                )
        channel_type = classify_observed_email_channel(email)
        discovery_class = classify_email_discovery(
            email,
            epistemic=EpistemicClass.OBSERVED,
            identity_associated=association.associated,
            ambiguous=association.ambiguous,
        )
        evidence = make_evidence(
            field="email",
            value=email,
            epistemic_class=EpistemicClass.OBSERVED,
            source_type="company_website",
            source_url=document.url,
            document_sha256=page_content_sha256,
            evidence_snippet=association.snippet,
            observed_at=document.retrieved_at,
            extraction_method=association.extraction_method,
            extra={
                "reason_codes": list(association.reason_codes),
                "email_discovery_class": discovery_class.value,
            },
        )
        extracted.evidence.append(evidence)
        route_evidence_id = evidence.evidence_id
        page_identity: dict[str, Any] = {}
        binding_allowed = False
        binding_reason = "PAGE_CNPJ_NOT_ATTESTED"
        if page_cnpj_attested and cnpj_match is not None:
            binding_allowed, binding_reason = account_mailbox_binding_context(
                email=email,
                snippet=association.snippet,
                page_text=document.text,
                cnpj_span=(cnpj_match.start(), cnpj_match.end()),
                canonical_domain=official_host,
            )
        if binding_allowed and page_document_witness is None:
            binding_allowed = False
            binding_reason = "PAGE_DOCUMENT_WITNESS_UNAVAILABLE"
        if binding_allowed and cnpj_match is not None and page_document_witness is not None:
            cnpj_snippet = _context_snippet(document.text, cnpj_match.start(), cnpj_match.end())
            binding = make_evidence(
                field="account_mailbox_binding",
                value=f"{cnpj}|{email}",
                epistemic_class=EpistemicClass.OBSERVED,
                source_type="company_website",
                source_url=document.url,
                document_sha256=page_content_sha256,
                evidence_snippet=f"{cnpj_snippet} | {association.snippet}".strip(" |"),
                observed_at=document.retrieved_at,
                extraction_method=f"official_page_exact_cnpj_and_email:{binding_reason.lower()}",
                extra={
                    "page_cnpj14": cnpj,
                    "page_content_sha256": page_content_sha256,
                    "email_evidence_id": evidence.evidence_id,
                },
            )
            extracted.evidence.append(binding)
            route_evidence_id = binding.evidence_id
            page_identity = {
                "company_associated": True,
                "mailbox_company_evidence": "OBSERVED",
                "official_domain": official_host,
                "page_cnpj14": cnpj,
                "page_cnpj_evidence_id": binding.evidence_id,
                "page_cnpj_evidence_sha256": page_content_sha256,
                "page_document_witness": page_document_witness,
                "account_mailbox_binding_evidence": binding.to_dict(),
                "mailbox_observation_evidence": evidence.to_dict(),
            }
        mailbox_domain = email.rsplit("@", 1)[-1].lower().removeprefix("www.")
        official_domain_mailbox = bool(
            official_host
            and (mailbox_domain == official_host or mailbox_domain.endswith(f".{official_host}"))
        )
        extracted.channels.append(
            ChannelObservation(
                observation_id=stable_id("web-email", cnpj, email, document.url),
                company_entity_id=cnpj,
                channel_type=channel_type,
                channel_value=email,
                person_name=association.person_name if association.associated else None,
                source_type="company_website",
                source_url=document.url,
                snippet=association.snippet,
                observed_at=document.retrieved_at,
                epistemic_class=EpistemicClass.OBSERVED,
                ownership=(
                    OwnershipStatus.COMPANY_OWNED
                    if official_domain_mailbox or binding_allowed
                    else OwnershipStatus.UNKNOWN
                ),
                evidence_id=route_evidence_id,
                extra={
                    "identity_explicitly_associated": association.associated,
                    "identity_ambiguous": association.ambiguous,
                    "email_discovery_class": discovery_class.value,
                    "association_reason_codes": list(association.reason_codes),
                    "extraction_method": association.extraction_method,
                    "third_party_echo": association.third_party_echo,
                    "person_may_have_left": association.stale,
                    "account_binding_context": binding_reason,
                    **({"source_published_at": source_published_at} if source_published_at else {}),
                    **page_identity,
                },
            )
        )
    for phone_match in _PHONE_RE.finditer(document.text):
        phone = normalize_phone(phone_match.group(0))
        if not phone or phone in cnpj:
            continue
        snippet = _context_snippet(document.text, phone_match.start(), phone_match.end())
        evidence = make_evidence(
            field="company_phone",
            value=phone,
            epistemic_class=EpistemicClass.OBSERVED,
            source_type="company_website",
            source_url=document.url,
            evidence_snippet=snippet,
            observed_at=document.retrieved_at,
            extraction_method="public_page_exact_text",
        )
        extracted.evidence.append(evidence)
        extracted.channels.append(
            ChannelObservation(
                observation_id=stable_id("web-phone", cnpj, phone, document.url),
                company_entity_id=cnpj,
                channel_type=ChannelType.COMPANY_SWITCHBOARD,
                channel_value=phone,
                source_type="company_website",
                source_url=document.url,
                snippet=snippet,
                observed_at=document.retrieved_at,
                epistemic_class=EpistemicClass.OBSERVED,
                ownership=OwnershipStatus.COMPANY_OWNED,
                evidence_id=evidence.evidence_id,
                extra={"person_owns_phone": False},
            )
        )
    return extracted


def dedupe_search_hits(hits: list[SearchHit]) -> list[SearchHit]:
    unique: dict[str, SearchHit] = {}
    for hit in hits:
        parsed = urlsplit(hit.url)
        normalized = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))
        unique.setdefault(normalized, hit)
    return list(unique.values())
