"""Reachability classification. Separate from Decision-Unit membership.

A company phone plus a named person is R3 (routed), never R1 (direct)
and never R0 (nothing). Inferred email is never OBSERVED.
"""

from __future__ import annotations

from dataclasses import dataclass

from scripts.decision_unit_intelligence.models import (
    FORBIDDEN_ACTION_MODES,
    ActionMode,
    ChannelObservation,
    ChannelType,
    ConfidenceLevel,
    DecisionUnitCandidate,
    EpistemicClass,
    FirstClassRouteKind,
    FirstClassRouteLabel,
    FreshnessState,
    OwnershipStatus,
    PersonRelation,
    ReachabilityClass,
    ReachabilityRoute,
    RouteRelation,
    SuppressionState,
    fold_text,
    normalize_email,
    stable_id,
)
from scripts.decision_unit_intelligence.route_class import finalize_route_draft

ROLE_MAILBOX_LOCALS = frozenset(
    {
        "licitacoes",
        "licitacao",
        "licita",
        "comercial",
        "orcamentos",
        "orcamento",
        "contratos",
        "diretoria",
        "engenharia",
        "obras",
        "financeiro",
        "administrativo",
        "vendas",
        "proposta",
        "propostas",
        "compras",
    }
)

GENERIC_MAILBOX_LOCALS = frozenset(
    {
        "contato",
        "contact",
        "adm",
        "admin",
        "sac",
        "ouvidoria",
        "rh",
        "info",
        "office",
        "suporte",
        "geral",
        "atendimento",
        "secretaria",
        "recepcao",
        "mailbox",
        "conduta",
        "etica",
        "denuncia",
        "denuncias",
        "compliance",
        "canal",
        "privacidade",
        "brasilia",
        "matriz",
        "filial",
        "unidade",
        "sede",
        "escritorio",
        "vitoria",
        "goiania",
        "brasilia",
        "curitiba",
        "florianopolis",
        "saopaulo",
        "riodejaneiro",
        "recife",
        "salvador",
        "fortaleza",
        "manaus",
        "belem",
        "natal",
        "maceio",
        "joaopessoa",
        "teresina",
        "palmas",
        "campogrande",
        "cuiaba",
        "portoalegre",
        "belohorizonte",
    }
)

FREEMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "hotmail.com",
        "yahoo.com",
        "yahoo.com.br",
        "outlook.com",
        "live.com",
        "icloud.com",
        "uol.com.br",
        "bol.com.br",
        "terra.com.br",
        "msn.com",
        "protonmail.com",
        "aol.com",
    }
)

# Observed routed access to the right person outranks inferred email.
# Inferred is useful and reviewable — it is not better than a switchboard call.
_CLASS_RANK = {
    ReachabilityClass.R1_DIRECT: 50,
    ReachabilityClass.R3_ROUTED_TO_NAMED_PERSON: 42,
    ReachabilityClass.R2_HIGH_CONFIDENCE_DIRECT: 34,
    ReachabilityClass.R4_ROLE_ROUTE: 25,
    ReachabilityClass.R5_CORPORATE_ONLY: 10,
    ReachabilityClass.INFERRED_UNVERIFIED: 6,
    ReachabilityClass.BLOCKED: 1,
    ReachabilityClass.R0_NO_ACTIONABLE_ROUTE: 0,
}


def email_local_part(value: str | None) -> str | None:
    email = normalize_email(value)
    if not email:
        return None
    return email.split("@", 1)[0]


def email_domain(value: str | None) -> str | None:
    email = normalize_email(value)
    if not email:
        return None
    return email.split("@", 1)[1]


def is_role_mailbox(value: str | None) -> bool:
    local = email_local_part(value)
    if not local:
        return False
    base = local.split("+", 1)[0]
    base = base.replace(".", "").replace("_", "").replace("-", "")
    # licitacao1 / licitacoes2 still count
    stem = "".join(c for c in base if c.isalpha())
    return stem in ROLE_MAILBOX_LOCALS or any(
        stem.startswith(r) and len(stem) <= len(r) + 2 for r in ROLE_MAILBOX_LOCALS
    )


def is_generic_mailbox(value: str | None) -> bool:
    local = email_local_part(value)
    if not local:
        return False
    base = "".join(c for c in local.split("+", 1)[0] if c.isalpha())
    return base in GENERIC_MAILBOX_LOCALS


def is_freemail(value: str | None) -> bool:
    domain = email_domain(value)
    return bool(domain and domain in FREEMAIL_DOMAINS)


def looks_nominal_local(value: str | None) -> bool:
    local = email_local_part(value)
    if not local or is_role_mailbox(value) or is_generic_mailbox(value):
        return False
    return bool(re_nominal(local))


def re_nominal(local: str) -> bool:
    import re

    return bool(re.match(r"^[a-z]{2,}[._\-][a-z]{2,}", local)) or (
        local.isalpha() and 3 <= len(local) <= 24 and local not in ROLE_MAILBOX_LOCALS | GENERIC_MAILBOX_LOCALS
    )


def is_brand_mailbox(value: str | None) -> bool:
    """Company-name@company-domain is a generic org box, not a person."""
    local = email_local_part(value)
    domain = email_domain(value)
    if not local or not domain:
        return False
    stem = domain.split(".", 1)[0]
    compact_local = local.replace("-", "").replace("_", "")
    compact_stem = stem.replace("-", "").replace("_", "")
    return compact_local == compact_stem or compact_stem.startswith(compact_local) and len(compact_local) >= 4


def classify_observed_email_channel(value: str) -> ChannelType:
    if is_role_mailbox(value):
        return ChannelType.ROLE_MAILBOX
    if is_generic_mailbox(value) or is_freemail(value) or is_brand_mailbox(value):
        return ChannelType.GENERIC_CORPORATE_EMAIL
    if looks_nominal_local(value):
        return ChannelType.DIRECT_EMAIL
    return ChannelType.GENERIC_CORPORATE_EMAIL


def assert_no_auto_send(action: ActionMode | str) -> None:
    raw = action.value if isinstance(action, ActionMode) else str(action)
    if raw in FORBIDDEN_ACTION_MODES or raw.upper() in FORBIDDEN_ACTION_MODES:
        raise ValueError(f"AUTO_SEND is forbidden in this domain: {raw}")


@dataclass
class RouteDraft:
    channel_type: ChannelType
    channel_value: str | None
    relation: RouteRelation
    epistemic: EpistemicClass
    reachability: ReachabilityClass
    action: ActionMode
    candidate_id: str | None
    target_role: str | None
    source_type: str | None
    source_url: str | None
    evidence_ids: list[str]
    confidence: ConfidenceLevel
    ownership: OwnershipStatus
    freshness: FreshnessState
    suppression: SuppressionState
    reason_codes: list[str]
    next_action: str
    extra: dict
    first_class_label: FirstClassRouteLabel = FirstClassRouteLabel.UNKNOWN
    first_class_kind: FirstClassRouteKind = FirstClassRouteKind.MANUAL_RESEARCH
    observed_at: str | None = None
    suitability: ConfidenceLevel = ConfidenceLevel.UNKNOWN


def classify_channel_observation(
    obs: ChannelObservation,
    *,
    candidate: DecisionUnitCandidate | None,
    suitable_person: bool,
) -> RouteDraft:
    """Project one channel observation into a first-class route. Does not invent association."""
    draft = _classify_channel_observation_raw(
        obs,
        candidate=candidate,
        suitable_person=suitable_person,
    )
    return finalize_route_draft(
        draft,
        obs=obs,
        candidate=candidate,
        suitable_person=suitable_person,
    )


def _classify_channel_observation_raw(
    obs: ChannelObservation,
    *,
    candidate: DecisionUnitCandidate | None,
    suitable_person: bool,
) -> RouteDraft:
    """Project one channel observation into a route. Does not invent association."""
    reasons: list[str] = []
    extra = dict(obs.extra or {})
    value = obs.channel_value
    ctype = obs.channel_type
    epistemic = obs.epistemic_class
    candidate_id = candidate.candidate_id if candidate else None
    person_name = candidate.person_name if candidate else obs.person_name
    target_role = (candidate.decision_role_class.value if candidate else None) or obs.target_role

    if obs.extra.get("suppression") in {"DNC", "OPT_OUT", "HARD_BOUNCE"}:
        return RouteDraft(
            channel_type=ctype,
            channel_value=value,
            relation=RouteRelation.CONTRADICTED,
            epistemic=epistemic,
            reachability=ReachabilityClass.BLOCKED,
            action=ActionMode.BLOCKED,
            candidate_id=candidate_id,
            target_role=target_role,
            source_type=obs.source_type,
            source_url=obs.source_url,
            evidence_ids=[obs.evidence_id] if obs.evidence_id else [],
            confidence=ConfidenceLevel.HIGH,
            ownership=obs.ownership,
            freshness=FreshnessState.UNKNOWN,
            suppression=SuppressionState(obs.extra["suppression"]),
            reason_codes=["SUPPRESSED"],
            next_action="Respeitar DNC/opt-out/bounce. Não contatar por este canal.",
            extra=extra,
        )

    # Inferred email is never a direct observed email.
    if ctype == ChannelType.INFERRED_DIRECT_EMAIL or epistemic == EpistemicClass.INFERRED:
        if ctype in {ChannelType.DIRECT_EMAIL, ChannelType.INFERRED_DIRECT_EMAIL}:
            reasons.append("INFERRED_EMAIL_REQUIRES_HUMAN_REVIEW")
            if epistemic == EpistemicClass.OBSERVED:
                raise ValueError("inferred email cannot carry epistemic_class=OBSERVED")
            verified = bool(extra.get("technically_validated") and extra.get("corroborated"))
            if verified and suitable_person:
                inferred_class = ReachabilityClass.R2_HIGH_CONFIDENCE_DIRECT
            elif suitable_person:
                inferred_class = ReachabilityClass.INFERRED_UNVERIFIED
            else:
                inferred_class = ReachabilityClass.R5_CORPORATE_ONLY
            return RouteDraft(
                channel_type=ChannelType.INFERRED_DIRECT_EMAIL,
                channel_value=value,
                relation=RouteRelation.INFERRED_ASSOCIATION,
                epistemic=EpistemicClass.INFERRED,
                reachability=inferred_class,
                action=ActionMode.HUMAN_REVIEW_EMAIL,
                candidate_id=candidate_id if suitable_person else None,
                target_role=target_role,
                source_type=obs.source_type,
                source_url=obs.source_url,
                evidence_ids=[obs.evidence_id] if obs.evidence_id else [],
                confidence=ConfidenceLevel.MEDIUM if verified else ConfidenceLevel.LOW,
                ownership=OwnershipStatus.COMPANY_OWNED,
                freshness=FreshnessState.UNKNOWN,
                suppression=SuppressionState.NONE,
                reason_codes=reasons + (["INFERRED_DIRECT_EMAIL_VERIFIED"] if verified else ["INFERRED_UNVERIFIED"]),
                next_action=(
                    f"Revisar humanamente o e-mail inferido {value} para {person_name}. Não enviar automaticamente."
                ),
                extra={
                    **extra,
                    "human_review_required": True,
                    "inferred_class": "INFERRED_DIRECT_EMAIL_VERIFIED" if verified else "INFERRED_DIRECT_EMAIL",
                },
            )

    if ctype == ChannelType.DIRECT_EMAIL and looks_nominal_local(value) and epistemic == EpistemicClass.OBSERVED:
        from scripts.decision_unit_intelligence.email_discovery import plausible_person_name
        from scripts.decision_unit_intelligence.email_resolution import is_third_party_professional_domain

        if (
            extra.get("identity_explicitly_associated") is False
            or not suitable_person
            or not plausible_person_name(person_name)
            or is_third_party_professional_domain(email_domain(value))
        ):
            reasons.append("OBSERVED_EMAIL_IDENTITY_UNRESOLVED")
            return RouteDraft(
                channel_type=ChannelType.DIRECT_EMAIL,
                channel_value=value,
                relation=RouteRelation.ACCOUNT_LEVEL_ONLY,
                epistemic=EpistemicClass.OBSERVED,
                reachability=ReachabilityClass.R5_CORPORATE_ONLY,
                action=ActionMode.HUMAN_REVIEW_EMAIL,
                candidate_id=candidate_id if suitable_person else None,
                target_role=target_role,
                source_type=obs.source_type,
                source_url=obs.source_url,
                evidence_ids=[obs.evidence_id] if obs.evidence_id else [],
                confidence=ConfidenceLevel.MEDIUM,
                ownership=OwnershipStatus.COMPANY_OWNED,
                freshness=FreshnessState.UNKNOWN,
                suppression=SuppressionState.NONE,
                reason_codes=reasons,
                next_action=f"Revisar e-mail nominal observado {value} sem associação explícita de identidade. Sem AUTO_SEND.",
                extra={**extra, "identity_explicitly_associated": False},
            )
        reasons.append("NAMED_EMAIL_OBSERVED")
        return RouteDraft(
            channel_type=ChannelType.DIRECT_EMAIL,
            channel_value=value,
            relation=RouteRelation.PERSON_OWNS_CHANNEL,
            epistemic=EpistemicClass.OBSERVED,
            reachability=ReachabilityClass.R1_DIRECT,
            action=ActionMode.HUMAN_REVIEW_EMAIL,
            candidate_id=candidate_id,
            target_role=target_role,
            source_type=obs.source_type,
            source_url=obs.source_url,
            evidence_ids=[obs.evidence_id] if obs.evidence_id else [],
            confidence=ConfidenceLevel.HIGH,
            ownership=OwnershipStatus.COMPANY_OWNED,
            freshness=FreshnessState.UNKNOWN,
            suppression=SuppressionState.NONE,
            reason_codes=reasons,
            next_action=f"Revisar e-mail nominal observado {value} para {person_name}. Sem AUTO_SEND.",
            extra=extra,
        )

    if ctype == ChannelType.DIRECT_PHONE and suitable_person and extra.get("person_owns_phone"):
        reasons.append("DIRECT_PHONE_OBSERVED")
        return RouteDraft(
            channel_type=ChannelType.DIRECT_PHONE,
            channel_value=value,
            relation=RouteRelation.PERSON_OWNS_CHANNEL,
            epistemic=epistemic,
            reachability=ReachabilityClass.R1_DIRECT,
            action=ActionMode.MANUAL_CALL,
            candidate_id=candidate_id,
            target_role=target_role,
            source_type=obs.source_type,
            source_url=obs.source_url,
            evidence_ids=[obs.evidence_id] if obs.evidence_id else [],
            confidence=ConfidenceLevel.HIGH,
            ownership=OwnershipStatus.PERSON_PROFESSIONAL,
            freshness=FreshnessState.UNKNOWN,
            suppression=SuppressionState.NONE,
            reason_codes=reasons,
            next_action=f"Ligar para o telefone profissional publicado de {person_name}: {value}.",
            extra=extra,
        )

    if ctype == ChannelType.PROFESSIONAL_WHATSAPP and suitable_person:
        reasons.append("PROFESSIONAL_WHATSAPP")
        return RouteDraft(
            channel_type=ChannelType.PROFESSIONAL_WHATSAPP,
            channel_value=value,
            relation=RouteRelation.PERSON_OWNS_CHANNEL,
            epistemic=epistemic,
            reachability=ReachabilityClass.R1_DIRECT,
            action=ActionMode.MANUAL_WHATSAPP,
            candidate_id=candidate_id,
            target_role=target_role,
            source_type=obs.source_type,
            source_url=obs.source_url,
            evidence_ids=[obs.evidence_id] if obs.evidence_id else [],
            confidence=ConfidenceLevel.MEDIUM,
            ownership=OwnershipStatus.PERSON_PROFESSIONAL,
            freshness=FreshnessState.UNKNOWN,
            suppression=SuppressionState.NONE,
            reason_codes=reasons,
            next_action=f"Mensagem profissional manual no WhatsApp publicado de {person_name}.",
            extra=extra,
        )

    if ctype == ChannelType.PROFESSIONAL_PROFILE and suitable_person:
        reasons.append("PROFESSIONAL_PROFILE")
        return RouteDraft(
            channel_type=ChannelType.PROFESSIONAL_PROFILE,
            channel_value=value,
            relation=RouteRelation.PERSON_OWNS_CHANNEL,
            epistemic=epistemic,
            reachability=ReachabilityClass.R1_DIRECT,
            action=ActionMode.MANUAL_PROFESSIONAL_SOCIAL,
            candidate_id=candidate_id,
            target_role=target_role,
            source_type=obs.source_type,
            source_url=obs.source_url,
            evidence_ids=[obs.evidence_id] if obs.evidence_id else [],
            confidence=ConfidenceLevel.MEDIUM,
            ownership=OwnershipStatus.PERSON_PROFESSIONAL,
            freshness=FreshnessState.UNKNOWN,
            suppression=SuppressionState.NONE,
            reason_codes=reasons,
            next_action=f"Abordar {person_name} pelo perfil profissional publicado ({value}).",
            extra=extra,
        )

    if ctype == ChannelType.CONTACT_FORM:
        if suitable_person:
            reasons.append("FORM_CAN_ADDRESS_NAMED_PERSON")
            return RouteDraft(
                channel_type=ChannelType.CONTACT_FORM,
                channel_value=value,
                relation=RouteRelation.ROUTES_TO_NAMED_PERSON,
                epistemic=epistemic,
                reachability=ReachabilityClass.R3_ROUTED_TO_NAMED_PERSON,
                action=ActionMode.CONTACT_FORM,
                candidate_id=candidate_id,
                target_role=target_role,
                source_type=obs.source_type,
                source_url=obs.source_url,
                evidence_ids=[obs.evidence_id] if obs.evidence_id else [],
                confidence=ConfidenceLevel.MEDIUM,
                ownership=OwnershipStatus.COMPANY_OWNED,
                freshness=FreshnessState.UNKNOWN,
                suppression=SuppressionState.NONE,
                reason_codes=reasons,
                next_action=f"Usar o formulário institucional e endereçar a mensagem a {person_name}.",
                extra=extra,
            )
        reasons.append("GENERIC_FORM")
        return RouteDraft(
            channel_type=ChannelType.CONTACT_FORM,
            channel_value=value,
            relation=RouteRelation.ACCOUNT_LEVEL_ONLY,
            epistemic=epistemic,
            reachability=ReachabilityClass.R5_CORPORATE_ONLY,
            action=ActionMode.CONTACT_FORM,
            candidate_id=None,
            target_role=target_role,
            source_type=obs.source_type,
            source_url=obs.source_url,
            evidence_ids=[obs.evidence_id] if obs.evidence_id else [],
            confidence=ConfidenceLevel.LOW,
            ownership=OwnershipStatus.COMPANY_OWNED,
            freshness=FreshnessState.UNKNOWN,
            suppression=SuppressionState.NONE,
            reason_codes=reasons,
            next_action="Enviar formulário institucional genérico (última rota de formulário).",
            extra=extra,
        )

    if ctype == ChannelType.COMPANY_SWITCHBOARD or (
        ctype == ChannelType.DIRECT_PHONE and not extra.get("person_owns_phone")
    ):
        if suitable_person and person_name:
            reasons.append("SWITCHBOARD_ROUTES_TO_NAMED_PERSON")
            reasons.append("NOT_PERSONAL_PHONE")
            return RouteDraft(
                channel_type=ChannelType.COMPANY_SWITCHBOARD,
                channel_value=value,
                relation=RouteRelation.ROUTES_TO_NAMED_PERSON,
                epistemic=epistemic,
                reachability=ReachabilityClass.R3_ROUTED_TO_NAMED_PERSON,
                action=ActionMode.MANUAL_ROUTED_CALL,
                candidate_id=candidate_id,
                target_role=target_role,
                source_type=obs.source_type,
                source_url=obs.source_url,
                evidence_ids=[obs.evidence_id] if obs.evidence_id else [],
                confidence=ConfidenceLevel.HIGH if epistemic == EpistemicClass.OBSERVED else ConfidenceLevel.MEDIUM,
                ownership=OwnershipStatus.COMPANY_OWNED,
                freshness=FreshnessState.UNKNOWN,
                suppression=SuppressionState.NONE,
                reason_codes=reasons,
                next_action=(
                    f"Ligar para {value} e pedir por {person_name}. Não alegar que o telefone pertence à pessoa."
                ),
                extra={**extra, "person_owns_phone": False},
            )
        reasons.append("SWITCHBOARD_NO_NAMED_PERSON")
        return RouteDraft(
            channel_type=ChannelType.COMPANY_SWITCHBOARD,
            channel_value=value,
            relation=RouteRelation.ACCOUNT_LEVEL_ONLY,
            epistemic=epistemic,
            reachability=ReachabilityClass.R5_CORPORATE_ONLY,
            action=ActionMode.MANUAL_CALL,
            candidate_id=None,
            target_role=target_role,
            source_type=obs.source_type,
            source_url=obs.source_url,
            evidence_ids=[obs.evidence_id] if obs.evidence_id else [],
            confidence=ConfidenceLevel.MEDIUM,
            ownership=OwnershipStatus.COMPANY_OWNED,
            freshness=FreshnessState.UNKNOWN,
            suppression=SuppressionState.NONE,
            reason_codes=reasons,
            next_action=f"Ligar para o telefone oficial da empresa {value} e pedir o setor relevante.",
            extra={**extra, "person_owns_phone": False},
        )

    if ctype == ChannelType.ROLE_MAILBOX or (value and is_role_mailbox(value)):
        reasons.append("ROLE_MAILBOX")
        return RouteDraft(
            channel_type=ChannelType.ROLE_MAILBOX,
            channel_value=value,
            relation=RouteRelation.ROUTES_TO_ROLE,
            epistemic=epistemic,
            reachability=ReachabilityClass.R4_ROLE_ROUTE,
            action=ActionMode.ROLE_EMAIL,
            candidate_id=None,
            target_role=target_role or email_local_part(value),
            source_type=obs.source_type,
            source_url=obs.source_url,
            evidence_ids=[obs.evidence_id] if obs.evidence_id else [],
            confidence=ConfidenceLevel.HIGH if epistemic == EpistemicClass.OBSERVED else ConfidenceLevel.MEDIUM,
            ownership=OwnershipStatus.COMPANY_OWNED,
            freshness=FreshnessState.UNKNOWN,
            suppression=SuppressionState.NONE,
            reason_codes=reasons,
            next_action=f"Escrever para a caixa funcional {value} (revisão humana; sem AUTO_SEND).",
            extra=extra,
        )

    # Generic corporate email / leftover
    reasons.append("GENERIC_CORPORATE")
    return RouteDraft(
        channel_type=ChannelType.GENERIC_CORPORATE_EMAIL if value and "@" in (value or "") else ctype,
        channel_value=value,
        relation=RouteRelation.ACCOUNT_LEVEL_ONLY,
        epistemic=epistemic,
        reachability=ReachabilityClass.R5_CORPORATE_ONLY,
        action=ActionMode.GENERIC_EMAIL_LAST_RESORT if value and "@" in (value or "") else ActionMode.NEEDS_ENRICHMENT,
        candidate_id=None,
        target_role=target_role,
        source_type=obs.source_type,
        source_url=obs.source_url,
        evidence_ids=[obs.evidence_id] if obs.evidence_id else [],
        confidence=ConfidenceLevel.LOW,
        ownership=obs.ownership if obs.ownership != OwnershipStatus.UNKNOWN else OwnershipStatus.COMPANY_OWNED,
        freshness=FreshnessState.UNKNOWN,
        suppression=SuppressionState.NONE,
        reason_codes=reasons,
        next_action=f"Último recurso: canal corporativo genérico {value}." if value else "Canal genérico sem valor.",
        extra=extra,
    )


def draft_to_route(draft: RouteDraft, *, company_entity_id: str) -> ReachabilityRoute:
    assert_no_auto_send(draft.action)
    rid = stable_id(
        company_entity_id,
        draft.channel_type.value,
        draft.channel_value or "",
        draft.candidate_id or "",
        draft.relation.value,
        draft.reachability.value,
    )
    return ReachabilityRoute(
        route_id=rid,
        company_entity_id=company_entity_id,
        decision_unit_candidate_id=draft.candidate_id,
        target_role=draft.target_role,
        channel_type=draft.channel_type,
        channel_value=draft.channel_value,
        route_relation=draft.relation,
        epistemic_class=draft.epistemic,
        source_type=draft.source_type,
        source_url=draft.source_url,
        evidence_ids=draft.evidence_ids,
        route_confidence=draft.confidence,
        freshness=draft.freshness,
        ownership=draft.ownership,
        suppression=draft.suppression,
        action_mode=draft.action,
        reason_codes=draft.reason_codes,
        next_action=draft.next_action,
        reachability_class=draft.reachability,
        first_class_label=draft.first_class_label,
        first_class_kind=draft.first_class_kind,
        observed_at=draft.observed_at,
        suitability=draft.suitability,
        extra=draft.extra,
    )


def route_rank(route: ReachabilityRoute) -> tuple[int, int, int]:
    return (
        _CLASS_RANK.get(route.reachability_class, 0),
        {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0, "NONE": 0}.get(route.route_confidence.value, 0),
        1 if route.suppression == SuppressionState.NONE else 0,
    )


def is_actionable_route(route: ReachabilityRoute) -> bool:
    if route.reachability_class in {
        ReachabilityClass.R0_NO_ACTIONABLE_ROUTE,
        ReachabilityClass.BLOCKED,
    }:
        return False
    if route.action_mode in {ActionMode.BLOCKED, ActionMode.NO_ACTIONABLE_ROUTE}:
        return False
    if route.suppression != SuppressionState.NONE:
        return False
    return True


def person_is_suitable(candidate: DecisionUnitCandidate | None) -> bool:
    if candidate is None:
        return False
    if candidate.relation != PersonRelation.COMPANY_MEMBER:
        return False
    if candidate.suitability in {ConfidenceLevel.NONE}:
        return False
    from scripts.decision_unit_intelligence.decision_policy import is_legal_entity_name

    if is_legal_entity_name(candidate.person_name):
        return False
    return True


def best_account_class(routes: list[ReachabilityRoute]) -> ReachabilityClass:
    actionable = [r for r in routes if is_actionable_route(r)]
    if not actionable:
        blocked = [r for r in routes if r.reachability_class == ReachabilityClass.BLOCKED]
        if blocked and not any(r.reachability_class != ReachabilityClass.BLOCKED for r in routes):
            return ReachabilityClass.BLOCKED
        return ReachabilityClass.R0_NO_ACTIONABLE_ROUTE
    return max(actionable, key=route_rank).reachability_class


def next_action_text(route: ReachabilityRoute, *, person_name: str | None) -> str:
    if route.reachability_class == ReachabilityClass.R3_ROUTED_TO_NAMED_PERSON and person_name:
        return (
            f"Ligar para {route.channel_value} e pedir por {person_name}. Não alegar que o telefone pertence à pessoa."
        )
    return route.next_action or ""


def looks_like_personal_unlabeled_phone(source_type: str | None, snippet: str | None) -> bool:
    text = fold_text(f"{source_type or ''} {snippet or ''}")
    return any(tok in text for tok in ("celular pessoal", "telefone pessoal", "whatsapp pessoal"))
