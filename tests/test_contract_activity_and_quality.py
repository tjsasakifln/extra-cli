"""#309 UNKNOWN vs ACTIVE_PROVEN and #312 date/value quarantine."""

from __future__ import annotations

from datetime import date

from scripts.contracts_truth import (
    ACTIVE_PROVEN,
    QUARANTINED,
    REVIEW,
    UNKNOWN,
    VALID,
    annotate_transformed_contract,
    classify_contract_activity,
    classify_contract_quality,
    in_active_proven,
    report_ready_allowed,
)
from scripts.crawl import contracts_crawler as cc


def test_missing_status_is_unknown_and_not_active_proven() -> None:
    activity = classify_contract_activity(
        raw_status=None,
        vigencia_inicio=None,
        vigencia_fim=None,
        is_active_default=True,
        today=date(2026, 8, 13),
    )
    assert activity.state == UNKNOWN
    assert in_active_proven(activity) is False
    assert "missing_status_and_vigencia" in activity.reasons


def test_proven_vigencia_window_is_active_proven() -> None:
    activity = classify_contract_activity(
        raw_status="vigente",
        vigencia_inicio="2026-01-01",
        vigencia_fim="2026-12-31",
        today=date(2026, 8, 13),
    )
    assert activity.state == ACTIVE_PROVEN
    assert in_active_proven(activity) is True


def test_year_8406_and_inverted_vigencia_are_quarantined() -> None:
    year_8406 = classify_contract_quality(
        data_assinatura="8406-05-16",
        data_inicio="2026-01-01",
        data_fim="2026-12-31",
        valor=1000,
        today=date(2026, 8, 13),
    )
    assert year_8406.state == QUARANTINED
    assert any("8406" in reason for reason in year_8406.reasons)
    assert report_ready_allowed(year_8406) is False

    inverted = classify_contract_quality(
        data_inicio="2026-12-31",
        data_fim="2026-01-01",
        valor=1000,
        today=date(2026, 8, 13),
    )
    assert inverted.state == QUARANTINED
    assert "inverted_vigencia" in inverted.reasons

    ancient = classify_contract_quality(data_assinatura="1890-01-01", valor=10)
    assert ancient.state == REVIEW

    negative = classify_contract_quality(valor=-1)
    assert negative.state == QUARANTINED
    assert "negative_value" in negative.reasons

    trillion = classify_contract_quality(valor=1_000_000_000_001)
    assert trillion.state == QUARANTINED
    assert "value_exceeds_one_trillion" in trillion.reasons

    ok = classify_contract_quality(
        data_assinatura="2026-05-16",
        data_inicio="2026-05-16",
        data_fim="2027-05-15",
        valor=150_000.50,
        today=date(2026, 8, 13),
    )
    assert ok.state == VALID
    assert report_ready_allowed(ok) is True


def test_transform_record_attaches_unknown_and_quarantine_on_live_path() -> None:
    raw = {
        "numeroControlePNCP": "11111111000191-1-000001/2026",
        "orgaoEntidade": {"cnpj": "11111111000191", "razaoSocial": "ORGAO X"},
        "unidadeOrgao": {"ufSigla": "SC", "municipioNome": "FLORIANOPOLIS", "nomeUnidade": "PMF"},
        "niFornecedor": "22222222000100",
        "tipoPessoa": "PJ",
        "nomeRazaoSocialFornecedor": "FORNECEDOR Y",
        "objetoContrato": "Pavimentacao",
        "valorGlobal": 2000,
        "dataAssinatura": "8406-05-16",
        "dataVigenciaInicio": "2026-12-01",
        "dataVigenciaFim": "2026-01-01",
    }
    record = cc._transform_record(raw)
    assert record is not None
    assert record["status_normalized"] == UNKNOWN
    assert record["quality_state"] == QUARANTINED
    assert record["report_ready"] is False
    assert record["canonical_contract_id"].startswith("pncp:")
    assert "11111111000191-1-000001/2026" in record["canonical_contract_id"]
    # Raw official fields remain as parsed; quality is a label, not a rewrite.
    assert record["data_assinatura"] is not None
    annotated = annotate_transformed_contract(dict(record), raw=raw)
    assert annotated["quality_state"] == QUARANTINED
