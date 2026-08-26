"""Adversarial tests for controlled email eligibility by route class.

Calls the shipped projection / eligibility / ranking functions. Named-person
is not a universal send gate. ROLE/GENERIC/FREEMAIL never become EMAIL_VALIDATED
and never mint a person.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.confenge_contact_resolution.send_readiness import evaluate_email_send_ready
from scripts.decision_unit_intelligence.controlled_email import (
    CONTROLLED_EMAIL_POLICY_VERSION,
    ControlledRiskClass,
    EmailRouteClass,
    alternative_after_preferred_bounce,
    apply_cross_account_preferred_mailbox_gate,
    classify_account_email_routes,
    classify_email_route_class,
    evaluate_controlled_email_eligible,
    observed_channels_have_controlled_eligible_route,
    stamp_and_rank_feed_contacts,
)
from scripts.decision_unit_intelligence.email_validated.policy import decide_promotion
from scripts.decision_unit_intelligence.email_validated.schema import AdjudicationRecord
from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    ActionMode,
    ChannelObservation,
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
from scripts.warmbly_bridge import SCHEMA_OUTREACH
from scripts.warmbly_bridge.mapping import build_leads, map_lead

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
    source_url: str | None = "https://empresaexemplo.com.br/contato",
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
        source_url=source_url,
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


def test_fresh_contact_page_without_observed_at_is_not_eligible_or_preferred() -> None:
    stamped = stamp_and_rank_feed_contacts(
        [
            {
                "email": "contato@empresaexemplo.com.br",
                "source_type": "contact_page",
                "source_url": "https://empresaexemplo.com.br/contato",
                "ownership_status": "COMPANY_OWNED",
                "route_freshness": "FRESH",
                "observed_at": "",
            }
        ],
        account_id=ACCOUNT_ID,
        official_domain="empresaexemplo.com.br",
    )

    assert stamped[0]["route_freshness"] == FreshnessState.FRESH.value
    assert stamped[0]["controlled_email_eligible"] is False
    assert stamped[0]["preferred_initial"] is False
    assert stamped[0]["risk_class"] == ControlledRiskClass.RISKY.value
    assert stamped[0]["publication_block_reason"] == "MISSING_OBSERVED_AT"
    assert "missing_observed_at" in stamped[0]["reason_codes"]


def test_associated_gmail_is_public_company_freemail() -> None:
    route = _route(
        "empresa@gmail.com",
        extra={
            "company_associated": True,
            "mailbox_company_evidence": "OBSERVED",
            "official_domain": "empresaexemplo.com.br",
        },
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


def _exact_registry_extra(*, cnpj: str = ACCOUNT_ID) -> dict:
    return {
        "company_associated": True,
        "mailbox_company_evidence": "OBSERVED",
        "mailbox_person_evidence": "UNKNOWN",
        "official_match_status": "MATCHED",
        "official_authority": "RECEITA_FEDERAL",
        "official_release_id": "rfb-2026-08",
        "registry_cnpj14": cnpj,
        "source_provenance": {
            "release_id": "rfb-2026-08",
            "source_label": "rfb_public_cadastral_via_opencnpj",
        },
    }


def test_exact_registry_freemail_is_public_company_route_without_person() -> None:
    route = _route(
        "empresa@gmail.com",
        source_type="company_registry",
        source_url=None,
        extra=_exact_registry_extra(),
    )
    classified = evaluate_controlled_email_eligible(route, person=None)

    assert classified.route_class == EmailRouteClass.PUBLIC_COMPANY_FREEMAIL
    assert classified.controlled_email_eligible is True
    assert classified.mailbox_company_evidence == "OBSERVED"
    assert classified.mailbox_person_evidence == "UNKNOWN"
    assert classified.person_name is None
    assert classified.email_validated is False


def test_exact_registry_nominal_local_is_company_route_not_invented_person() -> None:
    route = _route(
        "joao.silva@empresaexemplo.com.br",
        source_type="company_registry",
        source_url=None,
        extra=_exact_registry_extra(),
    )
    classified = evaluate_controlled_email_eligible(route, person=None)

    assert classified.route_class == EmailRouteClass.GENERIC_COMPANY
    assert classified.controlled_email_eligible is True
    assert classified.mailbox_person_evidence == "UNKNOWN"
    assert classified.person_name is None
    assert classified.email_validated is False
    assert "person_unknown" in classified.reason_codes


def test_registry_label_or_mismatched_cnpj_never_proves_company_association() -> None:
    ownership_only = _route(
        "empresa@gmail.com",
        source_type="company_registry",
        source_url=None,
        extra={},
    )
    mismatch = _route(
        "empresa@gmail.com",
        source_type="company_registry",
        source_url=None,
        extra=_exact_registry_extra(cnpj="99888777000166"),
    )

    for route in (ownership_only, mismatch):
        classified = evaluate_controlled_email_eligible(route, person=None)
        assert classified.route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY
        assert classified.controlled_email_eligible is False
        assert classified.mailbox_company_evidence == "UNKNOWN"


def test_exact_registry_channel_stops_only_for_its_canonical_account() -> None:
    channel = ChannelObservation(
        observation_id="registry-channel",
        company_entity_id=ACCOUNT_ID,
        channel_type=ChannelType.GENERIC_CORPORATE_EMAIL,
        channel_value="empresa@gmail.com",
        source_type="company_registry",
        observed_at="2026-08-24T00:00:00Z",
        epistemic_class=EpistemicClass.OBSERVED,
        ownership=OwnershipStatus.COMPANY_OWNED,
        evidence_id="registry-evidence",
        extra=_exact_registry_extra(),
    )

    assert observed_channels_have_controlled_eligible_route([channel], account_id=ACCOUNT_ID) is True
    assert (
        observed_channels_have_controlled_eligible_route(
            [channel],
            account_id="99888777000166",
        )
        is False
    )


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
            extra={
                "company_associated": True,
                "mailbox_company_evidence": "OBSERVED",
                "official_domain": "empresaexemplo.com.br",
            },
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
        extra={
            "company_associated": True,
            "mailbox_company_evidence": "OBSERVED",
            "official_domain": "empresaexemplo.com.br",
        },
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


def test_unassociated_web_search_llc_not_controlled_eligible() -> None:
    """Live junk: foreign .llc mailbox on Gmail-unsubscribe URL is not eligible."""
    classified = evaluate_controlled_email_eligible(
        _route(
            "ll@sustainconsulting.llc",
            source_type="web_search",
            source_url="https://multisend-unsubscribe.gmail.com/uc",
            ownership=OwnershipStatus.COMPANY_OWNED,
            extra={
                "company_associated": True,
                "mailbox_company_evidence": "OBSERVED",
                "official_domain": "zancoconstrutora.com.br",
            },
            observed_at="",
        )
    )
    assert classified.controlled_email_eligible is False
    assert classified.mailbox_company_evidence == "UNKNOWN"
    assert (
        classified.route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY
        or "web_search_unassociated" in classified.reason_codes
    )
    assert "untrustworthy_source_url" in classified.reason_codes


def test_gmail_unsubscribe_snippet_not_company_freemail() -> None:
    classified = evaluate_controlled_email_eligible(
        _route(
            "ghulamnabifai26@gmail.com",
            source_type="web_search",
            source_url="https://multisend-unsubscribe.gmail.com/uc",
            ownership=OwnershipStatus.UNKNOWN,
            extra={"official_domain": "empresaexemplo.com.br"},
        )
    )
    assert classified.controlled_email_eligible is False
    assert classified.route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY
    assert classified.mailbox_company_evidence == "UNKNOWN"


def test_missing_provenance_company_owned_flag_not_eligible() -> None:
    classified = evaluate_controlled_email_eligible(
        _route(
            "contato@outra-empresa.com.br",
            source_type="",
            source_url="",
            ownership=OwnershipStatus.COMPANY_OWNED,
            extra={"company_associated": True},
        )
    )
    assert classified.controlled_email_eligible is False
    assert "missing_provenance" in classified.reason_codes
    assert classified.mailbox_company_evidence == "UNKNOWN"


def test_stamp_live_junk_feed_contact_is_not_preferred_initial() -> None:
    stamped = stamp_and_rank_feed_contacts(
        [
            {
                "email": "ll@sustainconsulting.llc",
                "ownership_status": "COMPANY_OWNED",
                "source_url": "https://multisend-unsubscribe.gmail.com/uc",
                "provenance": {
                    "source_type": "web_search",
                    "source_url": "https://multisend-unsubscribe.gmail.com/uc",
                    "evidence_sha256": "",
                    "observed_at": "",
                },
            }
        ],
        account_id="95865044000190",
        official_domain="zancoconstrutora.com.br",
    )
    assert stamped[0]["controlled_email_eligible"] is False
    assert not stamped[0].get("preferred_initial")
    assert stamped[0]["mailbox_company_evidence"] == "UNKNOWN"


def test_map_lead_rejects_unassociated_web_search_mailbox() -> None:
    universe, intel, _ = _five_class_universe_intel_contacts()
    universe = dict(universe)
    universe["website"] = "https://zancoconstrutora.com.br"
    universe["official_domain"] = "zancoconstrutora.com.br"
    contacts = {
        "cnpj14": ACCOUNT_ID,
        "contacts": [
            {
                "email": "ll@sustainconsulting.llc",
                "ownership_status": "COMPANY_OWNED",
                "source_type": "web_search",
                "source_url": "https://multisend-unsubscribe.gmail.com/uc",
                "provenance": {
                    "source_type": "web_search",
                    "source_url": "https://multisend-unsubscribe.gmail.com/uc",
                    "evidence_sha256": "",
                    "observed_at": "",
                },
            }
        ],
    }
    lead = map_lead(universe, intel=intel, contacts_row=contacts, conn=None)
    assert lead is not None
    contact = lead["contacts"][0]
    assert contact["controlled_email_eligible"] is False
    assert not contact.get("preferred_initial")


def test_empty_official_site_source_rejects_mailbox_host_mismatch() -> None:
    """Live junk: site source with empty official_domain and mailbox≠page host."""
    classified = evaluate_controlled_email_eligible(
        _route(
            "contato@smartclub.com.br",
            source_type="site",
            source_url="https://smartlink.com.br/contato",
            ownership=OwnershipStatus.COMPANY_OWNED,
            extra={"company_associated": True},
        )
    )
    assert classified.controlled_email_eligible is False
    assert classified.mailbox_company_evidence == "UNKNOWN"
    assert "mailbox_source_host_mismatch" in classified.reason_codes
    stamped = stamp_and_rank_feed_contacts(
        [
            {
                "email": "contato@mattioli.eng.br",
                "ownership_status": "COMPANY_OWNED",
                "source_type": "site",
                "source_url": "https://dinamica.com.br/contato",
            }
        ],
        account_id=ACCOUNT_ID,
        official_domain=None,
    )
    assert stamped[0]["controlled_email_eligible"] is False
    assert not stamped[0].get("preferred_initial")
    universe, intel, _ = _five_class_universe_intel_contacts()
    universe = dict(universe)
    universe["website"] = ""
    universe["official_domain"] = ""
    lead = map_lead(
        universe,
        intel=intel,
        contacts_row={
            "cnpj14": ACCOUNT_ID,
            "contacts": [
                {
                    "email": "u003eancar@nectarc.com.br",
                    "ownership_status": "COMPANY_OWNED",
                    "source_type": "site",
                    "source_url": "https://ancar.com.br/",
                }
            ],
        },
        conn=None,
    )
    assert lead is not None
    assert lead["contacts"][0]["controlled_email_eligible"] is False


def test_empty_official_freemail_from_aggregator_page_is_not_eligible() -> None:
    classified = evaluate_controlled_email_eligible(
        _route(
            "empresa@terra.com.br",
            source_type="contact_page",
            source_url="https://cnpja.com/office/123",
            extra={"company_associated": True, "mailbox_company_evidence": "OBSERVED"},
        )
    )
    assert classified.controlled_email_eligible is False
    assert classified.route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY


def test_parser_minted_mailbox_host_is_not_eligible() -> None:
    classified = evaluate_controlled_email_eligible(
        _route(
            "1@model.phone.replace",
            source_type="site",
            source_url="https://amrconstrucoes.com.br/contato",
            ownership=OwnershipStatus.COMPANY_OWNED,
        )
    )
    assert classified.controlled_email_eligible is False
    assert "implausible_mailbox_host" in classified.reason_codes
    stamped = stamp_and_rank_feed_contacts(
        [
            {
                "email": "1@model.phone.replace",
                "ownership_status": "COMPANY_OWNED",
                "source_type": "contact_page",
                "source_url": "https://amrconstrucoes.com.br/",
            }
        ],
        account_id=ACCOUNT_ID,
    )
    assert stamped[0]["controlled_email_eligible"] is False


def test_duplicate_preferred_mailbox_across_accounts_fails_closed_for_both() -> None:
    universe_a, intel, _ = _five_class_universe_intel_contacts()
    universe_a = dict(universe_a)
    universe_a["cnpj14"] = "11111111000191"
    universe_a["website"] = "https://energia.com.br"
    universe_a["official_domain"] = "energia.com.br"
    universe_b = dict(universe_a)
    universe_b["cnpj14"] = "22222222000172"
    contacts = {
        "contacts": [
            {
                "email": "secretaria@energia.com.br",
                "ownership_status": "COMPANY_OWNED",
                "source_type": "site",
                "source_url": "https://energia.com.br/contato",
                "observed_at": "2026-08-24T12:00:00Z",
            }
        ]
    }
    leads = build_leads(
        [universe_a, universe_b],
        [],
        [
            {"cnpj14": "11111111000191", **contacts},
            {"cnpj14": "22222222000172", **contacts},
        ],
    )
    preferred = [
        (lead["company"]["cnpj14"], c["email"])
        for lead in leads
        for c in lead["contacts"]
        if c.get("preferred_initial") and c.get("email")
    ]
    assert preferred == []
    gated = apply_cross_account_preferred_mailbox_gate(leads)
    assert sum(1 for lead in gated for c in lead["contacts"] if c.get("preferred_initial")) == 0


def _evidenced_shared_registry_contact(account: str) -> dict:
    return {
        "email": "licitacoes@grupo.example.com",
        "preferred_initial": True,
        "recommended": True,
        "controlled_email_eligible": True,
        "email_send_ready": True,
        "company_associated": True,
        "mailbox_company_evidence": "OBSERVED",
        "channel_epistemic_class": "OBSERVED",
        "ownership_status": "COMPANY_OWNED",
        "route_freshness": "FRESH",
        "route_suppression": "NONE",
        "source_type": "company_registry",
        "source_reference": f"registry-contact:{account}",
        "evidence_ids": [f"registry-evidence:{account}"],
        "registry_cnpj14": account,
        "official_match_status": "MATCHED",
        "official_authority": "RECEITA_FEDERAL",
        "official_release_id": "registry-release-1",
    }


def test_shared_mailbox_keeps_each_independently_evidenced_account_claim() -> None:
    accounts = ("11111111000191", "22222222000172")
    leads = [
        {
            "company": {"cnpj14": account},
            "contacts": [_evidenced_shared_registry_contact(account)],
        }
        for account in accounts
    ]

    gated = apply_cross_account_preferred_mailbox_gate(leads)

    assert [
        lead["company"]["cnpj14"]
        for lead in gated
        if any(contact.get("preferred_initial") for contact in lead["contacts"])
    ] == list(accounts)


def test_specific_shared_mailbox_proof_beats_ambiguous_lexicographic_claim() -> None:
    ambiguous_account = "11111111000191"
    evidenced_account = "22222222000172"
    ambiguous = {
        **_evidenced_shared_registry_contact(ambiguous_account),
        "source_reference": "",
        "evidence_ids": [],
    }
    leads = [
        {"company": {"cnpj14": ambiguous_account}, "contacts": [ambiguous]},
        {
            "company": {"cnpj14": evidenced_account},
            "contacts": [_evidenced_shared_registry_contact(evidenced_account)],
        },
    ]

    gated = apply_cross_account_preferred_mailbox_gate(leads)

    assert gated[0]["contacts"][0]["preferred_initial"] is False
    assert "duplicate_preferred_mailbox_across_accounts" in gated[0]["contacts"][0]["reason_codes"]
    assert gated[1]["contacts"][0]["preferred_initial"] is True


def test_shared_website_mailbox_without_cnpj_specific_proof_fails_for_every_claimant() -> None:
    accounts = ("11111111000191", "22222222000172")
    contact = {
        "email": "geral@empresa.example.com",
        "preferred_initial": True,
        "recommended": True,
        "controlled_email_eligible": True,
        "company_associated": True,
        "mailbox_company_evidence": "OBSERVED",
        "channel_epistemic_class": "OBSERVED",
        "ownership_status": "COMPANY_OWNED",
        "route_freshness": "FRESH",
        "route_suppression": "NONE",
        "source_type": "site",
        "source_reference": "site:https://empresa.example.com/contato",
        "source_url": "https://empresa.example.com/contato",
        "official_domain": "empresa.example.com",
        "evidence_ids": ["site-evidence"],
        "provenance": {"source_type": "site"},
    }
    leads = [
        {"company": {"cnpj14": account}, "contacts": [dict(contact)]}
        for account in accounts
    ]

    gated = apply_cross_account_preferred_mailbox_gate(leads)

    assert not any(c.get("preferred_initial") for lead in gated for c in lead["contacts"])
    assert all(c.get("controlled_email_eligible") is False for lead in gated for c in lead["contacts"])
    assert all(
        "shared_mailbox_without_account_identity_evidence" in c.get("reason_codes", [])
        for lead in gated
        for c in lead["contacts"]
    )


def test_unique_website_mailbox_without_cnpj_specific_proof_fails_closed() -> None:
    account = "20368709000151"
    contact = {
        "email": "escritorio@pimenta.com.br",
        "preferred_initial": True,
        "recommended": True,
        "controlled_email_eligible": True,
        "company_associated": True,
        "mailbox_company_evidence": "OBSERVED",
        "channel_epistemic_class": "OBSERVED",
        "ownership_status": "COMPANY_OWNED",
        "route_freshness": "FRESH",
        "route_suppression": "NONE",
        "source_type": "contact_page",
        "source_reference": "https://pimenta.com.br/contato",
        "source_url": "https://pimenta.com.br/contato",
        "official_domain": "pimenta.com.br",
        "evidence_ids": ["website-contact-evidence"],
    }

    gated = apply_cross_account_preferred_mailbox_gate(
        [{"company": {"cnpj14": account}, "contacts": [contact], "email_send_ready": True}],
        require_account_identity_evidence=True,
    )

    result = gated[0]["contacts"][0]
    assert result["preferred_initial"] is False
    assert result["recommended"] is False
    assert result["controlled_email_eligible"] is False
    assert result["email_send_ready"] is False
    assert gated[0]["email_send_ready"] is False
    assert "recipient_without_account_identity_evidence" in result["reason_codes"]


def test_unique_registry_mailbox_with_exact_cnpj_proof_remains_preferred() -> None:
    account = "20368709000151"
    contact = _evidenced_shared_registry_contact(account)

    gated = apply_cross_account_preferred_mailbox_gate(
        [{"company": {"cnpj14": account}, "contacts": [contact]}],
        require_account_identity_evidence=True,
    )

    result = gated[0]["contacts"][0]
    assert result["preferred_initial"] is True
    assert result["recommended"] is True
    assert result["controlled_email_eligible"] is True


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
                "observed_at": "2026-08-24T12:00:00Z",
            },
            {
                "email": "contato@empresaexemplo.com.br",
                "ownership_status": "COMPANY_OWNED",
                "source_url": "https://empresaexemplo.com.br/contato",
                "observed_at": "2026-08-24T12:00:00Z",
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
            extra={
                "company_associated": True,
                "mailbox_company_evidence": "OBSERVED",
                "official_domain": "empresaexemplo.com.br",
            },
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
    generic = next(item for item in payload["classified_email_routes"] if item["mailbox"].startswith("contato@"))
    assert generic["person_id"] is None
    assert generic["person_name"] is None
    gmail = next(item for item in payload["classified_email_routes"] if "gmail.com" in item["mailbox"])
    assert gmail["route_class"] == EmailRouteClass.PUBLIC_COMPANY_FREEMAIL.value
    assert gmail["person_id"] is None
    contacts = stamp_and_rank_feed_contacts(
        [
            {
                "email": route.channel_value,
                "ownership_status": "COMPANY_OWNED",
                "source_url": route.source_url,
                "channel_epistemic_class": route.epistemic_class.value,
                "email_discovery_class": (route.extra or {}).get("email_discovery_class"),
                "reason_codes": route.reason_codes,
            }
            for route in routes
        ],
        account_id=ACCOUNT_ID,
        official_domain="empresaexemplo.com.br",
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


def _five_class_universe_intel_contacts() -> tuple[dict, dict, dict]:
    universe = {
        "cnpj14": ACCOUNT_ID,
        "razao_social": "EMPRESA EXEMPLO ENGENHARIA LTDA",
        "nome_fantasia": "Empresa Exemplo",
        "website": "https://empresaexemplo.com.br",
        "official_domain": "empresaexemplo.com.br",
        "source_lead_id": "canary-empresa-exemplo",
        "rank": 1,
        "score": 80,
        "tier": "HIGH",
        "outreach_eligibility": "ELIGIBLE",
        "construction_evidence": {
            "sector_fit": "CONFIRMED_ENGINEERING",
            "target_fit_class": "TARGET_CONFIRMED",
            "relevant_contract_count": 4,
        },
        "target_fit_class": "TARGET_CONFIRMED",
        "canonical_universe_member": True,
        "portfolio": {"pass_contract_count": 4},
    }
    intel = {
        "moment": {
            "code": "CONTRACT_EXTENSION",
            "summary": "Aditivo publicado",
            "observed_at": "2026-08-01",
            "confidence": "HIGH",
            "evidence_ids": ["ev-1"],
        },
        "offer": {
            "service_code": "REAJUSTE_14133",
            "service_name": "Reajuste",
            "entry_offer": "Leitura",
            "rationale": "Contrato ativo",
        },
        "messaging": {
            "fact_to_mention": "Aditivo publicado no portal oficial",
            "question_to_ask": "Faz sentido revisar o reajuste?",
            "cta": "Posso enviar o recorte?",
        },
        "evidence": [
            {
                "id": "ev-1",
                "type": "PUBLICATION",
                "title": "Aditivo",
                "url": "https://empresaexemplo.com.br/ev-1",
                "epistemic_class": "CONFIRMED_FACT",
            }
        ],
        "service_code": "REAJUSTE_14133",
        "factual_hook": "Aditivo publicado no portal oficial",
        "observed_fact": "aditivo recente",
        "why_this_account": "EMPRESA EXEMPLO com execução pública",
        "evidence_ids": ["ev-1"],
        "canonical_universe_member": True,
        "primary_service": {
            "service_id": "estruturacao_pleito_reajuste",
            "supporting_signal_ids": ["mature_no_reajuste"],
            "evidence_ids": ["ev-1"],
        },
    }
    contacts = {
        "cnpj14": ACCOUNT_ID,
        "contacts": [
            {
                "email": "ana.souza@empresaexemplo.com.br",
                "name": "ANA SOUZA",
                "role": "Gerente de Contratos",
                "ownership_status": "COMPANY_OWNED",
                "verification_status": "OFFICIAL_SOURCE",
                "source_type": "company_website",
                "source_url": "https://empresaexemplo.com.br/contato",
                "identity_explicitly_associated": True,
                "email_discovery_class": "EMAIL_VALIDATED",
                "source_contact_id": "c-ana",
                "observed_at": "2026-08-24T12:00:00Z",
            },
            {
                "email": "comercial@empresaexemplo.com.br",
                "ownership_status": "COMPANY_OWNED",
                "verification_status": "INSTITUTIONAL_GENERIC",
                "source_type": "company_website",
                "source_url": "https://empresaexemplo.com.br/contato",
                "source_contact_id": "c-comercial",
                "observed_at": "2026-08-24T12:00:00Z",
            },
            {
                "email": "contato@empresaexemplo.com.br",
                "ownership_status": "COMPANY_OWNED",
                "verification_status": "INSTITUTIONAL_GENERIC",
                "source_type": "company_website",
                "source_url": "https://empresaexemplo.com.br/contato",
                "source_contact_id": "c-contato",
                "observed_at": "2026-08-24T12:00:00Z",
            },
            {
                "email": "empresa@gmail.com",
                "ownership_status": "COMPANY_OWNED",
                "source_type": "company_website",
                "source_url": "https://empresaexemplo.com.br/contato",
                "mailbox_company_evidence": "OBSERVED",
                "source_contact_id": "c-gmail",
                "observed_at": "2026-08-24T12:00:00Z",
            },
            {
                "email": "joao.silva@empresaexemplo.com.br",
                "email_derivation": "INFERRED",
                "email_discovery_class": "INFERRED_PATTERN_EMAIL",
                "source_contact_id": "c-inferred",
                "observed_at": "2026-08-24T12:00:00Z",
            },
        ],
    }
    return universe, intel, contacts


def test_stamp_and_rank_uses_observed_feed_name_for_direct_person() -> None:
    stamped = stamp_and_rank_feed_contacts(
        [
            {
                "email": "ana.souza@empresaexemplo.com.br",
                "name": "ANA SOUZA",
                "ownership_status": "COMPANY_OWNED",
                "identity_explicitly_associated": True,
                "email_discovery_class": "EMAIL_VALIDATED",
                "source_url": "https://empresaexemplo.com.br/contato",
                "observed_at": "2026-08-24T12:00:00Z",
            },
            {
                "email": "contato@empresaexemplo.com.br",
                "ownership_status": "COMPANY_OWNED",
                "source_url": "https://empresaexemplo.com.br/contato",
                "observed_at": "2026-08-24T12:00:00Z",
            },
        ],
        account_id=ACCOUNT_ID,
    )
    ana = next(c for c in stamped if c["email"].startswith("ana.souza@"))
    assert ana["route_class"] == EmailRouteClass.DIRECT_PERSON.value
    assert ana["controlled_email_eligible"] is True
    assert ana.get("name") == "ANA SOUZA"
    assert not ana.get("person_id")
    contato = next(c for c in stamped if c["email"].startswith("contato@"))
    assert contato["route_class"] == EmailRouteClass.GENERIC_COMPANY.value
    assert not contato.get("person_id")
    assert not contato.get("name")


def test_five_class_mapping_feed_written_for_warmbly_ingest() -> None:
    """Unmodified map_lead output (stamp_and_rank inside mapping.py) as confenge.outreach.v1."""
    universe, intel, contacts_row = _five_class_universe_intel_contacts()
    lead = map_lead(universe, intel=intel, contacts_row=contacts_row, conn=None)
    assert lead is not None
    classes = {c["route_class"] for c in lead["contacts"]}
    assert classes == {
        EmailRouteClass.DIRECT_PERSON.value,
        EmailRouteClass.ROLE_OR_DEPARTMENT.value,
        EmailRouteClass.GENERIC_COMPANY.value,
        EmailRouteClass.PUBLIC_COMPANY_FREEMAIL.value,
        EmailRouteClass.PROBABILISTIC_OR_RISKY.value,
    }
    ana = next(c for c in lead["contacts"] if str(c.get("email", "")).startswith("ana.souza@"))
    assert ana["route_class"] == EmailRouteClass.DIRECT_PERSON.value
    assert "route_class:PROBABILISTIC_OR_RISKY" not in (ana.get("reason_codes") or [])
    generic = next(c for c in lead["contacts"] if str(c.get("email", "")).startswith("contato@"))
    assert not generic.get("person_id")
    assert generic.get("controlled_email_eligible") is True
    assert generic.get("email_send_ready") is False
    risky = next(c for c in lead["contacts"] if c["route_class"] == EmailRouteClass.PROBABILISTIC_OR_RISKY.value)
    assert risky.get("controlled_email_eligible") is False
    feed = {
        "schema_version": SCHEMA_OUTREACH,
        "generated_at": "2026-08-21T00:00:00Z",
        "synthetic": True,
        "smtp": "none",
        "source": {
            "system": "extra-cli",
            "run_id": "controlled-email-canary-synthetic",
            "snapshot_hash": "synthetic-five-class-canary",
            "profile_id": "confenge",
            "profile_version": "1",
        },
        "pagination": {"has_more": False},
        "leads": [lead],
    }
    here = Path(__file__).resolve().parent
    dest = here / "fixtures" / "controlled_email_five_class_canary.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    loaded = json.loads(dest.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == SCHEMA_OUTREACH
    assert len(loaded["leads"]) == 1
    sibling = (
        here.parents[1]
        / "warmbly"
        / "internal"
        / "app"
        / "confenge"
        / "testdata"
        / "controlled_email_five_class_canary.json"
    )
    if sibling.parent.is_dir():
        sibling.write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
        assert json.loads(sibling.read_text(encoding="utf-8"))["leads"][0]["contacts"][0]["email"]


def _doc_route(
    mailbox: str = "licitacoes@alphaengenharia.com.br",
    *,
    official_domain: str = "alphaengenharia.com.br",
    evidence_strength: str = "company_authored_document",
) -> ReachabilityRoute:
    """Company-authored document hosted on a portal host, not the company host."""
    extra: dict = {"evidence_strength": evidence_strength}
    if official_domain:
        extra["official_domain"] = official_domain
    return _route(
        mailbox,
        channel=ChannelType.ROLE_MAILBOX,
        ownership=OwnershipStatus.UNKNOWN,
        source_type="official_documents",
        source_url="https://pncp.gov.br/app/editais/1",
        extra=extra,
    )


def test_a_document_mailbox_on_the_proven_official_domain_is_associated():
    """The account's own proven domain is what binds it, not the document host."""
    verdict = evaluate_controlled_email_eligible(_doc_route())
    assert verdict.mailbox_company_evidence == "OBSERVED"
    assert verdict.to_dict()["company_associated"] is True
    assert verdict.controlled_email_eligible is True
    assert verdict.route_class == EmailRouteClass.ROLE_OR_DEPARTMENT


def test_a_document_route_without_a_proven_domain_has_no_association_at_all():
    """Extraction cannot say whose mailbox is printed in a document.

    The document's CNPJ tag is the CNPJ that was queried and the company name is
    producer-supplied, so neither can bind the mailbox. There is deliberately no
    carve-out here: with no proven official domain there is simply no evidence.
    """
    verdict = evaluate_controlled_email_eligible(_doc_route(official_domain=""))
    assert verdict.mailbox_company_evidence == "UNKNOWN"
    assert verdict.to_dict()["company_associated"] is False
    assert verdict.controlled_email_eligible is False
    assert "mailbox_company_evidence_unknown" in verdict.reason_codes


def test_a_notice_that_merely_lists_the_company_cannot_bind_the_agency_mailbox():
    verdict = evaluate_controlled_email_eligible(
        _doc_route("licitacao@saojoaquim.sc.gov.br", evidence_strength="official_cnpj_linked_document")
    )
    assert verdict.mailbox_company_evidence == "UNKNOWN"
    assert verdict.controlled_email_eligible is False


def test_a_consortium_partner_mailbox_in_our_document_is_not_ours():
    verdict = evaluate_controlled_email_eligible(_doc_route("comercial@terraplenagemsulmg.com.br"))
    assert verdict.mailbox_company_evidence == "UNKNOWN"
    assert verdict.controlled_email_eligible is False


def test_a_producer_supplied_company_name_cannot_create_an_association():
    """razao_social arrives on the contact payload, so it can never be a binding."""
    from scripts.decision_unit_intelligence.controlled_email import route_from_feed_contact

    route = route_from_feed_contact(
        {
            "email": "comercial@grupohorizonte.com.br",
            "source_type": "official_documents",
            "source_url": "https://pncp.gov.br/app/editais/1",
            "evidence_strength": "official_cnpj_linked_document",
            "razao_social": "GRUPO HORIZONTE PARTICIPACOES LTDA",
        },
        account_id=ACCOUNT_ID,
    )
    verdict = evaluate_controlled_email_eligible(route)
    assert verdict.mailbox_company_evidence == "UNKNOWN"
    assert verdict.controlled_email_eligible is False


def test_freemail_on_a_document_still_needs_a_company_page():
    verdict = evaluate_controlled_email_eligible(_doc_route("alphaengenharia@gmail.com"))
    assert verdict.controlled_email_eligible is False


def test_suppression_is_read_fail_closed_across_producer_vocabularies():
    """Reading two field names as the whole vocabulary let opted-out mail through."""
    from scripts.decision_unit_intelligence.controlled_email import suppression_from_feed_contact

    suppressing = [
        {"suppression": "opt-out"},
        {"suppression": "do_not_contact"},
        {"suppression": "hard_bounce"},
        {"suppression_state": "opt-out"},
        {"route_suppression": "quarantined"},
        {"suppression_reason": "unsubscribed"},
        {"email_status": "unsubscribed"},
        {"email_status": "hard_bounce"},
        {"opt_out": True},
        {"opt_out": "true"},
        {"opt_out": 1},
        {"opt_out": "yes"},
        {"unsubscribed": True},
        {"opted_out": True},
        {"suppressed": True},
        {"is_suppressed": True},
        {"complained": True},
        {"spam_complaint": True},
        {"blocklisted": True},
        {"do_not_contact": True},
        {"dnc": True},
        {"bounced": True},
        # Nested shapes this schema already uses for provenance.
        {"provenance": {"route_suppression": "OPT_OUT"}},
        {"extra": {"route_suppression": "OPT_OUT"}},
        {"extra": {"suppression": "opt-out"}},
    ]
    for payload in suppressing:
        assert suppression_from_feed_contact(payload) != SuppressionState.NONE, payload

    # A string "false" must not starve the cohort, and a clear token stays clear.
    clear = [
        {},
        {"route_suppression": "NONE"},
        {"route_suppression": "  none  "},
        {"suppression": "clear"},
        {"unsubscribed": "false"},
        {"do_not_contact": "false"},
        {"dnc": "false"},
        {"bounced": "false"},
        {"opt_out": False},
        {"opt_out": 0},
        # `status` is a generic field in this repo (READY, idle, backpressure).
        # Failing closed on it would mark healthy contacts suppressed.
        {"status": "READY"},
        {"status": "new"},
        {"status": "opt_out"},
        # A hint field only suppresses on a recognized suppression word.
        {"email_status": "valid"},
        {"email_status": "verified"},
    ]
    for payload in clear:
        assert suppression_from_feed_contact(payload) == SuppressionState.NONE, payload


def test_a_suppressed_contact_never_reaches_eligibility():
    from scripts.decision_unit_intelligence.controlled_email import route_from_feed_contact

    base = {
        "email": "contato@empresaexemplo.com.br",
        "source": "contact_page",
        "source_type": "contact_page",
        "source_url": "https://empresaexemplo.com.br/contato",
        "observed_at": "2026-08-24T12:00:00Z",
    }
    for payload in ({"suppression": "opt-out"}, {"suppressed": True}, {"opt_out": "true"}):
        route = route_from_feed_contact({**base, **payload}, account_id=ACCOUNT_ID)
        assert evaluate_controlled_email_eligible(route).controlled_email_eligible is False, payload

    route = route_from_feed_contact(base, account_id=ACCOUNT_ID)
    assert evaluate_controlled_email_eligible(route).controlled_email_eligible is True


def test_paraguayan_company_domain_is_not_a_parser_leftover():
    verdict = evaluate_controlled_email_eligible(
        _route(
            "licitaciones@constructoraalvo.com.py",
            source_type="contact_page",
            source_url="https://constructoraalvo.com.py/contacto",
            extra={"official_domain": "constructoraalvo.com.py"},
        )
    )
    assert "implausible_mailbox_host" not in verdict.reason_codes


def test_registry_freemail_proof_survives_bridge_mapping_and_reranking() -> None:
    universe, intel, _contacts = _five_class_universe_intel_contacts()
    proof = _exact_registry_extra()
    source_provenance = proof.pop("source_provenance")
    contacts = {
        "cnpj14": ACCOUNT_ID,
        "contacts": [
            {
                "email": "empresa@gmail.com",
                "source_contact_id": "registry-route-1",
                "source": "company_registry",
                "source_type": "company_registry",
                "source_reference": "registry-evidence-1",
                "evidence_ids": ["registry-evidence-1"],
                "observed_at": "2026-08-24T12:00:00Z",
                "ownership_status": "COMPANY_OWNED",
                "channel_epistemic_class": "OBSERVED",
                "route_freshness": "FRESH",
                "route_suppression": "NONE",
                "source_provenance": source_provenance,
                **proof,
            }
        ],
    }

    lead = map_lead(universe, intel=intel, contacts_row=contacts, conn=None)
    assert lead is not None
    contact = lead["contacts"][0]
    assert contact["route_class"] == EmailRouteClass.PUBLIC_COMPANY_FREEMAIL.value
    assert contact["controlled_email_eligible"] is True
    assert contact["preferred_initial"] is True
    assert contact["person_unknown"] is True
    assert contact["email_validated"] is False
    assert contact["company_associated"] is True
    assert contact["mailbox_company_evidence"] == "OBSERVED"
    assert contact["official_authority"] == "RECEITA_FEDERAL"
    assert contact["official_release_id"] == "rfb-2026-08"
    assert contact["registry_cnpj14"] == ACCOUNT_ID
    assert contact["source_provenance"]["release_id"] == "rfb-2026-08"
    assert contact["source_reference"] == "registry-evidence-1"
    assert contact["route_freshness"] == "FRESH"
    assert contact["route_suppression"] == "NONE"
    assert contact["provenance_chain_valid"] is True
    assert contact["root_source_type"] == "REAL_REGISTRY"


def test_registry_provenance_requires_exact_account_and_complete_release_tuple() -> None:
    universe, intel, _contacts = _five_class_universe_intel_contacts()
    base = _exact_registry_extra()
    source_provenance = base.pop("source_provenance")
    contact = {
        "email": "empresa@gmail.com",
        "source": "company_registry",
        "source_type": "company_registry",
        "source_reference": "registry-evidence-1",
        "observed_at": "2026-08-24T12:00:00Z",
        "ownership_status": "COMPANY_OWNED",
        "channel_epistemic_class": "OBSERVED",
        "route_freshness": "FRESH",
        "route_suppression": "NONE",
        "source_provenance": source_provenance,
        **base,
    }

    for mutation in (
        {"registry_cnpj14": "99888777000166"},
        {"official_release_id": ""},
        {"source_reference": ""},
        {"company_associated": False},
    ):
        contacts = {"cnpj14": ACCOUNT_ID, "contacts": [{**contact, **mutation}]}
        lead = map_lead(universe, intel=intel, contacts_row=contacts, conn=None)
        assert lead is not None
        mapped = lead["contacts"][0]
        assert mapped["provenance_chain_valid"] is False, mutation
        assert mapped["root_source_type"] == "UNKNOWN", mutation
        assert mapped["controlled_email_eligible"] is False, mutation
        assert mapped["preferred_initial"] is False, mutation


def test_bridge_mapping_never_drops_known_route_suppression() -> None:
    universe, intel, _contacts = _five_class_universe_intel_contacts()
    contacts = {
        "cnpj14": ACCOUNT_ID,
        "contacts": [
            {
                "email": "contato@empresaexemplo.com.br",
                "source": "company_website",
                "source_type": "company_website",
                "source_url": "https://empresaexemplo.com.br/contato",
                "observed_at": "2026-08-24T12:00:00Z",
                "ownership_status": "COMPANY_OWNED",
                "channel_epistemic_class": "OBSERVED",
                "route_freshness": "FRESH",
                "route_suppression": "OPT_OUT",
            }
        ],
    }

    lead = map_lead(universe, intel=intel, contacts_row=contacts, conn=None)
    assert lead is not None
    contact = lead["contacts"][0]
    assert contact["route_suppression"] == "OPT_OUT"
    assert contact["controlled_email_eligible"] is False
    assert contact["preferred_initial"] is False
    assert "suppressed:OPT_OUT" in contact["reason_codes"]
