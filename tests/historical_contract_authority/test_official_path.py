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
    assert dossier.state != "REJECT"


def test_handoff_ready_official_refs_use_real_sha256() -> None:
    from scripts.historical_contract_authority.cases import case_handoff_ready

    dossier = build_dossier(case_handoff_ready(), as_of="2026-08-17T12:00:00Z", snapshot_hash="snap-hash")
    payload = dossier.as_dict()
    for item in payload["documents"]:
        assert is_sha256(item["binary_sha256"])
        assert is_sha256(item["text_sha256"])
        assert not str(item["binary_sha256"]).startswith("inst-")
