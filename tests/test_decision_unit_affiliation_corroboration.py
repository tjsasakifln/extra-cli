"""Affiliation corroboration drives the shipped path — no copy, no invented cargo."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.decision_unit_intelligence.affiliation_consumer import evaluate_representative_cases
from scripts.decision_unit_intelligence.affiliation_policy import (
    FORBIDDEN_SOURCE_TYPES,
    SCHEMA_ID,
    SHIPPED_REASON_CODES,
    AffiliationReasonCode,
)
from scripts.decision_unit_intelligence.corroboration import (
    CandidatePerson,
    DatedEvidenceItem,
    corroborate_affiliation,
    email_association_gate,
    independence_origin,
    may_associate_email,
)
from scripts.decision_unit_intelligence.email_discovery import associate_person_to_email
from scripts.decision_unit_intelligence.models import (
    ConfidenceLevel,
    EpistemicClass,
    PersonObservation,
    PersonRelation,
)

AS_OF = "2026-08-15"
CNPJS = "12345678000190"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "decision_unit_intelligence"
    / "data"
    / "affiliation_corroboration.schema.json"
)


def _person(**kwargs) -> CandidatePerson:
    kwargs.setdefault("target_company_cnpj", CNPJS)
    kwargs.setdefault("target_company_name", "EXEMPLO ENGENHARIA LTDA")
    kwargs.setdefault("target_entity_kind", "operational")
    return CandidatePerson(**kwargs)


def _ev(**kwargs) -> DatedEvidenceItem:
    kwargs.setdefault("company_cnpj", CNPJS)
    kwargs.setdefault("company_name", "EXEMPLO ENGENHARIA LTDA")
    kwargs.setdefault("observed_at", "2026-04-01")
    kwargs.setdefault("published_at", "2026-04-01")
    return DatedEvidenceItem(**kwargs)


def _identity_bundle(
    *,
    name: str,
    origin: str,
    source_type: str,
    url: str,
    role: str | None,
    company_cnpj: str = CNPJS,
    company_name: str = "EXEMPLO ENGENHARIA LTDA",
    snippet: str | None = None,
    stale_signal: str | None = None,
    entity_kind: str = "operational",
    observed_at: str = "2026-04-01",
) -> list[DatedEvidenceItem]:
    extra = {"person_name": name}
    items = [
        _ev(
            evidence_id=f"{origin}-id",
            source_type=source_type,
            field="identity",
            value=name,
            source_url=url,
            origin_id=origin,
            snippet=snippet,
            stale_signal=stale_signal,
            entity_kind=entity_kind,
            company_cnpj=company_cnpj,
            company_name=company_name,
            observed_at=observed_at,
            published_at=observed_at,
            extra=extra,
        ),
        _ev(
            evidence_id=f"{origin}-aff",
            source_type=source_type,
            field="affiliation",
            value=company_name,
            source_url=url,
            origin_id=origin,
            snippet=snippet,
            stale_signal=stale_signal,
            entity_kind=entity_kind,
            company_cnpj=company_cnpj,
            company_name=company_name,
            observed_at=observed_at,
            published_at=observed_at,
            extra=extra,
        ),
    ]
    if role:
        items.append(
            _ev(
                evidence_id=f"{origin}-role",
                source_type=source_type,
                field="role",
                value=role,
                source_url=url,
                origin_id=origin,
                role_text=role,
                snippet=snippet,
                stale_signal=stale_signal,
                entity_kind=entity_kind,
                company_cnpj=company_cnpj,
                company_name=company_name,
                observed_at=observed_at,
                published_at=observed_at,
                extra=extra,
            )
        )
    return items


def test_schema_file_exists_and_names_per_field_confidences():
    payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert payload["$id"] == SCHEMA_ID
    required = set(payload["required"])
    assert {
        "identity_confidence",
        "affiliation_confidence",
        "role_confidence",
        "recency_confidence",
        "contradictions",
        "reason_codes",
    } <= required


def test_diretor_two_independent_sources_corroborates_identity_affiliation_role():
    person = _person(canonical_name="Ana Diretora", aliases=["Ana M. Diretora"])
    evidence = _identity_bundle(
        name="Ana Diretora",
        origin="site-equipe",
        source_type="company_website",
        url="https://exemplo.eng.br/equipe",
        role="Diretor de Engenharia",
    ) + _identity_bundle(
        name="Ana Diretora",
        origin="doe-sc-2026",
        source_type="official_gazette",
        url="https://doe.sc.gov.br/ato",
        role="Diretor de Engenharia",
        observed_at="2026-03-12",
    )
    record = corroborate_affiliation(person, evidence, as_of=AS_OF)
    assert record.identity_confidence is ConfidenceLevel.HIGH
    assert record.affiliation_confidence is ConfidenceLevel.HIGH
    assert record.role_confidence is ConfidenceLevel.HIGH
    assert AffiliationReasonCode.IDENTITY_CORROBORATED.value in record.reason_codes
    assert AffiliationReasonCode.AFFILIATION_CORROBORATED.value in record.reason_codes
    assert AffiliationReasonCode.ROLE_CORROBORATED.value in record.reason_codes
    assert record.canonical_decision_role == "diretor_engenharia"
    assert record.association_allowed is True
    assert email_association_gate(record).allowed is True
    assert record.contradictions == []
    assert record.to_dict()["schema_id"] == SCHEMA_ID
    assert record.to_dict()["promotes_email"] is False


def test_copy_sources_of_one_origin_are_not_independent():
    person = _person(canonical_name="Ana Diretora")
    evidence = _identity_bundle(
        name="Ana Diretora",
        origin="press-2026-03",
        source_type="press_release",
        url="https://exemplo.eng.br/imprensa/nomeacao",
        role="Diretora",
    ) + _identity_bundle(
        name="Ana Diretora",
        origin="press-2026-03",
        source_type="news",
        url="https://g1.globo.com/sc/nomeacao-espelho",
        role="Diretora",
    )
    record = corroborate_affiliation(person, evidence, as_of=AS_OF)
    origins = {independence_origin(item) for item in evidence}
    assert origins == {"press-2026-03"}
    assert AffiliationReasonCode.IDENTITY_CORROBORATED.value not in record.reason_codes
    assert AffiliationReasonCode.AFFILIATION_CORROBORATED.value not in record.reason_codes
    assert AffiliationReasonCode.ROLE_CORROBORATED.value not in record.reason_codes
    assert record.identity_confidence is not ConfidenceLevel.HIGH


def test_conflicting_roles_are_not_averaged():
    person = _person(canonical_name="Bruno Cargos")
    evidence = _identity_bundle(
        name="Bruno Cargos",
        origin="site-equipe",
        source_type="company_website",
        url="https://exemplo.eng.br/equipe",
        role="Diretor Comercial",
    ) + _identity_bundle(
        name="Bruno Cargos",
        origin="materia-2026",
        source_type="press_release",
        url="https://jornal.example/materia",
        role="Diretor de Engenharia",
    )
    record = corroborate_affiliation(person, evidence, as_of=AS_OF)
    assert AffiliationReasonCode.CONFLICTING_EVIDENCE.value in record.reason_codes
    assert AffiliationReasonCode.CONFLICTING_ROLE.value in record.reason_codes
    assert record.role_confidence is ConfidenceLevel.LOW
    assert record.role_confidence is not ConfidenceLevel.HIGH
    assert record.canonical_decision_role is None
    assert record.association_allowed is False
    assert email_association_gate(record).stop_the_line is True
    assert any(item.topic == "role" for item in record.contradictions)


def test_qsa_only_socio_is_not_operational_or_associable():
    person = _person(canonical_name="Carlos Socio", claimed_role="Sócio-Administrador")
    evidence = _identity_bundle(
        name="Carlos Socio",
        origin="qsa-rfb",
        source_type="qsa_rfb",
        url="https://casadosdados.com.br/cnpj/12345678000190",
        role="Sócio-Administrador",
        observed_at="2026-08-05",
    )
    record = corroborate_affiliation(person, evidence, as_of=AS_OF)
    assert AffiliationReasonCode.QSA_ONLY.value in record.reason_codes
    assert AffiliationReasonCode.ROLE_CORROBORATED.value not in record.reason_codes
    assert AffiliationReasonCode.AFFILIATION_CORROBORATED.value not in record.reason_codes
    assert record.affiliation_confidence is ConfidenceLevel.LOW
    assert record.role_confidence is ConfidenceLevel.LOW
    assert record.association_allowed is False
    gate = email_association_gate(record, email="carlos.socio@exemplo.eng.br")
    assert gate.allowed is False
    assert gate.stop_the_line is True
    assert gate.to_dict()["promotes_email"] is False
    assert gate.to_dict()["marks_email_validated"] is False
    assert gate.to_dict()["auto_send"] is False


def test_ex_diretor_nova_empresa_is_stale():
    person = _person(canonical_name="Diana Exdiretora")
    evidence = _identity_bundle(
        name="Diana Exdiretora",
        origin="saida-2025",
        source_type="press_release",
        url="https://jornal.example/saida",
        role="ex-diretora",
        snippet="ex-diretora saiu da empresa e agora na Nova Construtora",
        stale_signal="left_company",
        observed_at="2025-01-10",
    )
    record = corroborate_affiliation(person, evidence, as_of=AS_OF)
    assert AffiliationReasonCode.STALE_AFFILIATION.value in record.reason_codes
    assert (
        AffiliationReasonCode.INSUFFICIENT_RECENCY.value in record.reason_codes
        or AffiliationReasonCode.STALE_AFFILIATION.value in record.reason_codes
    )
    assert record.association_allowed is False
    assert record.affiliation_confidence is not ConfidenceLevel.HIGH


def test_homonym_does_not_affiliate_to_wrong_company():
    person = _person(
        canonical_name="Eduardo Silva",
        target_company_cnpj="11111111000191",
        target_company_name="ALVO CONSTRUCOES LTDA",
    )
    evidence = _identity_bundle(
        name="Eduardo Silva",
        origin="outra-equipe",
        source_type="company_website",
        url="https://outra.eng.br/equipe",
        role="Diretor",
        company_cnpj="22222222000191",
        company_name="OUTRA ENGENHARIA LTDA",
    )
    record = corroborate_affiliation(person, evidence, as_of=AS_OF)
    assert record.company_cnpj == "11111111000191"
    assert AffiliationReasonCode.AFFILIATION_CORROBORATED.value not in record.reason_codes
    assert record.association_allowed is False
    assert record.affiliation_confidence is not ConfidenceLevel.HIGH
    assert email_association_gate(record).allowed is False


def test_holding_vs_operational_mismatch():
    person = _person(
        canonical_name="Fernanda Holding",
        target_company_name="EXEMPLO ENGENHARIA LTDA",
        target_entity_kind="operational",
    )
    evidence = _identity_bundle(
        name="Fernanda Holding",
        origin="holding-site",
        source_type="company_website",
        url="https://exemplo-holding.com.br/diretoria",
        role="Diretora",
        company_name="EXEMPLO PARTICIPACOES HOLDING LTDA",
        entity_kind="holding",
    )
    # Keep target CNPJ so affiliation is "same CNPJ" only if we set it — use same
    # CNPJ with holding name to isolate entity-kind mismatch.
    record = corroborate_affiliation(person, evidence, as_of=AS_OF)
    assert AffiliationReasonCode.HOLDING_OPERATIONAL_MISMATCH.value in record.reason_codes
    assert AffiliationReasonCode.CONFLICTING_EVIDENCE.value in record.reason_codes
    assert record.association_allowed is False


def test_consortium_representation_is_not_member_operational_role():
    person = _person(
        canonical_name="Gabriel Consorcio",
        target_company_name="EXEMPLO ENGENHARIA LTDA",
        target_entity_kind="operational",
    )
    evidence = _identity_bundle(
        name="Gabriel Consorcio",
        origin="ata-consorcio",
        source_type="process_document",
        url="https://pncp.gov.br/ata",
        role="Representante do Consórcio",
        company_name="CONSORCIO NORTE SUL SPE",
        entity_kind="consortium",
    )
    record = corroborate_affiliation(person, evidence, as_of=AS_OF)
    assert AffiliationReasonCode.HOLDING_OPERATIONAL_MISMATCH.value in record.reason_codes
    assert record.association_allowed is False
    assert record.canonical_decision_role in {None, "representante_legal"}


def test_forbidden_sources_are_rejected_and_do_not_corroborate():
    person = _person(canonical_name="Helena Fonte")
    evidence = [
        _ev(
            evidence_id="li-auth",
            source_type="authenticated_linkedin",
            field="identity",
            value="Helena Fonte",
            source_url="https://linkedin.com/in/helena",
            extra={"person_name": "Helena Fonte"},
        ),
        _ev(
            evidence_id="broker",
            source_type="data_broker",
            field="affiliation",
            value="EXEMPLO ENGENHARIA LTDA",
            source_url="https://zoominfo.com/helena",
            extra={"person_name": "Helena Fonte"},
        ),
        _ev(
            evidence_id="localpart",
            source_type="company_website",
            field="role",
            value="Diretora",
            extraction_method="cargo_from_local_part",
            extra={"person_name": "Helena Fonte"},
        ),
        _ev(
            evidence_id="pj",
            source_type="qsa_rfb",
            field="identity",
            value="HELENA HOLDING PARTICIPACOES LTDA",
            extra={"person_name": "HELENA HOLDING PARTICIPACOES LTDA"},
        ),
    ]
    record = corroborate_affiliation(person, evidence, as_of=AS_OF)
    rejected_reasons = {item["reason"] for item in record.rejected_evidence}
    assert "authenticated_linkedin" in rejected_reasons or "data_broker" in rejected_reasons
    assert any("local_part" in str(reason) or "cargo" in str(reason) for reason in rejected_reasons)
    assert AffiliationReasonCode.ROLE_CORROBORATED.value not in record.reason_codes
    assert AffiliationReasonCode.AFFILIATION_CORROBORATED.value not in record.reason_codes
    assert record.association_allowed is False


def test_policy_vocabulary_contains_the_eight_reason_codes():
    assert len(SHIPPED_REASON_CODES) == 8
    assert "authenticated_linkedin" in FORBIDDEN_SOURCE_TYPES
    assert "data_broker" in FORBIDDEN_SOURCE_TYPES


def test_does_not_invent_role_or_company_when_evidence_is_silent():
    person = _person(canonical_name="Igor Semcargo", claimed_role="Diretor Comercial")
    evidence = [
        _ev(
            evidence_id="name-only",
            source_type="company_website",
            field="identity",
            value="Igor Semcargo",
            source_url="https://exemplo.eng.br/noticia",
            origin_id="noticia",
            extra={"person_name": "Igor Semcargo"},
        )
    ]
    record = corroborate_affiliation(person, evidence, as_of=AS_OF)
    assert record.canonical_decision_role is None
    assert record.role_candidates == []
    assert record.company_name == "EXEMPLO ENGENHARIA LTDA"
    assert AffiliationReasonCode.ROLE_CORROBORATED.value not in record.reason_codes


def test_stop_the_line_refuses_known_false_vinculo_on_email_promoter():
    person = _person(canonical_name="Carlos Socio")
    evidence = _identity_bundle(
        name="Carlos Socio",
        origin="qsa-rfb",
        source_type="qsa_rfb",
        url="https://receita.fazenda.gov.br/qsa",
        role="Sócio-Administrador",
    )
    decision = may_associate_email(
        person,
        evidence,
        email="carlos.socio@exemplo.eng.br",
        as_of=AS_OF,
    )
    assert decision.allowed is False
    assert decision.stop_the_line is True
    obs = PersonObservation(
        observation_id="p-carlos",
        company_entity_id=CNPJS,
        person_name="Carlos Socio",
        observed_role="Sócio-Administrador",
        relation=PersonRelation.COMPANY_MEMBER,
        source_type="qsa_rfb",
        epistemic_class=EpistemicClass.OBSERVED,
    )
    record = corroborate_affiliation(person, evidence, as_of=AS_OF)
    association = associate_person_to_email(
        "carlos.socio@exemplo.eng.br",
        people=[obs],
        html="<article><h3>Carlos Socio</h3><a href='mailto:carlos.socio@exemplo.eng.br'>x</a></article>",
        text="Carlos Socio carlos.socio@exemplo.eng.br",
        source_url="https://exemplo.eng.br/equipe",
        corroboration=record,
    )
    assert association.associated is False
    assert "AFFILIATION_GATE_REFUSED" in association.reason_codes


def test_consumer_payload_conforms_to_schema_and_is_deterministic():
    first = evaluate_representative_cases()
    second = evaluate_representative_cases()
    assert first == second
    diretor = first["cases"]["diretor_two_independent"]
    assert {
        diretor["identity_confidence"],
        diretor["affiliation_confidence"],
        diretor["role_confidence"],
        diretor["recency_confidence"],
    }
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    required = schema["required"]
    # Reconstruct a record-shaped dict from the consumer for schema keys.
    record = corroborate_affiliation(*__import__(
        "scripts.decision_unit_intelligence.affiliation_consumer",
        fromlist=["representative_cases"],
    ).representative_cases()["diretor_two_independent"], as_of=AS_OF)
    payload = record.to_dict()
    for key in required:
        assert key in payload
    assert payload["identity_confidence"] in schema["properties"]["identity_confidence"]["enum"]
