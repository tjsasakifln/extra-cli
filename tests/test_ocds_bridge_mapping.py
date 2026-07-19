from __future__ import annotations

from scripts.ocds_bridge.mapping import (
    bid_to_ocds_release,
    contract_to_ocds_release,
    essential_fields_preserved,
    ocds_release_to_bid_stub,
)


def test_bid_round_trip_preserves_essentials():
    bid = {
        "numero_controle_pncp": "SC-123",
        "objeto_compra": "Pavimentação asfáltica",
        "situacao_nome": "Divulgada no PNCP",
        "valor_total_estimado": 150000.5,
        "orgao_cnpj": "12.345.678/0001-90",
        "orgao_nome": "Prefeitura Teste",
        "content_hash": "deadbeef",
        "data_publicacao_pncp": "2026-07-01",
        "modalidade_nome": "Pregão Eletrônico",
    }
    rel = bid_to_ocds_release(bid)
    assert rel["tag"] == ["tender"]
    assert rel["tender"]["value"]["amount"] == 150000.5
    assert rel["extra:provenance"]["content_hash"] == "deadbeef"
    back = ocds_release_to_bid_stub(rel)
    lost = essential_fields_preserved(
        bid,
        back,
        [
            "numero_controle_pncp",
            "objeto_compra",
            "situacao_nome",
            "valor_total_estimado",
            "orgao_cnpj",
            "content_hash",
        ],
    )
    assert lost == [], lost


def test_contract_marks_not_paid():
    rel = contract_to_ocds_release(
        {
            "contrato_id": "C-1",
            "valor_global": 10_000,
            "objeto_contrato": "Obra X",
            "fornecedor_cnpj": "99888777000166",
            "orgao_cnpj": "11222333000144",
        }
    )
    assert rel["tag"] == ["contract"]
    assert rel["extra:value_semantics"]["is_paid"] is False
    assert rel["extra:value_semantics"]["is_contracted"] is True
    assert rel["contracts"][0]["value"]["amount"] == 10000.0


def test_linkage_field_preserved():
    rel = contract_to_ocds_release(
        {"contrato_id": "C-2", "numero_controle_pncp_compra": "TENDER-9", "valor_total": 1}
    )
    assert rel["extra:provenance"]["linked_tender_id"] == "TENDER-9"
