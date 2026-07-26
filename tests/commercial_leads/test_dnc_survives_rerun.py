"""DO_NOT_CONTACT must suppress leads across ranking and survive re-run."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from scripts.commercial_leads.profile import load_profile
from scripts.commercial_leads.scoring import rank_leads, score_supplier
from scripts.commercial_leads.signals import ContractRow, compute_signals_for_supplier

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "config/commercial_profiles/confenge.yaml"
AS_OF = date(2026, 7, 25)
# Valid CNPJs used across tests
CNPJ_A = "11222333000181"
CNPJ_B = "34028316000103"


def _contracts(cnpj: str, n_recent: int = 4) -> list[ContractRow]:
    prior = [
        ContractRow(
            contrato_id=f"P{cnpj[-4:]}{i}",
            orgao_cnpj="11111111000191",
            orgao_nome="ORGAO A",
            fornecedor_cnpj=cnpj,
            fornecedor_nome="EMPRESA",
            objeto_contrato="obra de pavimentacao",
            valor_total=80_000,
            data_inicio=None,
            data_fim=None,
            data_publicacao=AS_OF - timedelta(days=400 + i),
            uf="SC",
            source="pncp",
            source_id=f"P{i}",
        )
        for i in range(3)
    ]
    recent = [
        ContractRow(
            contrato_id=f"R{cnpj[-4:]}{i}",
            orgao_cnpj="22222222000191",
            orgao_nome="ORGAO B",
            fornecedor_cnpj=cnpj,
            fornecedor_nome="EMPRESA",
            objeto_contrato="construcao de edificio",
            valor_total=900_000,
            data_inicio=AS_OF - timedelta(days=60),
            data_fim=AS_OF + timedelta(days=40),
            data_publicacao=AS_OF - timedelta(days=20 + i),
            uf="PR",
            source="pncp",
            source_id=f"R{i}",
        )
        for i in range(n_recent)
    ]
    return prior + recent


def _score(cnpj: str):
    profile = load_profile(PROFILE)
    sigs = compute_signals_for_supplier(_contracts(cnpj), profile, as_of=AS_OF)
    return score_supplier(
        cnpj14=cnpj,
        razao_social=f"EMPRESA {cnpj}",
        signal_results=sigs,
        profile=profile,
        total_value=3_000_000,
        contract_count=7,
        last_publication=AS_OF.isoformat(),
    )


def test_rank_leads_excludes_do_not_contact():
    profile = load_profile(PROFILE)
    a = _score(CNPJ_A)
    b = _score(CNPJ_B)
    ranked_all = rank_leads([a, b], profile)
    assert {L.cnpj14 for L in ranked_all} == {CNPJ_A, CNPJ_B}

    ranked_dnc = rank_leads(
        [a, b],
        profile,
        suppressed_cnpjs={CNPJ_A},
        state_by_cnpj={CNPJ_A: "DO_NOT_CONTACT"},
    )
    assert CNPJ_A not in {L.cnpj14 for L in ranked_dnc}
    assert CNPJ_B in {L.cnpj14 for L in ranked_dnc}


def test_dnc_via_state_map_only():
    profile = load_profile(PROFILE)
    a = _score(CNPJ_A)
    b = _score(CNPJ_B)
    ranked = rank_leads(
        [a, b],
        profile,
        state_by_cnpj={CNPJ_A: "DO_NOT_CONTACT", CNPJ_B: "REVIEWED"},
    )
    cnpjs = [L.cnpj14 for L in ranked]
    assert CNPJ_A not in cnpjs
    assert CNPJ_B in cnpjs


def test_dnc_survives_second_ranking_pass():
    """Simulate re-run: first rank includes A; after DNC override, second rank excludes A."""
    profile = load_profile(PROFILE)
    a = _score(CNPJ_A)
    b = _score(CNPJ_B)
    first = rank_leads([a, b], profile)
    assert any(L.cnpj14 == CNPJ_A for L in first)

    # Human marks DNC — re-run ranking with state map (as pipeline does)
    second = rank_leads(
        [a, b],
        profile,
        state_by_cnpj={CNPJ_A: "DO_NOT_CONTACT"},
    )
    assert all(L.cnpj14 != CNPJ_A for L in second)
    # package top must not list DNC
    package = [
        {"cnpj14": L.cnpj14, "commercial_state": "NEW" if L.cnpj14 != CNPJ_A else "DO_NOT_CONTACT"}
        for L in second
    ]
    assert all(p["commercial_state"] != "DO_NOT_CONTACT" for p in package)
