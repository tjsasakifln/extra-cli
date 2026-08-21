"""Adversarial tests for controlled email eligibility by route class.

Calls the shipped projection / eligibility / ranking functions. Named-person
is not a universal send gate. ROLE/GENERIC/FREEMAIL never become EMAIL_VALIDATED
and never mint a person.
"""

from __future__ import annotations

from scripts.confenge_contact_resolution.send_readiness import evaluate_email_send_ready
from scripts.decision_unit_intelligence.controlled_email import (
    CONTROLLED_EMAIL_POLICY_VERSION,
    EmailRouteClass,
    alternative_after_preferred_bounce,
    classify_account_email_routes,
    classify_email_route_class,
    evaluate_controlled_email_eligible,
    stamp_and_rank_feed_contacts,
)
from scripts.decision_unit_intelligence.email_validated.policy import decide_promotion
from scripts.decision_unit_intelligence.email_validated.schema import AdjudicationRecord
from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    ActionMode,
    ChannelType,
    ConfidenceLevel,
    DecisionRoleClass,
    DecisionUnitCandidate,
    EpistemicClass,
    FreshnessState,
    OwnershipStatus,
    ReachabilityClass,
    ReachabilityRoute,
    RouteRelation,
    SuppressionState,
)
from scripts.decision_unit_intelligence.projection import (
    is_email_safe_for_warmbly,
    project_warmbly_outreach,
)

ACCOUNT_ID = "12345678000190"


def _person() -> DecisionUnitCandidate:
    return DecisionUnitCandidate(
        candidate_id="cand-ana",
        company_entity_id=ACCOUNT_ID,
        person_id="person-ana",
        person_name="ANA SOUZA",
        observed_roles=["Gerente de Contratos"],
        decision_role_class=DecisionRoleClass.GERENTE_CONTRATOS,
        identity_confidence=ConfidenceLevel.HIGH,
        role_confidence=ConfidenceLevel.HIGH,
    )


def _route(
    mailbox: str,
    *,
    channel: ChannelType = ChannelType.GENERIC_CORPORATE_EMAIL,
    relation: RouteRelation = RouteRelation.ACCOUNT_LEVEL_ONLY,
    epistemic: EpistemicClass = EpistemicClass.OBSERVED,
    reachability: ReachabilityClass = ReachabilityClass.R5_CORPORATE_ONLY,
    action: ActionMode = ActionMode.GENERIC_EMAIL_LAST_RESORT,
    candidate_id: str | None = None,
    ownership: OwnershipStatus = OwnershipStatus.COMPANY_OWNED,
    freshness: FreshnessState = FreshnessState.FRESH,
    suppression: SuppressionState = SuppressionState.NONE,
    extra: dict | None = None,
    reason_codes: list[str] | None = None,
    source_type: str = "company_website",
    observed_at: str = "2026-08-01T00:00:00Z",
) -> ReachabilityRoute:
    payload = dict(extra or {})
    return ReachabilityRoute(
        route_id=f"r-{mailbox}",
        company_entity_id=ACCOUNT_ID,
        channel_type=channel,
        reachability_class=reachability,
        action_mode=action,
        decision_unit_candidate_id=candidate_id,
        channel_value=mailbox,
        route_relation=relation,
        epistemic_class=epistemic,
        source_type=source_type,
        source_url="https://empresaexemplo.com.br/contato",
        evidence_ids=["ev-1"],
        freshness=freshness,
        ownership=ownership,
        suppression=suppression,
        reason_codes=list(reason_codes or []),
        observed_at=observed_at,
        extra=payload,
    )


def _account(
    routes: list[ReachabilityRoute], people: list[DecisionUnitCandidate] | None = None
) -> AccountInvestigation:
    return AccountInvestigation(
        company_entity_id=ACCOUNT_ID,
        cnpj=ACCOUNT_ID,
        legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA",
        service_context="reajuste_14133",
        why_now="contrato ativo",
        candidates=list(people or []),
        routes=routes,
    )


def test_observed_direct_person_is_controlled_eligible() -> None:
    person = _person()
    route = _route(
        "ana.souza@empresaexemplo.com.br",
        channel=ChannelType.DIRECT_EMAIL,
        relation=RouteRelation.PERSON_OWNS_CHANNEL,
        reachability=ReachabilityClass.R1_DIRECT,
        action=ActionMode.HUMAN_REVIEW_EMAIL,
        candidate_id=person.candidate_id,
        extra={"identity_explicitly_associated": True, "email_discovery_class": "EMAIL_VALIDATED"},
    )
    classified = evaluate_controlled_email_eligible(route, person=person, named_person_safe=True)
    assert classified.route_class == EmailRouteClass.DIRECT_PERSON
    assert classified.controlled_email_eligible is True
    assert classified.mailbox_person_evidence == "OBSERVED"
    assert classified.person_id == "person-ana"
    assert classified.email_validated is True
    assert is_email_safe_for_warmbly(route) is True


def test_comercial_associated_eligible_without_person_id() -> None:
    route = _route(
        "comercial@empresaexemplo.com.br",
        channel=ChannelType.ROLE_MAILBOX,
        relation=RouteRelation.ROUTES_TO_ROLE,
        reachability=ReachabilityClass.R4_ROLE_ROUTE,
        action=ActionMode.ROLE_EMAIL,
        extra={"email_discovery_class": "ROLE_MAILBOX"},
    )
    classified = evaluate_controlled_email_eligible(route, person=None)
    assert classified.route_class == EmailRouteClass.ROLE_OR_DEPARTMENT
    assert classified.controlled_email_eligible is True
    assert classified.person_id is None
    assert classified.person_name is None
    assert classified.email_validated is False
    assert classified.mailbox_person_evidence == "UNKNOWN"
    assert is_email_safe_for_warmbly(route) is False


def test_contato_eligible_without_inventing_person() -> None:
    route = _route(
        "contato@empresaexemplo.com.br",
        extra={"email_discovery_class": "GENERIC_MAILBOX"},
    )
    classified = evaluate_controlled_email_eligible(route, person=None)
    assert classified.route_class == EmailRouteClass.GENERIC_COMPANY
    assert classified.controlled_email_eligible is True
    assert classified.person_id is None
    assert classified.person_name is None
    assert "person_unknown" in classified.reason_codes
    assert classified.email_validated is False
    assert is_email_safe_for_warmbly(route) is False


def test_associated_gmail_is_public_company_freemail() -> None:
    route = _route(
        "empresa@gmail.com",
        extra={"company_associated": True, "mailbox_company_evidence": "OBSERVED"},
        source_type="company_website",
    )
    classified = evaluate_controlled_email_eligible(route, person=None)
    assert classified.route_class == EmailRouteClass.PUBLIC_COMPANY_FREEMAIL
    assert classified.controlled_email_eligible is True
    assert classified.person_id is None
    assert classified.email_validated is False
    assert is_email_safe_for_warmbly(route) is False


def test_unassociated_gmail_is_blocked_unknown() -> None:
    route = _route(
        "pessoa@gmail.com",
        ownership=OwnershipStatus.UNKNOWN,
        extra={"mailbox_company_evidence": "UNKNOWN"},
        source_type="unknown",
    )
    classified = evaluate_controlled_email_eligible(route, person=None)
    assert classified.route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY
    assert classified.controlled_email_eligible is False
    assert classified.provenance in {"UNKNOWN", "RISKY", "INFERRED"}
    assert "unassociated_freemail" in classified.reason_codes


def test_inferred_address_is_risky_outside_default_pilot() -> None:
    route = _route(
        "joao.silva@empresaexemplo.com.br",
        channel=ChannelType.INFERRED_DIRECT_EMAIL,
        epistemic=EpistemicClass.INFERRED,
        reachability=ReachabilityClass.INFERRED_UNVERIFIED,
        extra={"email_discovery_class": "INFERRED_PATTERN_EMAIL", "inferred_grade": "INFERRED_UNVERIFIED"},
        reason_codes=["INFERRED"],
    )
    classified = evaluate_controlled_email_eligible(route, person=None)
    assert classified.route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY
    assert classified.risk_class.value == "RISKY"
    assert classified.controlled_email_eligible is False
    assert "risky_excluded_from_default_pilot" in classified.reason_codes
    assert is_email_safe_for_warmbly(route) is False


def test_catch_all_inconclusive_is_risky() -> None:
    route = _route(
        "ana.souza@empresaexemplo.com.br",
        extra={"catch_all_inconclusive": True, "email_discovery_class": "INFERRED_PATTERN_CATCH_ALL"},
        epistemic=EpistemicClass.INFERRED,
        channel=ChannelType.INFERRED_DIRECT_EMAIL,
    )
    classified = evaluate_controlled_email_eligible(route, person=None)
    assert classified.route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY
    assert classified.controlled_email_eligible is False
    assert "inferred_or_catch_all" in classified.reason_codes


def test_suppressed_mailbox_never_transportable() -> None:
    route = _route("comercial@empresaexemplo.com.br", suppression=SuppressionState.HARD_BOUNCE)
    classified = evaluate_controlled_email_eligible(route, person=None)
    assert classified.controlled_email_eligible is False
    assert "hard_bounce" in classified.reason_codes


def test_opt_out_never_transportable() -> None:
    route = _route("contato@empresaexemplo.com.br", suppression=SuppressionState.OPT_OUT)
    classified = evaluate_controlled_email_eligible(route, person=None)
    assert classified.controlled_email_eligible is False
    assert "opt_out" in classified.reason_codes


def test_four_mailboxes_one_preferred_initial_route() -> None:
    person = _person()
    routes = [
        _route(
            "ana.souza@empresaexemplo.com.br",
            channel=ChannelType.DIRECT_EMAIL,
            relation=RouteRelation.PERSON_OWNS_CHANNEL,
            reachability=ReachabilityClass.R1_DIRECT,
            action=ActionMode.HUMAN_REVIEW_EMAIL,
            candidate_id=person.candidate_id,
            extra={"identity_explicitly_associated": True},
        ),
        _route(
            "comercial@empresaexemplo.com.br",
            channel=ChannelType.ROLE_MAILBOX,
            relation=RouteRelation.ROUTES_TO_ROLE,
            reachability=ReachabilityClass.R4_ROLE_ROUTE,
            action=ActionMode.ROLE_EMAIL,
        ),
        _route("contato@empresaexemplo.com.br"),
        _route(
            "empresa@gmail.com",
            extra={"company_associated": True, "mailbox_company_evidence": "OBSERVED"},
        ),
    ]
    ranking = classify_account_email_routes(_account(routes, [person]), named_person_safe=is_email_safe_for_warmbly)
    preferred = ranking.preferred_initial_route
    assert preferred is not None
    assert preferred.mailbox == "ana.souza@empresaexemplo.com.br"
    assert preferred.preferred_initial is True
    assert sum(1 for item in ranking.classified_routes if item.preferred_initial) == 1
    assert len(ranking.alternative_routes) == 3
    payload = project_warmbly_outreach(_account(routes, [person]))
    assert payload["auto_send"] is False
    assert payload["preferred_initial_route"]["mailbox"] == "ana.souza@empresaexemplo.com.br"
    assert payload["controlled_email_eligible_count"] == 4


def test_preferred_bounce_leaves_alternative_available() -> None:
    routes = [
        _route(
            "comercial@empresaexemplo.com.br",
            channel=ChannelType.ROLE_MAILBOX,
            relation=RouteRelation.ROUTES_TO_ROLE,
            reachability=ReachabilityClass.R4_ROLE_ROUTE,
            action=ActionMode.ROLE_EMAIL,
            suppression=SuppressionState.HARD_BOUNCE,
        ),
        _route("contato@empresaexemplo.com.br"),
    ]
    ranking = classify_account_email_routes(_account(routes))
    assert ranking.preferred_initial_route is not None
    assert ranking.preferred_initial_route.mailbox == "contato@empresaexemplo.com.br"
    nxt = alternative_after_preferred_bounce(ranking, bounced_mailbox="comercial@empresaexemplo.com.br")
    assert nxt is not None
    assert nxt.mailbox == "contato@empresaexemplo.com.br"


def test_non_reply_does_not_suppress() -> None:
    route = _route("contato@empresaexemplo.com.br", extra={"non_reply": True, "replies": 0})
    classified = evaluate_controlled_email_eligible(route, person=None)
    assert classified.controlled_email_eligible is True
    assert classified.suppression_state == SuppressionState.NONE.value
    assert "opt_out" not in classified.reason_codes
    assert "hard_bounce" not in classified.reason_codes


def test_generic_mailbox_never_becomes_fake_person() -> None:
    route = _route("contato@empresaexemplo.com.br")
    classified = evaluate_controlled_email_eligible(route, person=_person())
    assert classified.person_id is None
    assert classified.person_name is None
    assert classified.route_class == EmailRouteClass.GENERIC_COMPANY
    payload = project_warmbly_outreach(_account([route], [_person()]))
    generic = next(r for r in payload["classified_email_routes"] if r["mailbox"].startswith("contato@"))
    assert generic["person_id"] is None
    assert generic["person_name"] is None
    assert generic["email_validated"] is False
    for item in payload["recipient_candidates"]:
        assert item["channel_value"] != "contato@empresaexemplo.com.br"


def test_gmail_never_becomes_fake_corporate_domain() -> None:
    route = _route(
        "empresa@gmail.com",
        extra={"company_associated": True, "mailbox_company_evidence": "OBSERVED"},
    )
    classified = evaluate_controlled_email_eligible(route, person=None)
    assert classified.route_class == EmailRouteClass.PUBLIC_COMPANY_FREEMAIL
    assert classified.route_class.value != "DIRECT_PERSON"
    assert "corporate_domain" not in classified.reason_codes
    assert classify_email_route_class(route) != EmailRouteClass.DIRECT_PERSON


def test_risky_never_silently_enters_default_cohort() -> None:
    inferred = _route(
        "joao.silva@empresaexemplo.com.br",
        channel=ChannelType.INFERRED_DIRECT_EMAIL,
        epistemic=EpistemicClass.INFERRED,
        extra={"email_discovery_class": "INFERRED_PATTERN_EMAIL"},
        reason_codes=["INFERRED"],
    )
    generic = _route("contato@empresaexemplo.com.br")
    ranking = classify_account_email_routes(_account([inferred, generic]))
    payload = project_warmbly_outreach(_account([inferred, generic]))
    risky = [r for r in ranking.classified_routes if r.route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY]
    assert risky
    assert all(not item.controlled_email_eligible for item in risky)
    assert payload["preferred_initial_route"]["mailbox"] == "contato@empresaexemplo.com.br"
    assert payload["preferred_initial_route"]["route_class"] != EmailRouteClass.PROBABILISTIC_OR_RISKY.value


def _adjudication(email: str) -> AdjudicationRecord:
    return AdjudicationRecord.from_dict(
        {
            "case_id": email,
            "account_id": ACCOUNT_ID,
            "person_name": None,
            "role": None,
            "company": "EMPRESA EXEMPLO ENGENHARIA LTDA",
            "email": email,
            "epistemic": "OBSERVED",
            "source": "company_website",
            "source_date": "2026-08-01",
            "source_url": "https://empresaexemplo.com.br/contato",
            "frozen_evidence": email,
            "identity_association": "NONE",
            "affiliation": "DEFENSIBLE",
            "technical_status": "NONE",
            "freshness": "FRESH",
            "human_verdict": "GENERIC_ROLE",
            "notes": "fixture",
            "policy_version": "dui.email-validated-promotion.v1",
            "gold_set_version": "email-validated-gold.v1",
            "split": "development",
            "suppression": "NONE",
            "engine": "fixture",
        }
    )


def test_email_validated_promotion_still_refuses_generic_and_role() -> None:
    generic = decide_promotion(_adjudication("contato@empresaexemplo.com.br"))
    role = decide_promotion(_adjudication("comercial@empresaexemplo.com.br"))
    assert generic.promote is False
    assert role.promote is False
    assert generic.predicted_class != "EMAIL_VALIDATED"
    assert role.predicted_class != "EMAIL_VALIDATED"


def test_send_readiness_generic_is_controlled_eligible_not_email_send_ready() -> None:
    company = {
        "razao_social": "EMPRESA EXEMPLO ENGENHARIA LTDA",
        "official_domain": "empresaexemplo.com.br",
        "outreach_eligibility": "ELIGIBLE",
        "construction_evidence": {
            "sector_fit": "CONFIRMED_ENGINEERING",
            "target_fit_class": "TARGET_CONFIRMED",
            "relevant_contract_count": 4,
        },
        "target_fit_class": "TARGET_CONFIRMED",
        "service_code": "REAJUSTE_14133",
        "portfolio": {"pass_contract_count": 4},
        "factual_hook": "Contrato de engenharia PASS recente no órgão X.",
        "observed_fact": "objeto: pavimentação asfáltica CBUQ; órgão: Pref. Coxilha; UF RS",
        "why_this_account": "EMPRESA EXEMPLO com execução pública de pavimentação",
        "why_now": "aditivo recente no contrato de EMPRESA EXEMPLO de pavimentação",
        "micro_offer_code": "REAJUSTE_CHECK",
        "evidence_ids": ["ev-contract-1"],
        "cta": "Posso te mandar o recorte público que encontrei?",
        "canonical_universe_member": True,
        "primary_service": {
            "service_id": "estruturacao_pleito_reajuste",
            "supporting_signal_ids": ["mature_no_reajuste"],
            "evidence_ids": ["ev-contract-1"],
        },
    }
    ready = evaluate_email_send_ready(
        company=company,
        email="contato@empresaexemplo.com.br",
        ownership_status="COMPANY_OWNED",
        verification_status="OBSERVED",
        service_code="estruturacao_pleito_reajuste",
        factual_evidence=True,
        evidence_ids=["ev-contract-1"],
        source_type="site",
        source_url="https://empresaexemplo.com.br/contato",
    )
    assert ready.email_send_ready is False
    assert ready.human_recipient_evidence_valid is False
    assert ready.controlled_email_eligible is True


def test_hr_mailbox_not_controlled_eligible() -> None:
    route = _route("vagas@empresaexemplo.com.br")
    classified = evaluate_controlled_email_eligible(route, person=None)
    assert classified.controlled_email_eligible is False
    assert any("mailbox_purpose" in code or "human_recipient" in code for code in classified.reason_codes)


def test_stamp_and_rank_feed_contacts_emits_route_class_without_person() -> None:
    stamped = stamp_and_rank_feed_contacts(
        [
            {
                "email": "comercial@empresaexemplo.com.br",
                "ownership_status": "COMPANY_OWNED",
                "source_url": "https://empresaexemplo.com.br/contato",
            },
            {
                "email": "contato@empresaexemplo.com.br",
                "ownership_status": "COMPANY_OWNED",
                "source_url": "https://empresaexemplo.com.br/contato",
            },
        ],
        account_id=ACCOUNT_ID,
    )
    assert stamped[0]["route_class"] == EmailRouteClass.ROLE_OR_DEPARTMENT.value
    assert stamped[0]["controlled_email_eligible"] is True
    assert stamped[0]["person_unknown"] is True
    assert stamped[0]["email_validated"] is False
    assert sum(1 for c in stamped if c.get("preferred_initial")) == 1


def test_projection_emits_ingestible_contacts_with_route_class() -> None:
    payload = project_warmbly_outreach(_account([_route("contato@empresaexemplo.com.br")]))
    contacts = payload["contacts"]
    assert contacts
    contato = next(c for c in contacts if c["email"].startswith("contato@"))
    assert contato["route_class"] == EmailRouteClass.GENERIC_COMPANY.value
    assert contato["controlled_email_eligible"] is True
    assert contato["person_unknown"] is True
    assert contato["email_validated"] is False
    assert not contato.get("person_id")


def test_projection_auto_send_false_and_policy_version() -> None:
    payload = project_warmbly_outreach(_account([_route("contato@empresaexemplo.com.br")]))
    assert payload["auto_send"] is False
    assert payload["controlled_email_policy_version"] == CONTROLLED_EMAIL_POLICY_VERSION
    assert payload["schema_id"] == "confenge.outreach.v1"
    generic = payload["classified_email_routes"][0]
    assert generic["controlled_email_eligible"] is True
    assert generic["email_validated"] is False
    assert generic["person_id"] is None


def test_five_class_synthetic_canary_snapshot() -> None:
    """Real-path classified snapshot for Warmbly ingest. No SMTP."""
    person = _person()
    routes = [
        _route(
            "ana.souza@empresaexemplo.com.br",
            channel=ChannelType.DIRECT_EMAIL,
            relation=RouteRelation.PERSON_OWNS_CHANNEL,
            reachability=ReachabilityClass.R1_DIRECT,
            action=ActionMode.HUMAN_REVIEW_EMAIL,
            candidate_id=person.candidate_id,
            extra={"identity_explicitly_associated": True, "email_discovery_class": "EMAIL_VALIDATED"},
        ),
        _route(
            "comercial@empresaexemplo.com.br",
            channel=ChannelType.ROLE_MAILBOX,
            relation=RouteRelation.ROUTES_TO_ROLE,
            reachability=ReachabilityClass.R4_ROLE_ROUTE,
            action=ActionMode.ROLE_EMAIL,
        ),
        _route("contato@empresaexemplo.com.br"),
        _route(
            "empresa@gmail.com",
            extra={"company_associated": True, "mailbox_company_evidence": "OBSERVED"},
            source_type="company_website",
        ),
        _route(
            "joao.silva@empresaexemplo.com.br",
            channel=ChannelType.INFERRED_DIRECT_EMAIL,
            epistemic=EpistemicClass.INFERRED,
            extra={"email_discovery_class": "INFERRED_PATTERN_EMAIL"},
            reason_codes=["INFERRED"],
        ),
    ]
    payload = project_warmbly_outreach(_account(routes, [person]))
    classes = {item["route_class"] for item in payload["classified_email_routes"]}
    assert classes == {
        EmailRouteClass.DIRECT_PERSON.value,
        EmailRouteClass.ROLE_OR_DEPARTMENT.value,
        EmailRouteClass.GENERIC_COMPANY.value,
        EmailRouteClass.PUBLIC_COMPANY_FREEMAIL.value,
        EmailRouteClass.PROBABILISTIC_OR_RISKY.value,
    }
    assert payload["auto_send"] is False
    preferred = payload["preferred_initial_route"]
    assert preferred["mailbox"] == "ana.souza@empresaexemplo.com.br"
    assert sum(1 for item in payload["classified_email_routes"] if item.get("preferred_initial")) == 1
    risky = next(
        item
        for item in payload["classified_email_routes"]
        if item["route_class"] == EmailRouteClass.PROBABILISTIC_OR_RISKY.value
    )
    assert risky["controlled_email_eligible"] is False
    generic = next(
        item
        for item in payload["classified_email_routes"]
        if item["mailbox"].startswith("contato@")
    )
    assert generic["person_id"] is None
    assert generic["person_name"] is None
    gmail = next(item for item in payload["classified_email_routes"] if "gmail.com" in item["mailbox"])
    assert gmail["route_class"] == EmailRouteClass.PUBLIC_COMPANY_FREEMAIL.value
    assert gmail["person_id"] is None
    contacts = stamp_and_rank_feed_contacts(
        [
            {"email": r.channel_value, "ownership_status": "COMPANY_OWNED", "source_url": r.source_url}
            for r in routes
        ],
        account_id=ACCOUNT_ID,
    )
    stamped_classes = {c["route_class"] for c in contacts}
    assert EmailRouteClass.ROLE_OR_DEPARTMENT.value in stamped_classes
    assert EmailRouteClass.GENERIC_COMPANY.value in stamped_classes
    assert EmailRouteClass.PUBLIC_COMPANY_FREEMAIL.value in stamped_classes
    assert EmailRouteClass.PROBABILISTIC_OR_RISKY.value in stamped_classes
    for contact in contacts:
        if contact["route_class"] != EmailRouteClass.DIRECT_PERSON.value:
            assert not contact.get("person_id")
            assert not contact.get("person_name")
    payload["contacts"] = contacts
    payload["schema_version"] = payload.get("schema_id") or "confenge.outreach.v1"
    payload["synthetic"] = True
    payload["smtp"] = "none"
