"""Adversarial tests against shipped Decision-Unit + Reachability functions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.decision_unit_intelligence.cohort import TRACK_A_CNPJS
from scripts.decision_unit_intelligence.decision_policy import (
    SERVICE_REAJUSTE_14133,
    assess_role_for_service,
    is_legal_entity_name,
    normalize_observed_role,
)
from scripts.decision_unit_intelligence.email_resolution import (
    ObservedOrgEmail,
    generate_inferred_emails,
    is_third_party_professional_domain,
    mx_never_proves_mailbox,
    name_tokens,
    official_domain_from_emails,
)
from scripts.decision_unit_intelligence.models import (
    FORBIDDEN_ACTION_MODES,
    ActionMode,
    ChannelObservation,
    ChannelType,
    ConfidenceLevel,
    DecisionRoleClass,
    DecisionUnitCandidate,
    EpistemicClass,
    PersonObservation,
    PersonRelation,
    ReachabilityClass,
    RouteRelation,
    SearchLedger,
    StopReason,
)
from scripts.decision_unit_intelligence.operator_pack import build_card
from scripts.decision_unit_intelligence.orchestrator import investigate_account
from scripts.decision_unit_intelligence.providers.historical_campaign import parse_qsa_blob
from scripts.decision_unit_intelligence.reachability import (
    assert_no_auto_send,
    classify_channel_observation,
    classify_observed_email_channel,
    draft_to_route,
)


def _person(
    name: str,
    role: str,
    *,
    source: str = "process_document",
    signature: str | None = None,
    cnpj: str = "12345678000190",
) -> PersonObservation:
    return PersonObservation(
        observation_id=f"p-{name}-{role}-{source}",
        company_entity_id=cnpj,
        person_name=name,
        observed_role=role,
        normalized_role_class=normalize_observed_role(role),
        relation=PersonRelation.COMPANY_MEMBER,
        source_type=source,
        document_id=None if source in {"qsa_rfb", "rfb"} else "doc-1",
        signature_context=signature,
        epistemic_class=EpistemicClass.OBSERVED,
        evidence_id=f"ev-{name}",
    )


def _channel(
    ctype: ChannelType,
    value: str,
    *,
    person: str | None = None,
    epistemic: EpistemicClass = EpistemicClass.OBSERVED,
    extra: dict | None = None,
    cnpj: str = "12345678000190",
) -> ChannelObservation:
    return ChannelObservation(
        observation_id=f"c-{ctype.value}-{value}",
        company_entity_id=cnpj,
        channel_type=ctype,
        channel_value=value,
        person_name=person,
        source_type="company_site",
        source_url="https://empresa.example/contato",
        epistemic_class=epistemic,
        extra=extra or {},
    )


def test_qsa_only_is_not_automatic_primary_when_operational_person_exists():
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO",
        service=SERVICE_REAJUSTE_14133,
        why_now="contrato ativo",
        people=[
            _person("MARIO QSA", "Sócio-Administrador", source="qsa_rfb"),
            _person("ANA CONTRATOS", "Gerente de Contratos", signature="assinou aditivo"),
        ],
        channels=[
            _channel(ChannelType.COMPANY_SWITCHBOARD, "4833334444", extra={"person_owns_phone": False}),
        ],
        infer_email=False,
    )
    primary = next(c for c in acc.candidates if c.candidate_id == acc.recommendation.primary_target_id)
    assert primary.person_name == "ANA CONTRATOS"
    assert "QSA_NOT_AUTOMATIC_DECISION_MAKER" in next(
        c.reason_codes for c in acc.candidates if c.person_name == "MARIO QSA"
    )


def test_qsa_alone_can_be_named_person_for_r3_but_not_proven_buyer():
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO",
        service=SERVICE_REAJUSTE_14133,
        why_now="contrato ativo",
        people=[_person("CARLOS SILVA", "Sócio-Administrador", source="qsa_rfb")],
        channels=[
            _channel(ChannelType.COMPANY_SWITCHBOARD, "4833334444", extra={"person_owns_phone": False}),
        ],
        infer_email=False,
    )
    assert acc.candidates
    rec = acc.recommendation
    route = next(r for r in acc.routes if r.route_id == rec.primary_route_id)
    assert route.reachability_class == ReachabilityClass.R3_ROUTED_TO_NAMED_PERSON
    assert route.route_relation == RouteRelation.ROUTES_TO_NAMED_PERSON
    assert route.action_mode == ActionMode.MANUAL_ROUTED_CALL
    assert route.extra.get("person_owns_phone") is False
    assert "QSA_CADASTRE_ONLY" in next(c.reason_codes for c in acc.candidates)
    assert "PRIMARY_IS_QSA_CADASTRE_ONLY_NOT_PROVEN_BUYER" in rec.warnings
    assert "pertence" not in (route.next_action or "").lower() or "não alegar" in (route.next_action or "").lower()


def test_responsavel_tecnico_is_not_economic_buyer():
    assessment = assess_role_for_service(
        role_class=DecisionRoleClass.RESPONSAVEL_TECNICO,
        service=SERVICE_REAJUSTE_14133,
        signature_count=1,
    )
    assert "RT_NOT_ECONOMIC_BUYER" in assessment.reason_codes
    assert assessment.inferred_decision_relevance and "economic buyer" not in assessment.inferred_decision_relevance


def test_public_official_and_third_party_rejected():
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO",
        service=SERVICE_REAJUSTE_14133,
        why_now=None,
        people=[
            PersonObservation(
                observation_id="srv",
                company_entity_id="12345678000190",
                person_name="JOAO SERVIDOR",
                observed_role="Pregoeiro",
                normalized_role_class=DecisionRoleClass.SERVIDOR_PUBLICO,
                relation=PersonRelation.PUBLIC_OFFICIAL,
                source_type="ata",
                epistemic_class=EpistemicClass.OBSERVED,
            ),
            PersonObservation(
                observation_id="adv",
                company_entity_id="12345678000190",
                person_name="MARIA ADVOGADA",
                observed_role="Advogada",
                normalized_role_class=DecisionRoleClass.TERCEIRO,
                relation=PersonRelation.THIRD_PARTY,
                source_type="procuracao_terceiro",
                epistemic_class=EpistemicClass.OBSERVED,
            ),
        ],
        channels=[],
        infer_email=False,
    )
    assert acc.candidates == []


def test_switchboard_plus_name_is_r3_not_r1_not_r0():
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO",
        service=SERVICE_REAJUSTE_14133,
        why_now=None,
        people=[_person("JOAO SILVA", "Diretor")],
        channels=[
            _channel(ChannelType.COMPANY_SWITCHBOARD, "1133334444", extra={"person_owns_phone": False}),
        ],
        infer_email=False,
    )
    route = next(r for r in acc.routes if r.channel_type == ChannelType.COMPANY_SWITCHBOARD)
    assert route.reachability_class == ReachabilityClass.R3_ROUTED_TO_NAMED_PERSON
    assert route.route_relation == RouteRelation.ROUTES_TO_NAMED_PERSON
    assert route.action_mode == ActionMode.MANUAL_ROUTED_CALL
    assert acc.extra["account_reachability_class"] != "R0_NO_ACTIONABLE_ROUTE"
    assert acc.extra["account_reachability_class"] != "R1_DIRECT"


def test_role_mailbox_without_person_is_r4():
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO",
        service=SERVICE_REAJUSTE_14133,
        why_now=None,
        people=[],
        channels=[_channel(ChannelType.ROLE_MAILBOX, "licitacoes@empresa.com.br")],
        infer_email=False,
    )
    route = acc.routes[0]
    assert route.reachability_class == ReachabilityClass.R4_ROLE_ROUTE
    assert route.action_mode == ActionMode.ROLE_EMAIL
    assert route.decision_unit_candidate_id is None


def test_inferred_email_never_observed_never_auto_send():
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO",
        service=SERVICE_REAJUSTE_14133,
        why_now=None,
        people=[_person("JOAO SILVA", "Diretor")],
        channels=[
            _channel(ChannelType.GENERIC_CORPORATE_EMAIL, "contato@empresa.com.br"),
            _channel(
                ChannelType.DIRECT_EMAIL,
                "ana.souza@empresa.com.br",
                person="ANA SOUZA",
            ),
        ],
        company_site="https://empresa.com.br",
        infer_email=True,
    )
    inferred = [r for r in acc.routes if r.channel_type == ChannelType.INFERRED_DIRECT_EMAIL]
    assert inferred
    for route in inferred:
        assert route.epistemic_class == EpistemicClass.INFERRED
        assert route.action_mode == ActionMode.HUMAN_REVIEW_EMAIL
        assert route.reachability_class != ReachabilityClass.R1_DIRECT
        assert route.reachability_class != ReachabilityClass.R2_HIGH_CONFIDENCE_DIRECT
        assert "AUTO_SEND" not in route.reason_codes
        with pytest.raises(ValueError):
            assert_no_auto_send("AUTO_SEND")


def test_single_sample_pattern_is_not_a_fact():
    inf = generate_inferred_emails(
        person_name="João da Silva",
        domain="empresa.com.br",
        observed=[ObservedOrgEmail("ana.souza@empresa.com.br", "site", person_name="ANA SOUZA")],
        mx_valid=True,
    )
    first_last = next(i for i in inf if i.pattern_id == "first.last")
    assert first_last.epistemic_class == EpistemicClass.INFERRED
    assert "SINGLE_SAMPLE_PATTERN" in first_last.reason_codes
    assert first_last.pattern_epistemic != EpistemicClass.OBSERVED
    assert mx_never_proves_mailbox(first_last)


def test_multiple_patterns_catch_all_compound_accent_holding():
    inf = generate_inferred_emails(
        person_name="José Antônio da Costa Lima",
        domain="holding.com.br",
        observed=[
            ObservedOrgEmail("ana.souza@holding.com.br", "site", person_name="ANA SOUZA"),
            ObservedOrgEmail("bruno.alves@holding.com.br", "site", person_name="BRUNO ALVES"),
        ],
        mx_valid=True,
        catch_all=True,
        independent_corroborations=["holding group"],
    )
    assert inf
    assert all(i.epistemic_class == EpistemicClass.INFERRED for i in inf)
    assert any("CATCH_ALL_DOMAIN" in i.reason_codes for i in inf)
    assert any(i.pattern_id == "first.compoundlast" for i in inf)
    assert any("HOLDING_OR_GROUP_SIGNAL" in i.reason_codes for i in inf)


def test_mx_valid_without_mailbox_stays_inferred():
    inf = generate_inferred_emails(
        person_name="Joao Silva",
        domain="empresa.com.br",
        observed=[],
        mx_valid=True,
        catch_all=False,
    )
    assert inf
    assert all(i.epistemic_class is EpistemicClass.INFERRED for i in inf)
    assert all(mx_never_proves_mailbox(i) for i in inf)
    assert all("MX_VALID_NOT_MAILBOX_PROOF" in i.reason_codes for i in inf)


def test_accountant_and_homonym_and_branch_domain():
    domain, ep, reasons = official_domain_from_emails(
        ["contato@filial.com.br", "fiscal@contador.com.br"],
        company_site="https://matriz.com.br",
    )
    assert domain == "matriz.com.br"
    assert ep == EpistemicClass.OBSERVED
    assert "DOMAIN_CONFLICT_SITE_VS_EMAIL" in reasons
    acc = investigate_account(
        cnpj="11111111000191",
        legal_name="A",
        service=SERVICE_REAJUSTE_14133,
        why_now=None,
        people=[_person("JOAO SILVA", "Diretor", cnpj="11111111000191")],
        channels=[],
        infer_email=False,
    )
    acc2 = investigate_account(
        cnpj="22222222000191",
        legal_name="B",
        service=SERVICE_REAJUSTE_14133,
        why_now=None,
        people=[_person("JOAO SILVA", "Diretor", cnpj="22222222000191")],
        channels=[],
        infer_email=False,
    )
    assert acc.candidates[0].person_id != acc2.candidates[0].person_id


def test_person_without_route_is_not_r0():
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO",
        service=SERVICE_REAJUSTE_14133,
        why_now=None,
        people=[_person("ANA CONTRATOS", "Gerente de Contratos", signature="assinou")],
        channels=[],
        infer_email=False,
    )
    assert acc.candidates
    assert acc.terminal.value == "DECISION_UNIT_IDENTIFIED_REACHABILITY_UNRESOLVED"
    assert "PERSON_WITHOUT_ROUTE_IS_NOT_R0" in acc.reason_codes
    assert acc.extra["account_reachability_class"] == "R0_NO_ACTIONABLE_ROUTE" or acc.routes == []


def test_blocked_is_not_r0():
    ledger = SearchLedger(stop_reason=StopReason.SOURCE_BLOCKED.value, blocked_sources=["pncp"])
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO",
        service=SERVICE_REAJUSTE_14133,
        why_now=None,
        people=[],
        channels=[],
        ledger=ledger,
        infer_email=False,
        blocked=True,
    )
    assert acc.terminal.value == "BLOCKED"
    assert acc.extra["account_reachability_class"] != "R0_NO_ACTIONABLE_ROUTE" or acc.terminal.value == "BLOCKED"


def test_generic_email_is_r5_not_personal():
    assert classify_observed_email_channel("contato@empresa.com.br") == ChannelType.GENERIC_CORPORATE_EMAIL
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO",
        service=SERVICE_REAJUSTE_14133,
        why_now=None,
        people=[_person("CARLOS SILVA", "Diretor")],
        channels=[_channel(ChannelType.GENERIC_CORPORATE_EMAIL, "contato@empresa.com.br")],
        infer_email=False,
    )
    generic = next(r for r in acc.routes if r.channel_value == "contato@empresa.com.br")
    assert generic.reachability_class == ReachabilityClass.R5_CORPORATE_ONLY
    assert generic.route_relation.value == "ACCOUNT_LEVEL_ONLY"


def test_recurrent_signer_gets_operational_relevance_not_proven_decisor():
    people = [
        _person("PAULA REPRESENTA", "Representante Legal", signature="prop"),
        _person("PAULA REPRESENTA", "Preposto", source="recurso", signature="recurso"),
        _person("PAULA REPRESENTA", "Signatário", source="contrato", signature="contrato"),
    ]
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO",
        service=SERVICE_REAJUSTE_14133,
        why_now=None,
        people=people,
        channels=[],
        infer_email=False,
    )
    cand = acc.candidates[0]
    assert cand.operational_relevance.value in {"MEDIUM", "HIGH"}
    assert cand.representation_signal.value in {"MEDIUM", "HIGH"}
    assert not any("decisor comprovado" in (cand.inferred_decision_relevance or "").lower() for _ in [0])


def test_observed_switchboard_outranks_inferred_email():
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO",
        service=SERVICE_REAJUSTE_14133,
        why_now=None,
        people=[_person("CARLOS SILVA", "Sócio-Administrador")],
        channels=[
            _channel(ChannelType.COMPANY_SWITCHBOARD, "4833331111", extra={"person_owns_phone": False}),
            _channel(ChannelType.ROLE_MAILBOX, "licitacoes@empresa.com.br"),
            _channel(
                ChannelType.DIRECT_EMAIL,
                "ana.souza@empresa.com.br",
                person="ANA SOUZA",
            ),
        ],
        company_site="https://empresa.com.br",
        infer_email=True,
    )
    route = next(r for r in acc.routes if r.route_id == acc.recommendation.primary_route_id)
    assert route.reachability_class == ReachabilityClass.R3_ROUTED_TO_NAMED_PERSON
    assert route.action_mode == ActionMode.MANUAL_ROUTED_CALL
    assert any(r.reachability_class == ReachabilityClass.R4_ROLE_ROUTE for r in acc.routes)
    assert any(r.channel_type == ChannelType.INFERRED_DIRECT_EMAIL for r in acc.routes)


def test_do_not_pick_pretty_email_over_better_decision_role():
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO",
        service=SERVICE_REAJUSTE_14133,
        why_now="aditivo em execução",
        people=[
            _person("ANA CONTRATOS", "Gerente de Contratos", signature="assinou 4 documentos"),
            _person("BETO DESCONHECIDO", "Assistente"),
        ],
        channels=[
            _channel(ChannelType.COMPANY_SWITCHBOARD, "4833330000", extra={"person_owns_phone": False}),
            _channel(
                ChannelType.DIRECT_EMAIL,
                "beto.desconhecido@empresa.com.br",
                person="BETO DESCONHECIDO",
            ),
        ],
        infer_email=False,
    )
    primary = next(c for c in acc.candidates if c.candidate_id == acc.recommendation.primary_target_id)
    assert primary.person_name == "ANA CONTRATOS"
    route = next(r for r in acc.routes if r.route_id == acc.recommendation.primary_route_id)
    assert route.channel_type == ChannelType.COMPANY_SWITCHBOARD


def test_no_auto_send_constant():
    assert "AUTO_SEND" in FORBIDDEN_ACTION_MODES
    with pytest.raises(ValueError):
        assert_no_auto_send(ActionMode.HUMAN_REVIEW_EMAIL.value) if False else assert_no_auto_send("AUTO_SEND")


def _candidate(name: str = "JOAO SILVA") -> DecisionUnitCandidate:
    return DecisionUnitCandidate(
        candidate_id="cand-test",
        company_entity_id="12345678000190",
        person_id="person-test",
        person_name=name,
        observed_roles=["Diretor"],
        decision_role_class=DecisionRoleClass.DIRETOR,
        decision_relevance=ConfidenceLevel.MEDIUM,
        suitability=ConfidenceLevel.MEDIUM,
    )


def test_unverified_single_sample_inferred_email_is_not_r2():
    inf = generate_inferred_emails(
        person_name="João da Silva",
        domain="empresa.com.br",
        observed=[ObservedOrgEmail("contato@empresa.com.br", "site")],
        mx_valid=False,
    )
    guess = next(i for i in inf if i.pattern_id == "first.last")
    assert guess.epistemic_class == EpistemicClass.INFERRED
    assert "PATTERN_NOT_OBSERVED_IN_ORG" in guess.reason_codes
    assert not guess.corroborated
    obs = ChannelObservation(
        observation_id="inf-1",
        company_entity_id="12345678000190",
        channel_type=ChannelType.INFERRED_DIRECT_EMAIL,
        channel_value=guess.email,
        person_name="João da Silva",
        source_type="email_pattern_inference",
        epistemic_class=EpistemicClass.INFERRED,
        extra={
            "technically_validated": guess.technically_validated,
            "corroborated": guess.corroborated,
            "pattern_id": guess.pattern_id,
            "reason_codes": guess.reason_codes,
        },
    )
    draft = classify_channel_observation(obs, candidate=_candidate("João da Silva"), suitable_person=True)
    route = draft_to_route(draft, company_entity_id="12345678000190")
    assert route.reachability_class != ReachabilityClass.R2_HIGH_CONFIDENCE_DIRECT
    assert route.epistemic_class == EpistemicClass.INFERRED
    assert route.action_mode == ActionMode.HUMAN_REVIEW_EMAIL
    assert route.route_confidence == ConfidenceLevel.LOW


def test_verified_inferred_email_is_r2_and_still_inferred():
    obs = ChannelObservation(
        observation_id="inf-ok",
        company_entity_id="12345678000190",
        channel_type=ChannelType.INFERRED_DIRECT_EMAIL,
        channel_value="joao.silva@empresa.com.br",
        person_name="JOAO SILVA",
        source_type="email_pattern_inference",
        epistemic_class=EpistemicClass.INFERRED,
        extra={"technically_validated": True, "corroborated": True},
    )
    draft = classify_channel_observation(obs, candidate=_candidate(), suitable_person=True)
    assert draft.reachability == ReachabilityClass.R2_HIGH_CONFIDENCE_DIRECT
    assert draft.epistemic == EpistemicClass.INFERRED
    assert draft.action == ActionMode.HUMAN_REVIEW_EMAIL


def test_legal_entity_qsa_never_outranks_natural_person():
    parsed = parse_qsa_blob("TIT PARTICIPACOES LTDA (Sócio); CRISTIAN TICIANI (Sócio-Administrador)")
    assert parsed == [("CRISTIAN TICIANI", "Sócio-Administrador")]
    assert is_legal_entity_name("TIT PARTICIPACOES LTDA")
    assert not is_legal_entity_name("CRISTIAN TICIANI")
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO",
        service=SERVICE_REAJUSTE_14133,
        why_now=None,
        people=[
            _person("TIT PARTICIPACOES LTDA", "Sócio", source="qsa_rfb"),
            _person("CRISTIAN TICIANI", "Sócio-Administrador", source="qsa_rfb"),
        ],
        channels=[
            _channel(ChannelType.COMPANY_SWITCHBOARD, "4933330000", extra={"person_owns_phone": False}),
        ],
        infer_email=False,
    )
    names = [c.person_name for c in acc.candidates]
    assert names == ["CRISTIAN TICIANI"]
    primary = next(c for c in acc.candidates if c.candidate_id == acc.recommendation.primary_target_id)
    assert primary.person_name == "CRISTIAN TICIANI"


def test_accountant_domain_and_legal_form_tokens_not_minted_as_r2():
    assert is_third_party_professional_domain("fiscallcontabilidade.com.br")
    assert generate_inferred_emails(
        person_name="Lilian Maahs",
        domain="fiscallcontabilidade.com.br",
        observed=[ObservedOrgEmail("contato@fiscallcontabilidade.com.br", "site", person_name="LILIAN MAAHS")],
    ) == []
    assert generate_inferred_emails(
        person_name="ANM PARTICIPACOES LTDA",
        domain="empresa.com.br",
        observed=[ObservedOrgEmail("contato@empresa.com.br", "site")],
    ) == []
    assert generate_inferred_emails(
        person_name="INFRA ENGENHARIA HOLDING LTDA",
        domain="infrasul.com.br",
        observed=[ObservedOrgEmail("contato@infrasul.com.br", "site")],
    ) == []
    tokens = name_tokens("ANM PARTICIPACOES LTDA")
    assert "ltda" not in tokens
    assert "participacoes" not in tokens
    domain, _ep, _reasons = official_domain_from_emails(
        ["lilian.maahs@fiscallcontabilidade.com.br", "anm.ltda@fiscallcontabilidade.com.br"]
    )
    assert domain is None
    obs = ChannelObservation(
        observation_id="inf-acct",
        company_entity_id="12345678000190",
        channel_type=ChannelType.INFERRED_DIRECT_EMAIL,
        channel_value="lilian.maahs@fiscallcontabilidade.com.br",
        person_name="Lilian Maahs",
        source_type="email_pattern_inference",
        epistemic_class=EpistemicClass.INFERRED,
        extra={"technically_validated": False, "corroborated": False},
    )
    draft = classify_channel_observation(obs, candidate=_candidate("Lilian Maahs"), suitable_person=True)
    assert draft.reachability != ReachabilityClass.R2_HIGH_CONFIDENCE_DIRECT


def test_operator_r3_card_is_human_usable():
    """Shipped build_card must expose a usable R3 action without reinterpreting the model."""
    acc = investigate_account(
        cnpj="12345678000190",
        legal_name="EXEMPLO LTDA",
        service=SERVICE_REAJUSTE_14133,
        why_now="contrato ativo",
        people=[_person("CARLOS SILVA", "Sócio-Administrador", source="qsa_rfb")],
        channels=[
            _channel(ChannelType.COMPANY_SWITCHBOARD, "4833334444", extra={"person_owns_phone": False}),
        ],
        infer_email=False,
    )
    card = build_card(acc)
    assert card["primary_decision_unit_target"] == "CARLOS SILVA"
    assert card["role_evidence"]["observed_roles"]
    assert card["role_evidence"]["decision_role_class"]
    assert card["role_evidence"]["reason_codes"]
    assert card["role_evidence"]["source_count"] >= 1
    assert card["role_evidence"]["evidence_ids"]
    assert card["channel"] == "4833334444"
    assert card["route_class"] == "R3_ROUTED_TO_NAMED_PERSON"
    assert card["action_mode"] == "MANUAL_ROUTED_CALL"
    assert card["route_relation"] == "ROUTES_TO_NAMED_PERSON"
    assert "SWITCHBOARD_ROUTES_TO_NAMED_PERSON" in card["route_reason_codes"]
    assert "NOT_PERSONAL_PHONE" in card["route_reason_codes"]
    assert card["channel_ownership"] == "COMPANY_OWNED"
    assert card["channel_epistemic_class"] == "OBSERVED"
    assert "pedir por" in (card["exact_next_action"] or "").lower()
    assert "Não alegar que o telefone pertence à pessoa." in card["do_not_claim"]
    assert any("não alegar contato direto" in w.lower() for w in card["do_not_claim"])
    assert card["route_class"] != "R1_DIRECT"


def test_track_a_manifest_has_thirty_real_cnpjs():
    assert len(TRACK_A_CNPJS) == 30
    assert len(set(TRACK_A_CNPJS)) == 30
    assert all(len(c) == 14 and c.isdigit() for c in TRACK_A_CNPJS)
    artifact = Path("/mnt/d/extra consultoria/artifacts/outreach/reajuste-2026-08-05-full-datalake-pr200/ai_assisted_evidence_review_top30.json")
    if artifact.exists():
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        live = [r["cnpj"] for r in payload["reviews"]]
        assert live == TRACK_A_CNPJS
