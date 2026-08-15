"""First-class multi-channel labels. Observation-driven; never invents ownership."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from scripts.decision_unit_intelligence.models import (
    ActionMode,
    ChannelObservation,
    ChannelType,
    ConfidenceLevel,
    DecisionUnitCandidate,
    FirstClassRouteKind,
    FirstClassRouteLabel,
    FreshnessState,
    ReachabilityClass,
    RouteRelation,
    fold_text,
)

FRESH_MAX_DAYS = 180
AGING_MAX_DAYS = 365

_EXPLICIT_WHATSAPP_TOKENS = (
    "whatsapp",
    "wa.me/",
    "api.whatsapp.com",
    "web.whatsapp.com",
    "whats app",
)
_PERSONAL_OWNERSHIP_TOKENS = (
    "celular pessoal",
    "telefone pessoal",
    "whatsapp pessoal",
    "celular do titular",
)
_STALE_TOKENS = (
    "numero antigo",
    "telefone antigo",
    "contato antigo",
    "desatualizado",
    "nao usa mais",
    "linha desativada",
)


@dataclass(frozen=True)
class PhoneContext:
    kind: str
    blocks_personal_ownership: bool
    third_party: bool
    stale_marked: bool
    reason_codes: tuple[str, ...]


def parse_observed_at(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def freshness_from_observed_at(
    observed_at: str | None,
    *,
    now: datetime | None = None,
) -> FreshnessState:
    """UNKNOWN only when no parseable observed_at exists."""
    parsed = parse_observed_at(observed_at)
    if parsed is None:
        return FreshnessState.UNKNOWN
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    age = current - parsed
    if age <= timedelta(days=FRESH_MAX_DAYS):
        return FreshnessState.FRESH
    if age <= timedelta(days=AGING_MAX_DAYS):
        return FreshnessState.AGING
    return FreshnessState.STALE


def observation_text(obs: ChannelObservation) -> str:
    extra = obs.extra or {}
    parts = [
        obs.source_type or "",
        obs.snippet or "",
        obs.source_url or "",
        str(extra.get("label") or ""),
        str(extra.get("phone_label") or ""),
        str(extra.get("context") or ""),
        str(extra.get("phone_context") or ""),
        " ".join(str(code) for code in extra.get("reason_codes") or ()),
    ]
    return fold_text(" ".join(parts))


def explicit_public_whatsapp(obs: ChannelObservation) -> bool:
    extra = obs.extra or {}
    if extra.get("explicit_whatsapp") is True or extra.get("public_whatsapp") is True:
        return True
    if extra.get("explicit_whatsapp") is False or extra.get("public_whatsapp") is False:
        return False
    text = observation_text(obs)
    value = fold_text(obs.channel_value or "")
    haystack = f"{text} {value}"
    return any(token in haystack for token in _EXPLICIT_WHATSAPP_TOKENS)


def infer_phone_context(obs: ChannelObservation) -> PhoneContext:
    extra = obs.extra or {}
    text = observation_text(obs)
    reasons: list[str] = []
    kind = "unknown"
    blocks = False
    stale = bool(extra.get("stale") or extra.get("number_age") == "old")

    declared = fold_text(str(extra.get("phone_context") or ""))
    third_party_checks: tuple[tuple[str, tuple[str, ...], str], ...] = (
        ("contador", ("contador", "contabilidade", "escritorio contabil", "crc "), "THIRD_PARTY_ACCOUNTANT_PHONE"),
        (
            "juridico",
            ("escritorio juridico", "advocacia", "advogados associados", "oab/", "oab "),
            "THIRD_PARTY_LAW_OFFICE_PHONE",
        ),
        ("consorcio", ("consorcio", "sociedade de proposito"), "CONSORTIUM_PHONE"),
    )
    corporate_checks: tuple[tuple[str, tuple[str, ...], str], ...] = (
        ("recepcao", ("recepcao", "portaria", "pabx", "pbx", "switchboard", "mesa telefonica"), "RECEPTION_PHONE"),
        (
            "geral",
            ("telefone geral", "tel geral", "central de atendimento", "central telefonica"),
            "GENERAL_COMPANY_PHONE",
        ),
        ("matriz", ("matriz", "sede", "head office", "headquarters"), "HQ_MATRIX_PHONE"),
        ("filial", ("filial", "unidade ", "branch office"), "BRANCH_PHONE"),
        ("setor", ("setor de", "departamento de", "ramal do setor"), "SECTORAL_PHONE"),
    )
    scan = f"{declared} {text}".strip()
    third_party = False
    for name, tokens, code in third_party_checks:
        if name == declared or any(token in scan for token in tokens):
            kind = name
            blocks = True
            third_party = True
            reasons.append(code)
            break
    if not third_party:
        for name, tokens, code in corporate_checks:
            if name == declared or any(token in scan for token in tokens):
                kind = name
                blocks = True
                reasons.append(code)
                break
    if any(token in scan for token in _STALE_TOKENS):
        stale = True
        reasons.append("STALE_NUMBER_MARKED")
    if extra.get("person_owns_phone") is True and not blocks and kind == "unknown":
        kind = "pessoal"
    return PhoneContext(
        kind=kind,
        blocks_personal_ownership=blocks,
        third_party=third_party,
        stale_marked=stale,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def first_class_for(
    *,
    channel_type: ChannelType,
    relation: RouteRelation,
    extra: dict,
    obs: ChannelObservation,
) -> tuple[FirstClassRouteLabel, FirstClassRouteKind]:
    if channel_type == ChannelType.PROFESSIONAL_WHATSAPP and explicit_public_whatsapp(obs):
        return FirstClassRouteLabel.PUBLIC_WHATSAPP, FirstClassRouteKind.PUBLIC_WHATSAPP
    if channel_type == ChannelType.CONTACT_FORM:
        return FirstClassRouteLabel.FORM, FirstClassRouteKind.FORM
    if channel_type == ChannelType.PROFESSIONAL_PROFILE:
        return FirstClassRouteLabel.PROFILE, FirstClassRouteKind.PROFILE
    if channel_type in {ChannelType.COMPANY_SWITCHBOARD, ChannelType.DIRECT_PHONE}:
        if relation == RouteRelation.PERSON_OWNS_CHANNEL and extra.get("person_owns_phone"):
            return FirstClassRouteLabel.DIRECT_PERSON_PHONE, FirstClassRouteKind.PHONE
        if relation == RouteRelation.ROUTES_TO_NAMED_PERSON:
            return FirstClassRouteLabel.ROUTES_TO_NAMED_PERSON, FirstClassRouteKind.ROUTED_CALL
        return FirstClassRouteLabel.CORPORATE_PHONE, FirstClassRouteKind.PHONE
    return FirstClassRouteLabel.UNKNOWN, FirstClassRouteKind.MANUAL_RESEARCH


def route_suitability(
    *,
    suitable_person: bool,
    candidate: DecisionUnitCandidate | None,
    label: FirstClassRouteLabel,
    suppression_blocked: bool,
) -> ConfidenceLevel:
    if suppression_blocked:
        return ConfidenceLevel.NONE
    if label == FirstClassRouteLabel.UNKNOWN:
        return ConfidenceLevel.UNKNOWN
    if candidate is not None and suitable_person:
        return candidate.suitability
    if label in {
        FirstClassRouteLabel.CORPORATE_PHONE,
        FirstClassRouteLabel.FORM,
        FirstClassRouteLabel.PROFILE,
        FirstClassRouteLabel.PUBLIC_WHATSAPP,
    }:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


def finalize_route_draft(
    draft: object,
    *,
    obs: ChannelObservation,
    candidate: DecisionUnitCandidate | None,
    suitable_person: bool,
) -> object:
    """Stamp provenance + first-class labels. Does not invent person ownership."""
    extra = dict(getattr(draft, "extra", None) or {})
    ctx = infer_phone_context(obs)
    extra["phone_context"] = ctx.kind
    extra["source"] = obs.source_type
    if obs.observed_at:
        extra["observed_at"] = obs.observed_at
    reasons = list(getattr(draft, "reason_codes", []) or [])
    reasons.extend(ctx.reason_codes)

    channel_type = draft.channel_type
    relation = draft.relation
    reachability = draft.reachability
    action = draft.action

    phone_like = channel_type in {
        ChannelType.DIRECT_PHONE,
        ChannelType.COMPANY_SWITCHBOARD,
        ChannelType.PROFESSIONAL_WHATSAPP,
    }
    if phone_like and ctx.blocks_personal_ownership:
        extra["person_owns_phone"] = False
        extra["person_owns_whatsapp"] = False
        if ctx.third_party:
            channel_type = ChannelType.COMPANY_SWITCHBOARD
            relation = RouteRelation.ACCOUNT_LEVEL_ONLY
            reachability = ReachabilityClass.R5_CORPORATE_ONLY
            action = ActionMode.MANUAL_CALL
            draft.candidate_id = None
            reasons.append("THIRD_PARTY_PHONE_NOT_COMPANY_ROUTE")
        elif suitable_person and candidate and candidate.person_name:
            channel_type = ChannelType.COMPANY_SWITCHBOARD
            relation = RouteRelation.ROUTES_TO_NAMED_PERSON
            reachability = ReachabilityClass.R3_ROUTED_TO_NAMED_PERSON
            action = ActionMode.MANUAL_ROUTED_CALL
        else:
            channel_type = ChannelType.COMPANY_SWITCHBOARD
            relation = RouteRelation.ACCOUNT_LEVEL_ONLY
            reachability = ReachabilityClass.R5_CORPORATE_ONLY
            action = ActionMode.MANUAL_CALL
        reasons.append("GENERAL_PHONE_NOT_PERSONAL")

    if channel_type == ChannelType.PROFESSIONAL_WHATSAPP:
        if not explicit_public_whatsapp(obs):
            reasons.append("WHATSAPP_NOT_EXPLICITLY_MARKED")
            extra["person_owns_whatsapp"] = False
            extra["person_owns_phone"] = False
            if suitable_person and candidate and candidate.person_name:
                channel_type = ChannelType.COMPANY_SWITCHBOARD
                relation = RouteRelation.ROUTES_TO_NAMED_PERSON
                reachability = ReachabilityClass.R3_ROUTED_TO_NAMED_PERSON
                action = ActionMode.MANUAL_ROUTED_CALL
            else:
                channel_type = ChannelType.COMPANY_SWITCHBOARD
                relation = RouteRelation.ACCOUNT_LEVEL_ONLY
                reachability = ReachabilityClass.R5_CORPORATE_ONLY
                action = ActionMode.MANUAL_CALL
        elif not extra.get("person_owns_whatsapp"):
            extra["person_owns_whatsapp"] = False
            if suitable_person and candidate and candidate.person_name:
                relation = RouteRelation.ROUTES_TO_NAMED_PERSON
                reachability = ReachabilityClass.R3_ROUTED_TO_NAMED_PERSON
                action = ActionMode.MANUAL_WHATSAPP
            else:
                relation = RouteRelation.ACCOUNT_LEVEL_ONLY
                reachability = ReachabilityClass.R5_CORPORATE_ONLY
                action = ActionMode.MANUAL_WHATSAPP

    freshness = freshness_from_observed_at(obs.observed_at)
    if ctx.stale_marked:
        freshness = FreshnessState.STALE
        reasons.append("STALE_NUMBER_MARKED")

    label, kind = first_class_for(
        channel_type=channel_type,
        relation=relation,
        extra=extra,
        obs=obs,
    )
    if label == FirstClassRouteLabel.DIRECT_PERSON_PHONE and ctx.blocks_personal_ownership:
        label = (
            FirstClassRouteLabel.ROUTES_TO_NAMED_PERSON
            if relation == RouteRelation.ROUTES_TO_NAMED_PERSON
            else FirstClassRouteLabel.CORPORATE_PHONE
        )
        kind = (
            FirstClassRouteKind.ROUTED_CALL
            if label == FirstClassRouteLabel.ROUTES_TO_NAMED_PERSON
            else FirstClassRouteKind.PHONE
        )

    if candidate and suitable_person and candidate.person_name:
        extra.setdefault("associated_person_name", candidate.person_name)
        extra.setdefault("person_name", candidate.person_name)

    extra["first_class_label"] = label.value
    extra["first_class_kind"] = kind.value
    suitability = route_suitability(
        suitable_person=suitable_person,
        candidate=candidate,
        label=label,
        suppression_blocked=reachability == ReachabilityClass.BLOCKED,
    )

    draft.channel_type = channel_type
    draft.relation = relation
    draft.reachability = reachability
    draft.action = action
    draft.freshness = freshness
    draft.observed_at = obs.observed_at
    draft.first_class_label = label
    draft.first_class_kind = kind
    draft.suitability = suitability
    draft.reason_codes = list(dict.fromkeys(reasons))
    draft.extra = extra
    return draft
