"""Tests for the SC Compras scope contract (#240)."""

from __future__ import annotations

import pytest

from scripts.crawl.sc_compras_scope import (
    checkpoint_compatible,
    entity_verdict,
    invalidate_checkpoint,
    normalize_orgao,
    prove_entities,
    reconcile_counts,
    sha256_payload,
)


def test_counts_reconcile_and_reject_drift() -> None:
    proof = reconcile_counts(
        total_elementos=20,
        pages=2,
        chunks=2,
        persisted=18,
        rejected=2,
        page_size=10,
    )
    assert proof.balanced
    assert proof.pages_match
    with pytest.raises(ValueError, match="count_mismatch"):
        reconcile_counts(total_elementos=20, pages=2, chunks=2, persisted=10, rejected=2, page_size=10)
    with pytest.raises(ValueError, match="pagination_mismatch"):
        reconcile_counts(total_elementos=20, pages=1, chunks=1, persisted=20, rejected=0, page_size=10)


def test_orgao_cnpj_municipio_are_normalized() -> None:
    orgao = normalize_orgao(
        nome="  Secretaria   da Saude ",
        cnpj="12.345.678/0001-99",
        municipio=" Florianopolis ",
    )
    assert orgao["orgao_cnpj"] == "12345678000199"
    assert orgao["orgao_nome"] == "Secretaria da Saude"
    assert orgao["municipio"] == "Florianopolis"
    with pytest.raises(ValueError, match="cnpj_invalido"):
        normalize_orgao(nome="X", cnpj="123", municipio="Y")


def test_found_and_zero_require_complete_query() -> None:
    assert entity_verdict(query_complete=False, found_count=4) == "SCOPE_INCOMPLETE"
    assert entity_verdict(query_complete=True, found_count=2) == "FOUND"
    assert entity_verdict(query_complete=True, found_count=0) == "ZERO_CONFIRMED"


def test_snapshot_change_invalidates_checkpoint() -> None:
    snap_a = sha256_payload({"ano": 2025, "total": 2610})
    snap_b = sha256_payload({"ano": 2025, "total": 2611})
    assert checkpoint_compatible(snap_a, snap_a) is True
    assert checkpoint_compatible(snap_a, snap_b) is False
    assert invalidate_checkpoint(snap_a, snap_b) == "invalidate"
    assert invalidate_checkpoint(snap_a, snap_a) == "keep"


def test_entity_proof_hashes_raw_and_respects_completeness() -> None:
    report = prove_entities(
        rows=[{"ente_id": "e1", "objeto": "obra"}],
        universe=[
            {"ente_id": "e1", "nome": "Pref A", "cnpj": "12345678000199", "municipio": "A"},
            {"ente_id": "e2", "nome": "Pref B", "cnpj": "12345678000198", "municipio": "B"},
            {"ente_id": "e3", "nome": "Pref C", "cnpj": "12345678000197", "municipio": "C"},
        ],
        snapshot={"pages": 53, "total": 2610},
        previous_checkpoint_hash="old",
        query_complete_by_ente={"e1": True, "e2": True, "e3": False},
    )
    by_id = {e["ente_id"]: e for e in report["entities"]}
    assert by_id["e1"]["verdict"] == "FOUND"
    assert by_id["e2"]["verdict"] == "ZERO_CONFIRMED"
    assert by_id["e3"]["verdict"] == "SCOPE_INCOMPLETE"
    assert report["checkpoint"] == "invalidate"
    assert by_id["e1"]["raw_sha256"]
    assert report["sla_hours"] == 24
