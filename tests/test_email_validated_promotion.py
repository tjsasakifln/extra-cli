"""Promotion policy tests call the shipped decide_promotion path."""

from __future__ import annotations

from scripts.decision_unit_intelligence.email_validated.policy import POLICY_VERSION, decide_promotion
from scripts.decision_unit_intelligence.email_validated.schema import AdjudicationRecord
from scripts.decision_unit_intelligence.models import (
    ActionMode,
    ChannelType,
    EpistemicClass,
    ReachabilityClass,
    ReachabilityRoute,
    RouteRelation,
)
from scripts.decision_unit_intelligence.projection import is_email_safe_for_warmbly


def _record(**overrides) -> AdjudicationRecord:
    base = {
        "case_id": "fixture",
        "account_id": "12345678000190",
        "company": "EMPRESA EXEMPLO ENGENHARIA LTDA",
        "person_name": "ANA SOUZA",
        "role": "Gerente",
        "email": "ana.souza@empresaexemplo.com.br",
        "epistemic": "OBSERVED",
        "source": "company_website",
        "source_date": "2026-08-01",
        "source_url": "https://empresaexemplo.com.br/equipe",
        "frozen_evidence": "E-mail de Ana Souza: ana.souza@empresaexemplo.com.br",
        "identity_association": "ASSOCIATED",
        "affiliation": "DEFENSIBLE",
        "technical_status": "NONE",
        "freshness": "FRESH",
        "human_verdict": "VALIDATED_DIRECT",
        "notes": "fixture",
        "policy_version": POLICY_VERSION,
        "gold_set_version": "email-validated-gold.v1",
        "split": "development",
        "suppression": "NONE",
        "engine": "fixture",
    }
    base.update(overrides)
    return AdjudicationRecord.from_dict(base)


def test_score_only_does_not_promote():
    decision = decide_promotion(
        _record(
            identity_association="NONE",
            affiliation="UNCLEAR",
            score=0.99,
            frozen_evidence="score-only overlay",
            human_verdict="GENERIC_ROLE",
        )
    )
    assert decision.promote is False
    assert decision.predicted_class != "EMAIL_VALIDATED"
    assert "SCORE_ALONE_INSUFFICIENT" in decision.reasons


def test_mx_dns_only_does_not_promote():
    decision = decide_promotion(
        _record(
            person_name=None,
            identity_association="NONE",
            affiliation="NONE",
            technical_status="MX_PRESENT",
            human_verdict="UNKNOWN",
        )
    )
    assert decision.promote is False
    assert decision.predicted_class != "EMAIL_VALIDATED"
    assert "MX_DNS_NOT_IDENTITY" in decision.reasons


def test_inferred_stays_inferred_and_does_not_promote():
    decision = decide_promotion(
        _record(
            epistemic="INFERRED",
            identity_association="NONE",
            email="joao.silva@empresaexemplo.com.br",
            person_name="JOAO SILVA",
            human_verdict="INFERRED_UNVERIFIED",
        )
    )
    assert decision.promote is False
    assert decision.predicted_class != "EMAIL_VALIDATED"
    assert decision.epistemic == "INFERRED"
    assert "INFERRED_CANNOT_BECOME_OBSERVED" in decision.reasons


def test_generic_and_role_do_not_promote():
    generic = decide_promotion(
        _record(email="contato@empresaexemplo.com.br", identity_association="NONE", human_verdict="GENERIC_ROLE")
    )
    role = decide_promotion(
        _record(email="licitacoes@empresaexemplo.com.br", identity_association="NONE", human_verdict="GENERIC_ROLE")
    )
    assert generic.promote is False
    assert role.promote is False
    assert "GENERIC_OR_ROLE_MAILBOX" in generic.reasons
    assert "GENERIC_OR_ROLE_MAILBOX" in role.reasons


def test_stale_does_not_promote():
    decision = decide_promotion(
        _record(freshness="STALE", source_date="2022-10-01", human_verdict="OBSERVED_BUT_STALE")
    )
    assert decision.promote is False
    assert "STALE" in decision.reasons


def test_suppression_does_not_promote():
    decision = decide_promotion(_record(suppression="DNC", human_verdict="GENERIC_ROLE"))
    assert decision.promote is False
    assert "SUPPRESSED" in decision.reasons


def test_missing_provenance_does_not_promote():
    decision = decide_promotion(
        _record(source_url=None, frozen_evidence=None, source_date=None, human_verdict="UNKNOWN")
    )
    assert decision.promote is False
    assert "MISSING_PROVENANCE" in decision.reasons


def test_wrong_person_features_do_not_promote():
    decision = decide_promotion(
        _record(
            email="setep@setep.com.br",
            person_name="JOSE ROBERTO DE SOUZA",
            identity_association="NONE",
            human_verdict="WRONG_PERSON",
        )
    )
    assert decision.promote is False
    assert decision.predicted_class != "EMAIL_VALIDATED"


def test_wrong_company_features_do_not_promote():
    decision = decide_promotion(
        _record(
            email="societario.sbs@fiscallcontabilidade.com.br",
            affiliation="THIRD_PARTY",
            identity_association="NONE",
            third_party_echo=True,
            human_verdict="WRONG_COMPANY",
        )
    )
    assert decision.promote is False
    assert "HOLDING_OR_THIRD_PARTY_AFFILIATION" in decision.reasons


def test_full_policy_pass_promotes_and_aligns_with_email_safe_route():
    record = _record()
    decision = decide_promotion(record)
    assert decision.promote is True
    assert decision.predicted_class == "EMAIL_VALIDATED"
    assert decision.epistemic == "OBSERVED"
    assert decision.policy_version == POLICY_VERSION
    route = ReachabilityRoute(
        route_id="r1",
        company_entity_id=record.account_id,
        channel_type=ChannelType.DIRECT_EMAIL,
        reachability_class=ReachabilityClass.R1_DIRECT,
        action_mode=ActionMode.HUMAN_REVIEW_EMAIL,
        decision_unit_candidate_id="cand-ana",
        channel_value=record.email,
        route_relation=RouteRelation.PERSON_OWNS_CHANNEL,
        epistemic_class=EpistemicClass.OBSERVED,
        reason_codes=[],
    )
    assert is_email_safe_for_warmbly(route) is True
