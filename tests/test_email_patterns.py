"""Shipped ingest→derive→score→emit→verify path for corporate email patterns."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.decision_unit_intelligence.email_discovery import (
    EmailDiscoveryClass,
    classify_email_discovery,
)
from scripts.decision_unit_intelligence.email_patterns.engine import (
    InjectedTechnicalAdapter,
    assert_pattern_not_promoted_to_observed,
    candidate_to_evidence,
    ingest_observed_person_emails,
    run_email_patterns,
)
from scripts.decision_unit_intelligence.email_patterns.fixtures import (
    DOMAIN,
    all_fixtures,
    fixture_catchall,
    fixture_homonym,
    fixture_observed_alias,
    fixture_particles,
    fixture_single_example,
    fixture_three_first_last,
    fixture_two_competing_patterns,
    fixture_wrong_domain,
)
from scripts.decision_unit_intelligence.email_patterns.types import (
    InferredGrade,
    InferredPatternState,
    KnownPerson,
    ObservedPersonEmail,
    PatternState,
)
from scripts.decision_unit_intelligence.evidence import assert_not_promoted_to_observed
from scripts.decision_unit_intelligence.models import (
    ChannelObservation,
    ChannelType,
    EpistemicClass,
    PersonObservation,
    PersonRelation,
    ReachabilityClass,
    ReachabilityRoute,
    RouteRelation,
)
from scripts.decision_unit_intelligence.orchestrator import investigate_account
from scripts.decision_unit_intelligence.projection import is_email_safe_for_warmbly, project_warmbly_outreach


def _run(case: dict) -> object:
    return run_email_patterns(
        observed=case["observed"],
        known_people=case["known_people"],
        domain=case.get("domain"),
        technical=case.get("technical"),
    )


def test_ingest_keeps_only_observed_same_domain_person_emails():
    case = fixture_wrong_domain()
    ingested, exclusions = ingest_observed_person_emails(case["observed"], domain=DOMAIN)
    emails = [item.email for item in ingested]
    assert "pedro.lima@outrodominio.com.br" not in emails
    assert any(item.startswith("WRONG_DOMAIN:") for item in exclusions)
    inferred_raw = ObservedPersonEmail(
        email="inventado@empresaexemplo.com.br",
        person_name="Inventado",
        domain=DOMAIN,
        epistemic_class=EpistemicClass.INFERRED,
    )
    _, more = ingest_observed_person_emails([inferred_raw], domain=DOMAIN)
    assert any(item.startswith("NOT_OBSERVED:") for item in more)


def test_three_first_last_is_pattern_strong_with_provenance():
    result = _run(fixture_three_first_last())
    assert result.ingested
    assert all(item.epistemic_class == EpistemicClass.OBSERVED for item in result.ingested)
    record = next(item for item in result.patterns if item.pattern_id == "first.last")
    assert record.state == PatternState.PATTERN_STRONG
    assert record.independent_example_count == 3
    assert record.supporting_emails
    assert record.supporting_people
    assert record.source_urls
    assert record.observed_at
    assert record.domain == DOMAIN
    assert record.epistemic_class != EpistemicClass.OBSERVED
    assert "PATTERN_NOT_A_PERSON_FACT" in record.reason_codes
    assert result.candidates
    candidate = result.candidates[0]
    assert candidate.email == "joao.silva@empresaexemplo.com.br"
    assert candidate.epistemic_class == EpistemicClass.INFERRED
    assert candidate.inferred_grade == InferredGrade.INFERRED_HIGH
    assert candidate.candidate_state == InferredPatternState.INFERRED_PATTERN_MX_OK


def test_single_example_is_not_high_certainty():
    result = _run(fixture_single_example())
    record = next(item for item in result.patterns if item.pattern_id == "first.last")
    assert record.state != PatternState.PATTERN_STRONG
    assert record.state == PatternState.PATTERN_OBSERVED
    assert "SINGLE_SAMPLE_PATTERN" in record.reason_codes
    assert all(item.inferred_grade != InferredGrade.INFERRED_HIGH for item in result.candidates)
    assert all(item.epistemic_class == EpistemicClass.INFERRED for item in result.candidates)


def test_two_competing_patterns_are_ambiguous():
    result = _run(fixture_two_competing_patterns())
    states = {item.pattern_id: item.state for item in result.patterns}
    assert states["first.last"] == PatternState.PATTERN_AMBIGUOUS
    assert states["firstlast"] == PatternState.PATTERN_AMBIGUOUS
    assert result.candidates == ()


def test_brazilian_particles_normalize_to_observed_pattern():
    result = _run(fixture_particles())
    record = next(item for item in result.patterns if item.pattern_id == "first.last")
    assert record.state == PatternState.PATTERN_STRONG
    emails = {item.email for item in result.candidates}
    assert "jose.lima@empresaexemplo.com.br" in emails
    assert not any("da." in item.email or "de." in item.email for item in result.candidates)


def test_observed_alias_is_recorded_and_not_blindly_applied():
    result = _run(fixture_observed_alias())
    alias = next(item for item in result.patterns if item.pattern_id == "alias")
    assert "ze.silva@empresaexemplo.com.br" in alias.supporting_emails
    maria = next(item for item in result.candidates if item.person_name and item.person_name.startswith("Maria"))
    assert maria.email == "maria.oliveira@empresaexemplo.com.br"
    assert not any(item.email.startswith("ze.") and "oliveira" in item.email for item in result.candidates)
    jose = [item for item in result.candidates if item.person_name and item.person_name.startswith("José")]
    assert jose
    assert any(item.pattern_id == "first.last" for item in jose)
    # alias may be emitted for José only because ze was actually observed
    assert all(item.email != "ze.oliveira@empresaexemplo.com.br" for item in result.candidates)


def test_wrong_domain_example_is_excluded():
    result = _run(fixture_wrong_domain())
    ingested_emails = {item.email for item in result.ingested}
    assert "pedro.lima@outrodominio.com.br" not in ingested_emails
    assert any("WRONG_DOMAIN:pedro.lima@outrodominio.com.br" in item for item in result.exclusions)
    record = next(item for item in result.patterns if item.pattern_id == "first.last")
    assert record.state == PatternState.PATTERN_STRONG
    assert all(item.endswith(f"@{DOMAIN}") for item in record.supporting_emails)


def test_homonym_is_not_auto_assigned():
    result = _run(fixture_homonym())
    assert result.candidates == ()
    assert (
        all(item.domain != "empresa-b.com.br" or not item.supporting_emails for item in result.patterns)
        or not result.patterns
    )


def test_uncorroborated_or_unknown_person_gets_zero_candidates():
    case = fixture_three_first_last()
    result = run_email_patterns(
        observed=case["observed"],
        known_people=[KnownPerson("Fantasma Nulo", corroborated=False)],
        domain=DOMAIN,
        technical=case["technical"],
    )
    assert result.candidates == ()
    empty = run_email_patterns(
        observed=case["observed"],
        known_people=[],
        domain=DOMAIN,
        technical=case["technical"],
    )
    assert empty.candidates == ()


def test_no_blind_combinatorics_and_budget():
    case = fixture_three_first_last()
    result = _run(case)
    assert {item.pattern_id for item in result.candidates} <= {"first.last"}
    assert all(item.pattern_id != "firstlast" for item in result.candidates)
    by_person: dict[str, int] = {}
    for item in result.candidates:
        by_person[item.person_name] = by_person.get(item.person_name, 0) + 1
    assert all(count <= 2 for count in by_person.values())


def test_pattern_never_promoted_to_observed():
    result = _run(fixture_three_first_last())
    for record in result.patterns:
        assert record.epistemic_class != EpistemicClass.OBSERVED
        assert_pattern_not_promoted_to_observed(record.epistemic_class, "org-email-pattern.v1")
    for candidate in result.candidates:
        assert candidate.epistemic_class == EpistemicClass.INFERRED
        evidence = candidate_to_evidence(candidate)
        assert evidence.epistemic_class == EpistemicClass.INFERRED
        assert_not_promoted_to_observed(evidence)
        with pytest.raises(ValueError, match="OBSERVED"):
            assert_pattern_not_promoted_to_observed(EpistemicClass.OBSERVED, "org-email-pattern.v1")


def test_catch_all_is_not_inferred_high():
    result = _run(fixture_catchall())
    assert result.candidates
    for candidate in result.candidates:
        assert candidate.candidate_state == InferredPatternState.INFERRED_PATTERN_CATCH_ALL
        assert candidate.inferred_grade == InferredGrade.INFERRED_UNVERIFIED
        assert candidate.discovery_class == InferredPatternState.INFERRED_PATTERN_CATCH_ALL.value


def test_technical_mx_ok_reason_and_rejected():
    case = fixture_three_first_last()
    ok = _run(case)
    assert ok.candidates[0].candidate_state == InferredPatternState.INFERRED_PATTERN_MX_OK
    assert ok.candidates[0].mx_is_not_mailbox_proof is True
    assert "MX_PRESENT_NOT_MAILBOX_PROOF" in ok.candidates[0].reason_codes
    rejected = run_email_patterns(
        observed=case["observed"],
        known_people=case["known_people"],
        domain=DOMAIN,
        technical=InjectedTechnicalAdapter(
            mx_by_domain={DOMAIN: "MISSING"},
            catch_all_by_domain={DOMAIN: "UNKNOWN_NOT_PROBED"},
        ),
    )
    assert rejected.candidates[0].candidate_state == InferredPatternState.INFERRED_PATTERN_REJECTED


def test_smtp_only_when_policy_authorizes_and_stays_inferred():
    from scripts.decision_unit_intelligence.email_patterns.types import EmailPatternPolicy

    case = fixture_three_first_last()
    skipped = _run(case)
    assert skipped.candidates[0].technical is not None
    assert skipped.candidates[0].technical.smtp == "SKIPPED_POLICY"
    authorized = run_email_patterns(
        observed=case["observed"],
        known_people=case["known_people"],
        domain=DOMAIN,
        policy=EmailPatternPolicy(smtp_authorized=True),
        technical=InjectedTechnicalAdapter(
            mx_by_domain={DOMAIN: "MX_PRESENT"},
            catch_all_by_domain={DOMAIN: "UNKNOWN_NOT_PROBED"},
            smtp_by_email={"joao.silva@empresaexemplo.com.br": "ACCEPTED"},
        ),
    )
    assert authorized.candidates[0].technical.smtp == "ACCEPTED"
    assert authorized.candidates[0].epistemic_class == EpistemicClass.INFERRED
    assert "SMTP_ACCEPT_STILL_INFERRED" in authorized.candidates[0].reason_codes
    assert authorized.candidates[0].epistemic_class != EpistemicClass.OBSERVED


def _inferred_route(state: str) -> ReachabilityRoute:
    return ReachabilityRoute(
        route_id="r-inf",
        company_entity_id="12345678000190",
        channel_type=ChannelType.INFERRED_DIRECT_EMAIL,
        reachability_class=ReachabilityClass.INFERRED_UNVERIFIED,
        action_mode=__import__(
            "scripts.decision_unit_intelligence.models", fromlist=["ActionMode"]
        ).ActionMode.HUMAN_REVIEW_EMAIL,
        decision_unit_candidate_id="cand-1",
        channel_value="joao.silva@empresaexemplo.com.br",
        route_relation=RouteRelation.INFERRED_ASSOCIATION,
        epistemic_class=EpistemicClass.INFERRED,
        extra={
            "email_discovery_class": state,
            "inferred_pattern_state": state,
            "inferred_grade": "INFERRED_HIGH",
        },
    )


def test_warmbly_fail_closed_for_all_inferred_pattern_states():
    from scripts.decision_unit_intelligence.models import (
        AccountInvestigation,
        ActionMode,
        DecisionUnitCandidate,
        Recommendation,
    )

    person = DecisionUnitCandidate(
        candidate_id="cand-1",
        company_entity_id="12345678000190",
        person_id="p-1",
        person_name="João da Silva",
    )
    for state in (
        EmailDiscoveryClass.INFERRED_PATTERN_EMAIL.value,
        EmailDiscoveryClass.INFERRED_PATTERN_MX_OK.value,
        EmailDiscoveryClass.INFERRED_PATTERN_CATCH_ALL.value,
        EmailDiscoveryClass.INFERRED_PATTERN_REJECTED.value,
    ):
        route = _inferred_route(state)
        assert is_email_safe_for_warmbly(route) is False
        klass = classify_email_discovery(
            route.channel_value,
            epistemic=EpistemicClass.INFERRED,
            inferred_pattern=True,
            inferred_pattern_state=state,
            email_safe_policy=True,
            mx_present=True,
        )
        assert klass.value.startswith("INFERRED_PATTERN_")
        assert klass != EmailDiscoveryClass.EMAIL_VALIDATED
        account = AccountInvestigation(
            company_entity_id="12345678000190",
            cnpj="12345678000190",
            legal_name="EMPRESA EXEMPLO",
            service_context="reajuste_14133",
            why_now=None,
            candidates=[person],
            routes=[route],
            recommendation=Recommendation(
                primary_target_id=person.candidate_id,
                primary_route_id=route.route_id,
                action_mode=ActionMode.HUMAN_REVIEW_EMAIL,
            ),
        )
        payload = project_warmbly_outreach(account)
        assert payload["auto_send"] is False
        assert payload["email_safe_count"] == 0
        assert payload["recipient_candidates"] == []
        discovery = payload["email_discovery_routes"][0]
        assert discovery["contact_tier"] not in {"EMAIL_VALIDATED", "DIRECT_EMAIL_VALIDATED"}
        assert discovery["contact_tier"] == "CANDIDATE_UNVERIFIED"


def test_orchestrator_inferred_route_is_not_warmbly_validated():
    people = [
        PersonObservation(
            observation_id="p-ana",
            company_entity_id="12345678000190",
            person_name="ANA SOUZA",
            observed_role="Gerente",
            relation=PersonRelation.COMPANY_MEMBER,
            source_type="company_website",
            epistemic_class=EpistemicClass.OBSERVED,
        ),
        PersonObservation(
            observation_id="p-joao",
            company_entity_id="12345678000190",
            person_name="JOAO SILVA",
            observed_role="Diretor",
            relation=PersonRelation.COMPANY_MEMBER,
            source_type="company_website",
            epistemic_class=EpistemicClass.OBSERVED,
        ),
        PersonObservation(
            observation_id="p-bruno",
            company_entity_id="12345678000190",
            person_name="BRUNO ALVES",
            observed_role="Engenheiro",
            relation=PersonRelation.COMPANY_MEMBER,
            source_type="company_website",
            epistemic_class=EpistemicClass.OBSERVED,
        ),
        PersonObservation(
            observation_id="p-carla",
            company_entity_id="12345678000190",
            person_name="CARLA MENDES",
            observed_role="Coordenadora",
            relation=PersonRelation.COMPANY_MEMBER,
            source_type="company_website",
            epistemic_class=EpistemicClass.OBSERVED,
        ),
    ]
    channels = [
        ChannelObservation(
            observation_id="e-ana",
            company_entity_id="12345678000190",
            channel_type=ChannelType.DIRECT_EMAIL,
            channel_value="ana.souza@empresaexemplo.com.br",
            person_name="ANA SOUZA",
            source_type="company_website",
            source_url="https://empresaexemplo.com.br/equipe",
            epistemic_class=EpistemicClass.OBSERVED,
            extra={"identity_explicitly_associated": True},
        ),
        ChannelObservation(
            observation_id="e-bruno",
            company_entity_id="12345678000190",
            channel_type=ChannelType.DIRECT_EMAIL,
            channel_value="bruno.alves@empresaexemplo.com.br",
            person_name="BRUNO ALVES",
            source_type="company_website",
            source_url="https://empresaexemplo.com.br/equipe",
            epistemic_class=EpistemicClass.OBSERVED,
            extra={"identity_explicitly_associated": True},
        ),
        ChannelObservation(
            observation_id="e-carla",
            company_entity_id="12345678000190",
            channel_type=ChannelType.DIRECT_EMAIL,
            channel_value="carla.mendes@empresaexemplo.com.br",
            person_name="CARLA MENDES",
            source_type="company_website",
            source_url="https://empresaexemplo.com.br/equipe",
            epistemic_class=EpistemicClass.OBSERVED,
            extra={"identity_explicitly_associated": True},
        ),
    ]
    account = investigate_account(
        cnpj="12345678000190",
        legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA",
        service="reajuste_14133",
        why_now="contrato ativo",
        people=people,
        channels=channels,
        company_site="https://empresaexemplo.com.br",
        infer_email=True,
        mx_valid=True,
    )
    inferred = [route for route in account.routes if route.channel_type == ChannelType.INFERRED_DIRECT_EMAIL]
    assert inferred
    assert all(route.epistemic_class == EpistemicClass.INFERRED for route in inferred)
    assert all(not is_email_safe_for_warmbly(route) for route in inferred)
    payload = project_warmbly_outreach(account)
    assert payload["auto_send"] is False
    for item in payload["email_discovery_routes"]:
        if str(item["email_discovery_class"]).startswith("INFERRED_PATTERN_"):
            assert item["contact_tier"] == "CANDIDATE_UNVERIFIED"


def test_all_named_fixtures_are_wired():
    names = {case["name"] for case in all_fixtures()}
    assert names == {
        "three_first_last_strong",
        "single_example_not_high",
        "two_patterns_ambiguous",
        "brazilian_particles",
        "observed_alias",
        "catch_all_domain",
        "wrong_domain_excluded",
        "homonym_not_auto_assigned",
    }


def test_track_a_canary_has_zero_invented_person_emails():
    from scripts.decision_unit_intelligence.email_patterns.cli import (
        load_track_a_cases,
        run_fixture_case,
        summarize_results,
    )
    from scripts.decision_unit_intelligence.email_patterns.engine import run_email_patterns
    from scripts.decision_unit_intelligence.email_patterns.fixtures import audit_corpus_30

    path = Path("scripts/decision_unit_intelligence/data/track_a_30.observations.json")
    cases = load_track_a_cases(path)
    assert len(cases) == 30
    results = []
    for case in cases:
        if not case["domain"]:
            continue
        results.append(
            run_email_patterns(
                observed=case["observed"],
                known_people=case["known_people"],
                domain=case["domain"],
            )
        )
    metrics = summarize_results(results, persons_eligible=sum(len(case["known_people"]) for case in cases))
    assert metrics["candidates"] == 0
    assert metrics["incremental_reachable_rate"] == 0.0
    audit = run_fixture_case(audit_corpus_30())
    assert len(audit.candidates) == 30
    assert all(item.epistemic_class == EpistemicClass.INFERRED for item in audit.candidates)
    assert all(item.epistemic_class != EpistemicClass.OBSERVED for item in audit.patterns)


def test_cli_run_is_deterministic(tmp_path: Path):
    from scripts.decision_unit_intelligence.email_patterns.cli import main

    payload = {
        "domain": DOMAIN,
        "observed": [
            {
                "email": "ana.souza@empresaexemplo.com.br",
                "person_name": "Ana Souza",
                "domain": DOMAIN,
                "source_url": "https://empresaexemplo.com.br/equipe",
                "observed_at": "2026-06-01T12:00:00Z",
                "epistemic_class": "OBSERVED",
            },
            {
                "email": "bruno.alves@empresaexemplo.com.br",
                "person_name": "Bruno Alves",
                "domain": DOMAIN,
                "source_url": "https://empresaexemplo.com.br/equipe",
                "observed_at": "2026-06-01T12:00:00Z",
                "epistemic_class": "OBSERVED",
            },
            {
                "email": "carla.mendes@empresaexemplo.com.br",
                "person_name": "Carla Mendes",
                "domain": DOMAIN,
                "source_url": "https://empresaexemplo.com.br/equipe",
                "observed_at": "2026-06-01T12:00:00Z",
                "epistemic_class": "OBSERVED",
            },
        ],
        "known_people": [{"person_name": "João da Silva", "corroborated": True}],
        "technical": {
            "mx_by_domain": {DOMAIN: "MX_PRESENT"},
            "catch_all_by_domain": {DOMAIN: "UNKNOWN_NOT_PROBED"},
        },
    }
    source = tmp_path / "in.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    assert main(["run", "--input", str(source), "--out", str(out_a)]) == 0
    assert main(["run", "--input", str(source), "--out", str(out_b)]) == 0
    first = json.loads(out_a.read_text(encoding="utf-8"))
    second = json.loads(out_b.read_text(encoding="utf-8"))
    assert first["candidates"]
    assert first["candidates"] == second["candidates"]
    assert first["patterns"] == second["patterns"]
    assert all(item["epistemic_class"] != "OBSERVED" for item in first["candidates"])
    assert all(item["epistemic_class"] != "OBSERVED" for item in first["patterns"])
