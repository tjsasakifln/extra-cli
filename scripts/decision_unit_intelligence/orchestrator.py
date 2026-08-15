"""Pure orchestration: observations → decision unit + reachability + recommendation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from scripts.decision_unit_intelligence.corroboration import (
    CandidatePerson,
    corroborate_affiliation,
    detect_channel_conflicts,
    detect_person_conflicts,
    email_association_gate,
    evidence_items_from_observations,
    evidence_quality_label,
)
from scripts.decision_unit_intelligence.decision_policy import (
    POLICY_VERSION,
    assess_role_for_service,
    canonicalize_service,
    identity_confidence,
    is_excluded_observation,
    is_legal_entity_name,
    normalize_observed_role,
    role_confidence,
)
from scripts.decision_unit_intelligence.email_discovery import (
    EmailDiscoveryClass,
    classify_email_discovery,
    derive_versioned_patterns,
    inferred_candidates_from_supported_patterns,
)
from scripts.decision_unit_intelligence.email_resolution import (
    ObservedOrgEmail,
    official_domain_from_emails,
)
from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    AccountTerminal,
    ActionMode,
    ChannelObservation,
    ChannelType,
    ConfidenceLevel,
    DecisionRoleClass,
    DecisionUnitCandidate,
    EpistemicClass,
    FieldAspect,
    FieldEvidence,
    PersonObservation,
    PersonRelation,
    ReachabilityClass,
    ReachabilityRoute,
    Recommendation,
    RouteRelation,
    SearchLedger,
    StopReason,
    level_rank,
    normalize_cnpj,
    normalize_email,
    normalize_name,
    now_iso,
    stable_id,
)
from scripts.decision_unit_intelligence.projection import is_email_safe_for_warmbly
from scripts.decision_unit_intelligence.reachability import (
    best_account_class,
    classify_channel_observation,
    classify_observed_email_channel,
    draft_to_route,
    is_actionable_route,
    person_is_suitable,
    route_rank,
)

QSA_SOURCES = frozenset({"qsa_rfb", "brasilapi_cnpj", "rfb", "qsa"})


def _corroborate_candidates(
    candidates: list[DecisionUnitCandidate],
    *,
    people: list[PersonObservation],
    company_cnpj: str,
    company_name: str | None,
    as_of: str = "2026-08-15",
) -> list[Any]:
    records = []
    for candidate in candidates:
        name = normalize_name(candidate.person_name)
        if not name:
            continue
        person_obs = [
            obs
            for obs in people
            if normalize_name(obs.person_name) == name
            and (not obs.company_entity_id or normalize_cnpj(obs.company_entity_id) == company_cnpj)
        ]
        items = evidence_items_from_observations(person_obs, company_name=company_name)
        person = CandidatePerson(
            canonical_name=name,
            target_company_cnpj=company_cnpj,
            target_company_name=company_name,
            claimed_role=candidate.observed_roles[0] if candidate.observed_roles else None,
        )
        record = corroborate_affiliation(person, items, as_of=as_of)
        extra = dict(candidate.extra or {})
        extra["affiliation_corroboration"] = record.to_dict()
        candidate.extra = extra
        records.append(record)
    return records


def _apply_affiliation_email_gate(
    routes: list[ReachabilityRoute],
    records: list[Any],
    candidates: list[DecisionUnitCandidate] | None = None,
) -> None:
    """Refuse person↔email association on known false vínculo. Does not promote email."""
    by_name = {(normalize_name(record.canonical_name) or "").lower(): record for record in records}
    by_candidate: dict[str, Any] = {}
    for candidate in candidates or []:
        rec = by_name.get((normalize_name(candidate.person_name) or "").lower())
        if rec is not None:
            by_candidate[candidate.candidate_id] = rec
    for route in routes:
        if not route.channel_value or "@" not in str(route.channel_value):
            continue
        extra = dict(route.extra or {})
        name = normalize_name(extra.get("associated_person_name") or extra.get("person_name"))
        record = by_name.get((name or "").lower()) if name else None
        if record is None and route.decision_unit_candidate_id:
            record = by_candidate.get(route.decision_unit_candidate_id)
        if record is None:
            continue
        decision = email_association_gate(record, email=route.channel_value)
        extra["affiliation_gate"] = decision.to_dict()
        extra["affiliation_stop_the_line"] = decision.stop_the_line
        if not decision.allowed:
            extra["identity_explicitly_associated"] = False
            extra["affiliation_association_refused"] = True
            route.reason_codes = list(
                dict.fromkeys([*route.reason_codes, *decision.reason_codes, "AFFILIATION_GATE_REFUSED"])
            )
            if route.route_relation == RouteRelation.PERSON_OWNS_CHANNEL:
                route.route_relation = RouteRelation.ACCOUNT_LEVEL_ONLY
            if route.reachability_class == ReachabilityClass.R1_DIRECT:
                route.reachability_class = ReachabilityClass.R5_CORPORATE_ONLY
        route.extra = extra


def _stamp_email_discovery_classes(routes: list[ReachabilityRoute]) -> None:
    for route in routes:
        extra = route.extra if isinstance(route.extra, dict) else {}
        email_safe = is_email_safe_for_warmbly(route)
        extra["email_validated"] = email_safe
        extra["email_discovery_class"] = classify_email_discovery(
            route.channel_value,
            epistemic=route.epistemic_class,
            identity_associated=bool(extra.get("identity_explicitly_associated")),
            ambiguous=bool(extra.get("identity_ambiguous")),
            inferred_pattern=route.channel_type == ChannelType.INFERRED_DIRECT_EMAIL,
            inferred_pattern_state=str(extra.get("inferred_pattern_state") or extra.get("candidate_state") or ""),
            mx_present=(extra.get("email_verification") or {}).get("mx") == "MX_PRESENT"
            if isinstance(extra.get("email_verification"), dict)
            else False,
            email_safe_policy=email_safe,
        ).value
        if extra.get("affiliation_association_refused"):
            extra["identity_explicitly_associated"] = False
        elif (
            extra.get("identity_explicitly_associated") is None and route.route_relation.value == "PERSON_OWNS_CHANNEL"
        ):
            extra["identity_explicitly_associated"] = route.channel_type == ChannelType.DIRECT_EMAIL
        route.extra = extra


def person_id_for(company_entity_id: str, name: str | None) -> str:
    return stable_id("person", company_entity_id, (normalize_name(name) or "").lower())


def candidate_id_for(company_entity_id: str, person_id: str, service: str) -> str:
    return stable_id("cand", company_entity_id, person_id, canonicalize_service(service))


def _group_people(observations: list[PersonObservation]) -> dict[str, list[PersonObservation]]:
    groups: dict[str, list[PersonObservation]] = defaultdict(list)
    for obs in observations:
        name = normalize_name(obs.person_name)
        if not name:
            continue
        # Homonym safety: never merge across companies (key includes entity).
        key = f"{obs.company_entity_id}|{name.lower()}"
        groups[key].append(obs)
    return groups


def build_candidates(
    observations: list[PersonObservation],
    *,
    company_entity_id: str,
    service: str,
    why_now: str | None,
) -> list[DecisionUnitCandidate]:
    service = canonicalize_service(service)
    candidates: list[DecisionUnitCandidate] = []
    for _key, group in _group_people(observations).items():
        if any(is_excluded_observation(o) for o in group) and all(is_excluded_observation(o) for o in group):
            continue
        usable = [o for o in group if not is_excluded_observation(o)]
        if not usable:
            continue
        name = normalize_name(usable[0].person_name)
        if is_legal_entity_name(name):
            continue
        pid = person_id_for(company_entity_id, name)
        observed_roles = sorted({o.observed_role for o in usable if o.observed_role})
        role_classes = [o.normalized_role_class for o in usable if o.normalized_role_class != DecisionRoleClass.UNKNOWN]
        # Prefer more specific observed class; never invent.
        role_class = role_classes[0] if role_classes else DecisionRoleClass.UNKNOWN
        for preferred in (
            DecisionRoleClass.SOCIO_ADMINISTRADOR,
            DecisionRoleClass.DIRETOR,
            DecisionRoleClass.CONTRATOS,
            DecisionRoleClass.LICITACOES,
            DecisionRoleClass.REPRESENTANTE_LEGAL,
        ):
            if preferred in role_classes:
                role_class = preferred
                break
        sources = {o.source_type for o in usable}
        qsa_only = bool(sources) and sources <= QSA_SOURCES
        signature_count = sum(1 for o in usable if o.signature_context)
        assessment = assess_role_for_service(
            role_class=role_class,
            service=service,
            observation_count=len(usable),
            signature_count=signature_count,
            source_count=len(sources),
            relation=usable[0].relation,
            qsa_only=qsa_only,
        )
        if assessment.suitability == ConfidenceLevel.NONE:
            continue
        ev_ids = [o.evidence_id for o in usable if o.evidence_id]
        quality = evidence_quality_label(
            source_count=len(sources),
            has_document=any(o.document_id for o in usable),
            contradicted=False,
        )
        candidates.append(
            DecisionUnitCandidate(
                candidate_id=candidate_id_for(company_entity_id, pid, service),
                company_entity_id=company_entity_id,
                person_id=pid,
                person_name=name,
                observed_roles=observed_roles,
                decision_role_class=assessment.role_class,
                decision_relevance=assessment.decision_relevance,
                authority_signal=assessment.authority_signal,
                operational_relevance=assessment.operational_relevance,
                service_context=service,
                why_now_context=why_now,
                identity_confidence=identity_confidence(
                    name=name, observation_count=len(usable), source_count=len(sources)
                ),
                role_confidence=role_confidence(
                    observed_role=observed_roles[0] if observed_roles else None,
                    role_class=assessment.role_class,
                    qsa_only=qsa_only,
                ),
                suitability=assessment.suitability,
                service_fit=assessment.service_fit,
                evidence_quality=ConfidenceLevel(quality),
                evidence_ids=ev_ids,
                reason_codes=assessment.reason_codes,
                relation=PersonRelation.COMPANY_MEMBER,
                representation_signal=assessment.operational_relevance,
                inferred_decision_relevance=assessment.inferred_decision_relevance,
                observation_count=len(usable),
                signature_count=signature_count,
                source_count=len(sources),
                aspects=[
                    FieldAspect("person", EpistemicClass.OBSERVED, "name_in_source"),
                    FieldAspect(
                        "role",
                        EpistemicClass.OBSERVED if observed_roles else EpistemicClass.UNKNOWN,
                        "observed_role_text",
                    ),
                    FieldAspect(
                        "inferred_decision_relevance",
                        EpistemicClass.INFERRED if assessment.inferred_decision_relevance else EpistemicClass.UNKNOWN,
                        POLICY_VERSION,
                    ),
                ],
            )
        )
    return candidates


def _attach_switchboard_to_people(
    channels: list[ChannelObservation],
    candidates: list[DecisionUnitCandidate],
) -> list[tuple[ChannelObservation, DecisionUnitCandidate | None]]:
    """Company switchboard is not a personal phone. Emit one routed pair per suitable person."""
    pairs: list[tuple[ChannelObservation, DecisionUnitCandidate | None]] = []
    switchboards = [
        c
        for c in channels
        if c.channel_type in {ChannelType.COMPANY_SWITCHBOARD, ChannelType.DIRECT_PHONE}
        and not (c.extra or {}).get("person_owns_phone")
    ]
    other = [c for c in channels if c not in switchboards]
    suitable = [c for c in candidates if person_is_suitable(c)]
    for ch in other:
        owner = None
        if ch.person_name:
            n = (normalize_name(ch.person_name) or "").lower()
            owner = next((c for c in suitable if (c.person_name or "").lower() == n), None)
        pairs.append((ch, owner))
    if switchboards and suitable:
        for person in suitable:
            for ch in switchboards:
                pairs.append((ch, person))
    else:
        for ch in switchboards:
            pairs.append((ch, None))
    return pairs


def build_routes(
    channels: list[ChannelObservation],
    candidates: list[DecisionUnitCandidate],
    *,
    company_entity_id: str,
) -> list[ReachabilityRoute]:
    routes: list[ReachabilityRoute] = []
    seen: set[str] = set()
    for obs, cand in _attach_switchboard_to_people(channels, candidates):
        draft = classify_channel_observation(
            obs,
            candidate=cand,
            suitable_person=person_is_suitable(cand),
        )
        route = draft_to_route(draft, company_entity_id=company_entity_id)
        if route.route_id in seen:
            continue
        seen.add(route.route_id)
        routes.append(route)
    return routes


def maybe_infer_emails(
    *,
    candidates: list[DecisionUnitCandidate],
    channels: list[ChannelObservation],
    company_entity_id: str,
    company_site: str | None,
    mx_valid: bool = False,
    catch_all: bool = False,
    public_hits: list[str] | None = None,
) -> list[ReachabilityRoute]:
    observed = [
        ObservedOrgEmail(
            email=c.channel_value,
            source_type=c.source_type,
            source_url=c.source_url,
            person_name=c.person_name,
        )
        for c in channels
        if c.channel_value and "@" in c.channel_value and c.epistemic_class == EpistemicClass.OBSERVED
    ]
    emails = [o.email for o in observed]
    domain, _dep, _reasons = official_domain_from_emails(emails, company_site=company_site)
    if not domain:
        return []
    already = {normalize_email(c.channel_value) for c in channels if c.channel_value}
    pattern_records = [record.to_dict() for record in derive_versioned_patterns(observed)]
    routes: list[ReachabilityRoute] = []
    for cand in candidates:
        if not person_is_suitable(cand) or not cand.person_name:
            continue
        inferences = inferred_candidates_from_supported_patterns(
            person_name=cand.person_name,
            domain=domain,
            observed=observed,
            mx_valid=mx_valid,
            catch_all=catch_all,
            public_hits=public_hits,
        )
        preferred = next((i for i in inferences if i.pattern_id == "first.last"), inferences[0] if inferences else None)
        if not preferred or preferred.email in already:
            continue
        obs = ChannelObservation(
            observation_id=stable_id("infemail", company_entity_id, preferred.email),
            company_entity_id=company_entity_id,
            channel_type=ChannelType.INFERRED_DIRECT_EMAIL,
            channel_value=preferred.email,
            person_name=cand.person_name,
            source_type="email_pattern_inference",
            epistemic_class=EpistemicClass.INFERRED,
            extra={
                "technically_validated": preferred.technically_validated,
                "corroborated": preferred.corroborated,
                "pattern_id": preferred.pattern_id,
                "reason_codes": preferred.reason_codes,
                "verified_class": preferred.verified_class,
                "email_discovery_class": EmailDiscoveryClass.INFERRED_PATTERN_EMAIL.value,
                "identity_explicitly_associated": False,
                "person_name": cand.person_name,
                "associated_person_name": cand.person_name,
                "pattern_records": pattern_records,
                "pattern_state": (preferred.signals or {}).get("pattern_state"),
                "inferred_grade": (preferred.signals or {}).get("inferred_grade"),
                "inferred_pattern_state": EmailDiscoveryClass.INFERRED_PATTERN_EMAIL.value,
                "candidate_state": EmailDiscoveryClass.INFERRED_PATTERN_EMAIL.value,
            },
        )
        draft = classify_channel_observation(obs, candidate=cand, suitable_person=True)
        routes.append(draft_to_route(draft, company_entity_id=company_entity_id))
    return routes


def _candidate_sort_key(c: DecisionUnitCandidate) -> tuple:
    qsa_penalty = 0
    if "QSA_CADASTRE_ONLY" in c.reason_codes and c.operational_relevance in {
        ConfidenceLevel.NONE,
        ConfidenceLevel.UNKNOWN,
    }:
        qsa_penalty = -1
    return (
        qsa_penalty,
        level_rank(c.decision_relevance),
        level_rank(c.operational_relevance),
        level_rank(c.evidence_quality),
        level_rank(c.service_fit),
        level_rank(c.identity_confidence),
        0,
    )


def recommend(
    candidates: list[DecisionUnitCandidate],
    routes: list[ReachabilityRoute],
) -> Recommendation:
    usable_people = [c for c in candidates if person_is_suitable(c)]
    usable_people.sort(key=lambda c: c.person_name or "")
    usable_people.sort(key=_candidate_sort_key, reverse=True)
    actionable = [r for r in routes if is_actionable_route(r)]
    actionable.sort(key=route_rank, reverse=True)

    warnings: list[str] = []
    if not usable_people and not actionable:
        return Recommendation(
            primary_target_id=None,
            primary_route_id=None,
            why_this_person=["Nenhuma pessoa adequada na unidade decisória."],
            why_this_route=["Nenhuma rota defensável."],
            next_action="Enriquecer com documentos oficiais da empresa.",
            action_mode=ActionMode.NEEDS_ENRICHMENT,
            warnings=["NO_DECISION_UNIT_AND_NO_ROUTE"],
        )

    primary_person = usable_people[0] if usable_people else None
    # Prefer a route that reaches the primary person; do not pick a worse person
    # just because they have a prettier email.
    person_routes = [
        r for r in actionable if primary_person and r.decision_unit_candidate_id == primary_person.candidate_id
    ]
    role_or_corp = [
        r
        for r in actionable
        if r.reachability_class in {ReachabilityClass.R4_ROLE_ROUTE, ReachabilityClass.R5_CORPORATE_ONLY}
    ]
    primary_route = None
    if person_routes:
        primary_route = max(person_routes, key=route_rank)
    elif role_or_corp:
        primary_route = max(role_or_corp, key=route_rank)
        warnings.append("PRIMARY_ROUTE_NOT_TIED_TO_PRIMARY_PERSON")
    elif actionable:
        primary_route = actionable[0]

    why_person: list[str] = []
    why_route: list[str] = []
    dims: dict[str, str] = {}
    if primary_person:
        why_person.append(f"Papel observado: {', '.join(primary_person.observed_roles) or 'não informado'}.")
        why_person.append(f"Classe normalizada: {primary_person.decision_role_class.value}.")
        if primary_person.inferred_decision_relevance:
            why_person.append(primary_person.inferred_decision_relevance)
        why_person.extend(primary_person.reason_codes)
        dims = {
            "identity_confidence": primary_person.identity_confidence.value,
            "role_confidence": primary_person.role_confidence.value,
            "decision_relevance": primary_person.decision_relevance.value,
            "authority_signal": primary_person.authority_signal.value,
            "operational_relevance": primary_person.operational_relevance.value,
            "service_fit": primary_person.service_fit.value,
            "evidence_quality": primary_person.evidence_quality.value,
        }
        if "QSA_CADASTRE_ONLY" in primary_person.reason_codes:
            warnings.append("PRIMARY_IS_QSA_CADASTRE_ONLY_NOT_PROVEN_BUYER")
    if primary_route:
        why_route.append(f"Classe {primary_route.reachability_class.value} via {primary_route.channel_type.value}.")
        why_route.append(f"Relação: {primary_route.route_relation.value}.")
        why_route.extend(primary_route.reason_codes)
        dims["route_confidence"] = primary_route.route_confidence.value
        dims["ownership"] = primary_route.ownership.value
        dims["suppression"] = primary_route.suppression.value
        dims["freshness"] = primary_route.freshness.value
        dims["first_class_label"] = primary_route.first_class_label.value
        dims["first_class_kind"] = primary_route.first_class_kind.value
        if primary_route.channel_type == ChannelType.INFERRED_DIRECT_EMAIL:
            warnings.append("INFERRED_EMAIL_NOT_OBSERVED")

    secondary = [c.candidate_id for c in usable_people[1:4]]
    alternatives = [r.route_id for r in actionable if primary_route is None or r.route_id != primary_route.route_id][:5]
    action = (
        primary_route.action_mode
        if primary_route
        else (ActionMode.NEEDS_ENRICHMENT if primary_person else ActionMode.NO_ACTIONABLE_ROUTE)
    )
    return Recommendation(
        primary_target_id=primary_person.candidate_id if primary_person else None,
        primary_route_id=primary_route.route_id if primary_route else None,
        secondary_target_ids=secondary,
        alternative_route_ids=alternatives,
        why_this_person=why_person,
        why_this_route=why_route,
        evidence_ids=(primary_person.evidence_ids if primary_person else [])
        + (primary_route.evidence_ids if primary_route else []),
        next_action=primary_route.next_action if primary_route else "Unidade decisória sem rota — enriquecer canais.",
        action_mode=action,
        reachability_class=primary_route.reachability_class if primary_route else None,
        policy_version=POLICY_VERSION,
        warnings=warnings,
        dimensions=dims,
    )


def derive_terminal(
    *,
    candidates: list[DecisionUnitCandidate],
    routes: list[ReachabilityRoute],
    ledger: SearchLedger,
    blocked: bool,
) -> AccountTerminal:
    if blocked:
        return AccountTerminal.BLOCKED
    if any(is_actionable_route(r) for r in routes):
        return AccountTerminal.ACTIONABLE_ROUTE
    if candidates:
        # Person exists, no route: not a commercial failure and not R0-as-person-failure.
        return AccountTerminal.DECISION_UNIT_IDENTIFIED_REACHABILITY_UNRESOLVED
    stop = ledger.stop_reason
    if stop == StopReason.SOURCE_BLOCKED.value:
        return AccountTerminal.BLOCKED
    if stop == StopReason.BUDGET_EXHAUSTED.value:
        return AccountTerminal.EXHAUSTED
    return AccountTerminal.NEEDS_ENRICHMENT


def investigate_account(
    *,
    cnpj: str,
    legal_name: str | None,
    service: str,
    why_now: str | None,
    people: list[PersonObservation],
    channels: list[ChannelObservation],
    ledger: SearchLedger | None = None,
    company_site: str | None = None,
    infer_email: bool = True,
    mx_valid: bool = False,
    catch_all: bool = False,
    public_email_hits: list[str] | None = None,
    evidence: list[FieldEvidence] | None = None,
    discovery_extra: dict[str, Any] | None = None,
    blocked: bool = False,
) -> AccountInvestigation:
    entity_id = normalize_cnpj(cnpj)
    service = canonicalize_service(service)
    ledger = ledger or SearchLedger()
    people = list(people)
    for p in people:
        if p.normalized_role_class == DecisionRoleClass.UNKNOWN and p.observed_role:
            p.normalized_role_class = normalize_observed_role(p.observed_role)
    candidates = build_candidates(people, company_entity_id=entity_id, service=service, why_now=why_now)
    # Normalize observed emails to a channel type before routing.
    normalized_channels: list[ChannelObservation] = []
    for ch in channels:
        if (
            ch.channel_value
            and "@" in ch.channel_value
            and ch.channel_type
            in {
                ChannelType.DIRECT_EMAIL,
                ChannelType.GENERIC_CORPORATE_EMAIL,
                ChannelType.ROLE_MAILBOX,
                ChannelType.OTHER_PUBLIC_BUSINESS_ROUTE,
            }
        ):
            ch.channel_type = classify_observed_email_channel(ch.channel_value)
        normalized_channels.append(ch)
    routes = build_routes(normalized_channels, candidates, company_entity_id=entity_id)
    if infer_email:
        routes.extend(
            maybe_infer_emails(
                candidates=candidates,
                channels=normalized_channels,
                company_entity_id=entity_id,
                company_site=company_site,
                mx_valid=mx_valid,
                catch_all=catch_all,
                public_hits=public_email_hits,
            )
        )
    affiliation_records = _corroborate_candidates(
        candidates,
        people=people,
        company_cnpj=entity_id,
        company_name=legal_name,
    )
    _apply_affiliation_email_gate(routes, affiliation_records, candidates)
    _stamp_email_discovery_classes(routes)
    rec = recommend(candidates, routes)
    conflicts = detect_person_conflicts(people) + detect_channel_conflicts(normalized_channels)
    terminal = derive_terminal(candidates=candidates, routes=routes, ledger=ledger, blocked=blocked)
    if not ledger.stop_reason:
        if terminal == AccountTerminal.ACTIONABLE_ROUTE:
            ledger.stop_reason = StopReason.POSITIVE_ROUTE.value
        elif terminal == AccountTerminal.BLOCKED:
            ledger.stop_reason = StopReason.SOURCE_BLOCKED.value
        elif terminal == AccountTerminal.EXHAUSTED:
            ledger.stop_reason = StopReason.BUDGET_EXHAUSTED.value
    klass = best_account_class(routes)
    reasons = [terminal.value, klass.value]
    if terminal == AccountTerminal.DECISION_UNIT_IDENTIFIED_REACHABILITY_UNRESOLVED:
        reasons.append("PERSON_WITHOUT_ROUTE_IS_NOT_R0")
    return AccountInvestigation(
        company_entity_id=entity_id,
        cnpj=entity_id,
        legal_name=legal_name,
        service_context=service,
        why_now=why_now,
        candidates=candidates,
        routes=routes,
        recommendation=rec,
        ledger=ledger,
        terminal=terminal,
        evidence=evidence or [],
        conflicts=conflicts,
        reason_codes=reasons,
        warnings=list(dict.fromkeys(rec.warnings)),
        policy_version=POLICY_VERSION,
        built_at=now_iso(),
        extra={
            "account_reachability_class": klass.value,
            "primary_first_class_label": (
                next((r.first_class_label.value for r in routes if rec.primary_route_id == r.route_id), None)
            ),
            "primary_first_class_kind": (
                next((r.first_class_kind.value for r in routes if rec.primary_route_id == r.route_id), None)
            ),
            "affiliation_corroboration": [record.to_dict() for record in affiliation_records],
            **(discovery_extra or {}),
        },
    )
