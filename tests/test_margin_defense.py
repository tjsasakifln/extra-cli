"""Drive the shipped margin-defense projector and export."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.public_read.margin_defense import (
    FACT_FIELDS,
    FORBIDDEN_CONCLUSION_FIELDS,
    EvidenceIdentityError,
    ForbiddenConclusionError,
    project_margin_facts,
)
from scripts.public_read.margin_export import (
    EXPORT_FILENAME,
    build_margin_export,
    render_margin_bytes,
    write_margin_export,
)

REPO = Path(__file__).resolve().parents[1]
AS_OF = "2026-08-15T00:00:00+00:00"


def _complete_record() -> dict:
    return {
        "contrato_id": "83102277000152-2-000626/2026",
        "orgao_cnpj": "83102277000152",
        "orgao_nome": "PREFEITURA MUNICIPAL DE ITAJAI - SC",
        "fornecedor_cnpj": "42275797000180",
        "fornecedor_nome": "GHIMM TEC LTDA",
        "objeto_contrato": "Servicos de engenharia para reforma do auditorio",
        "valor_total": "740874.59",
        "data_assinatura": "2026-08-13",
        "data_inicio": "2026-08-13",
        "data_fim": "2027-01-10",
        "source": "pncp_contracts",
        "source_id": "83102277000152-2-000626/2026",
        "ingested_at": "2026-08-14T11:27:51+00:00",
        "adjustment_base_document_id": "clause-4.1",
        "adjustment_rule_text": "reajuste anual na data-base de 13 de agosto",
        "adjustment_anniversary": "2027-08-13",
        "adjustment_base": "2026-08-13",
        "amendments": [{"id": "aditivo-1", "at": "2026-09-01", "kind": "prazo"}],
        "value_changes": [{"at": "2026-09-01", "delta": "0"}],
        "term_changes": [{"at": "2026-09-01", "days": 30}],
        "scope_changes": [{"at": "2026-09-01", "note": "cobertura telhado"}],
        "measurement_events": [{"at": "2026-09-15", "ref": "med-1"}],
        "payment_events": [{"at": "2026-09-20", "ref": "pag-1"}],
        "suspension": {"at": "2026-10-01"},
        "resumption": {"at": "2026-10-15"},
        "extension": {"at": "2026-11-01"},
        "indices": [{"name": "SINAPI", "competence": "2026-07"}],
        "index_document_id": "clause-4.1",
    }


def test_complete_official_record_is_known() -> None:
    facts = project_margin_facts(_complete_record(), as_of=AS_OF)
    assert facts.canonical_contract_id == "83102277000152-2-000626/2026"
    assert {field.name for field in facts.fields} == set(FACT_FIELDS)
    assert all(field.status == "KNOWN" for field in facts.fields)
    assert facts.reason_codes == ()
    assert facts.fields[4].value["semantics"] == "integral_nominal_instrument"


def test_missing_fields_stay_unknown_with_reason_codes() -> None:
    facts = project_margin_facts({"contrato_id": "x-1", "source_id": "x-1"}, as_of=AS_OF)
    by_name = {field.name: field for field in facts.fields}
    assert by_name["object"].status == "UNKNOWN"
    assert by_name["object"].reason_code == "missing_object"
    assert by_name["nominal_value"].reason_code == "missing_nominal_value"
    assert by_name["adjustment_anniversary"].reason_code == "no_explicit_adjustment_document"
    assert by_name["indices"].reason_code == "index_without_document"
    assert by_name["measurement_events"].reason_code == "source_does_not_offer_measurements"
    assert by_name["payment_events"].reason_code == "source_does_not_offer_payments"
    assert all(field.value is None for field in facts.fields if field.status == "UNKNOWN")
    assert "missing_object" in facts.reason_codes


def test_evidence_without_identity_is_refused() -> None:
    with pytest.raises(EvidenceIdentityError, match="evidence_without_identity"):
        project_margin_facts({"evidence_ref": "cas://pncp/abc", "objeto_contrato": "obra"}, as_of=AS_OF)


def test_index_and_anniversary_without_document_remain_unknown() -> None:
    record = {
        "contrato_id": "x-2",
        "source_id": "x-2",
        "adjustment_anniversary": "2027-01-01",
        "adjustment_base": "2026-01-01",
        "indices": [{"name": "SINAPI"}],
    }
    facts = project_margin_facts(record, as_of=AS_OF)
    by_name = {field.name: field for field in facts.fields}
    assert by_name["adjustment_anniversary"].status == "UNKNOWN"
    assert by_name["adjustment_base"].status == "UNKNOWN"
    assert by_name["indices"].status == "UNKNOWN"
    assert by_name["indices"].reason_code == "index_without_document"


def test_legal_conclusion_fields_are_refused() -> None:
    for field in ("has_right", "imbalance", "loss", "should_adjust"):
        with pytest.raises(ForbiddenConclusionError):
            project_margin_facts({"contrato_id": "x-3", field: True}, as_of=AS_OF)


def test_export_is_deterministic_and_consumer_shaped() -> None:
    payload = {"as_of": AS_OF, "records": [_complete_record(), {"contrato_id": "sparse-1", "source_id": "sparse-1"}]}
    first = render_margin_bytes(payload)
    second = render_margin_bytes(payload)
    assert first == second
    document = build_margin_export(payload)
    assert document["consumer"]["id"] == "web-cfg/diagnostico-defesa-de-margem"
    assert document["grain"] == "canonical_contract_id"
    assert document["value_semantics"]["unknown_policy"]
    assert document["provenance"]["record_count"] == 2
    assert document["freshness"]["policy"] == "contracts-freshness-slo-v1"
    assert document["coverage"]["record_count"] == 2
    assert document["reason_codes"]
    raw = first.decode("utf-8")
    assert "CONFENGE" not in raw
    for banned in FORBIDDEN_CONCLUSION_FIELDS:
        assert f'"{banned}"' not in json.dumps(document["records"])
    sparse = document["records"][1]
    assert sparse["fields"]["nominal_value"]["status"] == "UNKNOWN"
    assert sparse["fields"]["nominal_value"]["value"] is None


def test_shipped_cli_export_margin_twice(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps({"as_of": AS_OF, "records": [_complete_record()]}),
        encoding="utf-8",
    )
    out_1 = tmp_path / "a"
    out_2 = tmp_path / "b"
    command = [sys.executable, "-m", "scripts.public_read", "export-margin"]
    first = subprocess.run(
        [*command, "--payload", str(payload_path), "--out", str(out_1)],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        [*command, "--payload", str(payload_path), "--out", str(out_2)],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    bytes_1 = (out_1 / EXPORT_FILENAME).read_bytes()
    bytes_2 = (out_2 / EXPORT_FILENAME).read_bytes()
    assert bytes_1 == bytes_2
    assert json.loads(first.stdout)["content_hash"] == json.loads(second.stdout)["content_hash"]
    written = write_margin_export({"as_of": AS_OF, "records": [_complete_record()]}, tmp_path / "c")
    assert written.read_bytes() == bytes_1
