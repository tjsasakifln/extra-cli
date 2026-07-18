"""Tests for Deliverable B competitor mapping (DoD)."""
from __future__ import annotations

from scripts.ops.deliverable_b_competitors import (
    SelectionRule,
    active_contract_record,
    audit_report,
    desagio_from_pair,
    fixture_candidates,
    fixture_report,
    select_competitors,
)


def test_fixture_selects_15_with_rule() -> None:
    report = fixture_report(15)
    assert report.status == "OK"
    assert report.valid_count == 15
    assert len(report.rows) == 15
    assert report.selection_rule["target_n"] == 15
    assert "n_contratos" in report.selection_rule["sort_keys"]
    audited = audit_report(report)
    assert audited["ok"] is True
    assert audited["summary"]["fail"] == 0
    assert audited["summary"]["pass"] >= 13


def test_insufficient_does_not_pad() -> None:
    report = select_competitors(fixture_candidates(4), SelectionRule(target_n=15))
    assert report.status == "INSUFFICIENT"
    assert report.valid_count == 4
    assert len(report.rows) == 4
    assert report.insufficiency["insufficient"] is True
    assert report.insufficiency["presented_all_valid"] is True
    assert audit_report(report)["ok"] is True


def test_desagio_requires_pair() -> None:
    pct, status, _ = desagio_from_pair(
        valor_estimado=100.0, valor_homologado=90.0, same_certame_lote_item=True
    )
    assert status == "PRESENTED"
    assert pct == 10.0
    pct2, status2, _ = desagio_from_pair(
        valor_estimado=100.0, valor_homologado=90.0, same_certame_lote_item=False
    )
    assert status2 == "INSUFFICIENT_PAIR"
    assert pct2 is None


def test_active_requires_vigencia_status() -> None:
    ok = active_contract_record(
        vigencia_inicio="2025-01-01",
        vigencia_fim="2026-12-31",
        status="ATIVO",
        status_as_of="2026-07-18",
    )
    assert ok["is_active_claim_allowed"] is True
    bad = active_contract_record(
        vigencia_inicio=None,
        vigencia_fim=None,
        status="ATIVO",
        status_as_of=None,
    )
    assert bad["is_active_claim_allowed"] is False


def test_capacity_is_hypothesis() -> None:
    report = fixture_report(5)
    for row in report.rows:
        cap = row["capacidade_operacional"]
        assert cap["label"] == "HYPOTHESIS"
        assert cap["claim_as_fact_forbidden"] is True


def test_cnpj_required_filters_noise() -> None:
    cands = [{"cnpj": "", "n_contratos": 99, "valor_contratado_total": 1e9, "nome": "noise"}]
    cands += fixture_candidates(5)
    report = select_competitors(cands, SelectionRule(target_n=15, require_cnpj=True))
    assert all(len(r["cnpj"]) == 14 for r in report.rows)
