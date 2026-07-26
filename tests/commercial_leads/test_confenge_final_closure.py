"""Unit tests for CONFENGE final evidence-closure pure functions.

Drive shipped modules — no reimplementation, no hardcoded PASS theater.
"""

from __future__ import annotations

from datetime import date

from scripts.ops.confenge_contract_status import (
    lifecycle_gate_ok,
    normalize_contract_status,
    reconcile_status_counts,
)


def test_normalize_active_via_data_fim_future() -> None:
    st = normalize_contract_status(
        {"data_fim": "2099-01-01", "contrato_id": "x"},
        as_of=date(2026, 7, 26),
    )
    assert st["normalized_status"] == "ACTIVE"
    assert st["is_active"] is True
    assert st["status_reason"] == "data_fim_null_or_future_v1"
    assert st["status_source"] == "derived_from_data_fim"


def test_normalize_completed_via_data_fim_past_with_rule() -> None:
    st = normalize_contract_status(
        {"data_fim": "2020-01-01", "contrato_id": "y"},
        as_of=date(2026, 7, 26),
    )
    assert st["normalized_status"] == "COMPLETED"
    assert st["is_active"] is False
    assert st["status_reason"] == "data_fim_before_as_of_v1"


def test_normalize_cancelled_from_source_token() -> None:
    st = normalize_contract_status(
        {"situacao": "Cancelado", "data_fim": "2020-01-01"},
        as_of=date(2026, 7, 26),
    )
    assert st["normalized_status"] == "CANCELLED"
    assert st["status_reason"] == "source_status_cancelled_v1"
    assert st["status_source"] == "source_feed_field"


def test_reconcile_status_sum_invariant() -> None:
    rows = [
        {"normalized_status": "ACTIVE"},
        {"normalized_status": "ACTIVE"},
        {"normalized_status": "COMPLETED"},
        {"normalized_status": "UNKNOWN"},
    ]
    rec = reconcile_status_counts(rows)
    assert rec["status_sum_matches_total"] is True
    assert rec["snapshot_total_contracts"] == 4
    assert rec["snapshot_active_contracts"] == 2
    assert rec["snapshot_completed_contracts"] == 1
    life = lifecycle_gate_ok(rec)
    assert life["ok"] is True
    assert life["has_active"] and life["has_closed_lifecycle"]


def test_lifecycle_gate_fails_without_closed() -> None:
    rows = [{"normalized_status": "ACTIVE"} for _ in range(5)]
    rec = reconcile_status_counts(rows)
    life = lifecycle_gate_ok(rec)
    assert life["ok"] is False
    assert life["block"] == "BLOCKED_SOURCE_DOES_NOT_PROVIDE_CONTRACT_LIFECYCLE"


def test_adversarial_historical_ratio_never_strong_by_concentration() -> None:
    """1 active relevant + 9 closed irrelevant → historical ratio 0.10."""
    from scripts.commercial_leads.sector_fit import compute_contract_history_stats

    rows = [
        {
            "objeto_contrato": "execução de obra de engenharia civil pavimentação",
            "is_active": True,
            "data_publicacao": "2025-01-01",
            "orgao_cnpj": "111",
        }
    ]
    for i in range(9):
        rows.append(
            {
                "objeto_contrato": "fornecimento de merenda escolar e generos alimenticios",
                "is_active": False,
                "data_publicacao": f"2024-0{(i % 9) + 1}-01",
                "orgao_cnpj": f"org{i}",
            }
        )
    stats = compute_contract_history_stats(rows)
    total = int(stats["total_contract_count_full_history"])
    relevant = int(stats["relevant_contract_count"])
    ratio = float(stats["relevant_contract_ratio_full_history"])
    assert total == 10
    assert relevant == 1
    assert abs(ratio - 0.10) < 1e-9
    # Classification must not be STRONG from concentration alone at 0.10
    from scripts.commercial_leads.sector_fit import classify_supplier_sector_fit

    dec = classify_supplier_sector_fit(
        razao_social="EMPRESA XYZ COMERCIO LTDA",
        contracts=rows,
        history_is_full=True,
    )
    assert dec.classification != "STRONG_ENGINEERING_FIT"
    assert ratio < 0.5


def test_official_source_classifier_rejects_brasilapi() -> None:
    from scripts.ops.confenge_official_cnpj import FALLBACK_SOURCES, _is_official_source

    assert "brasilapi_fallback" in FALLBACK_SOURCES
    assert _is_official_source("brasilapi_fallback", None) is False
    assert _is_official_source("brasilapi", "brasilapi") is False
    assert (
        _is_official_source(
            "rfb_public_cadastral_via_opencnpj", "receita_federal_dados_abertos"
        )
        is True
    )


def test_dump_package_not_metadata_theater(tmp_path) -> None:
    """Restorable package must include real CSV rows, not integrity_padding."""
    from scripts.ops.confenge_dump_restore import COLUMNS

    assert "contrato_id" in COLUMNS
    assert "normalized_status" in COLUMNS
    # marker theater keys must not be required columns
    assert "integrity_padding" not in COLUMNS
