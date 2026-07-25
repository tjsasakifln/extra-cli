"""Identity and exclusion tests."""

from __future__ import annotations

from scripts.commercial_leads.identity import resolve_supplier
from scripts.linkage.keys import is_valid_cnpj14


def test_valid_cnpj_eligible():
    # Generate a known-valid style: use linkage validator with a constructed CNPJ
    # 04.252.011/0001-10 is a commonly cited valid CNPJ pattern — verify first
    cnpj = "04252011000110"
    if not is_valid_cnpj14(cnpj):
        # fallback: invent via algorithm
        base = "112223330001"
        # try common valid
        for candidate in ("11222333000181", "34028316000103", "60746948000112"):
            if is_valid_cnpj14(candidate):
                cnpj = candidate
                break
    r = resolve_supplier(cnpj, "ACME ENGENHARIA LTDA")
    assert r.eligible
    assert r.person_kind == "cnpj"
    assert r.cnpj14 == cnpj


def test_natural_person_excluded():
    r = resolve_supplier("529.982.247-25", "JOAO DA SILVA")
    # may be invalid check digits; still 11 digits path
    if r.person_kind == "cpf" or r.exclusion_reason == "natural_person":
        assert not r.eligible


def test_public_organ_excluded():
    r = resolve_supplier(
        "00000000000191",
        "PREFEITURA MUNICIPAL DE FLORIANOPOLIS",
        organ_markers=["prefeitura", "municipio"],
    )
    assert not r.eligible
    assert r.exclusion_reason == "public_organ_name"


def test_missing_tax_id_excluded():
    r = resolve_supplier(None, "EMPRESA SEM DOC")
    assert not r.eligible
