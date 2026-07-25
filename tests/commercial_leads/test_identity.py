"""Identity and exclusion tests — honest (no vacuous passes)."""

from __future__ import annotations

from scripts.commercial_leads.identity import resolve_supplier
from scripts.linkage.keys import is_valid_cnpj14


def test_valid_cnpj_eligible():
    cnpj = "11222333000181"
    assert is_valid_cnpj14(cnpj), "fixture CNPJ must be valid for this test"
    r = resolve_supplier(cnpj, "ACME ENGENHARIA LTDA")
    assert r.eligible is True
    assert r.person_kind == "cnpj"
    assert r.cnpj14 == cnpj


def test_natural_person_excluded():
    # 11-digit tax id is always treated as CPF path when drop_persons=True
    r = resolve_supplier("52998224725", "JOAO DA SILVA")
    assert r.eligible is False
    assert r.person_kind == "cpf"
    assert r.exclusion_reason == "natural_person"


def test_natural_person_formatted_cpf_excluded():
    r = resolve_supplier("529.982.247-25", "MARIA SOUZA")
    assert r.eligible is False
    assert r.exclusion_reason == "natural_person"


def test_public_organ_excluded():
    r = resolve_supplier(
        "00000000000191",
        "PREFEITURA MUNICIPAL DE FLORIANOPOLIS",
        organ_markers=["prefeitura", "municipio"],
    )
    assert r.eligible is False
    assert r.exclusion_reason == "public_organ_name"


def test_missing_tax_id_excluded():
    r = resolve_supplier(None, "EMPRESA SEM DOC")
    assert r.eligible is False
    assert r.exclusion_reason in {"missing_tax_id", "invalid_or_missing_cnpj"}


def test_invalid_cnpj_excluded():
    r = resolve_supplier("11111111111111", "EMPRESA INVALIDA LTDA")
    assert r.eligible is False
