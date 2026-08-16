"""Shipped-path tests for the official paving canary (EXTRA-010)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts.contract_comparables.constants import (
    CATALOG_BLOCKED,
    CATALOG_LIVE_CANDIDATE,
    FORBIDDEN_CLAIM_TOKENS,
    FORBIDDEN_METRIC_KEYS,
    OFFICIAL_CANARY_SCHEMA,
    OFFICIAL_LIVE,
    REASON_DATASET_EMPTY,
    REASON_DSN_UNAVAILABLE,
    REASON_LIVE_COLUMNS,
    REASON_PHYSICAL_UNIT,
    STATUS_BLOCKED,
    STATUS_COMPARABLE,
    STATUS_HOLD,
    STATUS_NOT,
)
from scripts.contract_comparables.official_canary import (
    PAVING_SELECT,
    _hashable_copy,
    assert_select_only,
    build_official_envelope,
    observe_late_arrivals,
    refuse_physical_unit_metric,
    run_official_canary,
)
from scripts.contract_comparables.serialize import content_hash_for

REPO = Path(__file__).resolve().parents[2]


def _scan(text: str) -> str:
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _official_row(index: int, *, uf: str = "SC", year: str = "2025") -> dict[str, Any]:
    return {
        "contrato_id": f"83102277000152-2-off{index:03d}/{year}",
        "objeto_contrato": "Pavimentação asfáltica em CBUQ de vias urbanas",
        "valor_total": 700000 + (index * 15000),
        "data_publicacao": f"{year}-06-01",
        "data_inicio": f"{year}-06-01",
        "uf": uf,
        "municipio": "Florianopolis",
        "orgao_cnpj": "83102277000152",
        "orgao_nome": "Prefeitura",
        "fornecedor_cnpj": "00000000000191",
        "fornecedor_nome": "Construtora",
    }


def _official_mappings(n: int = 8) -> list[dict[str, Any]]:
    from scripts.contract_comparables.live import rows_to_records

    return rows_to_records([_official_row(index) for index in range(1, n + 1)])


def test_select_only_guard_accepts_official_sql() -> None:
    assert_select_only(PAVING_SELECT)
    assert PAVING_SELECT.lstrip().upper().startswith("SELECT")


def test_run_official_canary_without_dsn_is_blocked(monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    first = run_official_canary(dsn=None, as_of="2026-08-01")
    second = run_official_canary(dsn=None, as_of="2026-08-01")
    assert first["status"] == STATUS_BLOCKED
    assert first["schema"] == OFFICIAL_CANARY_SCHEMA
    assert REASON_DSN_UNAVAILABLE in first["reason_codes"]
    assert first["catalog_mode"] == CATALOG_BLOCKED
    assert first["catalog_mode"] != OFFICIAL_LIVE
    assert first["document"] is None
    assert first["prerequisite"]
    assert "official-canary" in first["next_command"]
    assert first["reviewable_sample"]["regime"]["status"] == "UNKNOWN"
    assert first["reviewable_sample"]["currency"]["code"] == "UNKNOWN"
    assert first["content_hash"] == second["content_hash"]
    assert first["content_hash"] == content_hash_for(_hashable_copy(first))


def test_physical_unit_metric_is_refused_before_any_denominator() -> None:
    payload = run_official_canary(dsn=None, as_of="2026-08-01", metric="custo/km")
    assert payload["status"] == STATUS_HOLD
    assert REASON_PHYSICAL_UNIT in payload["reason_codes"]
    assert payload["document"] is None
    assert payload["catalog_mode"] != OFFICIAL_LIVE
    metrics = (payload.get("document") or {}).get("metrics") or {}
    for key in FORBIDDEN_METRIC_KEYS:
        assert key not in metrics
    blob = _scan(json.dumps(payload, ensure_ascii=False))
    for token in ("irregularidade", "sobrepreco", "sobrepreço", "fraude", "culpa"):
        assert _scan(token) not in blob


def test_unknown_metric_is_not_comparable() -> None:
    payload = run_official_canary(dsn=None, as_of="2026-08-01", metric="bdi")
    assert payload["status"] == STATUS_NOT
    assert REASON_PHYSICAL_UNIT in payload["reason_codes"]


def test_official_shaped_rows_hold_and_never_official_live() -> None:
    mappings = _official_mappings(8)
    assert all(row["unidade"] is None for row in mappings)
    assert all(row["valor_semantic"] == "unknown" for row in mappings)
    envelope = build_official_envelope(
        mappings,
        as_of="2026-08-01",
        focal_id=None,
        missing_semantic_columns=("unidade", "quantidade", "regime", "modalidade", "valor_semantic"),
        official_columns=("contrato_id", "objeto_contrato", "valor_total", "uf"),
        active_row_count=8,
    )
    assert envelope["status"] == STATUS_HOLD
    assert envelope["status"] != STATUS_COMPARABLE
    assert REASON_LIVE_COLUMNS in envelope["reason_codes"]
    assert envelope["catalog_mode"] == CATALOG_LIVE_CANDIDATE
    assert envelope["catalog_mode"] != OFFICIAL_LIVE
    document = envelope["document"]
    assert document is not None
    assert document["catalog_mode"] != OFFICIAL_LIVE
    assert document["metrics"] in ({}, None) or document["status"] != STATUS_COMPARABLE
    sample = envelope["reviewable_sample"]
    assert sample["n_paving"] == 8
    assert sample["typology"]["label"] == "pavimentacao"
    assert sample["typology"]["sample_precision_reviewed"] is True
    assert sample["regime"]["status"] == "UNKNOWN"
    assert sample["currency"]["code"] == "UNKNOWN"
    assert "SC" in sample["geography"]["ufs"]
    assert 2025 in sample["period"]["years"]
    assert envelope["observability"]["not_comparable_rate"] is not None
    replay = build_official_envelope(
        list(reversed(mappings)),
        as_of="2026-08-01",
        focal_id=mappings[0]["contract_id"],
        missing_semantic_columns=("unidade", "quantidade", "regime", "modalidade", "valor_semantic"),
        official_columns=("contrato_id", "objeto_contrato", "valor_total", "uf"),
        active_row_count=8,
    )
    assert replay["content_hash"] == envelope["content_hash"]
    assert replay["document"]["content_hash"] == document["content_hash"]


def test_empty_official_snapshot_is_blocked() -> None:
    envelope = build_official_envelope(
        [],
        as_of="2026-08-01",
        focal_id=None,
        missing_semantic_columns=("unidade", "quantidade", "regime", "modalidade", "valor_semantic"),
        official_columns=("contrato_id", "objeto_contrato", "valor_total"),
        active_row_count=0,
    )
    assert envelope["status"] == STATUS_BLOCKED
    assert REASON_DATASET_EMPTY in envelope["reason_codes"]
    assert envelope["catalog_mode"] == CATALOG_BLOCKED
    assert envelope["document"] is None


def test_non_paving_rows_do_not_become_comparable() -> None:
    from scripts.contract_comparables.live import rows_to_records

    rows = [
        {
            **_official_row(1),
            "objeto_contrato": "Construção de sede escolar e reforma predial",
        },
        {
            **_official_row(2),
            "objeto_contrato": "Unidade básica de saúde",
        },
    ]
    envelope = build_official_envelope(
        rows_to_records(rows),
        as_of="2026-08-01",
        focal_id=None,
        missing_semantic_columns=("unidade", "quantidade", "regime", "modalidade", "valor_semantic"),
        official_columns=("contrato_id", "objeto_contrato", "valor_total"),
        active_row_count=2,
    )
    assert envelope["status"] != STATUS_COMPARABLE
    assert envelope["status"] == STATUS_BLOCKED
    assert envelope["catalog_mode"] != OFFICIAL_LIVE


def test_late_arrival_invalidates_only_affected_official_group() -> None:
    mappings = _official_mappings(8)
    isolated = _official_mappings(6)
    for row in isolated:
        row["contract_id"] = row["contract_id"].replace("off", "iso")
        row["uf"] = "PR"
        row["municipio"] = "Curitiba"
    universe = mappings + isolated
    late = observe_late_arrivals(
        universe,
        as_of="2026-08-01",
        live_semantic_columns_present=False,
    )
    ids = sorted(item["contract_id"] for item in universe)
    assert late["rectified_contract_id"] == ids[0]
    assert ids[0] in late["affected_groups"]
    assert ids[-1] in late["unaffected_groups"]
    assert ids[-1] not in late["affected_groups"]


def test_unknown_valor_is_not_zero_in_official_mapping() -> None:
    from scripts.contract_comparables.live import rows_to_records
    from scripts.contract_comparables.normalize import records_from_mappings

    row = _official_row(1)
    row["valor_total"] = None
    mapping = rows_to_records([row])[0]
    assert mapping["valor"] is None
    assert mapping["valor_is_unknown"] is True
    record = records_from_mappings([mapping])[0]
    assert record.valor is None
    assert record.valor != Decimal("0")
    assert record.valor_is_unknown is True


def test_outlier_language_absent_from_official_envelope() -> None:
    envelope = build_official_envelope(
        _official_mappings(8),
        as_of="2026-08-01",
        focal_id=None,
        missing_semantic_columns=("unidade", "quantidade", "regime", "modalidade", "valor_semantic"),
        official_columns=("contrato_id",),
        active_row_count=8,
    )
    blob = _scan(json.dumps(envelope, ensure_ascii=False))
    for token in FORBIDDEN_CLAIM_TOKENS:
        assert _scan(token) not in blob
    assert "irregular" not in blob
    assert "culpa" not in blob


def test_refuse_helper_is_the_shipped_entry_for_cost_per_km() -> None:
    payload = refuse_physical_unit_metric(metric="cost_per_km", as_of="2026-08-01")
    via_cli = run_official_canary(metric="cost_per_km", as_of="2026-08-01")
    assert payload["status"] == via_cli["status"] == STATUS_HOLD
    assert payload["reason_codes"] == via_cli["reason_codes"]
    assert payload["content_hash"] == via_cli["content_hash"]


def test_unreachable_dsn_is_blocked() -> None:
    payload = run_official_canary(
        dsn="postgresql://test:test@127.0.0.1:1/extra_test",
        as_of="2026-08-01",
    )
    assert payload["status"] == STATUS_BLOCKED
    assert payload["catalog_mode"] == CATALOG_BLOCKED
    assert payload["catalog_mode"] != OFFICIAL_LIVE
    assert payload["prerequisite"]
    assert any(
        code in payload["reason_codes"] for code in ("host_unavailable", "live_probe_failed", "official_table_missing")
    )


def test_cli_official_canary_replay_without_dsn() -> None:
    env = {key: value for key, value in os.environ.items() if key not in {"LOCAL_DATALAKE_DSN", "NATIONAL_INTEL_DSN"}}
    command = [
        sys.executable,
        "-m",
        "scripts.contract_comparables",
        "official-canary",
        "--as-of",
        "2026-08-01",
        "--metric",
        "valor_integral_nominal",
    ]
    first = subprocess.run(command, cwd=REPO, check=True, capture_output=True, text=True, env=env)
    second = subprocess.run(command, cwd=REPO, check=True, capture_output=True, text=True, env=env)
    doc1 = json.loads(first.stdout)
    doc2 = json.loads(second.stdout)
    assert doc1["status"] == STATUS_BLOCKED
    assert doc1["content_hash"] == doc2["content_hash"]
    assert doc1["reason_codes"] == doc2["reason_codes"]
    assert doc1["catalog_mode"] != OFFICIAL_LIVE
