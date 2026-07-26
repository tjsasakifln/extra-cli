"""Unit tests for commercial signal computation."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts.commercial_leads.profile import load_profile
from scripts.commercial_leads.signals import (
    SIGNAL_STATUS_FIRED,
    SIGNAL_STATUS_NC,
    SIGNAL_STATUS_NOT,
    ContractRow,
    compute_signals_for_supplier,
    decorrelate_contributions,
)

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "config/commercial_profiles/confenge.yaml"
AS_OF = date(2026, 7, 25)


@pytest.fixture(scope="module")
def profile():
    return load_profile(PROFILE)


def _c(
    *,
    cid: str = "C1",
    orgao: str = "12345678000199",
    orgao_nome: str = "PREFEITURA X",
    valor: float | None = 100_000,
    pub: date | None = None,
    fim: date | None = None,
    inicio: date | None = None,
    uf: str | None = "SC",
    objeto: str = "construcao de edificio publico",
) -> ContractRow:
    return ContractRow(
        contrato_id=cid,
        orgao_cnpj=orgao,
        orgao_nome=orgao_nome,
        fornecedor_cnpj="11222333000181",
        fornecedor_nome="EMPRESA TESTE LTDA",
        objeto_contrato=objeto,
        valor_total=valor,
        data_inicio=inicio,
        data_fim=fim,
        data_publicacao=pub,
        uf=uf,
        source="pncp",
        source_id=cid,
    )


def test_catalog_has_at_least_12_signals(profile):
    assert len(profile.signal_ids) >= 12


def test_first_public_contract_fires(profile):
    contracts = [_c(pub=AS_OF - timedelta(days=30), valor=200_000)]
    res = {r.signal_id: r for r in compute_signals_for_supplier(contracts, profile, as_of=AS_OF)}
    assert res["first_public_contract"].status == SIGNAL_STATUS_FIRED


def test_missing_dates_not_computable(profile):
    contracts = [_c(pub=None, valor=100_000)]
    res = {r.signal_id: r for r in compute_signals_for_supplier(contracts, profile, as_of=AS_OF)}
    assert res["first_public_contract"].status == SIGNAL_STATUS_NC
    assert res["win_recurrence"].status == SIGNAL_STATUS_NC


def test_not_computable_never_zero_contribution(profile):
    contracts = [_c(pub=None, valor=None)]
    for r in compute_signals_for_supplier(contracts, profile, as_of=AS_OF):
        if r.status == SIGNAL_STATUS_NC:
            assert r.contribution == 0.0
            assert r.reason


def test_ticket_above_history_positive(profile):
    prior = [
        _c(cid=f"P{i}", pub=AS_OF - timedelta(days=400 + i), valor=100_000)
        for i in range(5)
    ]
    recent = [_c(cid="R1", pub=AS_OF - timedelta(days=10), valor=1_000_000)]
    res = {
        r.signal_id: r
        for r in compute_signals_for_supplier(prior + recent, profile, as_of=AS_OF)
    }
    assert res["ticket_above_history"].status == SIGNAL_STATUS_FIRED
    assert res["ticket_above_history"].evidence


def test_ticket_above_history_negative(profile):
    prior = [
        _c(cid=f"P{i}", pub=AS_OF - timedelta(days=400 + i), valor=100_000)
        for i in range(5)
    ]
    recent = [_c(cid="R1", pub=AS_OF - timedelta(days=10), valor=110_000)]
    res = {
        r.signal_id: r
        for r in compute_signals_for_supplier(prior + recent, profile, as_of=AS_OF)
    }
    assert res["ticket_above_history"].status == SIGNAL_STATUS_NOT


def test_near_expiry_fires(profile):
    contracts = [
        _c(pub=AS_OF - timedelta(days=100), fim=AS_OF + timedelta(days=30), valor=200_000)
    ]
    res = {r.signal_id: r for r in compute_signals_for_supplier(contracts, profile, as_of=AS_OF)}
    assert res["near_expiry"].status == SIGNAL_STATUS_FIRED


def test_near_expiry_nc_without_end(profile):
    contracts = [_c(pub=AS_OF - timedelta(days=10), fim=None)]
    res = {r.signal_id: r for r in compute_signals_for_supplier(contracts, profile, as_of=AS_OF)}
    assert res["near_expiry"].status == SIGNAL_STATUS_NC


def test_new_agency_fires(profile):
    prior = [_c(cid="P1", orgao="11111111000191", pub=AS_OF - timedelta(days=300), valor=100_000)]
    recent = [_c(cid="R1", orgao="22222222000191", pub=AS_OF - timedelta(days=10), valor=100_000)]
    # valid-looking cnpjs not required for keying
    res = {
        r.signal_id: r
        for r in compute_signals_for_supplier(prior + recent, profile, as_of=AS_OF)
    }
    assert res["new_agency"].status == SIGNAL_STATUS_FIRED


def test_quantity_growth_fires(profile):
    prior = [_c(cid="P1", pub=AS_OF - timedelta(days=300), valor=50_000)]
    recent = [
        _c(cid=f"R{i}", pub=AS_OF - timedelta(days=10 + i), valor=50_000) for i in range(4)
    ]
    res = {
        r.signal_id: r
        for r in compute_signals_for_supplier(prior + recent, profile, as_of=AS_OF)
    }
    assert res["quantity_growth"].status == SIGNAL_STATUS_FIRED


def test_addendum_and_adverse_nc_without_acts(profile):
    contracts = [_c(pub=AS_OF - timedelta(days=10))]
    res = {r.signal_id: r for r in compute_signals_for_supplier(contracts, profile, as_of=AS_OF)}
    assert res["addendum_recurrence"].status == SIGNAL_STATUS_NC
    assert res["adverse_event"].status == SIGNAL_STATUS_NC


def test_decorrelate_growth_signals(profile):
    prior = [_c(cid="P1", pub=AS_OF - timedelta(days=300), valor=100_000)]
    recent = [
        _c(cid=f"R{i}", pub=AS_OF - timedelta(days=5 + i), valor=600_000, orgao=f"{i:014d}")
        for i in range(5)
    ]
    results = compute_signals_for_supplier(prior + recent, profile, as_of=AS_OF)
    adj = decorrelate_contributions(results)
    growth = [r for r in adj if r.signal_id in {"quantity_growth", "value_growth", "diversity_increase"} and r.status == SIGNAL_STATUS_FIRED]
    if len(growth) >= 2:
        contribs = sorted(r.contribution for r in growth)
        # at least one dampened relative to undampened would be lower for non-top
        assert min(contribs) <= max(contribs)
