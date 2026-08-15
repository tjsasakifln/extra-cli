"""Affiliation corroboration policy — data the shipped transform consults.

QSA is cadastral (names / controle societário). It never proves an operational
or buyer role. Republished copies of one origin are not independent sources.
Forbidden sources are dropped, never scored.
"""

from __future__ import annotations

from enum import StrEnum

POLICY_ID = "dui.affiliation-policy.v1"
SCHEMA_ID = "confenge.dui.affiliation_corroboration.v1"
COHORT_SCHEMA_ID = "confenge.dui.affiliation_cohort.v1"

# Recency is operational currency, not cadastre snapshot age.
RECENCY_FRESH_DAYS = 365
RECENCY_AGING_DAYS = 730


class AffiliationReasonCode(StrEnum):
    """Shipped vocabulary. Contradiction is never a silent average."""

    AFFILIATION_CORROBORATED = "AFFILIATION_CORROBORATED"
    ROLE_CORROBORATED = "ROLE_CORROBORATED"
    IDENTITY_CORROBORATED = "IDENTITY_CORROBORATED"
    STALE_AFFILIATION = "STALE_AFFILIATION"
    CONFLICTING_ROLE = "CONFLICTING_ROLE"
    HOLDING_OPERATIONAL_MISMATCH = "HOLDING_OPERATIONAL_MISMATCH"
    QSA_ONLY = "QSA_ONLY"
    INSUFFICIENT_RECENCY = "INSUFFICIENT_RECENCY"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"


REASON_CODE_VOCABULARY: frozenset[str] = frozenset(code.value for code in AffiliationReasonCode)

# The eight codes named in the mission, plus CONFLICTING_EVIDENCE as the
# explicit field-contradiction marker (roles also emit CONFLICTING_ROLE).
SHIPPED_REASON_CODES: tuple[str, ...] = (
    AffiliationReasonCode.AFFILIATION_CORROBORATED.value,
    AffiliationReasonCode.ROLE_CORROBORATED.value,
    AffiliationReasonCode.IDENTITY_CORROBORATED.value,
    AffiliationReasonCode.STALE_AFFILIATION.value,
    AffiliationReasonCode.CONFLICTING_ROLE.value,
    AffiliationReasonCode.HOLDING_OPERATIONAL_MISMATCH.value,
    AffiliationReasonCode.QSA_ONLY.value,
    AffiliationReasonCode.INSUFFICIENT_RECENCY.value,
)


class AllowedSourceClass(StrEnum):
    CORPORATE_SITE = "corporate_site"
    PUBLIC_DOCUMENT = "public_document"
    INSTITUTIONAL_PAGE = "institutional_page"
    OFFICIAL_GAZETTE = "official_gazette"
    PROFESSIONAL_ASSOCIATION = "professional_association"
    EVENT = "event"
    PRESS_RELEASE = "press_release"
    PUBLIC_PROFESSIONAL_PROFILE = "public_professional_profile"
    QSA_CADASTRE = "qsa_cadastre"


class ForbiddenSourceClass(StrEnum):
    AUTHENTICATED_LINKEDIN = "authenticated_linkedin"
    DATA_BROKER = "data_broker"
    LOCAL_PART_AS_ROLE = "local_part_as_role"
    QSA_PJ_AS_PERSON = "qsa_pj_as_person"
    BYPASS = "bypass"
    BREACH_DUMP = "breach_dump"


class EntityKind(StrEnum):
    HOLDING = "holding"
    OPERATIONAL = "operational"
    UNIT = "unit"
    BRAND = "brand"
    CONSORTIUM = "consortium"
    UNKNOWN = "unknown"


# Observed source_type strings already used in DUI providers → policy class.
SOURCE_TYPE_CLASS: dict[str, str] = {
    "company_website": AllowedSourceClass.CORPORATE_SITE.value,
    "company_site": AllowedSourceClass.CORPORATE_SITE.value,
    "corporate_site": AllowedSourceClass.CORPORATE_SITE.value,
    "public_page": AllowedSourceClass.CORPORATE_SITE.value,
    "institutional_page": AllowedSourceClass.INSTITUTIONAL_PAGE.value,
    "process_document": AllowedSourceClass.PUBLIC_DOCUMENT.value,
    "official_documents": AllowedSourceClass.PUBLIC_DOCUMENT.value,
    "public_document": AllowedSourceClass.PUBLIC_DOCUMENT.value,
    "administrative_process": AllowedSourceClass.PUBLIC_DOCUMENT.value,
    "official_gazette": AllowedSourceClass.OFFICIAL_GAZETTE.value,
    "diario_oficial": AllowedSourceClass.OFFICIAL_GAZETTE.value,
    "professional_association": AllowedSourceClass.PROFESSIONAL_ASSOCIATION.value,
    "crea": AllowedSourceClass.PROFESSIONAL_ASSOCIATION.value,
    "cau": AllowedSourceClass.PROFESSIONAL_ASSOCIATION.value,
    "event": AllowedSourceClass.EVENT.value,
    "conference": AllowedSourceClass.EVENT.value,
    "press_release": AllowedSourceClass.PRESS_RELEASE.value,
    "materia": AllowedSourceClass.PRESS_RELEASE.value,
    "news": AllowedSourceClass.PRESS_RELEASE.value,
    "public_professional_profile": AllowedSourceClass.PUBLIC_PROFESSIONAL_PROFILE.value,
    "professional_profile": AllowedSourceClass.PUBLIC_PROFESSIONAL_PROFILE.value,
    "qsa_rfb": AllowedSourceClass.QSA_CADASTRE.value,
    "brasilapi_cnpj": AllowedSourceClass.QSA_CADASTRE.value,
    "rfb": AllowedSourceClass.QSA_CADASTRE.value,
    "qsa": AllowedSourceClass.QSA_CADASTRE.value,
    "rfb_cadastre": AllowedSourceClass.QSA_CADASTRE.value,
}

FORBIDDEN_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        ForbiddenSourceClass.AUTHENTICATED_LINKEDIN.value,
        ForbiddenSourceClass.DATA_BROKER.value,
        ForbiddenSourceClass.LOCAL_PART_AS_ROLE.value,
        "cargo_from_local_part",
        "local_part_as_cargo",
        ForbiddenSourceClass.QSA_PJ_AS_PERSON.value,
        ForbiddenSourceClass.BYPASS.value,
        ForbiddenSourceClass.BREACH_DUMP.value,
        "linkedin_authenticated",
        "linkedin_scrape",
    }
)

QSA_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        "qsa_rfb",
        "brasilapi_cnpj",
        "rfb",
        "qsa",
        "rfb_cadastre",
        AllowedSourceClass.QSA_CADASTRE.value,
    }
)

# Hosts that republish RFB/QSA or scrape directories. Copies, not independent origins.
QSA_ECHO_HOST_MARKERS: tuple[str, ...] = (
    "casadosdados",
    "econodata",
    "empresadois",
    "consultacnpj",
    "receitanet",
    "cnpj.biz",
    "cnpja",
    "brasilapi",
    "receitaws",
    "checkpj",
    "guiapj",
    "escavador",
    "solutudo",
    "guiamais",
)

DATA_BROKER_HOST_MARKERS: tuple[str, ...] = (
    "apollo.io",
    "zoominfo.com",
    "hunter.io",
    "clearbit.com",
    "lusha.com",
    "rocketreach.co",
    "snov.io",
    "contactout.com",
    "cognism.com",
)

# Syndicated reprints of the same press release / gazette do not become independent
# just because the URL host differs. Callers should set origin_id; these hosts
# are a fail-closed hint when origin_id is missing.
SYNDICATION_HOST_MARKERS: tuple[str, ...] = (
    "noticias.uol.com.br",
    "g1.globo.com",
    "estadao.com.br",
    "folha.uol.com.br",
    "valor.globo.com",
    "terra.com.br",
    "ig.com.br",
    "r7.com",
)

HOLDING_NAME_MARKERS: tuple[str, ...] = (
    "holding",
    "participacoes",
    "participações",
    "participacao",
    "participação",
    "administradora de bens",
    "investimentos",
)
OPERATIONAL_NAME_MARKERS: tuple[str, ...] = (
    "engenharia",
    "construtora",
    "construcoes",
    "construções",
    "paviment",
    "terraplan",
    "mineracao",
    "mineração",
    "incorporadora",
    "empreiteira",
)
UNIT_NAME_MARKERS: tuple[str, ...] = ("filial", "unidade", "sucursal", "regional")
BRAND_NAME_MARKERS: tuple[str, ...] = ("marca", "brand")
CONSORTIUM_NAME_MARKERS: tuple[str, ...] = ("consorcio", "consórcio", "spe ", " spe")

STALE_SIGNAL_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        r"\bex[-\s](?:diretor|gerente|socio|s[oó]cio|colaborador|funcion[aá]rio|presidente|engenheir)",
        "ex_role",
    ),
    (r"\bcargo\s+anterior\b|\bantigo\s+(?:diretor|gerente|cargo)\b", "former_role"),
    (r"\bsaiu(?:\s+da\s+empresa)?\b|\bn[aã]o\s+faz\s+mais\s+parte\b|\bdesligad[oa]\b", "left_company"),
    (r"\bagora\s+na\b|\batualmente\s+na\b|\bmudou\s+para\b|\bnova\s+empresa\b", "new_company"),
    (
        r"\bsubstitu[ií]d[oa]\s+por\b|\bno\s+lugar\s+de\b|\bassume[m]?\s+(?:a\s+)?diretoria\b|"
        r"\bnovo\s+diretor\b|\breplacement\b|\bannounce(?:d|ment)\b",
        "replacement",
    ),
)

# Ownership/cadastral roles may coexist with an operational title.
OWNERSHIP_ROLE_CLASSES: frozenset[str] = frozenset(
    {
        "socio",
        "socio_administrador",
        "proprietario",
    }
)
SPECIFIC_EXECUTIVE_ROLE_CLASSES: frozenset[str] = frozenset(
    {
        "diretor_comercial",
        "diretor_engenharia",
        "diretor_operacoes",
    }
)

STOP_THE_LINE_CODES: frozenset[str] = frozenset(
    {
        AffiliationReasonCode.STALE_AFFILIATION.value,
        AffiliationReasonCode.CONFLICTING_ROLE.value,
        AffiliationReasonCode.CONFLICTING_EVIDENCE.value,
        AffiliationReasonCode.HOLDING_OPERATIONAL_MISMATCH.value,
        AffiliationReasonCode.QSA_ONLY.value,
    }
)

# Association is refused for these known false-vínculo classes even if an
# email local-part looks nominal. The gate never promotes email.
ASSOCIATION_REFUSED_WHEN: tuple[str, ...] = (
    AffiliationReasonCode.STALE_AFFILIATION.value,
    AffiliationReasonCode.CONFLICTING_ROLE.value,
    AffiliationReasonCode.CONFLICTING_EVIDENCE.value,
    AffiliationReasonCode.HOLDING_OPERATIONAL_MISMATCH.value,
    AffiliationReasonCode.QSA_ONLY.value,
)
