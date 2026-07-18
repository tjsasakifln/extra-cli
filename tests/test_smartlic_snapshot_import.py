"""Unit tests for SmartLic snapshot import bridge (no live SmartLic required)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.integrations.smartlic_snapshot_import import (
    CONTRACTS_FIELD_MAP,
    content_hash_record,
    digits_only,
    filter_universe,
    in_period,
    load_json_records,
    map_record,
    run_import,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "smartlic"


def test_digits_only():
    assert digits_only("12.345.678/0001-99") == "12345678000199"
    assert digits_only(None) is None


def test_load_and_map_contracts():
    rows = load_json_records(FIXTURES / "pncp_supplier_contracts_sample.json")
    assert len(rows) == 2
    rec = map_record(
        rows[0],
        CONTRACTS_FIELD_MAP,
        table="pncp_supplier_contracts",
        import_run_id="test-run",
        source_repo="https://github.com/tjsasakifln/SmartLic",
        source_commit="abc",
        extraction_ts="2026-07-18T00:00:00Z",
        snapshot_hash="deadbeef",
    )
    assert rec["contrato_id"] == "SL-CONTRACT-001"
    assert rec["fornecedor_cnpj"] == "12345678000199"
    assert rec["valor_total"] == 150000.50
    assert rec["_provenance"]["not_live"] is True
    assert rec["_provenance"]["not_coverage"] is True
    assert rec["_provenance"]["not_freshness"] is True
    assert rec["content_hash"]


def test_period_and_universe_filters():
    rows = load_json_records(FIXTURES / "pncp_supplier_contracts_sample.json")
    mapped = [
        map_record(
            r,
            CONTRACTS_FIELD_MAP,
            table="pncp_supplier_contracts",
            import_run_id="t",
            source_repo="r",
            source_commit="c",
            extraction_ts="t",
            snapshot_hash="h",
        )
        for r in rows
    ]
    # period: only 2024+
    in_win = [r for r in mapped if in_period(r, "2024-01-01", "2025-12-31")]
    assert len(in_win) == 1
    # universe: only cnpj8 of first orgao
    uni = {"83102373"}
    kept, rejected = filter_universe(mapped, uni, table="pncp_supplier_contracts")
    assert len(kept) == 1
    assert rejected == 1
    assert kept[0]["contrato_id"] == "SL-CONTRACT-001"


def test_content_hash_stable():
    a = {"contrato_id": "X", "fornecedor_cnpj": "1", "valor_total": 1, "objeto_contrato": "o"}
    b = {"contrato_id": "X", "fornecedor_cnpj": "1", "valor_total": 1, "objeto_contrato": "o"}
    assert content_hash_record(a, list(a.keys())) == content_hash_record(b, list(b.keys()))


def test_dry_run_cli(tmp_path):
    out = tmp_path / "manifest.json"
    code = run_import(
        type(
            "A",
            (),
            {
                "table": "pncp_supplier_contracts",
                "json_file": str(FIXTURES / "pncp_supplier_contracts_sample.json"),
                "source_dsn": None,
                "dsn": None,
                "date_from": "2024-01-01",
                "date_to": "2025-12-31",
                "filter_universe": False,
                "years": 3,
                "page_size": 500,
                "source_repo": "https://github.com/tjsasakifln/SmartLic",
                "source_commit": "93ea196",
                "extraction_ts": "2026-07-18T00:00:00Z",
                "import_run_id": "unit-dry",
                "extra_head": "test",
                "manifest_out": str(out),
                "dry_run": True,
            },
        )()
    )
    assert code == 0
    manifest = json.loads(out.read_text(encoding="utf-8"))
    assert manifest["dry_run"] is True
    assert manifest["stats"]["read"] == 2
    assert manifest["stats"]["mapped"] == 1  # period filter
    assert "snapshot_not_live" in manifest["disclaimers"]
