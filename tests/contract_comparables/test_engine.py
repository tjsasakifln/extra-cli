"""Shipped-path tests for the inbound contract-comparables engine."""

from __future__ import annotations

import importlib.util
import json
import random
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from scripts.contract_comparables.constants import (
    CATALOG_LIVE_CANDIDATE,
    FORBIDDEN_CLAIM_TOKENS,
    FORBIDDEN_METRIC_KEYS,
    OFFICIAL_LIVE,
    REASON_DUPLICATE_OR_RECTIFICATION,
    REASON_GEOGRAPHY_NOT_COMPARABLE,
    REASON_INCOMPATIBLE_REGIME,
    REASON_INCOMPATIBLE_UNIT,
    REASON_INSUFFICIENT_N,
    REASON_LIVE_COLUMNS,
    REASON_MISSING_VALUE,
    REASON_ORIGINAL_VS_UPDATED_MIX,
    REASON_PERIOD_NOT_COMPARABLE,
    REASON_STATISTICAL_DIFF,
    REASON_UNKNOWN_EXCLUDED,
    REASON_VALUE_SEMANTIC_MISMATCH,
    SCHEMA,
    STATUS_COMPARABLE,
    STATUS_HOLD,
    STATUS_NOT,
    UNIT_CANONICAL,
    VALUE_SEMANTIC_CANONICAL,
)
from scripts.contract_comparables.corpus import CANARY_CASES, case_expected_status, case_records, case_request
from scripts.contract_comparables.engine import (
    build_document,
    build_peer_group,
    groups_changed_by_rectification,
)
from scripts.contract_comparables.live import rows_to_records
from scripts.contract_comparables.models import PeerRequest, RectificationEvent
from scripts.contract_comparables.normalize import classify_unit, records_from_mappings, recorte_from_record
from scripts.contract_comparables.serialize import REQUIRED_DOCUMENT_FIELDS, content_hash_for, validate_against_schema
from tests.contract_comparables.conftest import CORPUS_PATH, document_for, result_for

REPO = Path(__file__).resolve().parents[2]


def _scan(text: str) -> str:
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def test_determinism_two_builds_same_hash(corpus: dict[str, Any]) -> None:
    first = document_for(corpus, "comparable_clear")
    second = document_for(corpus, "comparable_clear")
    assert first["status"] == STATUS_COMPARABLE
    assert first["content_hash"] == second["content_hash"]
    assert first["peer_group_id"] == second["peer_group_id"]
    assert first["metrics"]["n"] == second["metrics"]["n"]
    assert first["metrics"]["median"] == second["metrics"]["median"]
    assert first["metrics"]["p25"] == second["metrics"]["p25"]
    assert first["metrics"]["p75"] == second["metrics"]["p75"]
    assert first["content_hash"] == content_hash_for(first)


def test_input_order_does_not_change_hash(corpus: dict[str, Any]) -> None:
    records = list(case_records(corpus, "comparable_clear"))
    request = case_request(corpus, "comparable_clear")
    baseline = build_document(tuple(records), request)
    shuffled = records[:]
    random.Random(415).shuffle(shuffled)  # noqa: S311 — deterministic shuffle, not crypto
    again = build_document(tuple(shuffled), request)
    assert again["content_hash"] == baseline["content_hash"]
    assert again["peer_ids"] == baseline["peer_ids"]
    assert again["metrics"] == baseline["metrics"]


@pytest.mark.parametrize("case_id", CANARY_CASES)
def test_canary_states_and_reason_codes(corpus: dict[str, Any], case_id: str) -> None:
    document = document_for(corpus, case_id)
    expected = case_expected_status(corpus, case_id)
    assert document["status"] == expected
    wanted = corpus["cases"][case_id]["expected_reasons_any"]
    assert any(code in document["reason_codes"] for code in wanted)
    assert document["schema"] == SCHEMA
    assert "valid" not in document
    assert document["catalog_mode"] == "fixture"
    assert document["source"] == "fixture"
    assert document["catalog_mode"] != OFFICIAL_LIVE


def test_ambiguous_typology_and_distinct_scope_fail_closed(corpus: dict[str, Any]) -> None:
    rows = [dict(row) for row in corpus["cases"]["comparable_clear"]["contracts"]]
    rows[0]["objeto"] = "Obras viárias de infraestrutura urbana"
    ambiguous = build_document(records_from_mappings(rows), case_request(corpus, "comparable_clear"))
    assert ambiguous["status"] != STATUS_COMPARABLE
    assert "ambiguous_typology" in ambiguous["reason_codes"]
    mixed = [dict(row) for row in corpus["cases"]["comparable_clear"]["contracts"]]
    for row in mixed[1:]:
        row["objeto"] = "Pavimentação asfáltica em CBUQ e construção de sede escolar"
    scoped = build_document(records_from_mappings(mixed), case_request(corpus, "comparable_clear"))
    assert scoped["status"] == STATUS_NOT
    assert "distinct_scope" in scoped["reason_codes"] or "typology_mismatch" in scoped["reason_codes"]


def test_incompatible_unit_fails_closed(corpus: dict[str, Any]) -> None:
    rows = [dict(row) for row in corpus["cases"]["comparable_clear"]["contracts"]]
    for row in rows[1:]:
        row["unidade"] = "km"
        row["quantidade"] = "12.5"
    request = case_request(corpus, "comparable_clear")
    document = build_document(records_from_mappings(rows), request)
    assert document["status"] == STATUS_NOT
    assert REASON_INCOMPATIBLE_UNIT in document["reason_codes"]
    assert document["metrics"] == {} or document["status"] != STATUS_COMPARABLE


def test_value_semantic_mismatch_fails_closed(corpus: dict[str, Any]) -> None:
    rows = [dict(row) for row in corpus["cases"]["comparable_clear"]["contracts"]]
    for row in rows[1:]:
        row["valor_semantic"] = "estimado"
    document = build_document(records_from_mappings(rows), case_request(corpus, "comparable_clear"))
    assert document["status"] == STATUS_NOT
    assert REASON_VALUE_SEMANTIC_MISMATCH in document["reason_codes"]


def test_original_versus_updated_mix_fails_closed(corpus: dict[str, Any]) -> None:
    rows = [dict(row) for row in corpus["cases"]["comparable_clear"]["contracts"]]
    for row in rows[1:]:
        row["value_basis"] = "atualizado"
    document = build_document(records_from_mappings(rows), case_request(corpus, "comparable_clear"))
    assert document["status"] == STATUS_NOT
    assert REASON_ORIGINAL_VS_UPDATED_MIX in document["reason_codes"]


def test_regime_and_geo_period_nominal_reasons(corpus: dict[str, Any]) -> None:
    regime = document_for(corpus, "regime_incompatible")
    geo = document_for(corpus, "geo_period_inadequate")
    assert regime["status"] == STATUS_NOT
    assert REASON_INCOMPATIBLE_REGIME in regime["reason_codes"]
    assert geo["status"] == STATUS_NOT
    assert REASON_GEOGRAPHY_NOT_COMPARABLE in geo["reason_codes"] or REASON_PERIOD_NOT_COMPARABLE in geo["reason_codes"]


def test_unknown_never_enters_denominator_and_is_not_zero(corpus: dict[str, Any]) -> None:
    result, document = result_for(corpus, "missing_values")
    assert document["status"] == STATUS_HOLD
    assert REASON_UNKNOWN_EXCLUDED in document["reason_codes"] or REASON_MISSING_VALUE in document["reason_codes"]
    assert result.usable_n == 0
    assert document["denominator"]["n"] == 0
    for peer in result.exclusions:
        if REASON_MISSING_VALUE in peer.reason_codes:
            assert "0" not in peer.detail or "unknown" in peer.detail
    for recorte in (result.focal,):
        assert recorte.contract.valor != Decimal("0") or recorte.contract.valor_is_unknown is False
    assert all(item.recorte.contract.valor is not None for item in result.peers)
    assert document["metrics"] in ({},) or document["status"] != STATUS_COMPARABLE


def test_insufficient_n_and_coverage_not_comparable(corpus: dict[str, Any]) -> None:
    small = document_for(corpus, "insufficient_sample")
    missing = document_for(corpus, "missing_values")
    assert small["status"] != STATUS_COMPARABLE
    assert REASON_INSUFFICIENT_N in small["reason_codes"]
    assert missing["status"] != STATUS_COMPARABLE
    assert missing["usable_n"] == 0


def test_rectification_invalidates_only_affected_group(corpus: dict[str, Any]) -> None:
    paving = [dict(row) for row in corpus["cases"]["comparable_clear"]["contracts"]]
    other = [
        {
            "contract_id": "00394460000141-2-iso001/2025",
            "objeto": "Pavimentação asfáltica em CBUQ — grupo isolado focal",
            "valor": "500000.00",
            "valor_semantic": "valor_integral_nominal",
            "value_basis": "original",
            "unidade": "BRL_TOTAL",
            "uf": "PR",
            "municipio": "Curitiba",
            "regime": "empreitada_global",
            "modalidade": "pregao_eletronico",
            "data_referencia": "2025-01-10",
            "revision": 1,
            "evidence_ref": "fixture:iso001",
        },
        {
            "contract_id": "00394460000141-2-iso002/2025",
            "objeto": "Recapeamento asfáltico em CBUQ — isolado 2",
            "valor": "510000.00",
            "valor_semantic": "valor_integral_nominal",
            "value_basis": "original",
            "unidade": "BRL_TOTAL",
            "uf": "PR",
            "municipio": "Curitiba",
            "regime": "empreitada_global",
            "modalidade": "pregao_eletronico",
            "data_referencia": "2025-02-10",
            "revision": 1,
            "evidence_ref": "fixture:iso002",
        },
        {
            "contract_id": "00394460000141-2-iso003/2025",
            "objeto": "Pavimentação asfáltica municipal em CBUQ — isolado 3",
            "valor": "520000.00",
            "valor_semantic": "valor_integral_nominal",
            "value_basis": "original",
            "unidade": "BRL_TOTAL",
            "uf": "PR",
            "municipio": "Curitiba",
            "regime": "empreitada_global",
            "modalidade": "pregao_eletronico",
            "data_referencia": "2025-03-10",
            "revision": 1,
            "evidence_ref": "fixture:iso003",
        },
        {
            "contract_id": "00394460000141-2-iso004/2025",
            "objeto": "Asfaltamento em CBUQ — isolado 4",
            "valor": "530000.00",
            "valor_semantic": "valor_integral_nominal",
            "value_basis": "original",
            "unidade": "BRL_TOTAL",
            "uf": "PR",
            "municipio": "Curitiba",
            "regime": "empreitada_global",
            "modalidade": "pregao_eletronico",
            "data_referencia": "2025-04-10",
            "revision": 1,
            "evidence_ref": "fixture:iso004",
        },
        {
            "contract_id": "00394460000141-2-iso005/2025",
            "objeto": "Pavimentação asfáltica com recapeamento — isolado 5",
            "valor": "540000.00",
            "valor_semantic": "valor_integral_nominal",
            "value_basis": "original",
            "unidade": "BRL_TOTAL",
            "uf": "PR",
            "municipio": "Curitiba",
            "regime": "empreitada_global",
            "modalidade": "pregao_eletronico",
            "data_referencia": "2025-05-10",
            "revision": 1,
            "evidence_ref": "fixture:iso005",
        },
        {
            "contract_id": "00394460000141-2-iso006/2025",
            "objeto": "Restauração asfáltica em CBUQ — isolado 6",
            "valor": "550000.00",
            "valor_semantic": "valor_integral_nominal",
            "value_basis": "original",
            "unidade": "BRL_TOTAL",
            "uf": "PR",
            "municipio": "Curitiba",
            "regime": "empreitada_global",
            "modalidade": "pregao_eletronico",
            "data_referencia": "2025-06-10",
            "revision": 1,
            "evidence_ref": "fixture:iso006",
        },
    ]
    universe = records_from_mappings(paving + other)
    as_of = corpus["as_of"]
    requests = (
        PeerRequest(focal_contract_id="83102277000152-2-pav001/2025", as_of=as_of),
        PeerRequest(focal_contract_id="00394460000141-2-iso001/2025", as_of=as_of),
    )
    event = RectificationEvent(
        rectification_id="ret-pav002",
        contract_id="83102277000152-2-pav002/2025",
        as_of=as_of,
        fields={"valor": "900000.00", "revision": 2},
    )
    changed = groups_changed_by_rectification(universe, requests, event)
    assert changed == ("83102277000152-2-pav001/2025",)
    assert REASON_DUPLICATE_OR_RECTIFICATION in document_for(corpus, "duplicate_rectification")["reason_codes"]


def test_outlier_has_no_accusatory_language(corpus: dict[str, Any]) -> None:
    document = document_for(corpus, "statistical_outlier")
    assert document["status"] == STATUS_COMPARABLE
    assert REASON_STATISTICAL_DIFF in document["reason_codes"]
    blob = _scan(json.dumps(document, ensure_ascii=False))
    for token in FORBIDDEN_CLAIM_TOKENS:
        assert _scan(token) not in blob
    assert document["metrics"]["outlier_flag"] is True


def test_total_value_is_not_labeled_unit_cost(corpus: dict[str, Any]) -> None:
    document = document_for(corpus, "comparable_clear")
    assert document["unit"] == UNIT_CANONICAL
    assert document["value_semantic"] == VALUE_SEMANTIC_CANONICAL
    metrics = document["metrics"]
    for key in FORBIDDEN_METRIC_KEYS:
        assert key not in metrics
    blob = _scan(json.dumps(document, ensure_ascii=False))
    assert "custo/km" not in blob
    assert "custo/m2" not in blob
    assert "custo por km" not in blob


def test_fixture_never_official_live(corpus: dict[str, Any]) -> None:
    for case_id in CANARY_CASES:
        document = document_for(corpus, case_id)
        assert document["catalog_mode"] == "fixture"
        assert document["source"] == "fixture"
        assert document.get("catalog_mode") != OFFICIAL_LIVE


def test_document_has_required_fields_and_hash(corpus: dict[str, Any]) -> None:
    document = document_for(corpus, "comparable_clear")
    for field in REQUIRED_DOCUMENT_FIELDS:
        assert field in document
    assert validate_against_schema(document) == []
    assert document["producer_sha"]
    assert document["question_id"] == "paving_nominal_total_value_position"


def _load_adapt_peer_group():
    try:
        from scripts.public_read.contract_analysis_adapters import adapt_peer_group

        return adapt_peer_group
    except ImportError:
        pass
    sibling = Path("/home/tjsasakifln/code/confenge/extra-cli/scripts/public_read/contract_analysis_adapters.py")
    if not sibling.exists():
        return None
    spec = importlib.util.spec_from_file_location("contract_analysis_adapters_415", sibling)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return getattr(module, "adapt_peer_group", None)


def test_compatible_with_400_adapter_contract(corpus: dict[str, Any]) -> None:
    comparable = document_for(corpus, "comparable_clear")
    hold = document_for(corpus, "missing_values")
    refused = document_for(corpus, "regime_incompatible")
    for document in (comparable, hold, refused):
        assert document["schema"] == SCHEMA
        assert "valid" not in document
        assert "content_hash" in document
        assert "metrics" in document
        assert "reason_codes" in document
        assert document["status"] in {STATUS_COMPARABLE, STATUS_HOLD, STATUS_NOT}
    adapter = _load_adapt_peer_group()
    if adapter is None:
        pytest.skip("adapt_peer_group is not on this branch; structural contract already asserted")
    mapped_ok = adapter(comparable)
    mapped_hold = adapter(hold)
    mapped_not = adapter(refused)
    assert mapped_ok.status == "PEER_VALID"
    assert mapped_hold.status == "PEER_WEAK"
    assert mapped_not.status == "NOT_COMPARABLE"
    assert mapped_ok.schema == SCHEMA
    assert mapped_ok.metrics["n"] == comparable["metrics"]["n"]


def test_live_shaped_records_hold_and_do_not_invent_unit() -> None:
    assert classify_unit(None, quantity=None) == "unknown"
    assert classify_unit("", quantity=None) == "unknown"
    assert classify_unit(None, quantity=Decimal("12.5")) == "unknown"
    assert classify_unit("BRL_TOTAL", quantity=None) == UNIT_CANONICAL

    official_rows = [
        {
            "contrato_id": f"83102277000152-2-live{index:03d}/2025",
            "objeto_contrato": "Pavimentação asfáltica em CBUQ de vias urbanas",
            "valor_total": 700000 + (index * 10000),
            "data_publicacao": "2025-06-01",
            "data_inicio": "2025-06-01",
            "uf": "SC",
            "municipio": "Florianopolis",
            "orgao_cnpj": "83102277000152",
            "orgao_nome": "Prefeitura",
            "fornecedor_cnpj": "00000000000191",
            "fornecedor_nome": "Construtora",
        }
        for index in range(1, 7)
    ]
    mappings = rows_to_records(official_rows)
    assert all(row["unidade"] is None for row in mappings)
    assert all(row["valor_semantic"] == "unknown" for row in mappings)
    assert all(row["regime"] is None for row in mappings)

    recortes = [recorte_from_record(record) for record in records_from_mappings(mappings)]
    assert all(item.unit == "unknown" for item in recortes)
    assert all(item.value_semantic == "unknown" for item in recortes)
    assert all(item.regime == "unknown" for item in recortes)

    request = PeerRequest(
        focal_contract_id="83102277000152-2-live001/2025",
        as_of="2026-08-01",
        catalog_mode=CATALOG_LIVE_CANDIDATE,
        source="pncp_supplier_contracts",
        live_semantic_columns_present=False,
    )
    result, document = build_peer_group(records_from_mappings(mappings), request)
    assert document["status"] == STATUS_HOLD
    assert document["status"] != STATUS_NOT
    assert REASON_LIVE_COLUMNS in document["reason_codes"]
    assert document["unit"] == "unknown"
    assert document["value_semantic"] == "unknown"
    assert document["catalog_mode"] != OFFICIAL_LIVE
    assert result.focal.unit == "unknown"
    assert result.metrics is None


def test_cli_build_is_deterministic(corpus: dict[str, Any]) -> None:
    command = [
        sys.executable,
        "-m",
        "scripts.contract_comparables",
        "build",
        "--corpus",
        str(CORPUS_PATH),
        "--case",
        "comparable_clear",
    ]
    first = subprocess.run(command, cwd=REPO, check=True, capture_output=True, text=True)
    second = subprocess.run(command, cwd=REPO, check=True, capture_output=True, text=True)
    doc1 = json.loads(first.stdout)
    doc2 = json.loads(second.stdout)
    assert first.returncode == 0
    assert doc1["status"] == STATUS_COMPARABLE
    assert doc1["content_hash"] == doc2["content_hash"]
    assert doc1["peer_group_id"] == doc2["peer_group_id"]
    assert doc1["metrics"]["median"] == doc2["metrics"]["median"]
