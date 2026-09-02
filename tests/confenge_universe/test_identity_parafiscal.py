"""Identity taxonomy for parafiscal institutions — story-outbound-sector-classifier-false-positive-01.

Covers AC 11 (Sistema S / religious / foundational-education excluded with a
dedicated code), AC 12 (private engineering company named "FUNDACAO ..." is no
longer a false negative) and AC 13 (sanity check, unchanged behaviour).
"""

from __future__ import annotations

import pytest

from scripts.confenge_universe import NOT_CONSTRUCTION, PUBLIC_ORGAN
from scripts.confenge_universe.eligibility import decide_eligibility
from scripts.confenge_universe.identity import (
    PARAFISCAL_INSTITUTIONAL,
    resolve_identity,
)

# Valid CNPJ used only as a fixture — never hardcoded in production logic (AC 19).
VALID_CNPJ = "11222333000181"


@pytest.mark.parametrize(
    "razao_social",
    [
        "SEBRAE ES SERVICO DE APOIO AS MICRO E PEQUENAS EMPRESAS DO ESPIRITO SANTO",
        "SENAI DEPARTAMENTO REGIONAL DO ESPIRITO SANTO",
        "SESI DEPARTAMENTO REGIONAL DE MINAS GERAIS",
        "SESC ADMINISTRACAO REGIONAL NO ESTADO DA BAHIA",
        "SENAC ADMINISTRACAO REGIONAL DO PARANA",
        "SENAR ADMINISTRACAO REGIONAL DE GOIAS",
        "MITRA DIOCESANA DE COLATINA",
        "ARQUIDIOCESE DE VITORIA",
        "FUNDACAO EDUCACIONAL DE SAO JOSE",
        "FUNDACAO DE APOIO AO DESENVOLVIMENTO DA PESQUISA",
    ],
)
def test_parafiscal_institutions_are_excluded(razao_social: str) -> None:
    """AC 11."""
    ident = resolve_identity(VALID_CNPJ, razao_social)
    assert ident.valid is False, razao_social
    assert ident.exclusion_code == PARAFISCAL_INSTITUTIONAL, razao_social
    assert ident.exclusion_detail is not None


def test_parafiscal_exclusion_is_not_the_bank_taxonomy() -> None:
    """The new code must be its own bucket, not reuse the bank/utility list."""
    ident = resolve_identity(VALID_CNPJ, "SENAI DEPARTAMENTO REGIONAL")
    assert ident.exclusion_code == PARAFISCAL_INSTITUTIONAL
    assert ident.exclusion_code != NOT_CONSTRUCTION

    bank = resolve_identity(VALID_CNPJ, "BANCO DO BRASIL S.A.")
    assert bank.exclusion_code == NOT_CONSTRUCTION


def test_private_engineering_company_named_fundacao_is_valid() -> None:
    """AC 12 — inverse recall regression fixed."""
    ident = resolve_identity(VALID_CNPJ, "FUNDACAO ENGENHARIA E CONSTRUCOES LTDA")
    assert ident.valid is True
    assert ident.exclusion_code is None
    assert ident.person_kind == "cnpj"


def test_construtora_still_valid() -> None:
    """AC 13 — sanity check, behaviour unchanged."""
    ident = resolve_identity(VALID_CNPJ, "CONSTRUTORA ALFA ENGENHARIA LTDA")
    assert ident.valid is True
    assert ident.exclusion_code is None


def test_public_foundation_without_construction_evidence_is_still_public_organ() -> None:
    """Removing the bare "fundacao" organ marker must not open a hole."""
    ident = resolve_identity(VALID_CNPJ, "FUNDACAO DE PREVIDENCIA DOS SERVIDORES")
    assert ident.valid is False
    assert ident.exclusion_code == PUBLIC_ORGAN


@pytest.mark.parametrize(
    "razao_social",
    [
        "FUNDACAO MUNICIPAL DE CULTURA DE VITORIA",
        "FUNDACAO ESTADUAL DE SAUDE",
        "FUNDACAO CULTURAL PALMARES",
        "FUNDACAO HOSPITALAR DO ESTADO DE MINAS GERAIS",
        "FUNDACAO NACIONAL DE ARTES",
    ],
)
def test_generic_public_foundations_stay_public_organ(razao_social: str) -> None:
    """Guard against scope creep: these are public organs, NOT parafiscal bodies.

    Pre-change they were PUBLIC_ORGAN via the bare "fundacao" organ marker.
    Reclassifying them would silently shift `identity_exclusion_breakdown`
    counters in aggregate.py without any AC authorizing it.
    """
    ident = resolve_identity(VALID_CNPJ, razao_social)
    assert ident.valid is False
    assert ident.exclusion_code == PUBLIC_ORGAN, razao_social


def test_parafiscal_identity_maps_to_a_non_universe_eligibility() -> None:
    """Downstream eligibility must not silently label it INVALID_IDENTITY."""
    ident = resolve_identity(VALID_CNPJ, "SEBRAE ES SERVICO DE APOIO AS MICRO")
    decision = decide_eligibility(identity=ident, construction=None)
    assert decision.in_universe is False
    assert decision.outreach_eligibility == NOT_CONSTRUCTION
    assert "parafiscal" in decision.reason
