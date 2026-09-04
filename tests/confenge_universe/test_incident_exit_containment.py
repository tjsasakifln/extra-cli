"""Incident-exit residual: SEBRAE-ES / identity-exclusion census / CNPJ14 / official id.

Drives shipped ``classify_target_fit``, ``run_universe_build``,
``resolve_company_from_contract`` and ``public_contract_id`` — not a reimplementation.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts.confenge_contract_identity import public_contract_id
from scripts.confenge_target_fit.company_key import (
    canonical_target_membership,
    resolve_company_from_contract,
)
from scripts.confenge_universe import NOT_CONSTRUCTION
from scripts.confenge_universe.parafiscal import PARAFISCAL_HARD_OUT_REASON
from scripts.confenge_universe.pipeline import run_universe_build
from scripts.confenge_universe.target_fit import TARGET_CONFIRMED, TARGET_OUT_OF_SCOPE, classify_target_fit

AS_OF = date(2026, 8, 1)
VALID_CNPJ = "11222333000181"
SEBRAE_ES_NAME = "SEBRAE ES SERVICO DE APOIO AS MICRO E PEQUENAS EMPRESAS DO ESPIRITO SANTO"
EXECUTION_OBJECT = (
    "EXECUCAO DE OBRA DE REFORMA E AMPLIACAO DA UNIDADE, "
    "COM FUNDACAO EM SAPATA CORRIDA E ESTRUTURA EM CONCRETO ARMADO"
)


def test_sebrae_es_with_execution_contracts_never_reaches_target_confirmed() -> None:
    """Incident entity stays OUT even when the portfolio has real execution objects."""
    contracts = [
        {
            "contrato_id": "27080530000143-2-000648/2024",
            "id": "25394409",
            "fornecedor_nome": SEBRAE_ES_NAME,
            "objeto_contrato": EXECUTION_OBJECT,
            "valor_total": 1_000_000.0,
        }
        for _ in range(3)
    ]
    decision = classify_target_fit(
        razao_social=SEBRAE_ES_NAME,
        contracts=contracts,
        sector_fit="CONSTRUCTION_CONFIRMED",
        activity_class="CONSTRUCTION",
    )
    assert decision.target_fit_class == TARGET_OUT_OF_SCOPE
    assert decision.target_fit_class != TARGET_CONFIRMED
    assert PARAFISCAL_HARD_OUT_REASON in decision.target_fit_reason_codes
    assert decision.relevant_execution_contract_count == 3
    evidence_ids = [str(e.get("id") or "") for e in decision.target_fit_evidence]
    assert "27080530000143-2-000648/2024" in evidence_ids
    assert "25394409" not in evidence_ids


def test_official_contract_id_wins_over_technical_surrogate() -> None:
    row = {
        "id": "25394409",
        "contrato_id": "00028986000108-1-000123/2026",
        "numero_controle_pncp": "00028986000108-1-000123/2026",
    }
    assert public_contract_id(row) == "00028986000108-1-000123/2026"
    assert public_contract_id({"id": "25394409"}) == ""


def test_same_cnpj14_two_supplier_names_is_one_company_key() -> None:
    a = resolve_company_from_contract(
        {"fornecedor_cnpj": VALID_CNPJ, "fornecedor_nome": "ALFA CONSTRUTORA LTDA"}
    )
    b = resolve_company_from_contract(
        {"fornecedor_cnpj": VALID_CNPJ, "fornecedor_nome": "ALFA ENGENHARIA EIRELI"}
    )
    assert a is not None and b is not None
    assert a[0] == b[0] == "cnpj_root:11222333"
    assert a[1] == b[1] == "11222333"


def test_canonical_membership_refuses_duplicate_roots() -> None:
    try:
        canonical_target_membership([VALID_CNPJ, "11222333000262"])
    except ValueError as exc:
        assert "duplicate CNPJ roots" in str(exc)
    else:
        raise AssertionError("duplicate roots must not publish two commercial entities")


def test_all_rejected_parafiscal_rows_remain_in_exclusion_universe(tmp_path: Path) -> None:
    """A root whose every contract row is identity-rejected must not vanish."""
    rows = [
        {
            "fornecedor_cnpj": VALID_CNPJ,
            "fornecedor_nome": SEBRAE_ES_NAME,
            "objeto_contrato": EXECUTION_OBJECT,
            "valor_total": 500_000.0,
            "orgao_nome": "ORGAO TESTE",
        }
        for _ in range(120)
    ]
    result = run_universe_build(
        as_of=AS_OF,
        row_iter=iter(rows),
        out_dir=tmp_path / "excl",
        enable_independent_brand=False,
        load_human_dnc=False,
        load_registry=False,
    )
    assert all(r.get("cnpj14") != VALID_CNPJ for r in result["records"])
    excl = result["exclusions"]
    sebrae = [
        e
        for e in excl
        if e.get("cnpj14") == VALID_CNPJ
        or "SEBRAE" in str(e.get("razao_social") or "").upper()
        or "SEBRAE" in str(e.get("reason") or "").upper()
        or "parafiscal" in str(e.get("reason") or "").lower()
        or str(e.get("identity_exclusion_code") or "") == "PARAFISCAL_INSTITUTIONAL"
    ]
    assert sebrae, "SEBRAE-ES must remain in the exclusion universe"
    assert sebrae[0]["outreach_eligibility"] == NOT_CONSTRUCTION
    assert int(sebrae[0].get("rejected_row_count") or 0) == 120
    assert int(result["counts"]["identity_exclusion_entities"]) >= 1
    assert int(result["counts"]["identity_row_exclusions"]) == 120
    exclusions_path = Path(result["exclusions_jsonl_path"])
    dumped = exclusions_path.read_text(encoding="utf-8")
    assert "SEBRAE" in dumped.upper()
    assert "parafiscal" in dumped.lower()
