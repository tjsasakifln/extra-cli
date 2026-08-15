"""Public-document miner: empresa → documento → pessoa/cargo → email observado.

This module never invents a person or an email. It never assigns
EMAIL_VALIDATED. Observation in a public document is
OBSERVED_IN_PUBLIC_DOCUMENT, not CURRENT_IDENTITY_PROVEN.
MX/DNS are not consulted. Loose textual proximity is not proof.
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import re
import socket
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

from scripts.decision_unit_intelligence.decision_policy import (
    classify_person_relation,
    is_legal_entity_name,
    normalize_observed_role,
)
from scripts.decision_unit_intelligence.email_discovery import (
    EmailDiscoveryClass,
    classify_email_discovery,
)
from scripts.decision_unit_intelligence.email_resolution import is_third_party_professional_domain
from scripts.decision_unit_intelligence.evidence import make_evidence
from scripts.decision_unit_intelligence.models import (
    ChannelObservation,
    ChannelType,
    ConflictRecord,
    CostObservation,
    EpistemicClass,
    FieldAspect,
    FieldEvidence,
    OwnershipStatus,
    PersonObservation,
    SearchAttempt,
    fold_text,
    normalize_cnpj,
    normalize_email,
    normalize_name,
    now_iso,
    stable_id,
)
from scripts.decision_unit_intelligence.providers.base import InvestigationContext, ProviderResult
from scripts.decision_unit_intelligence.reachability import (
    email_domain,
    is_brand_mailbox,
    is_generic_mailbox,
    is_role_mailbox,
    looks_nominal_local,
)

REASON_DOC_IDENTITY_ASSOCIATED = "DOC_IDENTITY_ASSOCIATED"
REASON_DOC_EMAIL_OBSERVED = "DOC_EMAIL_OBSERVED"
REASON_DOC_STALE = "DOC_STALE"
REASON_DOC_AMBIGUOUS_PERSON = "DOC_AMBIGUOUS_PERSON"
REASON_DOC_THIRD_PARTY_DOMAIN = "DOC_THIRD_PARTY_DOMAIN"
REASON_DOC_COMPANY_MISMATCH = "DOC_COMPANY_MISMATCH"
REASON_DOC_UNREADABLE = "DOC_UNREADABLE"
REASON_DOC_NO_CONTACT = "DOC_NO_CONTACT"

DOC_REASON_CODES = (
    REASON_DOC_IDENTITY_ASSOCIATED,
    REASON_DOC_EMAIL_OBSERVED,
    REASON_DOC_STALE,
    REASON_DOC_AMBIGUOUS_PERSON,
    REASON_DOC_THIRD_PARTY_DOMAIN,
    REASON_DOC_COMPANY_MISMATCH,
    REASON_DOC_UNREADABLE,
    REASON_DOC_NO_CONTACT,
)

DOC_EPISTEMIC_OBSERVED = "OBSERVED_IN_PUBLIC_DOCUMENT"
DOC_EPISTEMIC_CURRENT = "CURRENT_IDENTITY_PROVEN"

EXTRACTOR_VERSION = "dui.public-documents.v1"
STALE_YEARS_DEFAULT = 3
SNIPPET_RADIUS = 140
MIN_READABLE_CHARS = 40

SOURCE_CLASS_ADMIN_PROCESS = "administrative_process"
SOURCE_CLASS_EDITAL = "edital_anexo"
SOURCE_CLASS_CONTRATO = "contrato"
SOURCE_CLASS_ATA = "ata"
SOURCE_CLASS_PROPOSTA = "proposta"
SOURCE_CLASS_DIARIO = "diario_oficial"
SOURCE_CLASS_ART_RRT = "art_rrt"
SOURCE_CLASS_RELATORIO = "relatorio_institucional"
SOURCE_CLASS_ORGAO = "orgao_anexo"
SOURCE_CLASS_ASSOCIACAO = "associacao_evento"
SOURCE_CLASS_INDEXED = "indexed_public_file"
SOURCE_CLASS_UNKNOWN = "unknown_public_document"

_EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w-])", re.I)
_MAILTO_RE = re.compile(r"(?i)mailto:([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})")
_CNPJ_RE = re.compile(r"\b(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})\b")
_ISO_DATE_RE = re.compile(r"\b(20\d{2}|19\d{2})-(\d{2})-(\d{2})\b")
_BR_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2}|19\d{2})\b")
_LONG_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+de\s+(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|"
    r"agosto|setembro|outubro|novembro|dezembro)\s+de\s+(20\d{2}|19\d{2})\b",
    re.I,
)
_MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
_NAME_WORD = r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÀ-ÖØ-öø-ÿ'’-]+"
_NAME_PATTERN = rf"{_NAME_WORD}(?:\s+(?:(?:d[aeo]s?|e)\s+)?{_NAME_WORD}){{1,4}}"
_NAME_RE = re.compile(_NAME_PATTERN)
_CAPS_NAME_RE = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}(?:\s+(?:(?:D[AEO]S?|E)\s+)?[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,4}\b")
_ROLE_RE = re.compile(
    r"(diretor(?:a)?(?:\s+(?:t[eé]cnic[oa]|comercial|de\s+engenharia|de\s+opera[cç][oõ]es|"
    r"financeiro|administrativ[oa]|geral))?|"
    r"gerente(?:\s+de\s+(?:contratos|licita[cç][oõ]es|engenharia|obras))?|"
    r"s[oó]ci[oa](?:[- ]administrador)?|propriet[aá]ri[oa]|presidente|"
    r"representante(?:\s+legal)?|procurador(?:a)?|preposto|signat[aá]ri[oa]|"
    r"respons[aá]vel\s+t[eé]cnic[oa]|engenheir[oa](?:\s+civil|\s+respons[aá]vel)?|"
    r"coordenador(?:a)?|administrador(?:a)?)",
    re.I,
)
_SIGNATURE_CUE_RE = re.compile(
    r"(atenciosamente|cordialmente|respeitosamente|sem\s+mais|"
    r"assinatura|subscreve|pelo\s+contratad[oa]|pela\s+contratada)",
    re.I,
)
_LABEL_RE = re.compile(
    r"(?:e-?mail|correio(?:\s+eletr[oô]nico)?|respons[aá]vel(?:\s+t[eé]cnic[oa])?|"
    r"representante(?:\s+legal)?|signat[aá]ri[oa]|preposto|procurador)\s*[:\-]",
    re.I,
)
_STALE_LANG_RE = re.compile(
    r"\b(?:ex[-\s](?:diretor|gerente|s[oó]cio|colaborador|funcion[aá]rio|presidente)|"
    r"saiu(?:\s+da\s+empresa)?|n[aã]o\s+faz\s+mais\s+parte|antigo\s+diretor|"
    r"desligad[oa]|falecid[oa]|aposentad[oa]|v[ií]nculo\s+encerrado)\b",
    re.I,
)
_CONSORTIUM_RE = re.compile(r"\bcons[oó]rcio\b", re.I)
_HOLDING_RE = re.compile(r"\bholding\b|\bparticipa[cç][oõ]es\b", re.I)
_GOV_DOMAIN_RE = re.compile(r"(?:^|\.)gov\.br$|(?:^|\.)mil\.br$|(?:^|\.)jus\.br$")
_LEAK_HOST_RE = re.compile(
    r"pastebin|ghostbin|raidforums|breachforums|haveibeenpwned|intelx\.|"
    r"leak-?base|combos?list|stealer|ulpmarket",
    re.I,
)
_REJECT_PATH_RE = re.compile(r"/(login|signin|sign-in|auth|conta/entrar)(/|$)", re.I)
_DOC_LINK_RE = re.compile(
    r"""(?:href|src)\s*=\s*["']([^"']+\.(?:pdf|docx?|odt)(?:\?[^"']*)?)["']""",
    re.I,
)
_PREFERRED_DOC_HOST = (
    "gov.br",
    "pncp.gov.br",
    "doe",
    "diario",
    "transparencia",
    "licitac",
    "compras",
    "crea",
    "cau.org",
    "diariomunicipal",
)
_ECHO_HOST_MARKERS = (
    "casadosdados",
    "econodata",
    "escavador",
    "cnpj.biz",
    "consultacnpj",
    "empresadois",
    "guiamais",
    "solutudo",
    "checkpj",
    "guiapj",
)
_TEMPLATE_DOC_MARKERS = (
    "modelo-de-contrato",
    "modelo_de_contrato",
    "modelo-contrato",
    "modelo_contrato",
    "jucespsorocaba",
    "modelo-de-alteracao",
    "modelo_de_alteracao",
    "/ltda/modelo",
)

DocumentFetcher = Callable[["PublicDocumentQuery", str, int], "FetchedDocument"]


class SearchBackendLike(Protocol):
    backend_id: str

    def search(self, query: str, *, limit: int) -> list[Any]: ...


@dataclass(frozen=True)
class DocumentBudget:
    max_queries: int = 4
    max_results_per_query: int = 5
    max_documents: int = 6
    max_bytes: int = 4_000_000
    timeout_seconds: float = 15.0
    stale_years: int = STALE_YEARS_DEFAULT

    def __post_init__(self) -> None:
        for value in (self.max_queries, self.max_results_per_query, self.max_documents, self.max_bytes):
            if value <= 0:
                raise ValueError("document miner budgets must be positive")


@dataclass(frozen=True)
class NamedPersonHint:
    name: str
    role: str | None = None


@dataclass(frozen=True)
class PublicDocumentQuery:
    cnpj: str
    legal_name: str | None = None
    aliases: tuple[str, ...] = ()
    domain: str | None = None
    named_people: tuple[NamedPersonHint, ...] = ()
    contract_refs: tuple[str, ...] = ()
    process_refs: tuple[str, ...] = ()
    known_urls: tuple[str, ...] = ()
    budget: DocumentBudget = field(default_factory=DocumentBudget)
    reference_date: str | None = None


@dataclass(frozen=True)
class FetchedDocument:
    url: str
    fetched_at: str
    sha256: str
    bytes_touched: int
    content_type: str
    text: str
    pages: tuple[tuple[int, str], ...] = ()
    source_class: str = SOURCE_CLASS_UNKNOWN
    title: str = ""
    published_at: str | None = None
    extraction_method: str = "text"
    readable: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StructuralUnit:
    kind: str
    text: str
    page: int | None
    section: str | None
    company_bound: bool


@dataclass(frozen=True)
class DocumentAssociation:
    email: str
    person_name: str | None
    role: str | None
    associated: bool
    ambiguous: bool
    stale: bool
    discarded: bool
    reason_codes: tuple[str, ...]
    extraction_method: str
    snippet: str
    source_url: str
    document_sha256: str
    page: int | None
    section: str | None
    source_class: str
    company_matched: bool
    current_identity_proven: bool = False
    document_epistemic_class: str = DOC_EPISTEMIC_OBSERVED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PublicDocumentMetrics:
    documents_found: int = 0
    documents_useful: int = 0
    documents_unreadable: int = 0
    emails_observed: int = 0
    emails_nominally_associated: int = 0
    people_corroborated: int = 0
    stale: int = 0
    ambiguous: int = 0
    third_party_discarded: int = 0
    company_mismatch: int = 0
    searches: int = 0
    bytes_touched: int = 0
    duration_ms: int = 0
    cost_brl: float = 0.0
    incremental_vs_web: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PublicDocumentMinerResult:
    documents: list[FetchedDocument] = field(default_factory=list)
    associations: list[DocumentAssociation] = field(default_factory=list)
    people: list[PersonObservation] = field(default_factory=list)
    channels: list[ChannelObservation] = field(default_factory=list)
    evidence: list[FieldEvidence] = field(default_factory=list)
    conflicts: list[ConflictRecord] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    metrics: PublicDocumentMetrics = field(default_factory=PublicDocumentMetrics)
    attempts: list[SearchAttempt] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "documents": [
                {
                    "url": doc.url,
                    "fetched_at": doc.fetched_at,
                    "sha256": doc.sha256,
                    "source_class": doc.source_class,
                    "extraction_method": doc.extraction_method,
                    "bytes_touched": doc.bytes_touched,
                    "readable": doc.readable,
                }
                for doc in self.documents
            ],
            "associations": [item.to_dict() for item in self.associations],
            "reason_codes": list(self.reason_codes),
            "metrics": self.metrics.to_dict(),
            "queries": list(self.queries),
        }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def snippet_around(text: str, needle: str, radius: int = SNIPPET_RADIUS) -> str:
    if not text:
        return ""
    folded = text
    idx = fold_text(folded).find(fold_text(needle))
    if idx < 0:
        raw = text.find(needle)
        idx = raw if raw >= 0 else 0
    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)
    chunk = re.sub(r"\s+", " ", text[start:end]).strip()
    return chunk[: 2 * radius + 40]


def host_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def is_public_http_url(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if _LEAK_HOST_RE.search(parsed.hostname) or _REJECT_PATH_RE.search(parsed.path or ""):
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


def classify_source_class(url: str, title: str = "", text: str = "") -> str:
    blob = fold_text(" ".join((url, title, text[:2000])))
    host = host_of(url)
    if any(tok in blob for tok in ("diario oficial", "diário oficial", "doe ", "/doe", "dom ")):
        return SOURCE_CLASS_DIARIO
    if any(tok in blob for tok in (" art ", " rrt ", "crea-", "cau/")):
        return SOURCE_CLASS_ART_RRT
    if "ata " in blob or "ata de" in blob:
        return SOURCE_CLASS_ATA
    if "proposta" in blob:
        return SOURCE_CLASS_PROPOSTA
    if "edital" in blob or "anexo" in blob:
        return SOURCE_CLASS_EDITAL
    if "contrato" in blob:
        return SOURCE_CLASS_CONTRATO
    if "processo administrativo" in blob or "processo n" in blob:
        return SOURCE_CLASS_ADMIN_PROCESS
    if any(tok in blob for tok in ("relatorio", "relatório", "apresentacao", "apresentação")):
        return SOURCE_CLASS_RELATORIO
    if any(tok in blob for tok in ("associacao", "associação", "seminario", "congresso", "workshop")):
        return SOURCE_CLASS_ASSOCIACAO
    if host.endswith(".gov.br") or host == "gov.br":
        return SOURCE_CLASS_ORGAO
    if url.lower().endswith(".pdf") or "filetype=pdf" in blob:
        return SOURCE_CLASS_INDEXED
    return SOURCE_CLASS_UNKNOWN


def extract_cnpjs(text: str) -> list[str]:
    found = [normalize_cnpj(match.group(1)) for match in _CNPJ_RE.finditer(text or "")]
    return list(dict.fromkeys(cnpj for cnpj in found if cnpj))


def extract_emails(text: str) -> list[str]:
    found = [normalize_email(match.group(1)) for match in _EMAIL_RE.finditer(text or "")]
    found.extend(normalize_email(match.group(1)) for match in _MAILTO_RE.finditer(text or ""))
    return list(dict.fromkeys(email for email in found if email))


def parse_document_dates(text: str) -> list[datetime]:
    dates: list[datetime] = []
    for match in _ISO_DATE_RE.finditer(text or ""):
        dates.append(_safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
    for match in _BR_DATE_RE.finditer(text or ""):
        dates.append(_safe_date(int(match.group(3)), int(match.group(2)), int(match.group(1))))
    for match in _LONG_DATE_RE.finditer(text or ""):
        month = _MONTHS.get(fold_text(match.group(2)))
        if month:
            dates.append(_safe_date(int(match.group(3)), month, int(match.group(1))))
    return [item for item in dates if item is not None]


def _safe_date(year: int, month: int, day: int) -> datetime | None:
    try:
        return datetime(year, month, day, tzinfo=UTC)
    except ValueError:
        return None


def reference_datetime(query: PublicDocumentQuery) -> datetime:
    if query.reference_date:
        parsed = _parse_iso_day(query.reference_date)
        if parsed:
            return parsed
    return datetime.now(UTC)


def _parse_iso_day(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            return None


def significant_name_tokens(value: str | None) -> list[str]:
    stop = {"ltda", "eireli", "epp", "mei", "cia", "sa", "engenharia", "construtora", "servicos", "serviços"}
    return [tok for tok in re.findall(r"[a-z0-9]{4,}", fold_text(value)) if tok not in stop]


_NEGATED_COMPANY_RE = re.compile(
    r"n[aã]o\s+se\s+trata\s+d[aeo]|exceto\s+a?\s*|exclu[ií]d[oa]\s+a?\s*",
    re.I,
)


def _word_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{4,}", fold_text(text)))


def company_mentioned(query: PublicDocumentQuery, text: str) -> bool:
    blob = fold_text(text)
    words = _word_tokens(text)
    target = normalize_cnpj(query.cnpj)
    if target and target in "".join(ch for ch in text if ch.isdigit()):
        return True
    names = [query.legal_name, *query.aliases]
    for name in names:
        folded = fold_text(name)
        if not folded:
            continue
        if folded in blob:
            idx = blob.find(folded)
            around = blob[max(0, idx - 48) : idx + len(folded) + 8]
            if _NEGATED_COMPANY_RE.search(around):
                continue
            return True
        tokens = significant_name_tokens(name)
        # Word tokens only — never treat "empresaexemplo" in an email as the razão.
        if len(tokens) >= 2 and all(tok in words for tok in tokens[:3]):
            return True
    return False


def other_company_dominant(query: PublicDocumentQuery, text: str) -> bool:
    """True when the unit is about another PJ and does not bind the target."""
    if company_mentioned(query, text):
        return False
    cnpjs = extract_cnpjs(text)
    target = normalize_cnpj(query.cnpj)
    if cnpjs and target and target not in cnpjs:
        return True
    our_names = [fold_text(query.legal_name), *[fold_text(alias) for alias in query.aliases]]
    our_names = [name for name in our_names if name]
    blob = fold_text(text)
    if is_legal_entity_name(text) and our_names and not any(name in blob for name in our_names):
        return True
    return False


def is_public_organ_email(email: str) -> bool:
    domain = email_domain(email) or ""
    return bool(_GOV_DOMAIN_RE.search(domain) or "prefeitura" in domain or "camara" in domain)


def account_domains(query: PublicDocumentQuery) -> set[str]:
    domains: set[str] = set()
    raw = (query.domain or "").strip().lower().removeprefix("www.")
    if raw:
        domains.add(raw)
    return domains


def email_matches_account_domain(email: str, query: PublicDocumentQuery) -> bool:
    """True when the account has no known domain, or the mailbox is on that domain."""
    expected = account_domains(query)
    if not expected:
        return True
    domain = (email_domain(email) or "").lower().removeprefix("www.")
    if not domain:
        return False
    return any(domain == item or domain.endswith(f".{item}") for item in expected)


def is_discarded_third_party_email(email: str, query: PublicDocumentQuery) -> bool:
    domain = email_domain(email)
    if is_public_organ_email(email):
        return True
    if is_third_party_professional_domain(domain):
        return True
    if not email_matches_account_domain(email, query):
        return True
    return False


def is_non_person_mailbox(email: str) -> bool:
    return is_generic_mailbox(email) or is_role_mailbox(email) or is_brand_mailbox(email)


_NAME_STOP = frozenset(
    {
        "diretor",
        "diretora",
        "gerente",
        "presidente",
        "representante",
        "procurador",
        "procuradora",
        "preposto",
        "signatario",
        "signatária",
        "signataria",
        "engenheiro",
        "engenheira",
        "coordenador",
        "coordenadora",
        "administrador",
        "administradora",
        "responsavel",
        "responsável",
        "socio",
        "sócio",
        "socia",
        "sócia",
        "ltda",
        "eireli",
        "cnpj",
        "cpf",
        "email",
        "e-mail",
        "atenciosamente",
        "cordialmente",
        "empresa",
        "construtora",
        "holding",
        "consorcio",
        "consórcio",
        "contrato",
        "processo",
        "anexo",
    }
)


def _trim_name(raw: str) -> str | None:
    words: list[str] = []
    for word in raw.split():
        folded = fold_text(word).strip(".,;:")
        if folded in _NAME_STOP or is_legal_entity_name(word):
            break
        if _ROLE_RE.fullmatch(word):
            break
        words.append(word)
    candidate = normalize_name(" ".join(words))
    if not candidate or is_legal_entity_name(candidate):
        return None
    if _ROLE_RE.fullmatch(candidate):
        return None
    if fold_text(candidate) in {"e mail", "email", "nome completo"}:
        return None
    if len(candidate.split()) < 2:
        return None
    return candidate


def extract_person_names(text: str) -> list[str]:
    names: list[str] = []
    for line in (text or "").splitlines() or [text or ""]:
        for match in list(_NAME_RE.finditer(line)) + list(_CAPS_NAME_RE.finditer(line)):
            candidate = _trim_name(match.group(0))
            if candidate:
                names.append(candidate)
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = fold_text(name)
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def extract_role(text: str) -> str | None:
    match = _ROLE_RE.search(text or "")
    if not match:
        return None
    role = re.sub(r"\s+", " ", match.group(0)).strip()
    return role or None


def names_compatible(left: str, right: str) -> bool:
    a = set(significant_name_tokens(left))
    b = set(significant_name_tokens(right))
    if not a or not b:
        return fold_text(left) == fold_text(right)
    return len(a & b) >= 2 or (len(a) == 1 and a <= b) or (len(b) == 1 and b <= a)


def hint_matches(name: str, query: PublicDocumentQuery) -> bool:
    if not query.named_people:
        return False
    return any(names_compatible(name, hint.name) for hint in query.named_people)


def assess_staleness(
    query: PublicDocumentQuery,
    document: FetchedDocument,
    unit_text: str,
) -> bool:
    if _STALE_LANG_RE.search(unit_text) or _STALE_LANG_RE.search(document.text or ""):
        return True
    dates = parse_document_dates(document.published_at or "")
    dates.extend(parse_document_dates(document.text or ""))
    if not dates:
        return False
    newest = max(dates)
    age_days = (reference_datetime(query) - newest).days
    return age_days > query.budget.stale_years * 365


def split_structural_units(document: FetchedDocument, query: PublicDocumentQuery) -> list[StructuralUnit]:
    pages = document.pages or ((None, document.text),)
    units: list[StructuralUnit] = []
    for page_no, page_text in pages:
        page = int(page_no) if page_no else None
        if not (page_text or "").strip():
            continue
        units.extend(_units_from_page(page_text, page, query))
    if not units and (document.text or "").strip():
        units.extend(_units_from_page(document.text, None, query))
    return units


def _units_from_page(page_text: str, page: int | None, query: PublicDocumentQuery) -> list[StructuralUnit]:
    units: list[StructuralUnit] = []
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in page_text.splitlines()]
    compact = [line for line in lines if line]
    table_rows = [_parse_table_row(line) for line in compact]
    for line, parsed in zip(compact, table_rows):
        if parsed:
            units.append(
                StructuralUnit(
                    kind="table_row",
                    text=line,
                    page=page,
                    section="table",
                    company_bound=company_mentioned(query, line),
                )
            )
    # Labeled field blocks: keep a 4-line window around an explicit label.
    for idx, line in enumerate(compact):
        if _LABEL_RE.search(line) or _SIGNATURE_CUE_RE.search(line):
            window = "\n".join(compact[idx : idx + 6])
            kind = "signature" if _SIGNATURE_CUE_RE.search(line) else "labeled_field"
            units.append(
                StructuralUnit(
                    kind=kind,
                    text=window,
                    page=page,
                    section=kind,
                    company_bound=company_mentioned(query, window),
                )
            )
    # Signature-like clusters start at a name or closing cue, never at a header.
    for idx, start_line in enumerate(compact):
        if not (extract_person_names(start_line) or _SIGNATURE_CUE_RE.search(start_line)):
            continue
        window_lines = compact[idx : idx + 6]
        window = "\n".join(window_lines)
        emails = extract_emails(window)
        names = extract_person_names(window)
        role = extract_role(window)
        if emails and names and role and len(window_lines) <= 6:
            units.append(
                StructuralUnit(
                    kind="signature",
                    text=window,
                    page=page,
                    section="signature",
                    company_bound=company_mentioned(query, window),
                )
            )
    return _dedupe_units(units)


def _parse_table_row(line: str) -> list[str] | None:
    if "|" in line:
        cells = [cell.strip() for cell in line.split("|") if cell.strip()]
        if len(cells) >= 3:
            return cells
    if "\t" in line:
        cells = [cell.strip() for cell in line.split("\t") if cell.strip()]
        if len(cells) >= 3:
            return cells
    cells = [cell.strip() for cell in re.split(r"\s{2,}", line) if cell.strip()]
    if len(cells) >= 3:
        return cells
    return None


def _dedupe_units(units: list[StructuralUnit]) -> list[StructuralUnit]:
    out: list[StructuralUnit] = []
    seen: set[str] = set()
    for unit in units:
        key = f"{unit.kind}|{unit.page}|{fold_text(unit.text)}"
        if key in seen:
            continue
        seen.add(key)
        out.append(unit)
    return out


def associate_unit(
    unit: StructuralUnit,
    *,
    query: PublicDocumentQuery,
    document: FetchedDocument,
    stale: bool,
) -> list[DocumentAssociation]:
    emails = extract_emails(unit.text)
    if not emails:
        return []
    names = extract_person_names(unit.text)
    role = extract_role(unit.text)
    foreign_cnpjs = [item for item in extract_cnpjs(unit.text) if item != normalize_cnpj(query.cnpj)]
    # Company binding is unit-local. A header mention must not bless another firm's signature.
    company_ok = bool(unit.company_bound) and not foreign_cnpjs
    company_other = other_company_dominant(query, unit.text) or bool(foreign_cnpjs)
    structural = unit.kind in {"signature", "table_row", "labeled_field"}
    results: list[DocumentAssociation] = []
    for email in emails:
        reasons: list[str] = []
        discarded = False
        associated = False
        ambiguous = False
        person: str | None = None
        method = unit.kind
        if is_discarded_third_party_email(email, query):
            reasons.append(REASON_DOC_THIRD_PARTY_DOMAIN)
            discarded = True
        if company_other and not company_ok:
            reasons.append(REASON_DOC_COMPANY_MISMATCH)
            discarded = True
        if not discarded:
            reasons.append(REASON_DOC_EMAIL_OBSERVED)
        if discarded:
            results.append(
                _association(
                    email=email,
                    person_name=None,
                    role=role,
                    associated=False,
                    ambiguous=False,
                    stale=stale,
                    discarded=True,
                    reasons=reasons,
                    method=method,
                    unit=unit,
                    document=document,
                    company_matched=company_ok,
                )
            )
            continue
        if is_non_person_mailbox(email):
            reasons.append(REASON_DOC_NO_CONTACT)
            results.append(
                _association(
                    email=email,
                    person_name=None,
                    role=role,
                    associated=False,
                    ambiguous=False,
                    stale=stale,
                    discarded=False,
                    reasons=reasons,
                    method=method,
                    unit=unit,
                    document=document,
                    company_matched=company_ok,
                )
            )
            continue
        if not structural:
            results.append(
                _association(
                    email=email,
                    person_name=None,
                    role=role,
                    associated=False,
                    ambiguous=False,
                    stale=stale,
                    discarded=False,
                    reasons=reasons,
                    method="unstructured_proximity",
                    unit=unit,
                    document=document,
                    company_matched=company_ok,
                )
            )
            continue
        bound_names = _names_structurally_bound(unit, email, names)
        if unit.kind == "table_row" and len(bound_names) != 1:
            # A row with two people and one email, or no person cell, is ambiguous.
            ambiguous = len(names) != 1
            if ambiguous or not names:
                reasons.append(REASON_DOC_AMBIGUOUS_PERSON)
                results.append(
                    _association(
                        email=email,
                        person_name=None,
                        role=role,
                        associated=False,
                        ambiguous=True,
                        stale=stale,
                        discarded=False,
                        reasons=reasons,
                        method="ambiguous_table",
                        unit=unit,
                        document=document,
                        company_matched=company_ok,
                    )
                )
                continue
            bound_names = names[:1]
        if len(bound_names) > 1:
            reasons.append(REASON_DOC_AMBIGUOUS_PERSON)
            results.append(
                _association(
                    email=email,
                    person_name=None,
                    role=role,
                    associated=False,
                    ambiguous=True,
                    stale=stale,
                    discarded=False,
                    reasons=reasons,
                    method="ambiguous_person",
                    unit=unit,
                    document=document,
                    company_matched=company_ok,
                )
            )
            continue
        if len(bound_names) == 1 and (role or unit.kind in {"signature", "labeled_field", "table_row"}):
            person = bound_names[0]
            if not company_ok:
                if company_other:
                    reasons.append(REASON_DOC_COMPANY_MISMATCH)
                    discarded = True
                person = None
            else:
                associated = True
                reasons.append(REASON_DOC_IDENTITY_ASSOCIATED)
        if stale:
            reasons.append(REASON_DOC_STALE)
        results.append(
            _association(
                email=email,
                person_name=person if associated else None,
                role=role,
                associated=associated,
                ambiguous=ambiguous,
                stale=stale,
                discarded=discarded,
                reasons=reasons,
                method=method,
                unit=unit,
                document=document,
                company_matched=company_ok,
            )
        )
    return results


def _names_structurally_bound(unit: StructuralUnit, email: str, names: list[str]) -> list[str]:
    if unit.kind == "table_row":
        cells = _parse_table_row(unit.text.replace("\n", " ")) or [unit.text]
        email_cells = [cell for cell in cells if email in cell.lower() or fold_text(email) in fold_text(cell)]
        if not email_cells:
            return names
        # Bind only names that share the email's row (the whole line is one row).
        row_names = [name for name in names if any(fold_text(name) in fold_text(cell) for cell in cells)]
        return row_names
    if unit.kind in {"signature", "labeled_field"}:
        return names
    return []


def _association(
    *,
    email: str,
    person_name: str | None,
    role: str | None,
    associated: bool,
    ambiguous: bool,
    stale: bool,
    discarded: bool,
    reasons: list[str],
    method: str,
    unit: StructuralUnit,
    document: FetchedDocument,
    company_matched: bool,
) -> DocumentAssociation:
    codes = tuple(dict.fromkeys(reasons))
    return DocumentAssociation(
        email=email,
        person_name=person_name,
        role=role,
        associated=associated,
        ambiguous=ambiguous,
        stale=stale,
        discarded=discarded,
        reason_codes=codes,
        extraction_method=method,
        snippet=snippet_around(unit.text, email or person_name or ""),
        source_url=document.url,
        document_sha256=document.sha256,
        page=unit.page,
        section=unit.section,
        source_class=document.source_class,
        company_matched=company_matched,
        current_identity_proven=False,
        document_epistemic_class=DOC_EPISTEMIC_OBSERVED,
    )


def mine_document_text(query: PublicDocumentQuery, document: FetchedDocument) -> PublicDocumentMinerResult:
    """Pure path: associate from an already-fetched document. No I/O."""
    result = PublicDocumentMinerResult(documents=[document])
    result.metrics.documents_found = 1
    if not document.readable or len((document.text or "").strip()) < MIN_READABLE_CHARS:
        result.reason_codes = [REASON_DOC_UNREADABLE]
        result.metrics.documents_unreadable = 1
        result.evidence.append(
            _document_evidence(
                query,
                document,
                field="document",
                value=document.url,
                reasons=[REASON_DOC_UNREADABLE],
                snippet=None,
            )
        )
        return result
    stale = assess_staleness(query, document, document.text)
    units = split_structural_units(document, query)
    associations: list[DocumentAssociation] = []
    for unit in units:
        associations.extend(associate_unit(unit, query=query, document=document, stale=stale))
    # Emails seen in the document but never inside a structural unit.
    seen_emails = {item.email for item in associations}
    for email in extract_emails(document.text):
        if email in seen_emails:
            continue
        reasons = [REASON_DOC_EMAIL_OBSERVED]
        discarded = False
        if is_discarded_third_party_email(email, query):
            reasons = [REASON_DOC_THIRD_PARTY_DOMAIN]
            discarded = True
        elif other_company_dominant(query, snippet_around(document.text, email, 80)):
            reasons.append(REASON_DOC_COMPANY_MISMATCH)
            discarded = True
        elif is_non_person_mailbox(email):
            reasons.append(REASON_DOC_NO_CONTACT)
        if stale:
            reasons.append(REASON_DOC_STALE)
        associations.append(
            DocumentAssociation(
                email=email,
                person_name=None,
                role=None,
                associated=False,
                ambiguous=False,
                stale=stale,
                discarded=discarded,
                reason_codes=tuple(dict.fromkeys(reasons)),
                extraction_method="document_scan",
                snippet=snippet_around(document.text, email),
                source_url=document.url,
                document_sha256=document.sha256,
                page=None,
                section=None,
                source_class=document.source_class,
                company_matched=company_mentioned(query, snippet_around(document.text, email, 80)),
                current_identity_proven=False,
                document_epistemic_class=DOC_EPISTEMIC_OBSERVED,
            )
        )
    associations = _dedupe_associations(associations)
    if not associations:
        result.reason_codes = [REASON_DOC_NO_CONTACT]
        if stale:
            result.reason_codes.append(REASON_DOC_STALE)
        return result
    result.associations = associations
    result.reason_codes = _collect_reason_codes(associations)
    _publish_observations(query, document, result)
    _fill_metrics(result)
    return result


def _dedupe_associations(items: list[DocumentAssociation]) -> list[DocumentAssociation]:
    best: dict[tuple[str, str, str], DocumentAssociation] = {}
    for item in items:
        key = (item.email, fold_text(item.person_name), item.source_url)
        prev = best.get(key)
        if (
            prev is None
            or (item.associated and not prev.associated)
            or (item.associated == prev.associated and len(item.reason_codes) > len(prev.reason_codes))
        ):
            best[key] = item
    return list(best.values())


def _collect_reason_codes(items: list[DocumentAssociation]) -> list[str]:
    codes: list[str] = []
    for item in items:
        for code in item.reason_codes:
            if code not in codes:
                codes.append(code)
    if not any(item.associated or REASON_DOC_EMAIL_OBSERVED in item.reason_codes for item in items):
        if REASON_DOC_NO_CONTACT not in codes and not any(
            code in codes
            for code in (
                REASON_DOC_THIRD_PARTY_DOMAIN,
                REASON_DOC_COMPANY_MISMATCH,
                REASON_DOC_UNREADABLE,
            )
        ):
            codes.append(REASON_DOC_NO_CONTACT)
    return codes


def _document_evidence(
    query: PublicDocumentQuery,
    document: FetchedDocument,
    *,
    field: str,
    value: str | None,
    reasons: list[str],
    snippet: str | None,
    page: int | None = None,
    section: str | None = None,
    extra: dict[str, Any] | None = None,
) -> FieldEvidence:
    payload = {
        "reason_codes": list(reasons),
        "document_epistemic_class": DOC_EPISTEMIC_OBSERVED,
        "current_identity_proven": False,
        "source_class": document.source_class,
        "extractor_version": EXTRACTOR_VERSION,
        **(extra or {}),
    }
    return make_evidence(
        field=field,
        value=value,
        epistemic_class=EpistemicClass.OBSERVED,
        source_type="public_document",
        source_url=document.url,
        source_id=normalize_cnpj(query.cnpj),
        document_id=document.sha256,
        document_sha256=document.sha256,
        page=page,
        section=section,
        evidence_snippet=snippet,
        observed_at=document.fetched_at,
        published_at=document.published_at,
        extraction_method=document.extraction_method,
        contract_id=query.contract_refs[0] if query.contract_refs else None,
        process_id=query.process_refs[0] if query.process_refs else None,
        aspects=[
            FieldAspect(
                field=field,
                epistemic_class=EpistemicClass.OBSERVED,
                method=document.extraction_method,
                note=DOC_EPISTEMIC_OBSERVED,
            )
        ],
        extra=payload,
    )


def _publish_observations(
    query: PublicDocumentQuery,
    document: FetchedDocument,
    result: PublicDocumentMinerResult,
) -> None:
    cnpj = normalize_cnpj(query.cnpj)
    for item in result.associations:
        ev = _document_evidence(
            query,
            document,
            field="email" if item.email else "person_name",
            value=item.email or item.person_name,
            reasons=list(item.reason_codes),
            snippet=item.snippet,
            page=item.page,
            section=item.section,
            extra={
                "document_identity_associated": item.associated,
                "identity_explicitly_associated": False,
                "email_discovery_class": _discovery_class(item).value,
                "promotion_blocked": "DOC_OBSERVATION_REQUIRES_CANONICAL_PROMOTER",
                "stale": item.stale,
                "ambiguous": item.ambiguous,
                "discarded": item.discarded,
                "person_name": item.person_name,
                "role": item.role,
            },
        )
        result.evidence.append(ev)
        if item.person_name and not item.discarded:
            result.people.append(
                PersonObservation(
                    observation_id=stable_id("doc-person", cnpj, item.person_name, document.sha256),
                    company_entity_id=cnpj,
                    person_name=item.person_name,
                    observed_role=item.role,
                    normalized_role_class=normalize_observed_role(item.role),
                    relation=classify_person_relation(observed_role=item.role, email=item.email),
                    source_type="public_document",
                    source_url=document.url,
                    document_id=document.sha256,
                    document_type=document.source_class,
                    page=item.page,
                    snippet=item.snippet,
                    observed_at=document.fetched_at,
                    signature_context=item.extraction_method if item.associated else None,
                    process_role=item.role,
                    epistemic_class=EpistemicClass.OBSERVED,
                    evidence_id=ev.evidence_id,
                    extra={
                        "document_epistemic_class": DOC_EPISTEMIC_OBSERVED,
                        "current_identity_proven": False,
                        "reason_codes": list(item.reason_codes),
                        "stale": item.stale,
                    },
                )
            )
        if item.discarded:
            continue
        result.channels.append(
            ChannelObservation(
                observation_id=stable_id("doc-email", cnpj, item.email, document.sha256),
                company_entity_id=cnpj,
                channel_type=_channel_type(item),
                channel_value=item.email,
                person_name=item.person_name if item.associated else None,
                target_role=item.role,
                source_type="public_document",
                source_url=document.url,
                document_id=document.sha256,
                page=item.page,
                snippet=item.snippet,
                observed_at=document.fetched_at,
                epistemic_class=EpistemicClass.OBSERVED,
                ownership=OwnershipStatus.COMPANY_OWNED if item.associated else OwnershipStatus.UNKNOWN,
                evidence_id=ev.evidence_id,
                extra={
                    "identity_explicitly_associated": False,
                    "document_identity_associated": item.associated,
                    "current_identity_proven": False,
                    "document_epistemic_class": DOC_EPISTEMIC_OBSERVED,
                    "email_discovery_class": _discovery_class(item).value,
                    "association_reason_codes": list(item.reason_codes),
                    "promotion_blocked": "DOC_OBSERVATION_REQUIRES_CANONICAL_PROMOTER",
                    "source_class": item.source_class,
                    "stale": item.stale,
                    "ambiguous": item.ambiguous,
                    "extraction_method": item.extraction_method,
                    "document_sha256": item.document_sha256,
                    "fetched_at": document.fetched_at,
                },
            )
        )
    result.conflicts.extend(_detect_conflicts(cnpj, result.associations))


def _discovery_class(item: DocumentAssociation) -> EmailDiscoveryClass:
    # Miner never passes email_safe_policy=True.
    return classify_email_discovery(
        item.email,
        epistemic=EpistemicClass.OBSERVED,
        identity_associated=item.associated and not item.stale and not item.ambiguous,
        ambiguous=item.ambiguous,
        email_safe_policy=False,
        blocked=item.discarded,
    )


def _channel_type(item: DocumentAssociation) -> ChannelType:
    if is_role_mailbox(item.email):
        return ChannelType.ROLE_MAILBOX
    if is_generic_mailbox(item.email) or is_brand_mailbox(item.email):
        return ChannelType.GENERIC_CORPORATE_EMAIL
    if item.associated and looks_nominal_local(item.email):
        return ChannelType.DIRECT_EMAIL
    if looks_nominal_local(item.email):
        return ChannelType.DIRECT_EMAIL
    return ChannelType.OTHER_PUBLIC_BUSINESS_ROUTE


def _detect_conflicts(cnpj: str, items: list[DocumentAssociation]) -> list[ConflictRecord]:
    conflicts: list[ConflictRecord] = []
    by_person: dict[str, list[DocumentAssociation]] = {}
    for item in items:
        if not item.associated or not item.person_name:
            continue
        by_person.setdefault(fold_text(item.person_name), []).append(item)
    for key, group in by_person.items():
        domains = sorted({email_domain(item.email) or "" for item in group})
        if len(domains) > 1:
            conflicts.append(
                ConflictRecord(
                    conflict_id=stable_id("doc-conflict", cnpj, key, "|".join(domains)),
                    topic="person_email_domain",
                    left=group[0].email,
                    right=group[-1].email,
                    resolution="preserved",
                    reason_codes=["DOC_LINK_CONFLICT", REASON_DOC_AMBIGUOUS_PERSON],
                )
            )
    return conflicts


def _fill_metrics(result: PublicDocumentMinerResult) -> None:
    metrics = result.metrics
    metrics.documents_found = len(result.documents)
    metrics.documents_useful = sum(1 for doc in result.documents if doc.readable and extract_emails(doc.text))
    metrics.documents_unreadable = sum(1 for doc in result.documents if not doc.readable)
    metrics.emails_observed = len({item.email for item in result.associations})
    associated = [item for item in result.associations if item.associated]
    metrics.emails_nominally_associated = len({item.email for item in associated})
    metrics.people_corroborated = len({fold_text(item.person_name) for item in associated if item.person_name})
    metrics.stale = sum(1 for item in result.associations if item.stale)
    metrics.ambiguous = sum(1 for item in result.associations if item.ambiguous)
    metrics.third_party_discarded = sum(
        1 for item in result.associations if REASON_DOC_THIRD_PARTY_DOMAIN in item.reason_codes
    )
    metrics.company_mismatch = sum(
        1 for item in result.associations if REASON_DOC_COMPANY_MISMATCH in item.reason_codes
    )
    metrics.bytes_touched = sum(doc.bytes_touched for doc in result.documents)


def fetched_document_from_text(
    text: str,
    *,
    url: str = "https://example.gov.br/documento.pdf",
    fetched_at: str = "2026-08-15T00:00:00Z",
    source_class: str | None = None,
    title: str = "",
    published_at: str | None = None,
    readable: bool | None = None,
    extraction_method: str = "fixture_text",
) -> FetchedDocument:
    body = text or ""
    digest = sha256_text(body)
    is_readable = body.strip() != "" if readable is None else readable
    return FetchedDocument(
        url=url,
        fetched_at=fetched_at,
        sha256=digest,
        bytes_touched=len(body.encode("utf-8")),
        content_type="text/plain",
        text=body,
        pages=((1, body),) if body else (),
        source_class=source_class or classify_source_class(url, title, body),
        title=title,
        published_at=published_at,
        extraction_method=extraction_method,
        readable=is_readable and len(body.strip()) >= MIN_READABLE_CHARS,
    )


def pncp_url_from_contract_ref(contrato_id: str | None) -> str | None:
    match = re.match(r"^(\d{14})-\d+-(\d+)/(\d{4})$", (contrato_id or "").strip())
    if not match:
        return None
    return f"https://pncp.gov.br/app/contratos/{match.group(1)}/{match.group(3)}/{int(match.group(2))}"


def seed_urls(query: PublicDocumentQuery) -> list[str]:
    urls = [url for url in query.known_urls if url]
    for ref in query.contract_refs:
        built = pncp_url_from_contract_ref(ref)
        if built:
            urls.append(built)
    return list(dict.fromkeys(urls))


def build_document_queries(query: PublicDocumentQuery) -> list[str]:
    name = (query.legal_name or "").strip()
    cnpj = normalize_cnpj(query.cnpj)
    queries: list[str] = []
    if name and cnpj:
        queries.append(f'"{name}" {cnpj} (edital OR contrato OR ata OR proposta) filetype:pdf')
        queries.append(f'"{name}" {cnpj} (representante OR "responsável técnico" OR ART) email')
    if name:
        queries.append(f'"{name}" site:gov.br (anexo OR edital OR contrato OR ata)')
        queries.append(f'"{name}" ("diário oficial" OR "diario oficial" OR DOE)')
    for ref in query.contract_refs[:2]:
        queries.append(f'{ref} "{name or cnpj}"')
    for hint in query.named_people[:2]:
        if hint.name:
            queries.append(f'"{hint.name}" "{name or cnpj}" (email OR e-mail) filetype:pdf')
    if query.domain:
        queries.append(f"site:{query.domain} (contrato OR ata OR proposta OR ART) filetype:pdf")
    for process_ref in query.process_refs[:2]:
        queries.append(f'"{process_ref}" "{name or cnpj}"')
    return list(dict.fromkeys(item for item in queries if item.strip()))


def prefer_document_hit(url: str, title: str = "", snippet: str = "") -> bool:
    parsed = urlsplit(url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = host_of(url)
    if not host or _LEAK_HOST_RE.search(host):
        return False
    if any(marker in host for marker in _ECHO_HOST_MARKERS):
        return False
    blob_url = fold_text(url)
    if any(marker in blob_url or marker in host for marker in _TEMPLATE_DOC_MARKERS):
        return False
    if _REJECT_PATH_RE.search(parsed.path or ""):
        return False
    blob = fold_text(" ".join((url, title, snippet)))
    if url.lower().endswith(".pdf") or "filetype=pdf" in blob:
        return True
    return any(marker in host or marker in blob for marker in _PREFERRED_DOC_HOST)


def extract_pages_from_pdf(data: bytes, *, max_chars: int = 300_000) -> tuple[str, tuple[tuple[int, str], ...], str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        from scripts.confenge_process_enrichment.text_extract import extract_from_pdf_bytes

        extracted = extract_from_pdf_bytes(data, max_chars=max_chars, allow_ocr=False)
        return extracted.text, ((1, extracted.text),) if extracted.text else (), extracted.origin
    reader = PdfReader(io.BytesIO(data))
    pages: list[tuple[int, str]] = []
    parts: list[str] = []
    used = 0
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if used + len(text) > max_chars:
            text = text[: max(0, max_chars - used)]
        pages.append((index, text))
        parts.append(text)
        used += len(text)
        if used >= max_chars:
            break
    joined = "\n".join(parts)
    origin = "pdf_embedded" if joined.strip() else "none"
    return joined, tuple(pages), origin


def extract_html_text(raw: bytes) -> tuple[str, list[str]]:
    from scripts.confenge_process_enrichment.text_extract import extract_from_html

    decoded = raw.decode("utf-8", errors="replace")
    extracted = extract_from_html(decoded)
    links = [match.group(1) for match in _DOC_LINK_RE.finditer(decoded)]
    return extracted.text, links


def fetch_public_document(
    url: str,
    *,
    max_bytes: int,
    timeout_seconds: float,
    fetched_at: str | None = None,
) -> FetchedDocument:
    if not is_public_http_url(url):
        raise ValueError(f"refusing non-public or leak-class URL: {url}")
    import httpx

    with httpx.stream(
        "GET",
        url,
        headers={
            "User-Agent": "CONFENGE-extra-cli-public-documents/1.0 (+https://github.com/tjsasakifln/extra-cli)",
            "Accept": "application/pdf,text/html,text/plain;q=0.8,*/*;q=0.1",
        },
        timeout=timeout_seconds,
        follow_redirects=True,
    ) as response:
        response.raise_for_status()
        final_url = str(response.url)
        if not is_public_http_url(final_url):
            raise ValueError("redirected outside public HTTP(S)")
        content_type = (response.headers.get("content-type") or "").split(";", 1)[0].lower()
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("document byte budget exceeded")
            chunks.append(chunk)
        raw = b"".join(chunks)
    stamp = fetched_at or now_iso()
    digest = sha256_bytes(raw)
    extra_links: list[str] = []
    if content_type == "application/pdf" or raw[:5] == b"%PDF-":
        text, pages, origin = extract_pages_from_pdf(raw)
        method = origin
    elif content_type in {"text/html", "application/xhtml+xml"} or b"<html" in raw[:400].lower():
        text, extra_links = extract_html_text(raw)
        pages = ((1, text),) if text else ()
        method = "html"
    elif content_type.startswith("text/"):
        text = raw.decode("utf-8", errors="replace")
        pages = ((1, text),)
        method = "text"
    else:
        text, pages, method = "", (), "unsupported"
    readable = len((text or "").strip()) >= MIN_READABLE_CHARS
    return FetchedDocument(
        url=final_url,
        fetched_at=stamp,
        sha256=digest,
        bytes_touched=len(raw),
        content_type=content_type or "application/octet-stream",
        text=text or "",
        pages=pages,
        source_class=classify_source_class(final_url, text=text or ""),
        extraction_method=method,
        readable=readable,
        extra={"annex_links": extra_links},
    )


def query_from_context(
    context: InvestigationContext,
    *,
    budget: DocumentBudget | None = None,
    extra_urls: list[str] | None = None,
) -> PublicDocumentQuery:
    extra = context.extra or {}
    row = extra.get("row") or extra.get("lake_row") or {}
    people_raw = extra.get("named_people") or extra.get("known_people") or []
    named: list[NamedPersonHint] = []
    for item in people_raw:
        if isinstance(item, NamedPersonHint):
            named.append(item)
        elif isinstance(item, dict) and item.get("name"):
            named.append(NamedPersonHint(name=str(item["name"]), role=item.get("role")))
        elif isinstance(item, str) and item.strip():
            named.append(NamedPersonHint(name=item.strip()))
    aliases = tuple(str(alias) for alias in (extra.get("aliases") or []) if alias)
    contract_refs = [str(ref) for ref in (extra.get("contract_refs") or []) if ref]
    if row.get("melhor_contrato"):
        contract_refs.append(str(row["melhor_contrato"]))
    process_refs = [str(ref) for ref in (extra.get("process_refs") or []) if ref]
    known_urls = [str(url) for url in (extra.get("document_urls") or extra.get("known_urls") or []) if url]
    if extra_urls:
        known_urls.extend(extra_urls)
    site = str(extra.get("company_site") or extra.get("domain") or "") or None
    domain = extra.get("domain") if extra.get("domain") else _domain_from_site(site)
    return PublicDocumentQuery(
        cnpj=normalize_cnpj(context.cnpj),
        legal_name=context.legal_name,
        aliases=aliases,
        domain=str(domain) if domain else None,
        named_people=tuple(named),
        contract_refs=tuple(dict.fromkeys(contract_refs)),
        process_refs=tuple(dict.fromkeys(process_refs)),
        known_urls=tuple(dict.fromkeys(known_urls)),
        budget=budget or DocumentBudget(),
        reference_date=extra.get("reference_date"),
    )


def _domain_from_site(site: str | None) -> str | None:
    if not site:
        return None
    candidate = site if "://" in site else f"https://{site}"
    host = host_of(candidate)
    return host or None


def enrich_query_from_campaign(query: PublicDocumentQuery) -> PublicDocumentQuery:
    """Read-only consume of Track A campaign cache. Never invents fields."""
    try:
        from scripts.decision_unit_intelligence.providers.historical_campaign import (
            load_campaign_index,
            parse_qsa_blob,
        )
    except Exception:
        return query
    row = load_campaign_index().get(normalize_cnpj(query.cnpj)) or {}
    if not row:
        return query
    legal_name = query.legal_name or row.get("legal_name") or row.get("razao_social")
    domain = query.domain or _domain_from_site(row.get("site"))
    people = list(query.named_people)
    if not people:
        for blob_key in ("qsa", "qsa2"):
            for name, role in parse_qsa_blob(row.get(blob_key)):
                people.append(NamedPersonHint(name=name, role=role))
    refs = list(query.contract_refs)
    if row.get("melhor_contrato"):
        refs.append(str(row["melhor_contrato"]))
    return PublicDocumentQuery(
        cnpj=query.cnpj,
        legal_name=legal_name,
        aliases=query.aliases,
        domain=domain,
        named_people=tuple(people),
        contract_refs=tuple(dict.fromkeys(refs)),
        process_refs=query.process_refs,
        known_urls=query.known_urls,
        budget=query.budget,
        reference_date=query.reference_date,
    )


def mine_public_documents(
    query: PublicDocumentQuery,
    *,
    backend: SearchBackendLike | None = None,
    fetcher: DocumentFetcher | None = None,
    documents: list[FetchedDocument] | None = None,
    enrich_campaign: bool = True,
) -> PublicDocumentMinerResult:
    """Entry point. `documents=` is the offline path used by tests and replay."""
    started = datetime.now(UTC)
    working = enrich_query_from_campaign(query) if enrich_campaign else query
    result = PublicDocumentMinerResult()
    queries = build_document_queries(working)
    result.queries = queries[: working.budget.max_queries]
    fetched: list[FetchedDocument] = list(documents or [])
    search_failures: list[str] = []
    if documents is None:
        explicit_urls = [url for url in working.known_urls if url]
        derived_urls = [url for url in seed_urls(working) if url not in explicit_urls]
        # Implicit PNCP/process seeds only when a backend or fetcher was injected.
        # Default run_account (search off) must stay offline and fail-closed.
        urls = list(explicit_urls)
        if backend is not None or fetcher is not None:
            urls.extend(derived_urls)
        if backend is not None:
            for planned in result.queries:
                try:
                    hits = backend.search(planned, limit=working.budget.max_results_per_query)
                except Exception as exc:
                    search_failures.append(f"{type(exc).__name__}:{planned}")
                    continue
                result.metrics.searches += 1
                for hit in hits:
                    url = str(getattr(hit, "url", None) or (hit.get("url") if isinstance(hit, dict) else "") or "")
                    title = str(
                        getattr(hit, "title", None) or (hit.get("title") if isinstance(hit, dict) else "") or ""
                    )
                    snippet = str(
                        getattr(hit, "snippet", None) or (hit.get("snippet") if isinstance(hit, dict) else "") or ""
                    )
                    if url and prefer_document_hit(url, title, snippet):
                        urls.append(url)
        fetch_fn = fetcher or (
            lambda _q, url, remaining: fetch_public_document(
                url,
                max_bytes=remaining,
                timeout_seconds=working.budget.timeout_seconds,
            )
        )
        remaining = working.budget.max_bytes
        seen: set[str] = set()
        queued = list(dict.fromkeys(urls))
        index = 0
        while index < len(queued) and len(fetched) < working.budget.max_documents and remaining > 0:
            url = queued[index]
            index += 1
            if url in seen or not url:
                continue
            seen.add(url)
            try:
                document = fetch_fn(working, url, remaining)
            except Exception as exc:
                search_failures.append(f"{type(exc).__name__}:{url}")
                continue
            fetched.append(document)
            remaining -= document.bytes_touched
            for annex in (document.extra or {}).get("annex_links") or []:
                absolute = urljoin(document.url, str(annex))
                if absolute not in seen and prefer_document_hit(absolute):
                    queued.append(absolute)
    merged = PublicDocumentMinerResult(queries=result.queries)
    merged.metrics.searches = result.metrics.searches
    for document in fetched:
        piece = mine_document_text(working, document)
        merged.documents.append(document)
        merged.associations.extend(piece.associations)
        merged.people.extend(piece.people)
        merged.channels.extend(piece.channels)
        merged.evidence.extend(piece.evidence)
        merged.conflicts.extend(piece.conflicts)
        for code in piece.reason_codes:
            if code not in merged.reason_codes:
                merged.reason_codes.append(code)
    if fetched and not merged.associations and REASON_DOC_UNREADABLE not in merged.reason_codes:
        if REASON_DOC_NO_CONTACT not in merged.reason_codes:
            merged.reason_codes.append(REASON_DOC_NO_CONTACT)
    _fill_metrics(merged)
    merged.metrics.searches = result.metrics.searches
    merged.metrics.duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
    merged.attempts.append(
        SearchAttempt(
            attempt_id=stable_id("att", "official_documents", working.cnpj, "|".join(merged.queries)),
            company_entity_id=normalize_cnpj(working.cnpj),
            tier=2,
            provider_id="official_documents",
            source="public_documents",
            status=_attempt_status(merged, backend, documents, search_failures),
            reason=_attempt_reason(merged, backend, documents, search_failures),
            documents_checked=len(merged.documents),
            queries=list(merged.queries),
            bytes_touched=merged.metrics.bytes_touched,
            duration_ms=merged.metrics.duration_ms,
            blocked=bool(search_failures and not merged.documents and backend is not None),
            stop_reason=(
                "SOURCE_BLOCKED"
                if search_failures and not merged.documents and backend is not None
                else ("BUDGET_EXHAUSTED" if len(merged.documents) >= working.budget.max_documents else None)
            ),
            extra={
                "reason_codes": list(merged.reason_codes),
                "metrics": merged.metrics.to_dict(),
                "failures": search_failures,
                "document_urls": [doc.url for doc in merged.documents],
                "document_hashes": [doc.sha256 for doc in merged.documents],
            },
        )
    )
    return merged


def _attempt_status(
    result: PublicDocumentMinerResult,
    backend: SearchBackendLike | None,
    documents: list[FetchedDocument] | None,
    failures: list[str],
) -> str:
    if documents is None and backend is None and not result.documents:
        return "skipped"
    if failures and not result.documents:
        return "blocked"
    if any(item.associated for item in result.associations) or result.channels:
        return "hit"
    if result.documents:
        return "miss"
    return "miss"


def _attempt_reason(
    result: PublicDocumentMinerResult,
    backend: SearchBackendLike | None,
    documents: list[FetchedDocument] | None,
    failures: list[str],
) -> str | None:
    if documents is None and backend is None and not result.documents:
        return "search_backend_not_configured_and_no_seed_urls"
    if failures and not result.documents:
        return "all_document_fetches_failed"
    if result.reason_codes:
        return ",".join(result.reason_codes)
    return None


def to_provider_result(mined: PublicDocumentMinerResult) -> ProviderResult:
    attempt = mined.attempts[0] if mined.attempts else None
    return ProviderResult(
        people=mined.people,
        channels=mined.channels,
        evidence=mined.evidence,
        attempts=mined.attempts,
        terminal=attempt.status if attempt else "ok",
        cost=CostObservation(
            cost_brl=mined.metrics.cost_brl,
            duration_ms=mined.metrics.duration_ms,
            bytes_touched=mined.metrics.bytes_touched,
            provider_calls=mined.metrics.searches,
        ),
        extra={
            "public_documents": mined.to_dict(),
            "document_epistemic_class": DOC_EPISTEMIC_OBSERVED,
            "current_identity_proven": False,
        },
    )
