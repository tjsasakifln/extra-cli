"""Golden/adversarial reachability: first-class labels drive shipped classifier."""

from __future__ import annotations

from scripts.decision_unit_intelligence.benchmark import funnel
from scripts.decision_unit_intelligence.decision_policy import (
    SERVICE_REAJUSTE_14133,
    normalize_observed_role,
)
from scripts.decision_unit_intelligence.models import (
    ActionMode,
    ChannelObservation,
    ChannelType,
    ConfidenceLevel,
    DecisionRoleClass,
    DecisionUnitCandidate,
    EpistemicClass,
    FirstClassRouteKind,
    FirstClassRouteLabel,
    FreshnessState,
    PersonObservation,
    PersonRelation,
    ReachabilityClass,
    RouteRelation,
)
from scripts.decision_unit_intelligence.operator_pack import build_card
from scripts.decision_unit_intelligence.orchestrator import investigate_account
from scripts.decision_unit_intelligence.projection import project_warmbly_outreach
from scripts.decision_unit_intelligence.reachability import (
    classify_channel_observation,
    draft_to_route,
)
from scripts.decision_unit_intelligence.route_class import freshness_from_observed_at


def _person(name: str = "ANA CONTRATOS", role: str = "Gerente de Contratos") -> PersonObservation:
    return PersonObservation(
        observation_id=f"p-{name}",
        company_entity_id="12345678000190",
        person_name=name,
        observed_role=role,
        normalized_role_class=normalize_observed_role(role),
        relation=PersonRelation.COMPANY_MEMBER,
        source_type="process_document",
        document_id="doc-1",
        observed_at="2026-07-01",
        epistemic_class=EpistemicClass.OBSERVED,
        evidence_id=f"ev-{name}",
    )


def _candidate(name: str = "ANA CONTRATOS") -> DecisionUnitCandidate:
    return DecisionUnitCandidate(
        candidate_id="cand-ana",
        company_entity_id="12345678000190",
        person_id="person-ana",
        person_name=name,
        observed_roles=["Gerente de Contratos"],
        decision_role_class=DecisionRoleClass.GERENTE_CONTRATOS,
        relation=PersonRelation.COMPANY_MEMBER,
        suitability=ConfidenceLevel.MEDIUM,
    )


def _obs(
    value: str,
    *,
    snippet: str,
    ctype: ChannelType = ChannelType.COMPANY_SWITCHBOARD,
    extra: dict | None = None,
    observed_at: str | None = "2026-07-01",
    person: str | None = None,
) -> ChannelObservation:
    return ChannelObservation(
        observation_id=f"c-{value}",
        company_entity_id="12345678000190",
        channel_type=ctype,
        channel_value=value,
        person_name=person,
        source_type="company_site",
        source_url="https://empresa.example/contato",
        snippet=snippet,
        observed_at=observed_at,
        epistemic_class=EpistemicClass.OBSERVED,
        extra=extra or {"person_owns_phone": False},
    )


def _classify(obs: ChannelObservation, *, suitable: bool = True):
    return classify_channel_observation(
        obs,
        candidate=_candidate() if suitable else None,
        suitable_person=suitable,
    )


def _assert_not_personal(draft) -> None:
    assert draft.first_class_label != FirstClassRouteLabel.DIRECT_PERSON_PHONE
    assert draft.relation != RouteRelation.PERSON_OWNS_CHANNEL
    assert draft.extra.get("person_owns_phone") is not True


def test_matriz_phone_is_routed_call_never_personal():
    draft = _classify(_obs("4833331000", snippet="Telefone da matriz — sede em Florianópolis"))
    route = draft_to_route(draft, company_entity_id="12345678000190")
    assert route.first_class_label == FirstClassRouteLabel.ROUTES_TO_NAMED_PERSON
    assert route.first_class_kind == FirstClassRouteKind.ROUTED_CALL
    assert route.reachability_class == ReachabilityClass.R3_ROUTED_TO_NAMED_PERSON
    assert route.action_mode == ActionMode.MANUAL_ROUTED_CALL
    assert "HQ_MATRIX_PHONE" in route.reason_codes
    _assert_not_personal(draft)
    assert route.freshness != FreshnessState.UNKNOWN
    assert route.observed_at == "2026-07-01"
    assert route.source_type == "company_site"
    assert route.epistemic_class == EpistemicClass.OBSERVED
    assert route.suppression.value == "NONE"
    assert route.suitability == ConfidenceLevel.MEDIUM


def test_filial_phone_is_corporate_or_routed_never_personal():
    draft = _classify(_obs("4733332000", snippet="Filial de Blumenau — telefone da unidade"))
    assert draft.first_class_label in {
        FirstClassRouteLabel.ROUTES_TO_NAMED_PERSON,
        FirstClassRouteLabel.CORPORATE_PHONE,
    }
    assert draft.first_class_kind in {FirstClassRouteKind.ROUTED_CALL, FirstClassRouteKind.PHONE}
    assert "BRANCH_PHONE" in draft.reason_codes
    _assert_not_personal(draft)
    assert draft.first_class_label != FirstClassRouteLabel.PUBLIC_WHATSAPP


def test_accountant_phone_is_not_company_route_to_named_person():
    draft = _classify(_obs("4832220000", snippet="Escritório de contabilidade — CRC/SC do contador da empresa"))
    assert draft.first_class_label == FirstClassRouteLabel.CORPORATE_PHONE
    assert draft.first_class_kind == FirstClassRouteKind.PHONE
    assert draft.reachability == ReachabilityClass.R5_CORPORATE_ONLY
    assert draft.candidate_id is None
    assert "THIRD_PARTY_ACCOUNTANT_PHONE" in draft.reason_codes
    _assert_not_personal(draft)


def test_law_office_phone_is_not_decisor_phone():
    draft = _classify(_obs("4832110000", snippet="Escritório jurídico Advogados Associados OAB/SC 1234"))
    assert draft.first_class_label == FirstClassRouteLabel.CORPORATE_PHONE
    assert draft.reachability == ReachabilityClass.R5_CORPORATE_ONLY
    assert "THIRD_PARTY_LAW_OFFICE_PHONE" in draft.reason_codes
    _assert_not_personal(draft)
    assert draft.first_class_label != FirstClassRouteLabel.PUBLIC_WHATSAPP


def test_consortium_phone_stays_corporate():
    draft = _classify(_obs("6130001000", snippet="Telefone do consórcio SPE Obras Sul — não é da empresa membro"))
    assert draft.first_class_label == FirstClassRouteLabel.CORPORATE_PHONE
    assert "CONSORTIUM_PHONE" in draft.reason_codes
    _assert_not_personal(draft)


def test_stale_number_is_not_personal_and_freshness_stale():
    draft = _classify(
        _obs(
            "4831000000",
            snippet="Número antigo — telefone antigo, linha desativada",
            observed_at="2020-01-15",
        )
    )
    assert draft.freshness == FreshnessState.STALE
    assert "STALE_NUMBER_MARKED" in draft.reason_codes
    _assert_not_personal(draft)
    assert draft.first_class_label != FirstClassRouteLabel.PUBLIC_WHATSAPP


def test_unproven_whatsapp_is_never_public_whatsapp():
    draft = _classify(
        _obs(
            "48999990000",
            snippet="Celular publicado no rodapé sem menção ao aplicativo",
            ctype=ChannelType.PROFESSIONAL_WHATSAPP,
            extra={"person_owns_phone": False, "explicit_whatsapp": False},
        )
    )
    assert draft.first_class_label != FirstClassRouteLabel.PUBLIC_WHATSAPP
    assert draft.first_class_kind != FirstClassRouteKind.PUBLIC_WHATSAPP
    assert "WHATSAPP_NOT_EXPLICITLY_MARKED" in draft.reason_codes
    _assert_not_personal(draft)


def test_general_phone_plus_named_person_is_routed_call():
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO LTDA",
        service=SERVICE_REAJUSTE_14133,
        why_now="aditivo em janela de reajuste",
        people=[_person()],
        channels=[
            _obs("4833334444", snippet="Telefone geral / central de atendimento da empresa"),
        ],
        infer_email=False,
    )
    route = next(r for r in acc.routes if r.channel_value == "4833334444")
    assert route.first_class_label == FirstClassRouteLabel.ROUTES_TO_NAMED_PERSON
    assert route.first_class_kind == FirstClassRouteKind.ROUTED_CALL
    assert route.reachability_class == ReachabilityClass.R3_ROUTED_TO_NAMED_PERSON
    assert route.action_mode == ActionMode.MANUAL_ROUTED_CALL
    assert "GENERAL_COMPANY_PHONE" in route.reason_codes
    assert route.first_class_label != FirstClassRouteLabel.DIRECT_PERSON_PHONE
    assert "AUTO_SEND" not in route.reason_codes
    card = build_card(acc)
    assert card["who"] == "ANA CONTRATOS"
    assert card["why_now"] == "aditivo em janela de reajuste"
    assert card["offer"]
    assert card["decision_unit"]["person"] == "ANA CONTRATOS"
    assert card["route"]["label"] == "ROUTES_TO_NAMED_PERSON"
    assert card["route"]["kind"] == "ROUTED_CALL"
    assert card["confidence"]
    assert card["evidence"]
    warmbly = project_warmbly_outreach(acc)
    assert warmbly["auto_send"] is False
    labels = {item["first_class_label"] for item in warmbly["first_class_routes"]}
    assert "ROUTES_TO_NAMED_PERSON" in labels
    assert any(item["first_class_kind"] == "ROUTED_CALL" for item in warmbly["first_class_routes"])


def test_explicit_public_whatsapp_is_first_class_public_whatsapp():
    draft = _classify(
        _obs(
            "48988887777",
            snippet="Fale conosco no WhatsApp institucional: https://wa.me/5548988887777",
            ctype=ChannelType.PROFESSIONAL_WHATSAPP,
            extra={"explicit_whatsapp": True, "person_owns_phone": False},
        )
    )
    assert draft.first_class_label == FirstClassRouteLabel.PUBLIC_WHATSAPP
    assert draft.first_class_kind == FirstClassRouteKind.PUBLIC_WHATSAPP
    assert draft.reachability == ReachabilityClass.R3_ROUTED_TO_NAMED_PERSON
    assert draft.action == ActionMode.MANUAL_WHATSAPP
    assert draft.relation == RouteRelation.ROUTES_TO_NAMED_PERSON
    assert draft.first_class_label != FirstClassRouteLabel.DIRECT_PERSON_PHONE


def test_freshness_unknown_only_without_observed_at():
    assert (
        freshness_from_observed_at(
            "2026-07-01", now=__import__("datetime").datetime(2026, 8, 15, tzinfo=__import__("datetime").UTC)
        )
        == FreshnessState.FRESH
    )
    assert (
        freshness_from_observed_at(
            "2025-01-01", now=__import__("datetime").datetime(2026, 8, 15, tzinfo=__import__("datetime").UTC)
        )
        == FreshnessState.STALE
    )
    assert freshness_from_observed_at(None) == FreshnessState.UNKNOWN
    assert (
        freshness_from_observed_at(
            "2099-01-01T00:00:00Z",
            now=__import__("datetime").datetime(2026, 8, 15, tzinfo=__import__("datetime").UTC),
        )
        == FreshnessState.UNKNOWN
    )
    blank = _classify(_obs("4833330001", snippet="Telefone geral", observed_at=None))
    assert blank.freshness == FreshnessState.UNKNOWN
    dated = _classify(_obs("4833330002", snippet="Telefone geral", observed_at="2026-07-01"))
    assert dated.freshness != FreshnessState.UNKNOWN


def test_form_and_profile_are_first_class_and_funnel_has_denominator():
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO LTDA",
        service=SERVICE_REAJUSTE_14133,
        why_now="contrato ativo",
        people=[_person()],
        channels=[
            _obs(
                "https://empresa.example/contato#form",
                snippet="Formulário institucional de contato",
                ctype=ChannelType.CONTACT_FORM,
                extra={},
            ),
            _obs(
                "https://empresa.example/equipe/ana",
                snippet="Perfil institucional público da gerente",
                ctype=ChannelType.PROFESSIONAL_PROFILE,
                person="ANA CONTRATOS",
                extra={},
            ),
        ],
        infer_email=False,
    )
    labels = {route.first_class_label for route in acc.routes}
    kinds = {route.first_class_kind for route in acc.routes}
    assert FirstClassRouteLabel.FORM in labels
    assert FirstClassRouteLabel.PROFILE in labels
    assert FirstClassRouteKind.FORM in kinds
    assert FirstClassRouteKind.PROFILE in kinds
    assert FirstClassRouteLabel.DIRECT_PERSON_PHONE not in labels
    assert FirstClassRouteLabel.PUBLIC_WHATSAPP not in labels
    metrics = funnel([acc])
    assert metrics["denominator"]["explicit"] is True
    assert metrics["denominator"]["investigated_non_blocked"] == 1
    assert metrics["actionable_route_per_account"] == 1.0
    assert metrics["decision_unit_known_per_account"] == 1.0
    assert "unresolved_reason_distribution" in metrics
    assert "cost_latency_per_route_class" in metrics
    warmbly = project_warmbly_outreach(acc)
    assert warmbly["auto_send"] is False
    exported = {item["first_class_label"] for item in warmbly["first_class_routes"]}
    assert "FORM" in exported
    assert "PROFILE" in exported
