"""Tests for Deliverable A org ranking schema and DoD audit."""
from __future__ import annotations

from scripts.ops.deliverable_a_org_ranking import (
    audit_report,
    build_row_from_raw,
    fixture_demo_report,
    ticket_medio,
)


def test_ticket_medio_formula() -> None:
    mean, formula = ticket_medio(1000.0, 4)
    assert mean == 250.0
    assert "valor_total" in formula
    mean0, formula0 = ticket_medio(100.0, 0)
    assert mean0 == 0.0
    assert "zero" in formula0


def test_fixture_report_audits_clean() -> None:
    report = fixture_demo_report()
    assert report.status == "OK"
    assert report.profile.get("version") is not None
    assert report.period["inicio"] and report.period["fim"]
    z = report.zero_vs_not_consulted
    assert z["consulted_zero"] >= 1
    assert z["not_consulted"] >= 1
    assert z["consulted_with_data"] >= 1
    # row with low data quality has limitation
    weak = [r for r in report.rows if (r.get("data_quality_score") or 1) < 1]
    assert weak
    assert all(r.get("data_quality_limitation") for r in weak)
    audited = audit_report(report)
    assert audited["ok"] is True
    assert audited["summary"]["fail"] == 0
    assert audited["summary"]["pass"] == 10


def test_zero_vs_not_consulted_distinct() -> None:
    zero = build_row_from_raw(
        rank=1,
        orgao="Z",
        cnpj="1",
        uf="SC",
        qtd=0,
        valor_total=0,
        semantic="CONTRATADO",
        modalidades={},
        periodo_inicio="2025-01-01",
        periodo_fim="2025-12-31",
        fontes=["x"],
        consultado=True,
    )
    missing = build_row_from_raw(
        rank=2,
        orgao="N",
        cnpj="2",
        uf="SC",
        qtd=0,
        valor_total=0,
        semantic="CONTRATADO",
        modalidades={},
        periodo_inicio="2025-01-01",
        periodo_fim="2025-12-31",
        fontes=[],
        consultado=False,
    )
    assert zero.resultado_zero is True
    assert missing.resultado_zero is False
    assert missing.consultado is False


def test_missing_ticket_fails_audit() -> None:
    report = fixture_demo_report()
    data = {
        "status": "OK",
        "period": report.period,
        "sources": report.sources,
        "coverage_notes": report.coverage_notes,
        "ranking_bias_warning": report.ranking_bias_warning,
        "zero_vs_not_consulted": report.zero_vs_not_consulted,
        "rows": [{"qtd_contratacoes": 1, "valor_total": 10, "valor_semantica": "X"}],
        "profile": report.profile,
    }
    audited = audit_report(data)
    assert audited["ok"] is False
