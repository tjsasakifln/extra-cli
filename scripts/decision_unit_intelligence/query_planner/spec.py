"""Query families, operator matrix, and instrumentation records.

Generation is separated from search I/O. Ranking never uses SERP count.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from scripts.decision_unit_intelligence.email_discovery import plausible_person_name
from scripts.decision_unit_intelligence.models import normalize_cnpj, normalize_name
from scripts.decision_unit_intelligence.providers.base import InvestigationContext

QUERY_PLANNER_SCHEMA = "confenge.dui.query-planner.v1"
DEFAULT_POLICY_VERSION = "query-policy.v2"
BASELINE_POLICY_VERSION = "query-policy.v1"

_LEGAL_NOISE = frozenset(
    {
        "ltda",
        "eireli",
        "me",
        "epp",
        "sa",
        "s.a",
        "engenharia",
        "construtora",
        "construcoes",
        "construções",
        "servicos",
        "serviços",
        "comercio",
        "comércio",
    }
)
_WHITESPACE_RE = re.compile(r"\s+")


class QueryFamily(StrEnum):
    COMPANY = "COMPANY"
    PERSON = "PERSON"
    ROLE = "ROLE"
    DOCUMENT = "DOCUMENT"
    SITE_PATH = "SITE_PATH"


class Operator(StrEnum):
    QUOTES = "quotes"
    SITE = "site"
    FILETYPE = "filetype"
    AT_DOMAIN = "at_domain"


# Real operator support — not marketing claims. filetype: is not reliable on DDGS.
BACKEND_OPERATORS: dict[str, frozenset[Operator]] = {
    "searxng": frozenset({Operator.QUOTES, Operator.SITE, Operator.FILETYPE, Operator.AT_DOMAIN}),
    "ddgs": frozenset({Operator.QUOTES, Operator.SITE, Operator.AT_DOMAIN}),
    "replay": frozenset({Operator.QUOTES, Operator.SITE, Operator.FILETYPE, Operator.AT_DOMAIN}),
    "replay-searxng": frozenset({Operator.QUOTES, Operator.SITE, Operator.FILETYPE, Operator.AT_DOMAIN}),
    "replay-ddgs": frozenset({Operator.QUOTES, Operator.SITE, Operator.AT_DOMAIN}),
}

ROLE_SHAPES = (
    "diretor engenharia",
    "gerente contratos",
    "licitações",
)

SITE_PATH_SLUGS = ("equipe", "diretoria", "contato", "engenharia")

SERVICE_ROLE_TERMS: dict[str, tuple[str, ...]] = {
    "reajuste_14133": ("diretor de engenharia", "contratos", "financeiro"),
    "acompanhamento_contratual": ("contratos", "diretor de engenharia", "jurídico contratual"),
    "licitacoes_propostas": ("licitações", "comercial", "suprimentos"),
    "orcamento_bdi": ("orçamento", "engenharia", "diretor de engenharia"),
}


def normalize_query(query: str) -> str:
    """Whitespace-fold + case-fold. Search engines treat these as the same request."""
    return _WHITESPACE_RE.sub(" ", (query or "").strip()).lower()


def cache_key(*, query: str, backend: str, policy_version: str, limit: int) -> str:
    return f"{backend}|{policy_version}|{limit}|{normalize_query(query)}"


def host_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        raw = url if "://" in url else f"https://{url}"
        host = (urlsplit(raw).hostname or "").lower().strip(".")
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


def infer_trade_name(legal_name: str | None, domain: str | None) -> str | None:
    if domain:
        label = domain.split(".", 1)[0].replace("-", " ").strip()
        if len(label) >= 4:
            return label
    if not legal_name:
        return None
    tokens = [tok for tok in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+", legal_name) if tok.lower() not in _LEGAL_NOISE]
    if len(tokens) >= 1 and tokens[0].lower() not in _LEGAL_NOISE:
        candidate = tokens[0]
        if candidate.lower() != (legal_name or "").strip().lower() and len(candidate) >= 4:
            return candidate
    return None


@dataclass(frozen=True)
class QuerySpec:
    family: QueryFamily
    shape_id: str
    query: str
    account_id: str
    person_name: str | None = None
    required_operators: tuple[Operator, ...] = ()
    policy_version: str = DEFAULT_POLICY_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["family"] = self.family.value
        payload["required_operators"] = [op.value for op in self.required_operators]
        return payload


@dataclass
class QueryExecution:
    spec: QuerySpec
    backend: str
    result_count: int = 0
    useful_url_count: int = 0
    useful_urls: tuple[str, ...] = ()
    observed_email_count: int = 0
    observed_emails: tuple[str, ...] = ()
    control_eligible_email_count: int = 0
    control_eligible_emails: tuple[str, ...] = ()
    identity_associated_count: int = 0
    identity_associated: tuple[str, ...] = ()
    weak_source_count: int = 0
    weak_source_urls: tuple[str, ...] = ()
    correct_domain: bool = False
    person_page: bool = False
    public_document: bool = False
    latency_ms: int = 0
    failure: str | None = None
    http_status: int | None = None
    cache_hit: bool = False
    executed: bool = False
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.spec.family.value,
            "shape_id": self.spec.shape_id,
            "query": self.spec.query,
            "account_id": self.spec.account_id,
            "person_name": self.spec.person_name,
            "backend": self.backend,
            "policy_version": self.spec.policy_version,
            "result_count": self.result_count,
            "useful_url_count": self.useful_url_count,
            "useful_urls": list(self.useful_urls),
            "observed_email_count": self.observed_email_count,
            "observed_emails": list(self.observed_emails),
            "control_eligible_email_count": self.control_eligible_email_count,
            "control_eligible_emails": list(self.control_eligible_emails),
            "identity_associated_count": self.identity_associated_count,
            "identity_associated": list(self.identity_associated),
            "weak_source_count": self.weak_source_count,
            "weak_source_urls": list(self.weak_source_urls),
            "correct_domain": self.correct_domain,
            "person_page": self.person_page,
            "public_document": self.public_document,
            "latency_ms": self.latency_ms,
            "failure": self.failure,
            "http_status": self.http_status,
            "cache_hit": self.cache_hit,
            "executed": self.executed,
            "skip_reason": self.skip_reason,
        }

    @property
    def downstream_yield(self) -> int:
        """Downstream evidence, never SERP count."""
        return self.observed_email_count + self.identity_associated_count + self.useful_url_count


@dataclass(frozen=True)
class QueryPlan:
    policy_version: str
    account_id: str
    known_domain: str | None
    known_people: tuple[str, ...]
    specs: tuple[QuerySpec, ...]
    adaptive_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "account_id": self.account_id,
            "known_domain": self.known_domain,
            "known_people": list(self.known_people),
            "adaptive_mode": self.adaptive_mode,
            "queries": [spec.to_dict() for spec in self.specs],
        }


@dataclass
class YieldSignals:
    useful_urls: tuple[str, ...] = ()
    observed_emails: tuple[str, ...] = ()
    control_eligible_emails: tuple[str, ...] = ()
    identity_associated: tuple[str, ...] = ()
    weak_source_urls: tuple[str, ...] = ()
    correct_domain: bool = False
    person_page: bool = False
    public_document: bool = False


@dataclass(frozen=True)
class QueryPolicy:
    version: str
    ranking_metric: str = "identity_associated_per_search"
    family_order: tuple[QueryFamily, ...] = (
        QueryFamily.PERSON,
        QueryFamily.SITE_PATH,
        QueryFamily.COMPANY,
        QueryFamily.DOCUMENT,
        QueryFamily.ROLE,
    )
    family_budgets: dict[QueryFamily, int] = field(
        default_factory=lambda: {
            QueryFamily.COMPANY: 4,
            QueryFamily.PERSON: 4,
            QueryFamily.ROLE: 3,
            QueryFamily.DOCUMENT: 3,
            QueryFamily.SITE_PATH: 4,
        }
    )
    disabled_families: frozenset[QueryFamily] = frozenset()
    min_identity_associated: int = 1
    min_observed_email: int = 2
    min_control_eligible_email: int = 1
    max_zero_yield_streak: int = 2
    known_person_and_domain_families: tuple[QueryFamily, ...] = (
        QueryFamily.PERSON,
        QueryFamily.SITE_PATH,
        QueryFamily.DOCUMENT,
    )
    unknown_domain_families: tuple[QueryFamily, ...] = (
        QueryFamily.COMPANY,
        QueryFamily.DOCUMENT,
        QueryFamily.ROLE,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": QUERY_PLANNER_SCHEMA,
            "version": self.version,
            "ranking_metric": self.ranking_metric,
            "family_order": [family.value for family in self.family_order],
            "family_budgets": {family.value: budget for family, budget in self.family_budgets.items()},
            "disabled_families": sorted(family.value for family in self.disabled_families),
            "early_stop": {
                "min_identity_associated": self.min_identity_associated,
                "min_observed_email": self.min_observed_email,
                "min_control_eligible_email": self.min_control_eligible_email,
                "max_zero_yield_streak": self.max_zero_yield_streak,
            },
            "adaptive": {
                "known_person_and_domain": [family.value for family in self.known_person_and_domain_families],
                "unknown_domain": [family.value for family in self.unknown_domain_families],
            },
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> QueryPolicy:
        early = payload.get("early_stop") or {}
        adaptive = payload.get("adaptive") or {}
        budgets_raw = payload.get("family_budgets") or {}
        order_raw = payload.get("family_order") or []
        disabled_raw = payload.get("disabled_families") or []
        return cls(
            version=str(payload["version"]),
            ranking_metric=str(payload.get("ranking_metric") or "identity_associated_per_search"),
            family_order=tuple(QueryFamily(item) for item in order_raw) or cls.family_order,
            family_budgets={QueryFamily(key): int(value) for key, value in budgets_raw.items()},
            disabled_families=frozenset(QueryFamily(item) for item in disabled_raw),
            min_identity_associated=int(early.get("min_identity_associated", 1)),
            min_observed_email=int(early.get("min_observed_email", 2)),
            min_control_eligible_email=int(early.get("min_control_eligible_email", 1)),
            max_zero_yield_streak=int(early.get("max_zero_yield_streak", 2)),
            known_person_and_domain_families=tuple(
                QueryFamily(item) for item in (adaptive.get("known_person_and_domain") or [])
            )
            or cls.known_person_and_domain_families,
            unknown_domain_families=tuple(QueryFamily(item) for item in (adaptive.get("unknown_domain") or []))
            or cls.unknown_domain_families,
        )


def operators_for(backend_id: str) -> frozenset[Operator]:
    key = (backend_id or "").lower()
    if key in BACKEND_OPERATORS:
        return BACKEND_OPERATORS[key]
    if key.startswith("replay"):
        return BACKEND_OPERATORS["replay"]
    return frozenset({Operator.QUOTES})


def unsupported_operators(spec: QuerySpec, backend_id: str) -> tuple[Operator, ...]:
    supported = operators_for(backend_id)
    return tuple(op for op in spec.required_operators if op not in supported)


def emit_query_specs(
    context: InvestigationContext,
    *,
    known_domain: str | None = None,
    known_people: list[str] | None = None,
    trade_name: str | None = None,
    policy_version: str = DEFAULT_POLICY_VERSION,
) -> list[QuerySpec]:
    """Emit every family shape once. Dedupes by normalized query. Does not budget."""
    company = (context.legal_name or "").strip()
    cnpj = normalize_cnpj(context.cnpj)
    domain = (known_domain or "").strip().lower() or None
    people = []
    for raw in known_people if known_people is not None else list(context.extra.get("known_people") or []):
        name = normalize_name(str(raw))
        if name and plausible_person_name(name) and name not in people:
            people.append(name)
    people = people[:4]
    trade = (trade_name or infer_trade_name(company, domain) or "").strip() or None
    if trade and company and trade.lower() == company.lower():
        trade = None

    specs: list[QuerySpec] = []

    def add(
        family: QueryFamily,
        shape_id: str,
        query: str,
        *,
        person_name: str | None = None,
        operators: tuple[Operator, ...] = (),
    ) -> None:
        text = query.strip()
        if not text:
            return
        specs.append(
            QuerySpec(
                family=family,
                shape_id=shape_id,
                query=text,
                account_id=cnpj,
                person_name=person_name,
                required_operators=operators,
                policy_version=policy_version,
            )
        )

    if company:
        add(
            QueryFamily.COMPANY,
            "company_legal_email",
            f'"{company}" email',
            operators=(Operator.QUOTES,),
        )
    if trade:
        add(
            QueryFamily.COMPANY,
            "trade_name_contact",
            f'"{trade}" contato',
            operators=(Operator.QUOTES,),
        )
    if cnpj:
        add(
            QueryFamily.COMPANY,
            "cnpj_email",
            f'"{cnpj}" email',
            operators=(Operator.QUOTES,),
        )
    if domain:
        add(
            QueryFamily.COMPANY,
            "site_at_domain",
            f'site:{domain} "@{domain}"',
            operators=(Operator.SITE, Operator.AT_DOMAIN),
        )

    if company:
        for person in people:
            add(
                QueryFamily.PERSON,
                "person_company",
                f'"{person}" "{company}"',
                person_name=person,
                operators=(Operator.QUOTES,),
            )
    if domain:
        for person in people:
            add(
                QueryFamily.PERSON,
                "person_at_domain",
                f'"{person}" "@{domain}"',
                person_name=person,
                operators=(Operator.QUOTES, Operator.AT_DOMAIN),
            )
            add(
                QueryFamily.PERSON,
                "site_person",
                f'site:{domain} "{person}"',
                person_name=person,
                operators=(Operator.SITE, Operator.QUOTES),
            )
    for person in people:
        add(
            QueryFamily.PERSON,
            "person_email",
            f'"{person}" email',
            person_name=person,
            operators=(Operator.QUOTES,),
        )
    if cnpj:
        for person in people[:2]:
            add(
                QueryFamily.PERSON,
                "person_cnpj_email",
                f'"{cnpj}" "{person}" email',
                person_name=person,
                operators=(Operator.QUOTES,),
            )

    if company:
        for role in ROLE_SHAPES:
            add(
                QueryFamily.ROLE,
                "company_role_email",
                f'"{company}" {role} email',
                operators=(Operator.QUOTES,),
            )
        for term in SERVICE_ROLE_TERMS.get(context.service, ("diretor", "engenharia", "comercial")):
            add(
                QueryFamily.ROLE,
                "company_service_role",
                f'"{company}" {term}',
                operators=(Operator.QUOTES,),
            )

    if cnpj:
        add(
            QueryFamily.DOCUMENT,
            "cnpj_pdf",
            f'"{cnpj}" filetype:pdf',
            operators=(Operator.QUOTES, Operator.FILETYPE),
        )
        add(
            QueryFamily.DOCUMENT,
            "cnpj_contrato",
            f'"{cnpj}" contrato email',
            operators=(Operator.QUOTES,),
        )
    if company:
        add(
            QueryFamily.DOCUMENT,
            "company_pdf_email",
            f'"{company}" filetype:pdf email',
            operators=(Operator.QUOTES, Operator.FILETYPE),
        )
        add(
            QueryFamily.DOCUMENT,
            "company_ata",
            f'"{company}" ata email',
            operators=(Operator.QUOTES,),
        )
        add(
            QueryFamily.DOCUMENT,
            "company_contrato",
            f'"{company}" contrato email',
            operators=(Operator.QUOTES,),
        )
    if domain:
        add(
            QueryFamily.DOCUMENT,
            "site_pdf",
            f"site:{domain} filetype:pdf",
            operators=(Operator.SITE, Operator.FILETYPE),
        )

    if domain:
        for slug in SITE_PATH_SLUGS:
            add(
                QueryFamily.SITE_PATH,
                f"site_{slug}",
                f"site:{domain} {slug}",
                operators=(Operator.SITE,),
            )

    return _dedupe_specs(specs)


def _dedupe_specs(specs: list[QuerySpec]) -> list[QuerySpec]:
    unique: dict[str, QuerySpec] = {}
    for spec in specs:
        unique.setdefault(normalize_query(spec.query), spec)
    return list(unique.values())
