"""Isolated corporate-site contact crawl.

Specialized, budget-hard planner + structural SITE_* association. Consumed
through the existing WebCrawler adapter after a defensible domain exists.
Does not rewrite public search, domain resolution, or query planning.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from scripts.decision_unit_intelligence.decision_policy import normalize_observed_role
from scripts.decision_unit_intelligence.email_discovery import (
    classify_email_discovery,
    extract_mailto_addresses,
    extract_visible_emails,
    local_part_name_signal,
    plausible_person_name,
)
from scripts.decision_unit_intelligence.email_resolution import (
    is_third_party_professional_domain,
    name_tokens,
)
from scripts.decision_unit_intelligence.evidence import make_evidence
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
from scripts.decision_unit_intelligence.reachability import (
    classify_observed_email_channel,
    email_domain,
    is_brand_mailbox,
    is_freemail,
    is_generic_mailbox,
    is_role_mailbox,
)
from scripts.decision_unit_intelligence.web_discovery import (
    CrawlDocument,
    WebCrawler,
    account_mailbox_binding_context,
)

SITE_CRAWL_VERSION = "dui.site-contact-crawl.v3"

SITE_PROFILE_EMAIL = "SITE_PROFILE_EMAIL"
SITE_TEAM_CARD_EMAIL = "SITE_TEAM_CARD_EMAIL"
SITE_MAILTO_ASSOCIATED = "SITE_MAILTO_ASSOCIATED"
SITE_STRUCTURED_CONTACT = "SITE_STRUCTURED_CONTACT"
SITE_GENERIC_ONLY = "SITE_GENERIC_ONLY"
SITE_JS_BLOCKED = "SITE_JS_BLOCKED"
SITE_NO_HIGH_VALUE_PATH = "SITE_NO_HIGH_VALUE_PATH"
SITE_STALE_OR_UNKNOWN = "SITE_STALE_OR_UNKNOWN"
SITE_ACCOUNT_MAILBOX_CONTEXT_AMBIGUOUS = "SITE_ACCOUNT_MAILBOX_CONTEXT_AMBIGUOUS"

STRONG_SITE_CODES = frozenset(
    {
        SITE_PROFILE_EMAIL,
        SITE_TEAM_CARD_EMAIL,
        SITE_MAILTO_ASSOCIATED,
        SITE_STRUCTURED_CONTACT,
    }
)

HIGH_VALUE_TERMS = (
    "equipe",
    "time",
    "team",
    "staff",
    "authors",
    "author",
    "quem-somos",
    "quem_somos",
    "quem somos",
    "diretoria",
    "diretor",
    "lideranca",
    "liderança",
    "leadership",
    "administracao",
    "administração",
    "administr",
    "engenharia",
    "comercial",
    "licitac",
    "licitações",
    "contratos",
    "contrato",
    "contato",
    "contact",
    "fale-conosco",
    "fale_conosco",
    "fale conosco",
    "imprensa",
    "press",
    "representantes",
    "unidades",
    "institucional",
    "sobre",
    "nossa-equipe",
    "corpo-tecnico",
    "profissionais",
    "colaboradores",
    "pessoas",
)

SKIP_PATH_MARKERS = (
    "/login",
    "/signin",
    "/sign-in",
    "/signon",
    "/entrar",
    "/autentic",
    "/auth/",
    "/carrinho",
    "/cart",
    "/checkout",
    "/loja/",
    "/webmail",
    "/roundcube",
    "/owa",
    "/outlook",
    "/wp-admin",
    "/wp-login",
    "/wp-json",
    "/calendario",
    "/calendário",
    "/calendar",
    "/agenda",
    "/busca",
    "/search",
    "/pesquisa",
    "/feed",
    "/comment",
    "/cdn-cgi/",
)

SKIP_QUERY_MARKERS = ("q=", "s=", "search=", "query=", "filter=", "sort=", "facet=")
TRACKING_QUERY_KEYS = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "mc_cid", "mc_eid"}
)
CORPORATE_SUBDOMAIN_LABELS = frozenset(
    {
        "www",
        "www2",
        "institucional",
        "equipe",
        "time",
        "contato",
        "contact",
        "engenharia",
        "comercial",
        "portal",
        "site",
        "sobre",
    }
)
CARD_TAGS = frozenset({"article", "li", "tr", "section", "figure", "aside"})
NAME_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "strong", "b"})
FOOTER_PARENTS = frozenset({"footer", "header", "nav"})
_ROLE_RE = re.compile(
    r"diretor(?:a)?(?:\s+(?:de\s+)?(?:engenharia|comercial|opera(?:ç|c)[oõ]es|contratos))?"
    r"|gerente(?:\s+(?:de\s+)?(?:engenharia|comercial|contratos|licita(?:ç|c)[oõ]es|suprimentos))?"
    r"|s[oó]ci[oa](?:[-\s]+administrador(?:a)?)?|propriet[aá]ri[oa]|presidente"
    r"|coordenador(?:a)?|engenheir[oa]|respons[aá]vel\s+t[eé]cnico"
    r"|representante\s+legal|preposto|signat[aá]rio",
    re.I,
)
_NAME_WORD = r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÀ-ÖØ-öø-ÿ'’-]+"
_NAME_RE = re.compile(rf"{_NAME_WORD}(?:\s+(?:(?:d[aeo]s?|e)\s+)?{_NAME_WORD}){{1,4}}")
_STALE_RE = re.compile(
    r"\b(?:ex[-\s](?:diretor|gerente|s[oó]cio|colaborador|funcion[aá]rio|presidente)|"
    r"saiu(?:\s+da\s+empresa)?|n[aã]o\s+faz\s+mais\s+parte|antigo\s+diretor|"
    r"desligad[oa]|falecid[oa]|aposentad[oa])\b",
    re.I,
)
_EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w-])", re.I)
_OBFUSCATED_EMAIL_RE = re.compile(
    r"([A-Z0-9._%+-]+)\s*(?:\[at\]|\(at\)|\s+at\s+|\[arroba\]|\(arroba\))\s*"
    r"([A-Z0-9.-]+)\s*(?:\[dot\]|\(dot\)|\s+dot\s+|\[ponto\]|\.)\s*"
    r"([A-Z]{2,})(?:\s*(?:\[dot\]|\(dot\)|\s+dot\s+|\[ponto\]|\.)\s*([A-Z]{2,}))?",
    re.I,
)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?55\s*)?(?:\(?\d{2}\)?[\s.-]*)?\d{4,5}[\s.-]*\d{4}(?!\d)")
_CNPJ_TEXT_RE = re.compile(
    r"(?<!\d)(\d{2}[.\s]?\d{3}[.\s]?\d{3}[\/\s]?\d{4}[-\s]?\d{2})(?!\d)"
)
_SITEMAP_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_FRESHNESS_RE = re.compile(
    r"(?:atualizado|publicado|last(?:[- ]modified)?|datePublished|dateModified)"
    r"[:\s]*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{2,4})",
    re.I,
)


@dataclass(frozen=True)
class SiteCrawlBudget:
    max_pages: int = 12
    max_depth: int = 3
    max_bytes: int = 2_500_000
    timeout_seconds: float = 20.0
    max_redirects: int = 5
    requests_per_minute: int = 20
    max_sitemap_urls: int = 80

    def __post_init__(self) -> None:
        for value in (
            self.max_pages,
            self.max_depth,
            self.max_bytes,
            self.max_redirects,
            self.requests_per_minute,
            self.max_sitemap_urls,
        ):
            if value <= 0:
                raise ValueError("site crawl budgets must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("site crawl budgets must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SITE_CRAWL_BUDGET_DEFAULTS = SiteCrawlBudget()


@dataclass
class SiteBudgetTracker:
    budget: SiteCrawlBudget
    pages: int = 0
    bytes_touched: int = 0
    redirects: int = 0
    started_at: float = field(default_factory=monotonic)
    request_times: list[float] = field(default_factory=list)
    stop_reason: str | None = None

    def remaining_bytes(self) -> int:
        return max(0, self.budget.max_bytes - self.bytes_touched)

    def elapsed(self) -> float:
        return monotonic() - self.started_at

    def allow_fetch(self, *, rate_limit: bool = True) -> bool:
        if self.pages >= self.budget.max_pages:
            self.stop_reason = self.stop_reason or "BUDGET_PAGES"
            return False
        if self.remaining_bytes() <= 0:
            self.stop_reason = self.stop_reason or "BUDGET_BYTES"
            return False
        if self.elapsed() >= self.budget.timeout_seconds:
            self.stop_reason = self.stop_reason or "BUDGET_TIME"
            return False
        if self.redirects > self.budget.max_redirects:
            self.stop_reason = self.stop_reason or "BUDGET_REDIRECTS"
            return False
        if rate_limit:
            self._wait_for_rate()
        return True

    def record(self, *, bytes_touched: int = 0, redirects: int = 0) -> None:
        self.pages += 1
        self.bytes_touched += max(0, bytes_touched)
        self.redirects += max(0, redirects)
        self.request_times.append(monotonic())

    def snapshot(self) -> dict[str, Any]:
        return {
            "pages": self.pages,
            "max_pages": self.budget.max_pages,
            "bytes_touched": self.bytes_touched,
            "max_bytes": self.budget.max_bytes,
            "redirects": self.redirects,
            "max_redirects": self.budget.max_redirects,
            "elapsed_seconds": round(self.elapsed(), 3),
            "timeout_seconds": self.budget.timeout_seconds,
            "requests_per_minute": self.budget.requests_per_minute,
            "max_depth": self.budget.max_depth,
            "max_sitemap_urls": self.budget.max_sitemap_urls,
            "stop_reason": self.stop_reason,
            "exceeded": bool(self.stop_reason),
        }

    def _wait_for_rate(self) -> None:
        window = [stamp for stamp in self.request_times if monotonic() - stamp < 60.0]
        self.request_times = window
        if len(window) < self.budget.requests_per_minute:
            return
        wait = 60.0 - (monotonic() - window[0])
        if wait > 0:
            remaining = self.budget.timeout_seconds - self.elapsed()
            if remaining <= 0:
                return
            sleep(min(wait, remaining))


@dataclass(frozen=True)
class SiteUrlSeed:
    url: str
    score: int
    depth: int
    origin: str
    anchor_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SiteContactRecord:
    email: str | None
    person_name: str | None
    role: str | None
    phone: str | None
    associated: bool
    candidate: bool
    same_block: bool
    page_title: str
    structured_data: dict[str, Any]
    observed_at: str
    freshness: str | None
    reason_codes: tuple[str, ...]
    extraction_method: str
    snippet: str
    source_url: str
    page_type: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SiteCrawlResult:
    canonical_domain: str
    high_value_urls: list[str] = field(default_factory=list)
    visited: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    contacts: list[SiteContactRecord] = field(default_factory=list)
    people: list[PersonObservation] = field(default_factory=list)
    channels: list[ChannelObservation] = field(default_factory=list)
    evidence: list[FieldEvidence] = field(default_factory=list)
    budget: dict[str, Any] = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)
    stop_reason: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_domain": self.canonical_domain,
            "high_value_urls": self.high_value_urls,
            "visited": self.visited,
            "skipped": self.skipped,
            "contacts": [item.to_dict() for item in self.contacts],
            "budget": self.budget,
            "reason_codes": self.reason_codes,
            "stop_reason": self.stop_reason,
            "metrics": self.metrics,
        }


def host_key(url: str) -> str | None:
    try:
        host = (urlsplit(url).hostname or "").lower().strip(".")
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


def canonicalize_site_url(url: str, *, prefer_https: bool = True) -> str | None:
    raw = (url or "").strip()
    if not raw or raw.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return None
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    scheme = "https" if prefer_https else parsed.scheme.lower()
    host = parsed.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    query = urlencode(query_pairs)
    return urlunsplit((scheme, host, path, query, ""))


def should_skip_site_url(url: str) -> tuple[bool, str]:
    parsed = urlsplit(url)
    path = (parsed.path or "/").lower()
    query = (parsed.query or "").lower()
    for marker in SKIP_PATH_MARKERS:
        if marker in path:
            return True, f"skip:{marker.strip('/')}"
    if any(marker in query for marker in SKIP_QUERY_MARKERS):
        return True, "skip:search-or-filter"
    kept = [(key, value) for key, value in parse_qsl(parsed.query) if key.lower() not in TRACKING_QUERY_KEYS]
    if len(kept) >= 3:
        return True, "skip:combinatorial"
    if path.count("/") > 8 or len(path) > 180:
        return True, "skip:deep-or-long-path"
    return False, ""


def score_high_value_path(url: str, anchor_text: str = "") -> int:
    path = urlsplit(url).path.lower()
    hay = f"{path} {anchor_text.lower()}"
    score = 0
    for term in HIGH_VALUE_TERMS:
        if term in hay:
            score += 10
    if path in {"", "/"}:
        score += 2
    if any(token in path for token in ("/equipe/", "/time/", "/staff/", "/author/", "/authors/")):
        score += 8
    if path.endswith(".pdf"):
        score -= 8
    return score


def classify_page_type(url: str, anchor_text: str = "") -> str:
    hay = f"{urlsplit(url).path.lower()} {anchor_text.lower()}"
    for label, needles in (
        ("equipe", ("equipe", "time", "team", "staff", "nossa-equipe", "colaboradores")),
        ("diretoria", ("diretoria", "diretor", "lideranca", "liderança", "leadership")),
        ("contato", ("contato", "contact", "fale-conosco", "fale conosco")),
        ("institucional", ("quem-somos", "quem somos", "institucional", "sobre")),
        ("comercial", ("comercial", "representantes")),
        ("engenharia", ("engenharia", "corpo-tecnico")),
        ("licitacoes", ("licitac", "contratos")),
        ("imprensa", ("imprensa", "press", "authors", "author")),
        ("unidades", ("unidades",)),
        ("profile", ("/equipe/", "/time/", "/staff/", "/author/")),
        ("homepage", ()),
    ):
        if label == "homepage":
            continue
        if any(needle in hay for needle in needles):
            return label
    if urlsplit(url).path in {"", "/"}:
        return "homepage"
    return "other"


def is_same_corporate_host(url: str, canonical_domain: str) -> bool:
    host = host_key(url)
    expected = (canonical_domain or "").lower().removeprefix("www.")
    if not host or not expected:
        return False
    if host == expected:
        return True
    if host.endswith(f".{expected}"):
        label = host[: -len(expected) - 1].split(".")[-1]
        return label in CORPORATE_SUBDOMAIN_LABELS
    return False


def parse_sitemap_urls(payload: str, *, limit: int) -> list[str]:
    found: list[str] = []
    for raw in _SITEMAP_LOC_RE.findall(payload or ""):
        clean = canonicalize_site_url(html_lib.unescape(raw.strip()))
        if clean and clean not in found:
            found.append(clean)
        if len(found) >= limit:
            break
    return found


def parse_robots_sitemaps(payload: str) -> list[str]:
    found: list[str] = []
    for line in (payload or "").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("sitemap:"):
            target = canonicalize_site_url(stripped.split(":", 1)[1].strip())
            if target and target not in found:
                found.append(target)
    return found


def recover_obfuscated_emails(text: str) -> list[str]:
    decoded = html_lib.unescape(text or "")
    found: list[str] = []
    for match in _OBFUSCATED_EMAIL_RE.finditer(decoded):
        local, domain, tld, extra = match.group(1), match.group(2), match.group(3), match.group(4)
        host = f"{domain}.{tld}" + (f".{extra}" if extra else "")
        email = normalize_email(f"{local}@{host}")
        if email:
            found.append(email)
    joined = re.sub(
        r"([A-Z0-9._%+-]+)\s*(?:@|\[at\]|\(at\))\s*([A-Z0-9.-]+\.[A-Z]{2,}(?:\.[A-Z]{2,})?)",
        lambda match: f"{match.group(1)}@{match.group(2)}",
        decoded,
        flags=re.I,
    )
    for raw in _EMAIL_RE.findall(joined):
        email = normalize_email(raw)
        if email:
            found.append(email)
    return _dedupe_email_prefixes(found)


def recover_broken_span_emails(html: str) -> list[str]:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    compact = re.sub(r"\s+", "", soup.get_text("", strip=True))
    compact = html_lib.unescape(compact)
    found: list[str] = []
    for raw in _EMAIL_RE.findall(compact):
        email = normalize_email(raw)
        if email:
            found.append(email)
    return list(dict.fromkeys(found))


def seed_corporate_site_urls(
    *,
    canonical_domain: str,
    extra_urls: Iterable[str] = (),
    sitemap_urls: Iterable[str] = (),
    robots_sitemaps: Iterable[str] = (),
    internal_links: Iterable[tuple[str, str]] = (),
) -> list[SiteUrlSeed]:
    expected = canonical_domain.lower().removeprefix("www.")
    homepage = canonicalize_site_url(f"https://{expected}/")
    seeds: list[SiteUrlSeed] = []
    seen: set[str] = set()

    def _add(url: str, *, origin: str, depth: int, anchor: str = "") -> None:
        clean = canonicalize_site_url(url)
        if not clean or clean in seen or not is_same_corporate_host(clean, expected):
            return
        skip, _reason = should_skip_site_url(clean)
        if skip:
            return
        seen.add(clean)
        score = score_high_value_path(clean, anchor)
        if origin == "search_hit":
            score += 20
        seeds.append(
            SiteUrlSeed(
                url=clean,
                score=score,
                depth=depth,
                origin=origin,
                anchor_text=anchor,
            )
        )

    if homepage:
        _add(homepage, origin="homepage", depth=0)
    for path in (
        "/contato",
        "/fale-conosco",
        "/comercial",
        "/licitacoes",
        "/contratos",
        "/engenharia",
        "/equipe",
        "/diretoria",
        "/institucional",
        "/unidades",
        "/quem-somos",
        "/sobre",
    ):
        _add(f"https://{expected}{path}", origin="seed_path", depth=0)
    _add(f"https://{expected}/robots.txt", origin="robots", depth=0)
    _add(f"https://{expected}/sitemap.xml", origin="sitemap", depth=0)
    for url in extra_urls:
        _add(url, origin="search_hit", depth=0)
    for url in robots_sitemaps:
        _add(url, origin="robots", depth=0)
    for url in sitemap_urls:
        _add(url, origin="sitemap", depth=1)
    for url, anchor in internal_links:
        _add(url, origin="internal_link", depth=1, anchor=anchor)
    seeds.sort(key=lambda item: (-item.score, item.depth, item.url))
    return seeds


def _is_xml_payload(payload: str) -> bool:
    head = (payload or "").lstrip()[:200].lower()
    return head.startswith("<?xml") or head.startswith("<urlset") or head.startswith("<sitemapindex")


def extract_nav_links(html: str, page_url: str, canonical_domain: str) -> list[tuple[str, str]]:
    if not html or _is_xml_payload(html):
        return []
    soup = BeautifulSoup(html, "lxml")
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:")):
            continue
        absolute = canonicalize_site_url(urljoin(page_url, href))
        if not absolute or absolute in seen or not is_same_corporate_host(absolute, canonical_domain):
            continue
        skip, _reason = should_skip_site_url(absolute)
        if skip:
            continue
        seen.add(absolute)
        text = anchor.get_text(" ", strip=True)
        links.append((absolute, text))
    return links


def page_looks_js_blocked(html: str, text: str) -> bool:
    if not html:
        return False
    soup = BeautifulSoup(html, "lxml")
    scripts = soup.find_all("script")
    visible = re.sub(r"\s+", " ", text or soup.get_text(" ", strip=True)).strip()
    return len(scripts) >= 4 and len(visible) < 80 and not _EMAIL_RE.search(visible)


def _page_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    heading = soup.find(["h1", "h2"])
    return heading.get_text(" ", strip=True) if heading else ""


def _freshness(soup: BeautifulSoup, text: str) -> str | None:
    time_node = soup.find("time", datetime=True)
    if time_node:
        return str(time_node.get("datetime") or "").strip() or None
    match = _FRESHNESS_RE.search(text or "")
    return match.group(1) if match else None


def _visible_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def _in_chrome(node: Tag) -> bool:
    for parent in node.parents:
        if isinstance(parent, Tag) and parent.name in FOOTER_PARENTS:
            return True
    return False


_LEADING_NAME_NOISE = frozenset(
    {"comite", "comitê", "equipe", "time", "nossa", "nosso", "conheca", "conheça", "sobre", "diretoria"}
)


def _names_in_blob(blob: str) -> list[str]:
    found: list[str] = []
    for segment in _ROLE_RE.split(blob or ""):
        for match in _NAME_RE.finditer(segment):
            tokens = (normalize_name(match.group(0)) or "").split()
            while tokens and fold_text(tokens[0]) in _LEADING_NAME_NOISE:
                tokens = tokens[1:]
            name = normalize_name(" ".join(tokens))
            if name and plausible_person_name(name) and not _ROLE_RE.search(name):
                found.append(name)
    return list(dict.fromkeys(found))


def _dedupe_email_prefixes(emails: list[str]) -> list[str]:
    unique = list(dict.fromkeys(email for email in emails if email))
    return [email for email in unique if not any(other != email and other.startswith(email) for other in unique)]


def _role_in_blob(blob: str) -> str | None:
    match = _ROLE_RE.search(blob or "")
    return match.group(0).strip() if match else None


def _phone_in_blob(blob: str) -> str | None:
    match = _PHONE_RE.search(blob or "")
    return normalize_phone(match.group(0)) if match else None


def _emails_from_container(container: Tag) -> tuple[list[str], list[str]]:
    mailtos: list[str] = []
    visible: list[str] = []
    for anchor in container.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if href.lower().startswith("mailto:"):
            email = normalize_email(href.split(":", 1)[1].split("?", 1)[0])
            if email:
                mailtos.append(email)
    blob = container.get_text(" ", strip=True)
    visible.extend(extract_visible_emails(blob))
    visible.extend(recover_obfuscated_emails(blob))
    visible.extend(recover_broken_span_emails(str(container)))
    return _dedupe_email_prefixes(mailtos), _dedupe_email_prefixes(visible)


def _name_from_container(container: Tag) -> str | None:
    for tag in container.find_all(NAME_TAGS):
        name = normalize_name(tag.get_text(" ", strip=True))
        if name and plausible_person_name(name):
            return name
    itemprop = container.find(attrs={"itemprop": re.compile(r"^name$", re.I)})
    if itemprop:
        name = normalize_name(itemprop.get_text(" ", strip=True))
        if name and plausible_person_name(name):
            return name
    names = _names_in_blob(container.get_text(" ", strip=True))
    return names[0] if len(names) == 1 else None


def _parse_jsonld_blocks(html: str) -> list[dict[str, Any]]:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    blocks: list[dict[str, Any]] = []
    for node in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = node.string or node.get_text() or ""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            item = stack.pop(0)
            if isinstance(item, dict):
                blocks.append(item)
                graph = item.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
    return blocks


def extract_structured_people(html: str, visible_text: str) -> list[dict[str, Any]]:
    people: list[dict[str, Any]] = []
    visible_fold = fold_text(visible_text or "")
    for block in _parse_jsonld_blocks(html):
        types = block.get("@type") or block.get("type") or ""
        type_blob = " ".join(types) if isinstance(types, list) else str(types)
        if "person" not in type_blob.lower() and "employee" not in type_blob.lower():
            continue
        name = normalize_name(str(block.get("name") or ""))
        email = normalize_email(str(block.get("email") or "").replace("mailto:", ""))
        role = str(block.get("jobTitle") or block.get("roleName") or "") or None
        if not name or not email:
            continue
        coherent = fold_text(name) in visible_fold and email.lower() in (visible_text or "").lower()
        people.append(
            {
                "name": name,
                "email": email,
                "role": role,
                "coherent": coherent,
                "source": "jsonld",
            }
        )
    if not html:
        return people
    soup = BeautifulSoup(html, "lxml")
    for node in soup.find_all(attrs={"itemtype": re.compile(r"schema\.org/Person", re.I)}):
        name_node = node.find(attrs={"itemprop": re.compile(r"^name$", re.I)})
        email_node = node.find(attrs={"itemprop": re.compile(r"^email$", re.I)})
        role_node = node.find(attrs={"itemprop": re.compile(r"jobTitle", re.I)})
        name = normalize_name(name_node.get_text(" ", strip=True) if name_node else "")
        email_raw = ""
        if email_node:
            email_raw = str(email_node.get("href") or email_node.get_text(" ", strip=True))
        email = normalize_email(email_raw.replace("mailto:", ""))
        role = role_node.get_text(" ", strip=True) if role_node else None
        if not name or not email:
            continue
        blob = node.get_text(" ", strip=True)
        coherent = fold_text(name) in fold_text(blob) and email.lower() in blob.lower()
        people.append(
            {
                "name": name,
                "email": email,
                "role": role,
                "coherent": coherent,
                "source": "microdata",
            }
        )
    return people


def _looks_card_div(node: Tag) -> bool:
    class_blob = " ".join(node.get("class") or []).lower()
    identity = f"{class_blob} {node.get('id') or ''} {node.get('itemtype') or ''}".lower()
    return any(
        token in identity for token in ("card", "member", "pessoa", "person", "equipe", "staff", "team", "diretor")
    )


def _card_containers(soup: BeautifulSoup) -> list[Tag]:
    candidates: list[Tag] = []
    for node in soup.find_all([*CARD_TAGS, "div"]):
        if _in_chrome(node):
            continue
        if node.name == "div" and not _looks_card_div(node):
            continue
        text = node.get_text(" ", strip=True)
        if 16 <= len(text) <= 520 and (_NAME_RE.search(text) or node.find("a", href=re.compile(r"^mailto:", re.I))):
            candidates.append(node)
    leaves: list[Tag] = []
    for node in candidates:
        if any(isinstance(child, Tag) and child in candidates for child in node.descendants):
            continue
        leaves.append(node)
    return leaves


def associate_site_email(
    *,
    email: str,
    person_name: str | None,
    other_visible_names: list[str],
    mailto_in_block: bool,
    unique_in_block: bool,
    unique_on_profile: bool,
    structured_coherent: bool,
    generic: bool,
    in_footer: bool,
    stale: bool,
    foreign_domain: bool,
    js_blocked: bool,
) -> tuple[bool, bool, list[str], str]:
    """Return (associated, candidate, reason_codes, method). Never uses text-window proximity."""
    reasons: list[str] = []
    if generic or in_footer:
        # Footer/header of the official site is not person identity, but it is
        # still a company mailbox. Do not treat chrome as commercial junk.
        return False, False, [SITE_GENERIC_ONLY], "company_mailbox_unbound_to_person"
    if js_blocked:
        return False, False, [SITE_JS_BLOCKED], "js_blocked"
    if stale or foreign_domain:
        return False, True, [SITE_STALE_OR_UNKNOWN], "stale_or_foreign"
    if person_name and other_visible_names:
        others = [name for name in other_visible_names if fold_text(name) != fold_text(person_name)]
        for other in others:
            if local_part_name_signal(email, other):
                return False, True, [SITE_STALE_OR_UNKNOWN], "cross_card_or_mismatched_mailto"
    if structured_coherent and person_name:
        return True, False, [SITE_STRUCTURED_CONTACT], "structured_contact"
    if unique_on_profile and person_name:
        reasons.append(SITE_PROFILE_EMAIL)
        if mailto_in_block:
            reasons.append(SITE_MAILTO_ASSOCIATED)
        return True, False, reasons, "profile_page"
    if unique_in_block and person_name:
        reasons.append(SITE_TEAM_CARD_EMAIL)
        if mailto_in_block:
            reasons.append(SITE_MAILTO_ASSOCIATED)
        return True, False, reasons, "team_card"
    if person_name:
        return False, True, [], "candidate_proximity_not_promoted"
    return False, False, [], "unresolved"


def extract_site_contacts(
    document: CrawlDocument,
    *,
    canonical_domain: str,
    target_cnpj: str | None = None,
) -> list[SiteContactRecord]:
    html = document.html or ""
    text = _visible_text(html) if html else (document.text or "")
    soup = BeautifulSoup(html, "lxml") if html else BeautifulSoup("", "lxml")
    title = _page_title(soup)
    freshness = _freshness(soup, text)
    page_type = classify_page_type(document.url)
    js_blocked = page_looks_js_blocked(html, text)
    expected = canonical_domain.lower().removeprefix("www.")
    records: list[SiteContactRecord] = []
    claimed_emails: set[str] = set()

    if js_blocked:
        records.append(
            SiteContactRecord(
                email=None,
                person_name=None,
                role=None,
                phone=None,
                associated=False,
                candidate=False,
                same_block=False,
                page_title=title,
                structured_data={},
                observed_at=document.retrieved_at,
                freshness=freshness,
                reason_codes=(SITE_JS_BLOCKED,),
                extraction_method="js_blocked",
                snippet=text[:240],
                source_url=document.url,
                page_type=page_type,
            )
        )
        return records

    visible_names = _names_in_blob(text)
    structured = extract_structured_people(html, text)
    for item in structured:
        email = item["email"]
        foreign = _foreign_or_generic_domain(email, expected)
        generic = _generic_box(email)
        associated, candidate, reasons, method = associate_site_email(
            email=email,
            person_name=item["name"],
            other_visible_names=visible_names,
            mailto_in_block=False,
            unique_in_block=False,
            unique_on_profile=False,
            structured_coherent=bool(item["coherent"]),
            generic=generic,
            in_footer=False,
            stale=False,
            foreign_domain=foreign,
            js_blocked=False,
        )
        if not item["coherent"] and SITE_STRUCTURED_CONTACT in reasons:
            associated = False
            candidate = True
            reasons = [code for code in reasons if code != SITE_STRUCTURED_CONTACT]
            method = "structured_incoherent"
        records.append(
            _record(
                email=email,
                name=item["name"] if associated or candidate else None,
                role=item["role"],
                associated=associated,
                candidate=candidate,
                same_block=True,
                title=title,
                structured={"source": item["source"], "coherent": item["coherent"]},
                observed_at=document.retrieved_at,
                freshness=freshness,
                reasons=reasons,
                method=method,
                snippet=f"{item['name']} {email}",
                url=document.url,
                page_type=page_type,
            )
        )
        claimed_emails.add(email)

    profile_unique = _is_individual_profile(document.url, text, visible_names)

    for card in _card_containers(soup):
        blob = card.get_text(" ", strip=True)
        mailtos, visible_emails = _emails_from_container(card)
        emails = list(dict.fromkeys([*mailtos, *visible_emails]))
        names = _names_in_blob(blob)
        tagged = _name_from_container(card)
        if tagged and tagged not in names:
            names = [tagged, *names]
        names = list(dict.fromkeys(names))
        in_footer = _in_chrome(card)
        stale = bool(_STALE_RE.search(blob))
        role = _role_in_blob(blob)
        phone = _phone_in_blob(blob)
        unique = len(names) == 1 and len(emails) == 1
        for email in emails:
            if email in claimed_emails:
                continue
            name = names[0] if len(names) == 1 else None
            if len(names) > 1:
                name = None
            associated, candidate, reasons, method = associate_site_email(
                email=email,
                person_name=name,
                other_visible_names=visible_names,
                mailto_in_block=email in mailtos,
                unique_in_block=unique,
                unique_on_profile=False,
                structured_coherent=False,
                generic=_generic_box(email),
                in_footer=in_footer,
                stale=stale,
                foreign_domain=_foreign_or_generic_domain(email, expected),
                js_blocked=False,
            )
            records.append(
                _record(
                    email=email,
                    name=name if associated or candidate else None,
                    role=role,
                    phone=phone,
                    associated=associated,
                    candidate=candidate or (len(names) > 1 and not associated),
                    same_block=True,
                    title=title,
                    structured={},
                    observed_at=document.retrieved_at,
                    freshness=freshness,
                    reasons=reasons if reasons else ((SITE_GENERIC_ONLY,) if in_footer or _generic_box(email) else ()),
                    method=method if method != "unresolved" or len(names) <= 1 else "ambiguous_nearby_not_promoted",
                    snippet=blob[:280],
                    url=document.url,
                    page_type=page_type,
                )
            )
            claimed_emails.add(email)

    footer_emails = _chrome_emails(soup)
    page_emails = _dedupe_email_prefixes(
        [
            *extract_mailto_addresses(html),
            *extract_visible_emails(text),
            *recover_obfuscated_emails(text),
            *recover_broken_span_emails(html),
            *footer_emails,
        ]
    )
    for email in page_emails:
        if email in claimed_emails:
            continue
        in_footer = email in footer_emails
        generic = _generic_box(email) or in_footer
        foreign = _foreign_or_generic_domain(email, expected)
        stale = bool(_STALE_RE.search(text))
        unique_profile = (
            profile_unique
            and len(_dedupe_email_prefixes([*extract_visible_emails(text), *extract_mailto_addresses(html)])) == 1
        )
        name = visible_names[0] if unique_profile and len(visible_names) == 1 else None
        associated, candidate, reasons, method = associate_site_email(
            email=email,
            person_name=name,
            other_visible_names=visible_names,
            mailto_in_block=False,
            unique_in_block=False,
            unique_on_profile=bool(unique_profile and name),
            structured_coherent=False,
            generic=generic,
            in_footer=in_footer,
            stale=stale,
            foreign_domain=foreign,
            js_blocked=False,
        )
        if not associated and not generic and not in_footer and visible_names:
            candidate = True
            method = "candidate_proximity_not_promoted"
        records.append(
            _record(
                email=email,
                name=name if associated or (candidate and unique_profile) else None,
                role=_role_in_blob(text) if associated else None,
                associated=associated,
                candidate=candidate,
                same_block=bool(unique_profile),
                title=title,
                structured={},
                observed_at=document.retrieved_at,
                freshness=freshness,
                reasons=reasons if reasons else ((SITE_GENERIC_ONLY,) if generic or in_footer else ()),
                method=method,
                snippet=_snippet(text, email),
                url=document.url,
                page_type=page_type,
            )
        )
        claimed_emails.add(email)

    normalized_target = normalize_cnpj(target_cnpj)
    page_cnpj_match = next(
        (
            match
            for match in _CNPJ_TEXT_RE.finditer(text)
            if normalize_cnpj(match.group(1)) == normalized_target
        ),
        None,
    )
    document_host = (urlsplit(document.url).hostname or "").lower().removeprefix("www.")
    if normalized_target and page_cnpj_match is not None and document_host == expected:
        page_sha256 = hashlib.sha256((document.html or document.text or "").encode("utf-8")).hexdigest()
        cnpj_snippet = _snippet(text, page_cnpj_match.group(1))
        attested_records: list[SiteContactRecord] = []
        for record in records:
            if not record.email:
                attested_records.append(record)
                continue
            allowed, binding_reason = account_mailbox_binding_context(
                email=record.email,
                snippet=record.snippet,
                page_text=text,
                cnpj_span=(page_cnpj_match.start(), page_cnpj_match.end()),
                canonical_domain=expected,
            )
            if allowed:
                attested_records.append(
                    replace(
                        record,
                        structured_data={
                            **record.structured_data,
                            "page_cnpj14": normalized_target,
                            "page_cnpj_evidence_sha256": page_sha256,
                            "page_cnpj_snippet": cnpj_snippet,
                            "account_binding_context": binding_reason,
                        },
                    )
                )
            else:
                attested_records.append(
                    replace(
                        record,
                        reason_codes=tuple(
                            dict.fromkeys(
                                (*record.reason_codes, SITE_ACCOUNT_MAILBOX_CONTEXT_AMBIGUOUS)
                            )
                        ),
                        structured_data={
                            **record.structured_data,
                            "account_binding_context": binding_reason,
                        },
                    )
                )
        records = attested_records
    return records


def contacts_to_observations(
    context: InvestigationContext,
    records: list[SiteContactRecord],
    *,
    canonical_domain: str | None = None,
) -> tuple[list[PersonObservation], list[ChannelObservation], list[FieldEvidence]]:
    cnpj = normalize_cnpj(context.cnpj)
    expected = (canonical_domain or "").lower().removeprefix("www.")
    people: list[PersonObservation] = []
    channels: list[ChannelObservation] = []
    evidence: list[FieldEvidence] = []
    seen_people: set[str] = set()
    for record in records:
        if record.associated and record.person_name and record.person_name not in seen_people:
            seen_people.add(record.person_name)
            person_evidence = make_evidence(
                field="person_role",
                value=f"{record.person_name}|{record.role or ''}",
                epistemic_class=EpistemicClass.OBSERVED,
                source_type="company_website",
                source_url=record.source_url,
                evidence_snippet=record.snippet,
                observed_at=record.observed_at,
                extraction_method=record.extraction_method,
                extra={"reason_codes": list(record.reason_codes), "page_title": record.page_title},
            )
            evidence.append(person_evidence)
            people.append(
                PersonObservation(
                    observation_id=stable_id("site-person", cnpj, record.person_name, record.source_url),
                    company_entity_id=cnpj,
                    person_name=record.person_name,
                    observed_role=record.role,
                    normalized_role_class=normalize_observed_role(record.role),
                    relation=PersonRelation.COMPANY_MEMBER,
                    source_type="company_website",
                    source_url=record.source_url,
                    snippet=record.snippet,
                    observed_at=record.observed_at,
                    epistemic_class=EpistemicClass.OBSERVED,
                    evidence_id=person_evidence.evidence_id,
                    extra={"reason_codes": list(record.reason_codes), "freshness": record.freshness},
                )
            )
        if not record.email:
            continue
        associated = bool(record.associated and record.person_name)
        discovery = classify_email_discovery(
            record.email,
            epistemic=EpistemicClass.OBSERVED,
            identity_associated=associated,
            ambiguous=record.candidate and not associated,
        )
        foreign = bool(expected and _foreign_or_generic_domain(record.email, expected))
        email_evidence = make_evidence(
            field="email",
            value=record.email,
            epistemic_class=EpistemicClass.OBSERVED,
            source_type="company_website",
            source_url=record.source_url,
            evidence_snippet=record.snippet,
            observed_at=record.observed_at,
            extraction_method=record.extraction_method,
            extra={
                "reason_codes": list(record.reason_codes),
                "email_discovery_class": discovery.value,
                "page_title": record.page_title,
                "freshness": record.freshness,
                "structured_data": record.structured_data,
                "same_block": record.same_block,
            },
        )
        evidence.append(email_evidence)
        page_cnpj = normalize_cnpj(record.structured_data.get("page_cnpj14"))
        page_sha256 = str(record.structured_data.get("page_cnpj_evidence_sha256") or "").lower()
        route_evidence_id = email_evidence.evidence_id
        page_identity: dict[str, Any] = {}
        if page_cnpj == cnpj and re.fullmatch(r"[0-9a-f]{64}", page_sha256):
            binding = make_evidence(
                field="account_mailbox_binding",
                value=f"{cnpj}|{record.email}",
                epistemic_class=EpistemicClass.OBSERVED,
                source_type="company_website",
                source_url=record.source_url,
                evidence_snippet=(
                    f"{record.structured_data.get('page_cnpj_snippet') or ''} | {record.snippet}"
                ).strip(" |"),
                observed_at=record.observed_at,
                extraction_method=(
                    "official_page_exact_cnpj_and_email:"
                    f"{str(record.structured_data.get('account_binding_context') or '').lower()}"
                ),
                extra={
                    "page_cnpj14": cnpj,
                    "page_content_sha256": page_sha256,
                    "email_evidence_id": email_evidence.evidence_id,
                },
            )
            evidence.append(binding)
            route_evidence_id = binding.evidence_id
            page_identity = {
                "company_associated": True,
                "mailbox_company_evidence": "OBSERVED",
                "official_domain": expected,
                "page_cnpj14": cnpj,
                "page_cnpj_evidence_id": binding.evidence_id,
                "page_cnpj_evidence_sha256": page_sha256,
                "account_mailbox_binding_evidence": binding.to_dict(),
                "mailbox_observation_evidence": email_evidence.to_dict(),
            }
        page_attested = bool(page_identity)
        company_owned = bool((not foreign and not is_freemail(record.email)) or page_attested)
        channels.append(
            ChannelObservation(
                observation_id=stable_id("site-email", cnpj, record.email, record.source_url),
                company_entity_id=cnpj,
                channel_type=classify_observed_email_channel(record.email),
                channel_value=record.email,
                person_name=record.person_name if associated else None,
                source_type="company_website",
                source_url=record.source_url,
                snippet=record.snippet,
                observed_at=record.observed_at,
                epistemic_class=EpistemicClass.OBSERVED,
                ownership=OwnershipStatus.COMPANY_OWNED if company_owned else OwnershipStatus.UNKNOWN,
                evidence_id=route_evidence_id,
                extra={
                    "identity_explicitly_associated": associated,
                    "identity_ambiguous": bool(record.candidate and not associated),
                    "company_associated": company_owned,
                    "mailbox_company_evidence": "OBSERVED" if company_owned else "UNKNOWN",
                    "email_discovery_class": discovery.value,
                    "association_reason_codes": list(record.reason_codes),
                    "account_binding_context": record.structured_data.get(
                        "account_binding_context"
                    ),
                    "extraction_method": record.extraction_method,
                    "site_association_strength": "strong"
                    if associated
                    else (
                        "candidate"
                        if record.candidate
                        else ("company_only" if SITE_GENERIC_ONLY in record.reason_codes else "rejected")
                    ),
                    "candidate_person_name": record.person_name if record.candidate and not associated else None,
                    "page_title": record.page_title,
                    "page_type": record.page_type,
                    "freshness": record.freshness,
                    **({"source_published_at": record.freshness} if record.freshness else {}),
                    "same_block": record.same_block,
                    "site_crawl_version": SITE_CRAWL_VERSION,
                    **page_identity,
                },
            )
        )
        if record.phone:
            phone_evidence = make_evidence(
                field="company_phone",
                value=record.phone,
                epistemic_class=EpistemicClass.OBSERVED,
                source_type="company_website",
                source_url=record.source_url,
                evidence_snippet=record.snippet,
                observed_at=record.observed_at,
                extraction_method="site_card_phone",
            )
            evidence.append(phone_evidence)
            channels.append(
                ChannelObservation(
                    observation_id=stable_id("site-phone", cnpj, record.phone, record.source_url),
                    company_entity_id=cnpj,
                    channel_type=ChannelType.COMPANY_SWITCHBOARD,
                    channel_value=record.phone,
                    source_type="company_website",
                    source_url=record.source_url,
                    snippet=record.snippet,
                    observed_at=record.observed_at,
                    epistemic_class=EpistemicClass.OBSERVED,
                    ownership=OwnershipStatus.COMPANY_OWNED,
                    evidence_id=phone_evidence.evidence_id,
                    extra={"person_owns_phone": False},
                )
            )
    return people, channels, evidence


def run_site_contact_crawl(
    *,
    crawler: WebCrawler,
    context: InvestigationContext,
    canonical_domain: str,
    seed_urls: Iterable[str] = (),
    budget: SiteCrawlBudget | None = None,
    baseline: bool = False,
    rate_limit: bool = False,
) -> SiteCrawlResult:
    """Bounded corporate-site contact crawl. baseline=True fetches seeds only."""
    expected = canonical_domain.lower().removeprefix("www.")
    tracker = SiteBudgetTracker(budget or SiteCrawlBudget())
    result = SiteCrawlResult(canonical_domain=expected)
    queued: list[SiteUrlSeed] = seed_corporate_site_urls(
        canonical_domain=expected,
        extra_urls=seed_urls,
    )
    seen = {item.url for item in queued}
    sitemap_consumed = False
    robots_consumed = False
    index = 0
    while index < len(queued) and tracker.allow_fetch(rate_limit=rate_limit):
        item = queued[index]
        index += 1
        skip, reason = should_skip_site_url(item.url)
        if skip:
            result.skipped.append(f"{reason}:{item.url}")
            continue
        if item.depth > tracker.budget.max_depth:
            result.skipped.append(f"skip:depth:{item.url}")
            continue
        try:
            document = crawler.fetch(item.url, max_bytes=tracker.remaining_bytes())
        except Exception as exc:
            result.skipped.append(f"{type(exc).__name__}:{item.url}")
            tracker.record(bytes_touched=0)
            continue
        final_url = canonicalize_site_url(document.url) or document.url
        redirects = 1 if host_key(final_url) != host_key(item.url) or final_url != item.url else 0
        tracker.record(bytes_touched=document.bytes_touched, redirects=redirects)
        if not is_same_corporate_host(final_url, expected):
            result.skipped.append(f"skip:external-redirect:{item.url}->{final_url}")
            continue
        result.visited.append(final_url)
        if score_high_value_path(final_url, item.anchor_text) >= 10:
            result.high_value_urls.append(final_url)

        payload = document.html or document.text or ""
        if not robots_consumed and item.origin == "robots":
            robots_consumed = True
            if not baseline:
                for sitemap in parse_robots_sitemaps(payload):
                    _enqueue(queued, seen, sitemap, origin="robots", depth=0, canonical_domain=expected)
        if not sitemap_consumed and (item.origin == "sitemap" or final_url.endswith("sitemap.xml")):
            sitemap_consumed = True
            sitemap_urls = parse_sitemap_urls(payload, limit=tracker.budget.max_sitemap_urls)
            if len(_SITEMAP_LOC_RE.findall(payload)) > tracker.budget.max_sitemap_urls:
                tracker.stop_reason = tracker.stop_reason or "BUDGET_SITEMAP"
            if not baseline:
                for url in sitemap_urls:
                    _enqueue(
                        queued,
                        seen,
                        url,
                        origin="sitemap",
                        depth=min(item.depth + 1, tracker.budget.max_depth),
                        canonical_domain=expected,
                    )

        if _looks_markup(document):
            contacts = extract_site_contacts(
                document,
                canonical_domain=expected,
                target_cnpj=context.cnpj,
            )
            result.contacts.extend(contacts)
            people, channels, evidence = contacts_to_observations(context, contacts, canonical_domain=expected)
            result.people.extend(people)
            result.channels.extend(channels)
            result.evidence.extend(evidence)
            if not baseline:
                for url, anchor in extract_nav_links(document.html, final_url, expected):
                    _enqueue(
                        queued,
                        seen,
                        url,
                        origin="internal_link",
                        depth=item.depth + 1,
                        anchor=anchor,
                        canonical_domain=expected,
                    )

    if tracker.stop_reason is None and index >= len(queued):
        tracker.stop_reason = "COMPLETE"
    if not result.high_value_urls:
        result.reason_codes.append(SITE_NO_HIGH_VALUE_PATH)
    result.high_value_urls = list(dict.fromkeys(result.high_value_urls))
    result.visited = list(dict.fromkeys(result.visited))
    result.budget = tracker.snapshot()
    result.stop_reason = tracker.stop_reason
    result.metrics = summarize_site_crawl(result)
    result.reason_codes = list(dict.fromkeys([*result.reason_codes, *result.metrics.get("reason_codes", [])]))
    return result


def summarize_site_crawl(result: SiteCrawlResult) -> dict[str, Any]:
    emails = [item for item in result.contacts if item.email]
    named = [item for item in emails if item.associated and item.person_name]
    candidates = [item for item in emails if item.candidate and not item.associated]
    generic = [item for item in emails if SITE_GENERIC_ONLY in item.reason_codes]
    false_assoc = 0
    yield_by_type: dict[str, int] = {}
    for item in named:
        yield_by_type[item.page_type] = yield_by_type.get(item.page_type, 0) + 1
    reason_codes = []
    for item in result.contacts:
        reason_codes.extend(item.reason_codes)
    return {
        "high_value_pages": len(result.high_value_urls),
        "pages_fetched": len(result.visited),
        "pages_per_account": len(result.visited),
        "emails_observed": len({item.email for item in emails if item.email}),
        "named_associated": len({(item.email, item.person_name) for item in named}),
        "candidates": len(candidates),
        "generic_only": len(generic),
        "false_association": false_assoc,
        "latency_ms": int(float(result.budget.get("elapsed_seconds") or 0) * 1000),
        "bytes_touched": int(result.budget.get("bytes_touched") or 0),
        "yield_by_page_type": yield_by_type,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "stop_reason": result.stop_reason,
        "budget_exceeded": bool(result.budget.get("exceeded")),
    }


class MappingCrawler:
    """In-memory WebCrawler for fixtures. Optional redirects are resolved once."""

    def __init__(
        self,
        pages: dict[str, str],
        *,
        redirects: dict[str, str] | None = None,
        content_types: dict[str, str] | None = None,
    ) -> None:
        self.pages = {canonicalize_site_url(url) or url: body for url, body in pages.items()}
        self.redirects = {
            (canonicalize_site_url(src) or src): (canonicalize_site_url(dst) or dst)
            for src, dst in (redirects or {}).items()
        }
        self.content_types = content_types or {}
        self.fetched: list[str] = []

    def fetch(self, url: str, *, max_bytes: int) -> CrawlDocument:
        start = canonicalize_site_url(url) or url
        final = self.redirects.get(start, start)
        self.fetched.append(start)
        if final not in self.pages:
            raise FileNotFoundError(final)
        raw = self.pages[final]
        encoded = raw.encode("utf-8")
        if len(encoded) > max_bytes:
            raise ValueError("crawl byte budget exceeded")
        content_type = self.content_types.get(final) or _guess_content_type(final, raw)
        links = [target for target, _anchor in extract_nav_links(raw, final, host_key(final) or "")]
        return CrawlDocument(
            url=final,
            text=_visible_text(raw) if "html" in content_type else raw,
            content_type=content_type,
            retrieved_at=now_iso(),
            links=tuple(links),
            bytes_touched=len(encoded),
            html=raw if "html" in content_type or "xml" in content_type else "",
        )


class FileCorpusCrawler:
    """Local corporate-site corpus. Implements WebCrawler. No network."""

    def __init__(self, root: Path, *, origin: str, redirects: dict[str, str] | None = None) -> None:
        self.root = Path(root)
        self.origin = origin.rstrip("/")
        self.redirects = redirects or {}
        self.fetched: list[str] = []

    def fetch(self, url: str, *, max_bytes: int) -> CrawlDocument:
        start = canonicalize_site_url(url) or url
        final = canonicalize_site_url(self.redirects.get(start, start)) or start
        self.fetched.append(start)
        path = _resolve_corpus_path(self.root, self.origin, final)
        if path is None:
            raise FileNotFoundError(final)
        raw = path.read_text(encoding="utf-8", errors="replace")
        encoded = raw.encode("utf-8")
        if len(encoded) > max_bytes:
            raise ValueError("crawl byte budget exceeded")
        content_type = _guess_content_type(str(path), raw)
        domain = host_key(self.origin) or ""
        links = [target for target, _anchor in extract_nav_links(raw, final, domain)]
        return CrawlDocument(
            url=final,
            text=_visible_text(raw) if "html" in content_type else raw,
            content_type=content_type,
            retrieved_at=now_iso(),
            links=tuple(links),
            bytes_touched=len(encoded),
            html=raw if "html" in content_type or "xml" in content_type else raw,
        )


def load_fixture_corpus(root: Path) -> tuple[FileCorpusCrawler, str]:
    root = Path(root)
    meta_path = root / "_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    origin = str(meta.get("origin") or f"https://{root.name}/")
    redirects = {str(src): str(dst) for src, dst in (meta.get("redirects") or {}).items()}
    return FileCorpusCrawler(root, origin=origin, redirects=redirects), host_key(origin) or root.name


def _enqueue(
    queued: list[SiteUrlSeed],
    seen: set[str],
    url: str,
    *,
    origin: str,
    depth: int,
    canonical_domain: str,
    anchor: str = "",
) -> None:
    clean = canonicalize_site_url(url)
    if not clean or clean in seen or not is_same_corporate_host(clean, canonical_domain):
        return
    skip, _reason = should_skip_site_url(clean)
    if skip:
        return
    seen.add(clean)
    queued.append(
        SiteUrlSeed(
            url=clean,
            score=score_high_value_path(clean, anchor),
            depth=depth,
            origin=origin,
            anchor_text=anchor,
        )
    )
    queued.sort(key=lambda item: (-item.score, item.depth, item.url))


def _generic_box(email: str) -> bool:
    return bool(is_generic_mailbox(email) or is_role_mailbox(email) or is_brand_mailbox(email))


def _foreign_or_generic_domain(email: str, canonical_domain: str) -> bool:
    domain = email_domain(email)
    if not domain:
        return True
    if is_third_party_professional_domain(domain):
        return True
    expected = canonical_domain.lower().removeprefix("www.")
    if domain == expected:
        return False
    if domain.endswith(f".{expected}"):
        return False
    if expected.endswith(f".{domain}"):
        return True
    return domain != expected


def _is_individual_profile(url: str, text: str, names: list[str]) -> bool:
    path = urlsplit(url).path.lower()
    if not any(token in path for token in ("/equipe/", "/time/", "/staff/", "/author/", "/diretor", "/profissional")):
        return False
    if path.rstrip("/").count("/") < 2:
        return False
    if len(names) != 1:
        return False
    tokens = name_tokens(names[0])
    return len(tokens) >= 2 and tokens[0] in path and tokens[-1] in path


def _chrome_emails(soup: BeautifulSoup) -> list[str]:
    found: list[str] = []
    for chrome in soup.find_all(FOOTER_PARENTS):
        found.extend(extract_visible_emails(chrome.get_text(" ", strip=True)))
        found.extend(extract_mailto_addresses(str(chrome)))
    return list(dict.fromkeys(found))


def _snippet(text: str, email: str, *, radius: int = 160) -> str:
    hay = text or ""
    idx = hay.lower().find(email.lower())
    if idx < 0:
        return hay[: radius * 2].strip()
    return hay[max(0, idx - radius) : min(len(hay), idx + len(email) + radius)].strip()


def _record(
    *,
    email: str | None,
    name: str | None,
    associated: bool,
    candidate: bool,
    same_block: bool,
    title: str,
    structured: dict[str, Any],
    observed_at: str,
    freshness: str | None,
    reasons: Iterable[str],
    method: str,
    snippet: str,
    url: str,
    page_type: str,
    role: str | None = None,
    phone: str | None = None,
) -> SiteContactRecord:
    codes = tuple(dict.fromkeys(reasons))
    if associated and not (set(codes) & STRONG_SITE_CODES):
        associated = False
        candidate = True
    if associated:
        candidate = False
    return SiteContactRecord(
        email=email,
        person_name=name if associated or candidate else None,
        role=role,
        phone=phone,
        associated=associated,
        candidate=candidate,
        same_block=same_block,
        page_title=title,
        structured_data=structured,
        observed_at=observed_at,
        freshness=freshness,
        reason_codes=codes,
        extraction_method=method,
        snippet=snippet,
        source_url=url,
        page_type=page_type,
    )


def _looks_markup(document: CrawlDocument) -> bool:
    ctype = (document.content_type or "").lower()
    if "html" in ctype:
        return True
    if document.html and ("<html" in document.html.lower() or "<article" in document.html.lower()):
        return True
    return False


def _guess_content_type(url_or_path: str, payload: str) -> str:
    lowered = url_or_path.lower()
    if lowered.endswith(".xml") or payload.lstrip().startswith("<urlset") or payload.lstrip().startswith("<?xml"):
        return "application/xml"
    if lowered.endswith(".txt") or payload.lstrip().lower().startswith("user-agent"):
        return "text/plain"
    return "text/html"


def _resolve_corpus_path(root: Path, origin: str, url: str) -> Path | None:
    parsed = urlsplit(url)
    origin_parsed = urlsplit(origin if "://" in origin else f"https://{origin}")
    rel = parsed.path or "/"
    origin_path = (origin_parsed.path or "/").rstrip("/")
    if origin_path and rel.startswith(origin_path):
        rel = rel[len(origin_path) :] or "/"
    if rel in {"", "/"}:
        for name in ("index.html", "index.htm", "home.html"):
            candidate = root / name
            if candidate.is_file():
                return candidate
        return None
    rel = rel.lstrip("/")
    direct = root / rel
    if direct.is_file():
        return direct
    html = direct.with_suffix(".html") if not direct.suffix else direct
    if html.is_file():
        return html
    if (direct / "index.html").is_file():
        return direct / "index.html"
    if Path(str(direct) + ".html").is_file():
        return Path(str(direct) + ".html")
    return None
