"""Email-discovery classification and person↔email association.

MX/DNS/SMTP never prove identity. A local-part name match is a signal, not
proof. Patterns derived from OBSERVED addresses stay INFERRED even when
technically plausible. Generic/role mailboxes never become a person.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from scripts.decision_unit_intelligence.email_resolution import (
    ObservedOrgEmail,
    derive_org_patterns,
    is_third_party_professional_domain,
    name_tokens,
)
from scripts.decision_unit_intelligence.models import (
    EpistemicClass,
    PersonObservation,
    fold_text,
    normalize_email,
    normalize_name,
)
from scripts.decision_unit_intelligence.reachability import (
    email_domain,
    is_brand_mailbox,
    is_generic_mailbox,
    is_role_mailbox,
    looks_nominal_local,
)

EMAIL_DISCOVERY_POLICY_VERSION = "dui.email-discovery.v1"
PATTERN_EVIDENCE_VERSION = "org-email-pattern.v1"

_NAME_WORD = r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÀ-ÖØ-öø-ÿ'’-]+"
_NAME_PATTERN = rf"{_NAME_WORD}(?:\s+(?:(?:d[aeo]s?|e)\s+)?{_NAME_WORD}){{1,4}}"
_NAME_FIND_RE = re.compile(_NAME_PATTERN)
_ROLE_HINT_RE = re.compile(
    r"diretor(?:a)?|gerente|s[oó]ci[oa]|propriet[aá]ri[oa]|presidente|"
    r"respons[aá]vel\s+t[eé]cnico|representante|engenheir[oa]|coordenador(?:a)?",
    re.I,
)
_STALE_RE = re.compile(
    r"\b(?:ex[-\s](?:diretor|gerente|s[oó]cio|colaborador|funcion[aá]rio|presidente)|"
    r"saiu(?:\s+da\s+empresa)?|n[aã]o\s+faz\s+mais\s+parte|antigo\s+diretor|"
    r"desligad[oa]|falecid[oa]|aposentad[oa])\b",
    re.I,
)
_EXPLICIT_EMAIL_LABEL_RE = re.compile(
    r"(?:e-?mail|correio)\s+(?:de|do|da)\s+(?P<name>" + _NAME_PATTERN + r")",
    re.I,
)
_MAILTO_RE = re.compile(r"(?i)mailto:([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})")
_EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w-])", re.I)
_CONTAINER_TAGS = frozenset({"article", "li", "tr", "td", "section", "figcaption", "dd", "header"})
_NAME_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "strong", "b", "span"})
_HIGH_VALUE_SLUGS = (
    "equipe",
    "time",
    "team",
    "staff",
    "diretoria",
    "diretor",
    "contato",
    "contact",
    "fale-conosco",
    "fale_conosco",
    "engenharia",
    "comercial",
    "licitac",
    "contrato",
    "administr",
    "imprensa",
    "quem-somos",
    "quem_somos",
    "institucional",
    "sobre",
    "nossa-equipe",
    "corpo-tecnico",
)
_THIRD_PARTY_ECHO_MARKERS = (
    "cnpj",
    "econodata",
    "empresadois",
    "escavador",
    "guiamais",
    "solutudo",
    "consultacnpj",
    "casadosdados",
    "receitanet",
)
_THIRD_PARTY_ECHO_HOSTS = (
    "checkpj.app",
    "guiapj.com.br",
    "jusbrasil.com.br",
    "glassdoor.com.br",
)
_NON_PERSON_NAME_TOKENS = frozenset(
    {
        "whatsapp",
        "enviar",
        "redes",
        "contato",
        "contact",
        "email",
        "equipe",
        "diretoria",
        "instagram",
        "facebook",
        "linkedin",
        "youtube",
        "home",
        "menu",
        "saiba",
        "empresa",
        "engenharia",
        "construtora",
        "ltda",
        "copyright",
        "privacidade",
        "cookies",
        "newsletter",
        "telefone",
        "comercial",
        "officer",
        "chief",
        "compliance",
        "content",
        "website",
        "privacy",
        "policy",
        "cookie",
        "conduta",
        "etica",
        "ética",
        "denuncia",
        "canal",
        "endereco",
        "endereço",
        "rua",
        "avenida",
        "central",
        "atendimento",
        "portfolio",
        "portfólio",
        "denominacao",
        "responsabilidade",
        "conheca",
        "conheça",
        "nosso",
        "obras",
        "matriz",
        "asa",
        "indiquem",
        "tem",
        "como",
        "seus",
        "sua",
        "duque",
        "caxias",
        "saldanha",
        "marinho",
    }
)


class EmailDiscoveryClass(StrEnum):
    OBSERVED_DIRECT_EMAIL_IDENTITY_ASSOCIATED = "OBSERVED_DIRECT_EMAIL_IDENTITY_ASSOCIATED"
    OBSERVED_DIRECT_EMAIL_IDENTITY_UNRESOLVED = "OBSERVED_DIRECT_EMAIL_IDENTITY_UNRESOLVED"
    INFERRED_PATTERN_EMAIL = "INFERRED_PATTERN_EMAIL"
    INFERRED_PATTERN_MX_OK = "INFERRED_PATTERN_MX_OK"
    INFERRED_PATTERN_CATCH_ALL = "INFERRED_PATTERN_CATCH_ALL"
    INFERRED_PATTERN_REJECTED = "INFERRED_PATTERN_REJECTED"
    GENERIC_MAILBOX = "GENERIC_MAILBOX"
    ROLE_MAILBOX = "ROLE_MAILBOX"
    DOMAIN_ONLY = "DOMAIN_ONLY"
    TECHNICALLY_PLAUSIBLE = "TECHNICALLY_PLAUSIBLE"
    EMAIL_VALIDATED = "EMAIL_VALIDATED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


INFERRED_PATTERN_CLASSES = frozenset(
    {
        EmailDiscoveryClass.INFERRED_PATTERN_EMAIL,
        EmailDiscoveryClass.INFERRED_PATTERN_MX_OK,
        EmailDiscoveryClass.INFERRED_PATTERN_CATCH_ALL,
        EmailDiscoveryClass.INFERRED_PATTERN_REJECTED,
    }
)


@dataclass(frozen=True)
class PersonEmailAssociation:
    email: str
    person_name: str | None
    associated: bool
    ambiguous: bool
    stale: bool
    third_party_echo: bool
    reason_codes: tuple[str, ...]
    extraction_method: str
    snippet: str
    source_url: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EmailPatternRecord:
    pattern_id: str
    domain: str
    version: str
    supporting_emails: tuple[str, ...]
    epistemic_class: EpistemicClass
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["epistemic_class"] = self.epistemic_class.value
        return payload


@dataclass
class EmailDiscoverySummary:
    accounts_attempted: int = 0
    domains: dict[str, int] = field(default_factory=lambda: {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0})
    named_people: int = 0
    named_people_investigated: int = 0
    observed_emails: int = 0
    observed_identity_associated: int = 0
    inferred_pattern_emails: int = 0
    generic_or_role: int = 0
    technically_plausible: int = 0
    email_validated: int = 0
    unresolved: int = 0
    north_star: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_third_party_echo_source(url: str | None) -> bool:
    if not url:
        return False
    host = (urlsplit(url).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    if any(host == suffix or host.endswith(f".{suffix}") for suffix in _THIRD_PARTY_ECHO_HOSTS):
        return True
    return any(marker in host for marker in _THIRD_PARTY_ECHO_MARKERS)


def local_part_name_signal(email: str, person_name: str | None) -> bool:
    """Signal only: first + last tokens appear in the local-part."""
    normalized = normalize_email(email)
    name = normalize_name(person_name)
    if not normalized or not name:
        return False
    local = re.sub(r"[^a-z0-9]", "", normalized.split("@", 1)[0].lower())
    tokens = name_tokens(name)
    if len(tokens) < 2:
        return False
    return tokens[0] in local and tokens[-1] in local


def classify_email_discovery(
    email: str | None,
    *,
    epistemic: EpistemicClass | str | None = None,
    identity_associated: bool = False,
    ambiguous: bool = False,
    inferred_pattern: bool = False,
    inferred_pattern_state: str | None = None,
    mx_present: bool = False,
    blocked: bool = False,
    email_safe_policy: bool = False,
) -> EmailDiscoveryClass:
    """Distinct classes. EMAIL_VALIDATED only when the existing policy already allows it."""
    if blocked:
        return EmailDiscoveryClass.BLOCKED
    epistemic_value = epistemic.value if isinstance(epistemic, EpistemicClass) else str(epistemic or "")
    if inferred_pattern or epistemic_value == EpistemicClass.INFERRED.value:
        extra_state = str(inferred_pattern_state or "")
        if extra_state in {item.value for item in INFERRED_PATTERN_CLASSES}:
            return EmailDiscoveryClass(extra_state)
        return EmailDiscoveryClass.INFERRED_PATTERN_EMAIL
    if email_safe_policy:
        return EmailDiscoveryClass.EMAIL_VALIDATED
    if not email or "@" not in str(email):
        return EmailDiscoveryClass.UNKNOWN
    if is_role_mailbox(email):
        return EmailDiscoveryClass.ROLE_MAILBOX
    if is_generic_mailbox(email) or is_brand_mailbox(email):
        return EmailDiscoveryClass.GENERIC_MAILBOX
    if identity_associated and epistemic_value == EpistemicClass.OBSERVED.value:
        return EmailDiscoveryClass.OBSERVED_DIRECT_EMAIL_IDENTITY_ASSOCIATED
    if epistemic_value == EpistemicClass.OBSERVED.value:
        if ambiguous or looks_nominal_local(email):
            return EmailDiscoveryClass.OBSERVED_DIRECT_EMAIL_IDENTITY_UNRESOLVED
        return EmailDiscoveryClass.DOMAIN_ONLY
    if mx_present:
        return EmailDiscoveryClass.TECHNICALLY_PLAUSIBLE
    return EmailDiscoveryClass.UNKNOWN


def associate_person_to_email(
    email: str,
    *,
    people: list[PersonObservation],
    html: str = "",
    text: str = "",
    source_url: str = "",
    canonical_domain: str | None = None,
    corroboration: Any = None,
) -> PersonEmailAssociation:
    """Associate only from auditável contextual evidence. Local-part is a signal."""
    normalized = normalize_email(email) or email
    reasons: list[str] = []
    snippet = ""
    method = "unresolved"
    third_party = is_third_party_echo_source(source_url)
    if third_party:
        reasons.append("THIRD_PARTY_ECHO_NOT_IDENTITY")
    domain = email_domain(normalized)
    if is_brand_mailbox(normalized) or is_generic_mailbox(normalized) or is_role_mailbox(normalized):
        reasons.append("GENERIC_OR_BRAND_MAILBOX_NOT_PERSON")
        return PersonEmailAssociation(
            email=normalized,
            person_name=None,
            associated=False,
            ambiguous=False,
            stale=False,
            third_party_echo=third_party,
            reason_codes=tuple(dict.fromkeys(reasons + ["GENERIC_OR_BRAND_MAILBOX_NOT_PERSON"])),
            extraction_method="rejected_generic_or_brand",
            snippet=_snippet_for_email(text or _strip_html(html), normalized),
            source_url=source_url,
        )
    if is_third_party_professional_domain(domain):
        reasons.append("THIRD_PARTY_PROFESSIONAL_DOMAIN")
        return PersonEmailAssociation(
            email=normalized,
            person_name=None,
            associated=False,
            ambiguous=False,
            stale=False,
            third_party_echo=True,
            reason_codes=tuple(dict.fromkeys(reasons + ["FOREIGN_OR_THIRD_PARTY_DOMAIN"])),
            extraction_method="rejected_third_party_domain",
            snippet=_snippet_for_email(text or _strip_html(html), normalized),
            source_url=source_url,
        )
    expected = (canonical_domain or "").lower().removeprefix("www.")
    if expected and domain and domain != expected:
        reasons.append("EMAIL_DOMAIN_NOT_CANONICAL")
        return PersonEmailAssociation(
            email=normalized,
            person_name=None,
            associated=False,
            ambiguous=False,
            stale=False,
            third_party_echo=False,
            reason_codes=tuple(dict.fromkeys(reasons + ["FOREIGN_OR_THIRD_PARTY_DOMAIN"])),
            extraction_method="rejected_foreign_domain",
            snippet=_snippet_for_email(text or _strip_html(html), normalized),
            source_url=source_url,
        )

    html_hit = _associate_from_html(normalized, people, html, source_url) if html else None
    text_hit = _associate_from_text(normalized, people, text or _strip_html(html), source_url)
    page_hit = _associate_from_person_page(normalized, people, html or text, source_url, canonical_domain)

    chosen = html_hit or page_hit or text_hit
    if chosen is None:
        return PersonEmailAssociation(
            email=normalized,
            person_name=None,
            associated=False,
            ambiguous=False,
            stale=False,
            third_party_echo=third_party,
            reason_codes=tuple(reasons + ["NO_CONTEXTUAL_PERSON_EMAIL_EVIDENCE"]),
            extraction_method=method,
            snippet=_snippet_for_email(text or _strip_html(html), normalized),
            source_url=source_url,
        )

    person_name, extra_reasons, method, snippet, ambiguous, stale = chosen
    reasons.extend(extra_reasons)
    if person_name and local_part_name_signal(normalized, person_name):
        reasons.append("LOCAL_PART_NAME_SIGNAL")
    if stale:
        reasons.append("PERSON_MAY_HAVE_LEFT")
    associated = bool(person_name) and not ambiguous and not stale and not third_party
    if associated and corroboration is not None:
        from scripts.decision_unit_intelligence.corroboration import email_association_gate

        gate = email_association_gate(corroboration, email=normalized)
        if not gate.allowed:
            associated = False
            reasons.append("AFFILIATION_GATE_REFUSED")
            reasons.extend(gate.reason_codes)
    if associated:
        reasons.append("CONTEXTUAL_IDENTITY_ASSOCIATED")
    elif ambiguous:
        reasons.append("AMBIGUOUS_PERSON_EMAIL_CONTEXT")
    elif not person_name:
        reasons.append("IDENTITY_UNRESOLVED")
    return PersonEmailAssociation(
        email=normalized,
        person_name=person_name if associated or ambiguous else None,
        associated=associated,
        ambiguous=ambiguous,
        stale=stale,
        third_party_echo=third_party,
        reason_codes=tuple(dict.fromkeys(reasons)),
        extraction_method=method,
        snippet=snippet,
        source_url=source_url,
    )


def extract_mailto_addresses(html: str) -> list[str]:
    found: list[str] = []
    for raw in _MAILTO_RE.findall(html or ""):
        email = normalize_email(raw)
        if email:
            found.append(email)
    return list(dict.fromkeys(found))


def extract_visible_emails(text: str) -> list[str]:
    found: list[str] = []
    for raw in _EMAIL_RE.findall(text or ""):
        email = normalize_email(raw)
        if email and not email.endswith((".png", ".jpg", ".gif", ".svg", ".webp")):
            found.append(email)
    return list(dict.fromkeys(found))


def discover_internal_targets(
    *,
    links: list[str] | tuple[str, ...],
    html: str = "",
    canonical_domain: str,
    already: set[str] | None = None,
    limit: int = 6,
    page_url: str = "",
) -> list[str]:
    """Bounded same-domain high-value links. Not an infinite spider."""
    seen = set(already or ())
    scored: list[tuple[int, str]] = []
    candidates = list(links)
    if html:
        candidates.extend(_anchor_targets(html, canonical_domain, page_url=page_url))
    host = canonical_domain.lower().removeprefix("www.")
    for raw in candidates:
        parsed = urlsplit(raw)
        target_host = (parsed.hostname or "").lower().removeprefix("www.")
        if target_host != host or parsed.scheme not in {"http", "https"}:
            continue
        clean = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
        if clean in seen:
            continue
        score = score_internal_url(clean)
        if score <= 0:
            continue
        seen.add(clean)
        scored.append((score, clean))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [url for _score, url in scored[:limit]]


def score_internal_url(url: str, anchor_text: str = "") -> int:
    path = urlsplit(url).path.lower()
    hay = f"{path} {anchor_text.lower()}"
    score = 0
    for slug in _HIGH_VALUE_SLUGS:
        if slug in hay:
            score += 10
    if path in {"", "/"}:
        score += 1
    if path.endswith(".pdf"):
        score -= 8
    return score


def derive_versioned_patterns(observed: list[ObservedOrgEmail]) -> list[EmailPatternRecord]:
    """Patterns come only from OBSERVED same-domain addresses. Never a fact about a person."""
    usable = [
        item
        for item in observed
        if normalize_email(item.email)
        and item.person_name
        and not is_role_mailbox(item.email)
        and not is_generic_mailbox(item.email)
    ]
    by_domain: dict[str, list[ObservedOrgEmail]] = {}
    for item in usable:
        domain = email_domain(item.email)
        if domain:
            by_domain.setdefault(domain, []).append(item)
    records: list[EmailPatternRecord] = []
    for domain, items in by_domain.items():
        hits = derive_org_patterns(items)
        for pattern_id, emails in hits.items():
            unique = tuple(dict.fromkeys(emails))
            if len(unique) >= 2:
                epistemic = EpistemicClass.CORROBORATED
                reasons = ("PATTERN_CORROBORATED_BY_ORG_EMAILS", "PATTERN_NOT_A_PERSON_FACT")
            else:
                epistemic = EpistemicClass.INFERRED
                reasons = ("SINGLE_SAMPLE_PATTERN", "PATTERN_NOT_A_PERSON_FACT")
            records.append(
                EmailPatternRecord(
                    pattern_id=pattern_id,
                    domain=domain,
                    version=PATTERN_EVIDENCE_VERSION,
                    supporting_emails=unique,
                    epistemic_class=epistemic,
                    reason_codes=reasons,
                )
            )
    return records


def inferred_candidates_from_supported_patterns(
    *,
    person_name: str,
    domain: str,
    observed: list[ObservedOrgEmail],
    mx_valid: bool = False,
    catch_all: bool = False,
    public_hits: list[str] | None = None,
) -> list[Any]:
    """Emit INFERRED candidates only for patterns actually seen on OBSERVED org mail."""
    from scripts.decision_unit_intelligence.email_patterns.engine import (
        InjectedTechnicalAdapter,
        run_email_patterns,
    )
    from scripts.decision_unit_intelligence.email_patterns.types import KnownPerson, ObservedPersonEmail
    from scripts.decision_unit_intelligence.email_resolution import EmailInference

    observed_inputs = [
        ObservedPersonEmail(
            email=item.email,
            person_name=item.person_name or "",
            domain=email_domain(item.email) or domain,
            source_url=item.source_url,
            source_type=item.source_type,
        )
        for item in observed
        if item.person_name
    ]
    result = run_email_patterns(
        observed=observed_inputs,
        known_people=[KnownPerson(person_name, corroborated=True)],
        domain=domain,
        technical=InjectedTechnicalAdapter(
            mx_by_domain={domain: "MX_PRESENT" if mx_valid else "MISSING"},
            catch_all_by_domain={domain: "CATCH_ALL" if catch_all else "UNKNOWN_NOT_PROBED"},
        ),
    )
    inferences: list[EmailInference] = []
    public = {normalize_email(item) for item in (public_hits or [])}
    for candidate in result.candidates:
        reasons = list(candidate.reason_codes)
        if candidate.email in public:
            reasons.append("CANDIDATE_SEEN_IN_PUBLIC_SOURCE")
        inferences.append(
            EmailInference(
                email=candidate.email,
                pattern_id=candidate.pattern_id,
                epistemic_class=EpistemicClass.INFERRED,
                domain=domain,
                domain_epistemic=EpistemicClass.OBSERVED,
                pattern_epistemic=(
                    EpistemicClass.CORROBORATED
                    if candidate.pattern_state.value == "PATTERN_STRONG"
                    else EpistemicClass.INFERRED
                ),
                technically_validated=candidate.candidate_state.value == "INFERRED_PATTERN_MX_OK",
                corroborated=False,
                reason_codes=reasons,
                signals={
                    "domain": domain,
                    "pattern": candidate.pattern_id,
                    "pattern_state": candidate.pattern_state.value,
                    "inferred_grade": candidate.inferred_grade.value,
                },
                mx_valid=mx_valid,
            )
        )
    return inferences


def build_email_job_queries(
    *,
    company: str | None,
    cnpj: str | None,
    domain: str | None,
    known_people: list[str] | None = None,
    role_terms: list[str] | None = None,
) -> list[str]:
    """Email-job query shapes. Planner concatenates these ahead of generic role queries."""
    queries: list[str] = []
    people = [normalize_name(name) for name in (known_people or [])]
    people = [name for name in people if name and plausible_person_name(name)][:4]
    if domain:
        for slug in ("equipe", "diretoria", "contato"):
            queries.append(f"site:{domain} {slug}")
        for name in people:
            queries.extend(
                [
                    f'site:{domain} "{name}"',
                    f'"{name}" "@{domain}"',
                    f'"{name}" email',
                ]
            )
        queries.append(f'site:{domain} "@{domain}"')
        if company:
            queries.append(f'"{company}" "@{domain}"')
        for slug in ("engenharia", "comercial", "licitacoes"):
            queries.append(f"site:{domain} {slug}")
    if company:
        queries.append(f'"{company}" email')
        for name in people:
            queries.append(f'"{name}" "{company}"')
        for term in role_terms or []:
            queries.append(f'"{company}" {term} email')
    if cnpj:
        queries.append(f'"{cnpj}" email')
        for name in people[:2]:
            queries.append(f'"{cnpj}" "{name}" email')
    return list(dict.fromkeys(query for query in queries if query.strip()))


def summarize_email_discovery(accounts: list[Any]) -> EmailDiscoverySummary:
    summary = EmailDiscoverySummary(accounts_attempted=len(accounts))
    named_with_route = 0
    named_total = 0
    for account in accounts:
        resolution = (getattr(account, "extra", None) or {}).get("domain_resolution") or {}
        confidence = str(resolution.get("confidence") or "UNKNOWN").upper()
        if confidence not in summary.domains:
            confidence = "UNKNOWN"
        summary.domains[confidence] += 1
        people = list(getattr(account, "candidates", []) or [])
        named_total += len(people)
        summary.named_people += len(people)
        summary.named_people_investigated += len(people)
        routes = list(getattr(account, "routes", []) or [])
        people_with_direct = set()
        for route in routes:
            extra = getattr(route, "extra", None) or {}
            klass = extra.get("email_discovery_class") or classify_email_discovery(
                getattr(route, "channel_value", None),
                epistemic=getattr(route, "epistemic_class", None),
                identity_associated=bool(extra.get("identity_explicitly_associated")),
                inferred_pattern=getattr(route, "channel_type", None)
                and getattr(route.channel_type, "value", "") == "INFERRED_DIRECT_EMAIL",
                email_safe_policy=bool(extra.get("email_validated")),
            )
            if not isinstance(klass, EmailDiscoveryClass):
                try:
                    klass = EmailDiscoveryClass(str(klass))
                except ValueError:
                    klass = EmailDiscoveryClass.UNKNOWN
            if klass == EmailDiscoveryClass.EMAIL_VALIDATED:
                summary.email_validated += 1
                people_with_direct.add(getattr(route, "decision_unit_candidate_id", None))
            elif klass == EmailDiscoveryClass.OBSERVED_DIRECT_EMAIL_IDENTITY_ASSOCIATED:
                summary.observed_identity_associated += 1
                summary.observed_emails += 1
                people_with_direct.add(getattr(route, "decision_unit_candidate_id", None))
            elif klass == EmailDiscoveryClass.OBSERVED_DIRECT_EMAIL_IDENTITY_UNRESOLVED:
                summary.observed_emails += 1
                summary.unresolved += 1
            elif klass in INFERRED_PATTERN_CLASSES:
                summary.inferred_pattern_emails += 1
            elif klass in {EmailDiscoveryClass.GENERIC_MAILBOX, EmailDiscoveryClass.ROLE_MAILBOX}:
                summary.generic_or_role += 1
            elif klass == EmailDiscoveryClass.TECHNICALLY_PLAUSIBLE:
                summary.technically_plausible += 1
            value = getattr(route, "channel_value", None)
            epistemic = getattr(route, "epistemic_class", None)
            if value and "@" in str(value) and epistemic == EpistemicClass.OBSERVED:
                if klass not in {
                    EmailDiscoveryClass.OBSERVED_DIRECT_EMAIL_IDENTITY_ASSOCIATED,
                    EmailDiscoveryClass.OBSERVED_DIRECT_EMAIL_IDENTITY_UNRESOLVED,
                    EmailDiscoveryClass.GENERIC_MAILBOX,
                    EmailDiscoveryClass.ROLE_MAILBOX,
                    EmailDiscoveryClass.EMAIL_VALIDATED,
                }:
                    summary.observed_emails += 1
        named_with_route += len({item for item in people_with_direct if item})
    summary.north_star = round(named_with_route / named_total, 4) if named_total else 0.0
    return summary


def _strip_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def _snippet_for_email(text: str, email: str, *, radius: int = 160) -> str:
    hay = text or ""
    idx = hay.lower().find(email.lower())
    if idx < 0:
        return hay[: radius * 2].strip()
    return hay[max(0, idx - radius) : min(len(hay), idx + len(email) + radius)].strip()


def plausible_person_name(name: str | None) -> bool:
    normalized = normalize_name(name)
    if not normalized:
        return False
    tokens = [token for token in re.split(r"\s+", normalized) if token]
    if len(tokens) < 2 or len(tokens) > 6:
        return False
    if any(len(re.sub(r"[^A-Za-zÀ-ÿ]", "", token)) < 3 for token in tokens[:1]):
        return False
    folded_tokens = {fold_text(token) for token in tokens}
    if folded_tokens & _NON_PERSON_NAME_TOKENS:
        return False
    folded = fold_text(normalized)
    if folded.startswith(("nossa senhora", "sao ", "santa ", "santo ")):
        return False
    return True


def _people_names(people: list[PersonObservation]) -> list[str]:
    names: list[str] = []
    for person in people:
        name = normalize_name(person.person_name)
        if name and plausible_person_name(name):
            names.append(name)
    return list(dict.fromkeys(names))


def _names_in_text(blob: str, known: list[str]) -> list[str]:
    folded = fold_text(blob)
    hits = [name for name in known if fold_text(name) and fold_text(name) in folded]
    if hits:
        return hits
    discovered: list[str] = []
    for match in _NAME_FIND_RE.finditer(blob):
        name = normalize_name(match.group(0))
        if not plausible_person_name(name):
            continue
        discovered.append(name)
    return list(dict.fromkeys(discovered))


def _associate_from_html(
    email: str,
    people: list[PersonObservation],
    html: str,
    source_url: str,
) -> tuple[str | None, list[str], str, str, bool, bool] | None:
    soup = BeautifulSoup(html, "lxml")
    known = _people_names(people)
    nodes = _nodes_for_email(soup, email)
    if not nodes:
        return None
    best: tuple[str | None, list[str], str, str, bool, bool] | None = None
    for node in nodes:
        container = _smallest_container(node)
        if container is None:
            continue
        blob = re.sub(r"\s+", " ", container.get_text(" ", strip=True))
        names = _names_in_container(container, known)
        stale = bool(_STALE_RE.search(blob))
        explicit = _explicit_label_name(blob, email)
        if explicit:
            names = list(dict.fromkeys([explicit, *names]))
        mailto = node.name == "a" and str(node.get("href") or "").lower().startswith("mailto:")
        reasons = ["SAME_DOM_CONTAINER"]
        method = "dom_card_proximity"
        if mailto:
            reasons.append("MAILTO_IN_PERSON_BLOCK")
            method = "mailto_in_person_block"
        if explicit:
            reasons.append("EXPLICIT_EMAIL_DE_NOME")
            method = "explicit_email_label"
        if len(names) > 1:
            return names[0], reasons, method, blob[:280], True, stale
        if len(names) == 1:
            return names[0], reasons, method, blob[:280], False, stale
        best = best or (None, reasons, method, blob[:280], False, stale)
    return best


def _associate_from_text(
    email: str,
    people: list[PersonObservation],
    text: str,
    source_url: str,
) -> tuple[str | None, list[str], str, str, bool, bool] | None:
    if not text:
        return None
    snippet = _snippet_for_email(text, email)
    if email.lower() not in snippet.lower() and email.lower() not in text.lower():
        return None
    known = _people_names(people)
    names = _names_in_text(snippet, known)
    stale = bool(_STALE_RE.search(snippet))
    explicit = _explicit_label_name(snippet, email)
    reasons = ["SAME_TEXT_WINDOW"]
    method = "text_window_proximity"
    if explicit:
        names = list(dict.fromkeys([explicit, *names]))
        reasons.append("EXPLICIT_EMAIL_DE_NOME")
        method = "explicit_email_label"
    if len(names) > 1:
        return names[0], reasons, method, snippet, True, stale
    if len(names) == 1:
        reasons.append("UNIQUE_PERSON_IN_EMAIL_WINDOW")
        return names[0], reasons, method, snippet, False, stale
    return None


def _associate_from_person_page(
    email: str,
    people: list[PersonObservation],
    blob: str,
    source_url: str,
    canonical_domain: str | None,
) -> tuple[str | None, list[str], str, str, bool, bool] | None:
    if not source_url or not blob:
        return None
    host = (urlsplit(source_url).hostname or "").lower().removeprefix("www.")
    expected = (canonical_domain or "").lower().removeprefix("www.")
    if expected and host != expected:
        return None
    path = urlsplit(source_url).path.lower()
    known = _people_names(people)
    slug_hits = []
    for name in known:
        tokens = name_tokens(name)
        if len(tokens) >= 2 and tokens[0] in path and tokens[-1] in path:
            slug_hits.append(name)
    page_names = _names_in_text(blob, known)
    emails = extract_visible_emails(blob) + extract_mailto_addresses(blob)
    unique_emails = list(dict.fromkeys(emails))
    stale = bool(_STALE_RE.search(blob))
    if len(slug_hits) == 1 and len(unique_emails) == 1 and unique_emails[0] == email:
        return (
            slug_hits[0],
            ["PERSON_PAGE_UNIQUE_EMAIL", "SAME_DOMAIN_PERSON_PAGE"],
            "person_page_unique",
            _snippet_for_email(blob, email),
            False,
            stale,
        )
    if (
        len(page_names) == 1
        and len(unique_emails) == 1
        and unique_emails[0] == email
        and any(slug in path for slug in ("equipe", "time", "diretor", "profissional", "curriculo"))
    ):
        return (
            page_names[0],
            ["PERSON_SECTION_UNIQUE_EMAIL"],
            "person_section_unique",
            _snippet_for_email(blob, email),
            False,
            stale,
        )
    return None


def _explicit_label_name(blob: str, email: str) -> str | None:
    window = _snippet_for_email(blob, email, radius=80)
    match = _EXPLICIT_EMAIL_LABEL_RE.search(window)
    if match:
        return normalize_name(match.group("name"))
    return None


def _nodes_for_email(soup: BeautifulSoup, email: str) -> list[Tag]:
    nodes: list[Tag] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if href.lower().startswith("mailto:") and email in href.lower():
            nodes.append(anchor)
    for node in soup.find_all(string=re.compile(re.escape(email), re.I)):
        if isinstance(node, str) and node.parent:
            nodes.append(node.parent)
    return nodes


def _smallest_container(node: Tag) -> Tag | None:
    for parent in node.parents:
        if not isinstance(parent, Tag):
            continue
        text = parent.get_text(" ", strip=True)
        if parent.name in _CONTAINER_TAGS and 16 <= len(text) <= 420:
            return parent
        if parent.name == "div" and 16 <= len(text) <= 420:
            return parent
    return None


def _names_in_container(container: Tag, known: list[str]) -> list[str]:
    blob = container.get_text(" ", strip=True)
    names = _names_in_text(blob, known)
    tagged: list[str] = []
    for tag in container.find_all(_NAME_TAGS):
        candidate = normalize_name(tag.get_text(" ", strip=True))
        if candidate and (candidate in known or (len(candidate.split()) >= 2 and _NAME_FIND_RE.fullmatch(candidate))):
            tagged.append(candidate)
    return list(dict.fromkeys([*tagged, *names]))


def _anchor_targets(html: str, canonical_domain: str, *, page_url: str = "") -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    host = canonical_domain.lower().removeprefix("www.")
    out: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(page_url, href) if page_url else href
        parsed = urlsplit(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        target_host = (parsed.hostname or "").lower().removeprefix("www.")
        if target_host == host:
            out.append(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")))
    return out
