"""Versioned service × role policy.

Codes match the existing CONFENGE offer identifiers used in
`scripts/confenge_contact_factory/why_now.py` and
`scripts/confenge_process_enrichment/contact_graph.py::SERVICE_ROLE_PRIORITY`.
This file does not invent a competing taxonomy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from scripts.decision_unit_intelligence.models import (
    ConfidenceLevel,
    DecisionRoleClass,
    PersonObservation,
    PersonRelation,
    fold_text,
)

POLICY_VERSION = "dui.policy.v1"

# Canonical CONFENGE service codes already used in this repository.
SERVICE_REAJUSTE_14133 = "reajuste_14133"
SERVICE_ACOMPANHAMENTO = "acompanhamento_contratual"
SERVICE_LICITACOES = "licitacoes_propostas"
SERVICE_ORCAMENTO_BDI = "orcamento_bdi"
SERVICE_DIAGNOSTICO_B2G = "diagnostico_b2g"
SERVICE_GESTAO_DOCUMENTAL = "gestao_documental"
SERVICE_GENERIC = "generic"

# Aliases used by older SERVICE_ROLE_PRIORITY keys.
SERVICE_ALIASES: dict[str, str] = {
    "reajuste": SERVICE_REAJUSTE_14133,
    "orcamento": SERVICE_ORCAMENTO_BDI,
    "diretoria_b2g": SERVICE_DIAGNOSTICO_B2G,
    "diagnostico": SERVICE_DIAGNOSTICO_B2G,
    "acompanhamento": SERVICE_ACOMPANHAMENTO,
    "licitacoes": SERVICE_LICITACOES,
    "gestao_documental": SERVICE_GESTAO_DOCUMENTAL,
}

CANONICAL_SERVICES: tuple[str, ...] = (
    SERVICE_REAJUSTE_14133,
    SERVICE_ACOMPANHAMENTO,
    SERVICE_LICITACOES,
    SERVICE_ORCAMENTO_BDI,
    SERVICE_DIAGNOSTICO_B2G,
    SERVICE_GESTAO_DOCUMENTAL,
    SERVICE_GENERIC,
)

# Role priority per service. First = most relevant to THAT offer.
# QSA/socio is never first. Technical responsible is never treated as economic buyer.
SERVICE_ROLE_PRIORITY: dict[str, list[DecisionRoleClass]] = {
    SERVICE_REAJUSTE_14133: [
        DecisionRoleClass.CONTRATOS,
        DecisionRoleClass.GERENTE_CONTRATOS,
        DecisionRoleClass.DIRETOR,
        DecisionRoleClass.FINANCEIRO,
        DecisionRoleClass.ADMINISTRATIVO,
        DecisionRoleClass.REPRESENTANTE_LEGAL,
        DecisionRoleClass.ENGENHARIA,
        DecisionRoleClass.DIRETOR_ENGENHARIA,
        DecisionRoleClass.PREPOSTO,
        DecisionRoleClass.SOCIO_ADMINISTRADOR,
        DecisionRoleClass.SOCIO,
    ],
    SERVICE_ACOMPANHAMENTO: [
        DecisionRoleClass.CONTRATOS,
        DecisionRoleClass.GERENTE_CONTRATOS,
        DecisionRoleClass.OPERACOES,
        DecisionRoleClass.DIRETOR_OPERACOES,
        DecisionRoleClass.ENGENHARIA,
        DecisionRoleClass.DIRETOR_ENGENHARIA,
        DecisionRoleClass.RESPONSAVEL_TECNICO,
        DecisionRoleClass.DIRETOR,
        DecisionRoleClass.SOCIO_ADMINISTRADOR,
    ],
    SERVICE_LICITACOES: [
        DecisionRoleClass.LICITACOES,
        DecisionRoleClass.GERENTE_LICITACOES,
        DecisionRoleClass.COMERCIAL,
        DecisionRoleClass.DIRETOR_COMERCIAL,
        DecisionRoleClass.ORCAMENTO,
        DecisionRoleClass.DIRETOR,
        DecisionRoleClass.SOCIO_ADMINISTRADOR,
    ],
    SERVICE_ORCAMENTO_BDI: [
        DecisionRoleClass.ORCAMENTO,
        DecisionRoleClass.LICITACOES,
        DecisionRoleClass.ENGENHARIA,
        DecisionRoleClass.COMERCIAL,
        DecisionRoleClass.DIRETOR,
        DecisionRoleClass.SOCIO_ADMINISTRADOR,
    ],
    SERVICE_DIAGNOSTICO_B2G: [
        DecisionRoleClass.DIRETOR,
        DecisionRoleClass.DIRETOR_COMERCIAL,
        DecisionRoleClass.COMERCIAL,
        DecisionRoleClass.LICITACOES,
        DecisionRoleClass.PRESIDENTE,
        DecisionRoleClass.SOCIO_ADMINISTRADOR,
        DecisionRoleClass.REPRESENTANTE_LEGAL,
    ],
    SERVICE_GESTAO_DOCUMENTAL: [
        DecisionRoleClass.ADMINISTRATIVO,
        DecisionRoleClass.LICITACOES,
        DecisionRoleClass.REPRESENTANTE_LEGAL,
        DecisionRoleClass.DIRETOR,
        DecisionRoleClass.SOCIO_ADMINISTRADOR,
    ],
    SERVICE_GENERIC: [
        DecisionRoleClass.DIRETOR,
        DecisionRoleClass.COMERCIAL,
        DecisionRoleClass.REPRESENTANTE_LEGAL,
        DecisionRoleClass.LICITACOES,
        DecisionRoleClass.CONTRATOS,
        DecisionRoleClass.PREPOSTO,
        DecisionRoleClass.SOCIO_ADMINISTRADOR,
        DecisionRoleClass.SOCIO,
    ],
}

AUTHORITY_ROLES = frozenset(
    {
        DecisionRoleClass.SOCIO_ADMINISTRADOR,
        DecisionRoleClass.PROPRIETARIO,
        DecisionRoleClass.PRESIDENTE,
        DecisionRoleClass.DIRETOR,
        DecisionRoleClass.DIRETOR_COMERCIAL,
        DecisionRoleClass.DIRETOR_ENGENHARIA,
        DecisionRoleClass.DIRETOR_OPERACOES,
        DecisionRoleClass.REPRESENTANTE_LEGAL,
        DecisionRoleClass.SOCIO,
    }
)

OPERATIONAL_ROLES = frozenset(
    {
        DecisionRoleClass.CONTRATOS,
        DecisionRoleClass.GERENTE_CONTRATOS,
        DecisionRoleClass.LICITACOES,
        DecisionRoleClass.GERENTE_LICITACOES,
        DecisionRoleClass.PREPOSTO,
        DecisionRoleClass.SIGNATARIO,
        DecisionRoleClass.RESPONSAVEL_TECNICO,
        DecisionRoleClass.ENGENHARIA,
        DecisionRoleClass.ORCAMENTO,
        DecisionRoleClass.COMERCIAL,
        DecisionRoleClass.OPERACOES,
    }
)

# Responsible técnico can be a strong operational route for execution topics
# and a weak economic-buyer signal for commercial offers.
ECONOMIC_BUYER_ROLES = frozenset(
    {
        DecisionRoleClass.SOCIO_ADMINISTRADOR,
        DecisionRoleClass.PROPRIETARIO,
        DecisionRoleClass.PRESIDENTE,
        DecisionRoleClass.DIRETOR,
        DecisionRoleClass.DIRETOR_COMERCIAL,
        DecisionRoleClass.DIRETOR_OPERACOES,
    }
)

EXCLUDED_FROM_DECISION_UNIT = frozenset(
    {
        DecisionRoleClass.TERCEIRO,
        DecisionRoleClass.SERVIDOR_PUBLICO,
        PersonRelation.THIRD_PARTY,
        PersonRelation.PUBLIC_OFFICIAL,
        PersonRelation.OTHER_BIDDER,
    }
)

_ROLE_RULES: list[tuple[re.Pattern[str], DecisionRoleClass]] = [
    (re.compile(r"servidor|pregoeiro|comissao de licitac|ordenador da despesa|prefeito"), DecisionRoleClass.SERVIDOR_PUBLICO),
    (re.compile(r"contador|contabil|advogad|escritorio|despachante|consultor terceir"), DecisionRoleClass.TERCEIRO),
    (re.compile(r"socio[- ]administrador|socio administrador|administrador"), DecisionRoleClass.SOCIO_ADMINISTRADOR),
    (re.compile(r"proprietario|dono|owner"), DecisionRoleClass.PROPRIETARIO),
    (re.compile(r"presidente"), DecisionRoleClass.PRESIDENTE),
    (re.compile(r"diretor comercial"), DecisionRoleClass.DIRETOR_COMERCIAL),
    (re.compile(r"diretor de engenharia|diretor tecnico"), DecisionRoleClass.DIRETOR_ENGENHARIA),
    (re.compile(r"diretor de operac|diretor operacional"), DecisionRoleClass.DIRETOR_OPERACOES),
    (re.compile(r"gerente de contratos"), DecisionRoleClass.GERENTE_CONTRATOS),
    (re.compile(r"gerente de licitac"), DecisionRoleClass.GERENTE_LICITACOES),
    (re.compile(r"responsavel tecnico|art\b|rrt\b"), DecisionRoleClass.RESPONSAVEL_TECNICO),
    (re.compile(r"representante legal"), DecisionRoleClass.REPRESENTANTE_LEGAL),
    (re.compile(r"procurador"), DecisionRoleClass.PROCURADOR),
    (re.compile(r"preposto"), DecisionRoleClass.PREPOSTO),
    (re.compile(r"signatario"), DecisionRoleClass.SIGNATARIO),
    (re.compile(r"licitac"), DecisionRoleClass.LICITACOES),
    (re.compile(r"contratos?"), DecisionRoleClass.CONTRATOS),
    (re.compile(r"comercial|novos negocios"), DecisionRoleClass.COMERCIAL),
    (re.compile(r"financeir"), DecisionRoleClass.FINANCEIRO),
    (re.compile(r"administrativ"), DecisionRoleClass.ADMINISTRATIVO),
    (re.compile(r"orcament|bdi"), DecisionRoleClass.ORCAMENTO),
    (re.compile(r"engenheir"), DecisionRoleClass.ENGENHARIA),
    (re.compile(r"operac"), DecisionRoleClass.OPERACOES),
    (re.compile(r"diretor|diretoria"), DecisionRoleClass.DIRETOR),
    (re.compile(r"socio|quotista"), DecisionRoleClass.SOCIO),
]

_SERVICE_HINTS: list[tuple[str, re.Pattern[str]]] = [
    (SERVICE_REAJUSTE_14133, re.compile(r"reajust|repactua|reequil|aditivo|claim")),
    (SERVICE_ORCAMENTO_BDI, re.compile(r"orcament|bdi|planilha|composi")),
    (SERVICE_ACOMPANHAMENTO, re.compile(r"apostilamento|medi[cç][aã]o|fiscaliza|gestao contratual")),
    (SERVICE_LICITACOES, re.compile(r"preg[aã]o|concorr|dispensa|inexigibilidade|proposta")),
    (SERVICE_GESTAO_DOCUMENTAL, re.compile(r"habilita|atestado|acervo|crea|cau")),
    (SERVICE_DIAGNOSTICO_B2G, re.compile(r"obra|engenharia|infraestrutura|paviment|terraplen")),
]


_LEGAL_ENTITY_MARKERS = (
    "ltda",
    "eireli",
    "participacoes",
    "participacao",
    "holding",
    "administradora de bens",
    "s.a",
    "s/a",
    "sociedade anonima",
    "representacoes",
)
_LEGAL_ENTITY_TAIL = frozenset({"sa", "me", "epp", "mei", "cia", "companhia"})


def is_legal_entity_name(name: str | None) -> bool:
    """True for PJ/holding QSA strings. Those are not human decision-unit members."""
    text = fold_text(name)
    if not text:
        return False
    if any(marker in text for marker in _LEGAL_ENTITY_MARKERS):
        return True
    tokens = text.split()
    return bool(tokens) and tokens[-1] in _LEGAL_ENTITY_TAIL


def canonicalize_service(code: str | None) -> str:
    raw = (code or SERVICE_GENERIC).strip().lower()
    return SERVICE_ALIASES.get(raw, raw if raw in CANONICAL_SERVICES else SERVICE_GENERIC)


def infer_service_from_text(*blobs: str | None) -> str:
    text = fold_text(" ".join(b or "" for b in blobs))
    if not text:
        return SERVICE_GENERIC
    for code, pat in _SERVICE_HINTS:
        if pat.search(text):
            return code
    return SERVICE_DIAGNOSTICO_B2G if re.search(r"constru|paviment|obra", text) else SERVICE_GENERIC


def normalize_observed_role(observed_role: str | None, *, name_hint: str | None = None) -> DecisionRoleClass:
    """Map free text to a role class. Absence → UNKNOWN. Never invents a title."""
    text = fold_text(" ".join(x for x in (observed_role or "", name_hint or "") if x))
    if not text:
        return DecisionRoleClass.UNKNOWN
    for pat, role in _ROLE_RULES:
        if pat.search(text):
            return role
    return DecisionRoleClass.UNKNOWN


def classify_person_relation(
    *,
    observed_role: str | None,
    email: str | None = None,
    surrounding: str | None = None,
    source_type: str | None = None,
) -> PersonRelation:
    text = fold_text(" ".join(x or "" for x in (observed_role, surrounding, source_type)))
    email_l = (email or "").lower()
    if email_l.endswith(".gov.br") or "prefeitura" in email_l or "camara" in email_l:
        return PersonRelation.PUBLIC_OFFICIAL
    if re.search(r"pregoeiro|servidor publico|comissao de licitac|ordenador da despesa", text):
        return PersonRelation.PUBLIC_OFFICIAL
    if re.search(r"contador|contabilidade|advogad|escritorio de adv|despachante", text):
        return PersonRelation.THIRD_PARTY
    if any(tok in email_l for tok in ("contabil", "contador", "advocacia", "advogados")):
        return PersonRelation.THIRD_PARTY
    if re.search(r"outra licitante|concorrente|outro licitante", text):
        return PersonRelation.OTHER_BIDDER
    return PersonRelation.COMPANY_MEMBER


@dataclass(frozen=True)
class RoleAssessment:
    role_class: DecisionRoleClass
    decision_relevance: ConfidenceLevel
    authority_signal: ConfidenceLevel
    operational_relevance: ConfidenceLevel
    service_fit: ConfidenceLevel
    suitability: ConfidenceLevel
    inferred_decision_relevance: str | None
    reason_codes: list[str]


def assess_role_for_service(
    *,
    role_class: DecisionRoleClass,
    service: str,
    observation_count: int = 1,
    signature_count: int = 0,
    source_count: int = 1,
    relation: PersonRelation = PersonRelation.COMPANY_MEMBER,
    qsa_only: bool = False,
) -> RoleAssessment:
    """Explainable dimensions. No opaque score."""
    service = canonicalize_service(service)
    reasons: list[str] = []

    if relation in {PersonRelation.PUBLIC_OFFICIAL, PersonRelation.OTHER_BIDDER, PersonRelation.THIRD_PARTY}:
        reasons.append(f"EXCLUDED_{relation.value}")
        return RoleAssessment(
            role_class=role_class,
            decision_relevance=ConfidenceLevel.NONE,
            authority_signal=ConfidenceLevel.NONE,
            operational_relevance=ConfidenceLevel.NONE,
            service_fit=ConfidenceLevel.NONE,
            suitability=ConfidenceLevel.NONE,
            inferred_decision_relevance=None,
            reason_codes=reasons,
        )
    if role_class in {DecisionRoleClass.TERCEIRO, DecisionRoleClass.SERVIDOR_PUBLICO}:
        reasons.append(f"EXCLUDED_{role_class.value}")
        return RoleAssessment(
            role_class=role_class,
            decision_relevance=ConfidenceLevel.NONE,
            authority_signal=ConfidenceLevel.NONE,
            operational_relevance=ConfidenceLevel.NONE,
            service_fit=ConfidenceLevel.NONE,
            suitability=ConfidenceLevel.NONE,
            inferred_decision_relevance=None,
            reason_codes=reasons,
        )

    priority = SERVICE_ROLE_PRIORITY.get(service, SERVICE_ROLE_PRIORITY[SERVICE_GENERIC])
    if role_class in priority:
        idx = priority.index(role_class)
        if idx == 0:
            fit, relevance = ConfidenceLevel.HIGH, ConfidenceLevel.HIGH
        elif idx <= 2:
            fit, relevance = ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM
        elif idx <= 5:
            fit, relevance = ConfidenceLevel.MEDIUM, ConfidenceLevel.MEDIUM
        else:
            fit, relevance = ConfidenceLevel.LOW, ConfidenceLevel.LOW
        reasons.append(f"ROLE_IN_SERVICE_POLICY:{service}:{idx}")
    elif role_class == DecisionRoleClass.UNKNOWN:
        fit, relevance = ConfidenceLevel.UNKNOWN, ConfidenceLevel.UNKNOWN
        reasons.append("ROLE_UNKNOWN")
    else:
        fit, relevance = ConfidenceLevel.LOW, ConfidenceLevel.LOW
        reasons.append("ROLE_OFF_POLICY")

    authority = ConfidenceLevel.HIGH if role_class in AUTHORITY_ROLES else (
        ConfidenceLevel.MEDIUM if role_class in OPERATIONAL_ROLES else ConfidenceLevel.LOW
    )

    operational = ConfidenceLevel.NONE
    if signature_count >= 3 or observation_count >= 4:
        operational = ConfidenceLevel.HIGH
        reasons.append("RECURRENT_REPRESENTATION")
    elif signature_count >= 1 or (role_class in OPERATIONAL_ROLES and observation_count >= 2):
        operational = ConfidenceLevel.MEDIUM
        reasons.append("OBSERVED_OPERATIONAL_ACT")
    elif role_class in OPERATIONAL_ROLES:
        operational = ConfidenceLevel.LOW
        reasons.append("OPERATIONAL_ROLE_WITHOUT_REPEATED_ACT")

    if qsa_only:
        reasons.append("QSA_CADASTRE_ONLY")
        # Cadastral authority is real; it is not proof of buying participation.
        if operational == ConfidenceLevel.NONE:
            relevance = ConfidenceLevel.LOW
            fit = ConfidenceLevel.LOW if fit == ConfidenceLevel.HIGH else fit
            reasons.append("QSA_NOT_AUTOMATIC_DECISION_MAKER")

    if role_class == DecisionRoleClass.RESPONSAVEL_TECNICO:
        reasons.append("RT_NOT_ECONOMIC_BUYER")
        if service in {SERVICE_REAJUSTE_14133, SERVICE_DIAGNOSTICO_B2G, SERVICE_LICITACOES}:
            relevance = ConfidenceLevel.LOW
        if service == SERVICE_ACOMPANHAMENTO:
            relevance = max(relevance, ConfidenceLevel.MEDIUM, key=lambda x: ["NONE", "UNKNOWN", "LOW", "MEDIUM", "HIGH"].index(x.value))

    inferred = None
    if role_class in ECONOMIC_BUYER_ROLES and not qsa_only and operational != ConfidenceLevel.NONE:
        inferred = f"provavel economic buyer para {service} (interpretacao {POLICY_VERSION})"
        reasons.append("INFERRED_ECONOMIC_BUYER")
    elif role_class == DecisionRoleClass.RESPONSAVEL_TECNICO:
        inferred = f"influenciador/rota operacional para {service} (interpretacao {POLICY_VERSION})"
    elif qsa_only:
        inferred = f"autoridade cadastral sem atividade operacional observada ({POLICY_VERSION})"

    suitability = relevance
    if operational == ConfidenceLevel.HIGH and relevance != ConfidenceLevel.NONE:
        suitability = ConfidenceLevel.HIGH if relevance != ConfidenceLevel.LOW else ConfidenceLevel.MEDIUM
    if source_count >= 2:
        reasons.append("MULTI_SOURCE")

    return RoleAssessment(
        role_class=role_class,
        decision_relevance=relevance,
        authority_signal=authority,
        operational_relevance=operational,
        service_fit=fit,
        suitability=suitability,
        inferred_decision_relevance=inferred,
        reason_codes=reasons,
    )


def identity_confidence(*, name: str | None, observation_count: int, source_count: int) -> ConfidenceLevel:
    if not name:
        return ConfidenceLevel.NONE
    if source_count >= 2 or observation_count >= 3:
        return ConfidenceLevel.HIGH
    if observation_count >= 1:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


def role_confidence(*, observed_role: str | None, role_class: DecisionRoleClass, qsa_only: bool) -> ConfidenceLevel:
    if role_class == DecisionRoleClass.UNKNOWN:
        return ConfidenceLevel.UNKNOWN
    if qsa_only:
        return ConfidenceLevel.HIGH  # the cadastral role itself is observed
    if observed_role:
        return ConfidenceLevel.HIGH
    return ConfidenceLevel.LOW


def is_excluded_observation(obs: PersonObservation) -> bool:
    return obs.relation in {
        PersonRelation.PUBLIC_OFFICIAL,
        PersonRelation.OTHER_BIDDER,
        PersonRelation.THIRD_PARTY,
    } or obs.normalized_role_class in {
        DecisionRoleClass.TERCEIRO,
        DecisionRoleClass.SERVIDOR_PUBLICO,
    }
