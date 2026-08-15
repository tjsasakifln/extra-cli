"""Shipped consumer of corroborate_affiliation.

Used by tests and the offline verification harness. Cases are structured
dated observations — no live HTTP, no invented people.
"""

from __future__ import annotations

from typing import Any

from scripts.decision_unit_intelligence.corroboration import (
    CandidatePerson,
    DatedEvidenceItem,
    corroborate_affiliation,
    email_association_gate,
)

AS_OF = "2026-08-15"
TARGET_CNPJS = {
    "diretor": "12345678000190",
    "conflict": "12345678000190",
    "qsa": "12345678000190",
    "stale": "12345678000190",
    "homonym": "11111111000191",
}


def _item(**kwargs: Any) -> DatedEvidenceItem:
    return DatedEvidenceItem(**kwargs)


def representative_cases() -> dict[str, tuple[CandidatePerson, list[DatedEvidenceItem]]]:
    diretor = CandidatePerson(
        canonical_name="Ana Diretora",
        aliases=["Ana M. Diretora"],
        target_company_cnpj=TARGET_CNPJS["diretor"],
        target_company_name="EXEMPLO ENGENHARIA LTDA",
        target_entity_kind="operational",
    )
    conflict = CandidatePerson(
        canonical_name="Bruno Cargos",
        target_company_cnpj=TARGET_CNPJS["conflict"],
        target_company_name="EXEMPLO ENGENHARIA LTDA",
        target_entity_kind="operational",
    )
    socio = CandidatePerson(
        canonical_name="Carlos Socio",
        target_company_cnpj=TARGET_CNPJS["qsa"],
        target_company_name="EXEMPLO ENGENHARIA LTDA",
        target_entity_kind="operational",
        claimed_role="Sócio-Administrador",
    )
    stale = CandidatePerson(
        canonical_name="Diana Exdiretora",
        target_company_cnpj=TARGET_CNPJS["stale"],
        target_company_name="EXEMPLO ENGENHARIA LTDA",
        target_entity_kind="operational",
    )
    homonym = CandidatePerson(
        canonical_name="Eduardo Silva",
        target_company_cnpj=TARGET_CNPJS["homonym"],
        target_company_name="ALVO CONSTRUCOES LTDA",
        target_entity_kind="operational",
    )
    return {
        "diretor_two_independent": (
            diretor,
            [
                _item(
                    evidence_id="site-id",
                    source_type="company_website",
                    field="identity",
                    value="Ana Diretora",
                    source_url="https://exemplo.eng.br/equipe",
                    origin_id="exemplo-equipe-2026",
                    observed_at="2026-03-01",
                    published_at="2026-03-01",
                    company_cnpj=TARGET_CNPJS["diretor"],
                    company_name="EXEMPLO ENGENHARIA LTDA",
                    entity_kind="operational",
                    snippet="Ana Diretora, diretor de engenharia",
                    extra={"person_name": "Ana Diretora"},
                ),
                _item(
                    evidence_id="site-aff",
                    source_type="company_website",
                    field="affiliation",
                    value="EXEMPLO ENGENHARIA LTDA",
                    source_url="https://exemplo.eng.br/equipe",
                    origin_id="exemplo-equipe-2026",
                    observed_at="2026-03-01",
                    published_at="2026-03-01",
                    company_cnpj=TARGET_CNPJS["diretor"],
                    company_name="EXEMPLO ENGENHARIA LTDA",
                    entity_kind="operational",
                    extra={"person_name": "Ana Diretora"},
                ),
                _item(
                    evidence_id="site-role",
                    source_type="company_website",
                    field="role",
                    value="Diretor de Engenharia",
                    source_url="https://exemplo.eng.br/equipe",
                    origin_id="exemplo-equipe-2026",
                    observed_at="2026-03-01",
                    published_at="2026-03-01",
                    company_cnpj=TARGET_CNPJS["diretor"],
                    company_name="EXEMPLO ENGENHARIA LTDA",
                    role_text="Diretor de Engenharia",
                    extra={"person_name": "Ana Diretora"},
                ),
                _item(
                    evidence_id="gazette-id",
                    source_type="official_gazette",
                    field="identity",
                    value="Ana Diretora",
                    source_url="https://doe.sc.gov.br/2026/03/12/ato",
                    origin_id="doe-sc-2026-03-12",
                    document_id="doe-sc-2026-03-12",
                    observed_at="2026-03-12",
                    published_at="2026-03-12",
                    company_cnpj=TARGET_CNPJS["diretor"],
                    company_name="EXEMPLO ENGENHARIA LTDA",
                    extra={"person_name": "Ana Diretora"},
                ),
                _item(
                    evidence_id="gazette-aff",
                    source_type="official_gazette",
                    field="affiliation",
                    value="EXEMPLO ENGENHARIA LTDA",
                    source_url="https://doe.sc.gov.br/2026/03/12/ato",
                    origin_id="doe-sc-2026-03-12",
                    document_id="doe-sc-2026-03-12",
                    observed_at="2026-03-12",
                    published_at="2026-03-12",
                    company_cnpj=TARGET_CNPJS["diretor"],
                    company_name="EXEMPLO ENGENHARIA LTDA",
                    extra={"person_name": "Ana Diretora"},
                ),
                _item(
                    evidence_id="gazette-role",
                    source_type="official_gazette",
                    field="role",
                    value="Diretor de Engenharia",
                    source_url="https://doe.sc.gov.br/2026/03/12/ato",
                    origin_id="doe-sc-2026-03-12",
                    document_id="doe-sc-2026-03-12",
                    observed_at="2026-03-12",
                    published_at="2026-03-12",
                    company_cnpj=TARGET_CNPJS["diretor"],
                    company_name="EXEMPLO ENGENHARIA LTDA",
                    role_text="Diretor de Engenharia",
                    extra={"person_name": "Ana Diretora"},
                ),
            ],
        ),
        "conflicting_roles": (
            conflict,
            [
                _item(
                    evidence_id="c-id-1",
                    source_type="company_website",
                    field="identity",
                    value="Bruno Cargos",
                    source_url="https://exemplo.eng.br/equipe",
                    origin_id="site-equipe",
                    observed_at="2026-04-01",
                    published_at="2026-04-01",
                    company_cnpj=TARGET_CNPJS["conflict"],
                    extra={"person_name": "Bruno Cargos"},
                ),
                _item(
                    evidence_id="c-role-1",
                    source_type="company_website",
                    field="role",
                    value="Diretor Comercial",
                    source_url="https://exemplo.eng.br/equipe",
                    origin_id="site-equipe",
                    observed_at="2026-04-01",
                    published_at="2026-04-01",
                    company_cnpj=TARGET_CNPJS["conflict"],
                    role_text="Diretor Comercial",
                    extra={"person_name": "Bruno Cargos"},
                ),
                _item(
                    evidence_id="c-aff-1",
                    source_type="company_website",
                    field="affiliation",
                    value="EXEMPLO ENGENHARIA LTDA",
                    source_url="https://exemplo.eng.br/equipe",
                    origin_id="site-equipe",
                    observed_at="2026-04-01",
                    published_at="2026-04-01",
                    company_cnpj=TARGET_CNPJS["conflict"],
                    company_name="EXEMPLO ENGENHARIA LTDA",
                    extra={"person_name": "Bruno Cargos"},
                ),
                _item(
                    evidence_id="c-id-2",
                    source_type="press_release",
                    field="identity",
                    value="Bruno Cargos",
                    source_url="https://jornal.example/materia",
                    origin_id="materia-2026",
                    observed_at="2026-05-01",
                    published_at="2026-05-01",
                    company_cnpj=TARGET_CNPJS["conflict"],
                    extra={"person_name": "Bruno Cargos"},
                ),
                _item(
                    evidence_id="c-role-2",
                    source_type="press_release",
                    field="role",
                    value="Diretor de Engenharia",
                    source_url="https://jornal.example/materia",
                    origin_id="materia-2026",
                    observed_at="2026-05-01",
                    published_at="2026-05-01",
                    company_cnpj=TARGET_CNPJS["conflict"],
                    role_text="Diretor de Engenharia",
                    extra={"person_name": "Bruno Cargos"},
                ),
                _item(
                    evidence_id="c-aff-2",
                    source_type="press_release",
                    field="affiliation",
                    value="EXEMPLO ENGENHARIA LTDA",
                    source_url="https://jornal.example/materia",
                    origin_id="materia-2026",
                    observed_at="2026-05-01",
                    published_at="2026-05-01",
                    company_cnpj=TARGET_CNPJS["conflict"],
                    company_name="EXEMPLO ENGENHARIA LTDA",
                    extra={"person_name": "Bruno Cargos"},
                ),
            ],
        ),
        "qsa_only_socio": (
            socio,
            [
                _item(
                    evidence_id="qsa-id",
                    source_type="qsa_rfb",
                    field="identity",
                    value="Carlos Socio",
                    source_url="https://casadosdados.com.br/cnpj/12345678000190",
                    observed_at="2026-08-05",
                    company_cnpj=TARGET_CNPJS["qsa"],
                    company_name="EXEMPLO ENGENHARIA LTDA",
                    extra={"person_name": "Carlos Socio"},
                ),
                _item(
                    evidence_id="qsa-aff",
                    source_type="qsa_rfb",
                    field="affiliation",
                    value="EXEMPLO ENGENHARIA LTDA",
                    source_url="https://casadosdados.com.br/cnpj/12345678000190",
                    observed_at="2026-08-05",
                    company_cnpj=TARGET_CNPJS["qsa"],
                    company_name="EXEMPLO ENGENHARIA LTDA",
                    extra={"person_name": "Carlos Socio"},
                ),
                _item(
                    evidence_id="qsa-role",
                    source_type="qsa_rfb",
                    field="role",
                    value="Sócio-Administrador",
                    source_url="https://casadosdados.com.br/cnpj/12345678000190",
                    observed_at="2026-08-05",
                    company_cnpj=TARGET_CNPJS["qsa"],
                    role_text="Sócio-Administrador",
                    extra={"person_name": "Carlos Socio"},
                ),
            ],
        ),
        "ex_diretor_nova_empresa": (
            stale,
            [
                _item(
                    evidence_id="stale-id",
                    source_type="press_release",
                    field="identity",
                    value="Diana Exdiretora",
                    source_url="https://jornal.example/saida",
                    origin_id="saida-2025",
                    observed_at="2025-01-10",
                    published_at="2025-01-10",
                    company_cnpj=TARGET_CNPJS["stale"],
                    extra={"person_name": "Diana Exdiretora"},
                ),
                _item(
                    evidence_id="stale-aff",
                    source_type="press_release",
                    field="affiliation",
                    value="EXEMPLO ENGENHARIA LTDA",
                    source_url="https://jornal.example/saida",
                    origin_id="saida-2025",
                    observed_at="2025-01-10",
                    published_at="2025-01-10",
                    company_cnpj=TARGET_CNPJS["stale"],
                    company_name="EXEMPLO ENGENHARIA LTDA",
                    stale_signal="left_company",
                    snippet="ex-diretora saiu da empresa e agora na Nova Construtora",
                    extra={"person_name": "Diana Exdiretora"},
                ),
                _item(
                    evidence_id="stale-role",
                    source_type="press_release",
                    field="role",
                    value="ex-diretora",
                    source_url="https://jornal.example/saida",
                    origin_id="saida-2025",
                    observed_at="2025-01-10",
                    published_at="2025-01-10",
                    company_cnpj=TARGET_CNPJS["stale"],
                    role_text="ex-diretora",
                    stale_signal="ex_role",
                    snippet="ex-diretora saiu da empresa e agora na Nova Construtora",
                    extra={"person_name": "Diana Exdiretora"},
                ),
            ],
        ),
        "homonym_other_company": (
            homonym,
            [
                _item(
                    evidence_id="hom-id",
                    source_type="company_website",
                    field="identity",
                    value="Eduardo Silva",
                    source_url="https://outra.eng.br/equipe",
                    origin_id="outra-equipe",
                    observed_at="2026-06-01",
                    published_at="2026-06-01",
                    company_cnpj="22222222000191",
                    company_name="OUTRA ENGENHARIA LTDA",
                    extra={"person_name": "Eduardo Silva"},
                ),
                _item(
                    evidence_id="hom-aff",
                    source_type="company_website",
                    field="affiliation",
                    value="OUTRA ENGENHARIA LTDA",
                    source_url="https://outra.eng.br/equipe",
                    origin_id="outra-equipe",
                    observed_at="2026-06-01",
                    published_at="2026-06-01",
                    company_cnpj="22222222000191",
                    company_name="OUTRA ENGENHARIA LTDA",
                    extra={"person_name": "Eduardo Silva"},
                ),
                _item(
                    evidence_id="hom-role",
                    source_type="company_website",
                    field="role",
                    value="Diretor",
                    source_url="https://outra.eng.br/equipe",
                    origin_id="outra-equipe",
                    observed_at="2026-06-01",
                    published_at="2026-06-01",
                    company_cnpj="22222222000191",
                    company_name="OUTRA ENGENHARIA LTDA",
                    role_text="Diretor",
                    extra={"person_name": "Eduardo Silva"},
                ),
            ],
        ),
    }


def evaluate_representative_cases(*, as_of: str = AS_OF) -> dict[str, Any]:
    """Drive the shipped entry on the five verification inputs."""
    payload: dict[str, Any] = {"as_of": as_of, "cases": {}}
    for key, (person, items) in representative_cases().items():
        record = corroborate_affiliation(person, items, as_of=as_of)
        gate = email_association_gate(record)
        payload["cases"][key] = {
            "identity_confidence": record.identity_confidence.value,
            "affiliation_confidence": record.affiliation_confidence.value,
            "role_confidence": record.role_confidence.value,
            "recency_confidence": record.recency_confidence.value,
            "reason_codes": list(record.reason_codes),
            "association_allowed": record.association_allowed,
            "stop_reasons": list(record.stop_reasons),
            "canonical_decision_role": record.canonical_decision_role,
            "company_cnpj": record.company_cnpj,
            "company_name": record.company_name,
            "contradictions": [item.to_dict() for item in record.contradictions],
            "gate": gate.to_dict(),
        }
    return payload


def main() -> int:
    import json
    import sys

    print(json.dumps(evaluate_representative_cases(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not sys.argv[1:] else 0


if __name__ == "__main__":
    raise SystemExit(main())
