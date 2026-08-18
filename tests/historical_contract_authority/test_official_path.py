"""Official/snapshot path: HOLD not REJECT; real SHA-256; fetch and assemble."""

from __future__ import annotations

from pathlib import Path

from scripts.contract_publication.official_snapshot import row_to_record
from scripts.historical_contract_authority.acquire import document_from_mapping
from scripts.historical_contract_authority.cli import record_to_case
from scripts.historical_contract_authority.engine import build_dossier
from scripts.historical_contract_authority.gates import hashed_located
from scripts.historical_contract_authority.schema import is_sha256


def _snapshot_row() -> dict:
    return row_to_record(
        {
            "contrato_id": "1536471100010442024001",
            "orgao_cnpj": "82940433000194",
            "orgao_nome": "Municipio de Brusque",
            "fornecedor_cnpj": "07894512000133",
            "fornecedor_nome": "Construtora Vale Verde Ltda",
            "objeto_contrato": "Pavimentacao asfaltica de vias urbanas",
            "valor_total": "180000000.00",
            "data_assinatura": "2024-03-01",
            "data_inicio": "2024-04-01",
            "data_fim": "2025-04-01",
            "uf": "SC",
            "municipio": "Brusque",
            "source": "pncp",
            "source_id": "1536471100010442024001",
            "ingested_at": "2024-10-01T12:00:00+00:00",
            "is_active": True,
        }
    )


def test_snapshot_shaped_record_holds_not_reject() -> None:
    case = record_to_case(_snapshot_row())
    assert case["technical_question"] == ""
    assert case["claims"] == []
    assert case["catalog_mode"] == "official_projection"
    dossier = build_dossier(case, as_of="2026-08-17T12:00:00Z", fetch=False, snapshot_hash="snap-lake-1")
    assert dossier.state == "HOLD_FOR_DATA"
    assert "no_specific_technical_question" not in dossier.reason_codes
    assert "missing_technical_question" in dossier.reason_codes or "insufficient_documents" in dossier.reason_codes
    assert "missing_official_instrument" in dossier.reason_codes


def test_hashed_located_rejects_slug_and_accepts_real_sha256() -> None:
    slug = document_from_mapping(
        {
            "document_id": "x",
            "class": "instrument",
            "family": "instrument",
            "url": "https://pncp.gov.br/app/contratos/x",
            "locator": {"page": "1", "section": "cl.1"},
            "binary_sha256": "inst-001-bin".ljust(64, "0"),
            "text": "",
            "bytes_len": 0,
        }
    )
    assert not is_sha256("inst-001-bin".ljust(64, "0"))
    assert not hashed_located((slug,))
    real = document_from_mapping(
        {
            "document_id": "y",
            "class": "instrument",
            "family": "instrument",
            "url": "https://pncp.gov.br/app/contratos/y",
            "locator": {"page": "1", "section": "cl.1"},
            "text": "Contrato de pavimentacao. Valor original R$ 1.000,00.",
        }
    )
    assert is_sha256(real.binary_sha256)
    assert hashed_located((real,))


def test_fetch_and_assemble_from_official_docs(tmp_path: Path) -> None:
    instrument = tmp_path / "instrumento.txt"
    additive = tmp_path / "aditivo.txt"
    instrument.write_text("Contrato de pavimentacao. Valor original R$ 4.250.000,00. Assinatura registrada.")
    additive.write_text("Termo aditivo de prazo: acrescimo de 120 dias.")
    case = record_to_case(_snapshot_row())
    case["documents"] = [
        {
            "url": instrument.resolve().as_uri(),
            "class": "instrument",
            "family": "instrument",
            "locator": {"page": "1", "section": "cl.1"},
        },
        {
            "url": additive.resolve().as_uri(),
            "class": "amendment_term",
            "family": "amendment",
            "locator": {"page": "1", "section": "art.1"},
        },
    ]
    budget = {"requests": 0, "bytes": 0}
    dossier = build_dossier(
        case,
        as_of="2026-08-17T12:00:00Z",
        fetch=True,
        budget=budget,
        snapshot_hash="snap-fetch-1",
    )
    assert budget["requests"] >= 1
    assert dossier.documents
    assert all(is_sha256(item.binary_sha256) for item in dossier.documents)
    assert any(item.klass == "FACT" for item in dossier.claims)
    assert any(item.kind == "amendment_term" for item in dossier.chronology)
    assert dossier.editorial.central_question
    assert "what is the contract value?" not in dossier.editorial.central_question.lower()
    assert dossier.state == "HOLD_FOR_DATA"
    assert dossier.catalog_mode == "official_projection"
    assert dossier.state != "HANDOFF_READY"


def test_klass_without_supporting_text_does_not_invent_fact() -> None:
    case = record_to_case(_snapshot_row())
    case["documents"] = [
        {
            "document_id": "empty-adt",
            "class": "amendment_term",
            "family": "amendment",
            "url": "https://pncp.gov.br/app/contratos/empty-adt",
            "locator": {"page": "1", "section": "art.1"},
            "text": "Documento administrativo sem mencao a prazo ou valor.",
        },
        {
            "document_id": "inst-plain",
            "class": "instrument",
            "family": "instrument",
            "url": "https://pncp.gov.br/app/contratos/inst-plain",
            "locator": {"page": "1", "section": "cl.1"},
            "text": "Contrato de pavimentacao asfaltica. Assinatura registrada.",
        },
    ]
    dossier = build_dossier(case, as_of="2026-08-17T12:00:00Z", fetch=False, snapshot_hash="snap-klass")
    assert not any(item.claim_id.startswith("fact-prazo") for item in dossier.claims)
    assert not any(item.kind == "amendment_term" for item in dossier.chronology)
    assert dossier.state != "HANDOFF_READY"


def test_run_live_missing_dsn_is_unavailable_not_success(tmp_path: Path, monkeypatch) -> None:
    from scripts.historical_contract_authority.cli import run_live

    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = run_live(
        output=tmp_path,
        dsn=None,
        limit=2,
        as_of="2026-08-17T12:00:00Z",
    )
    live = result["live"]
    assert live["official_live"] is False
    assert live["source_kind"] == "blocked"
    assert "dsn_absent" in live["reason_codes"]
    assert result["handoff"]["status"]["handoff_ready_count"] == 0
    assert result["handoff"]["status"]["catalog_mode"] == "official_unavailable"
    assert result["handoff"]["manifest"]["catalog_mode"] == "official_unavailable"
    assert all(item.get("catalog_mode") != "fixture" for item in result["dossiers"])
    assert not (tmp_path / "dossiers").exists() or not list((tmp_path / "dossiers").glob("*.json"))


def test_run_live_refuses_committed_fixture_dir() -> None:
    import pytest

    from scripts.historical_contract_authority.cli import LIVE_OVERWRITE_FIXTURE, main, run_live
    from scripts.historical_contract_authority.schema import HANDOFF_DIR

    with pytest.raises(ValueError, match=LIVE_OVERWRITE_FIXTURE):
        run_live(output=HANDOFF_DIR, dsn="postgresql://invalid:invalid@127.0.0.1:1/nope", limit=1)
    assert main(["--mode", "live", "--limit", "1"]) == 2


def test_handoff_ready_official_refs_use_real_sha256() -> None:
    from scripts.historical_contract_authority.cases import case_handoff_ready

    dossier = build_dossier(case_handoff_ready(), as_of="2026-08-17T12:00:00Z", snapshot_hash="snap-hash")
    payload = dossier.as_dict()
    for item in payload["documents"]:
        assert is_sha256(item["binary_sha256"])
        assert is_sha256(item["text_sha256"])
        assert not str(item["binary_sha256"]).startswith("inst-")
