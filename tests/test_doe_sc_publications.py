from __future__ import annotations

from scripts.crawl import doe_sc_publications as doe


def test_selects_latest_public_csv() -> None:
    package = {
        "resources": [
            {"id": "x", "format": "XLSX", "name": "publicacoes_2025.xlsx"},
            {"id": "a", "format": "CSV", "name": "publicacoes_2024.csv"},
            {"id": "b", "format": "CSV", "name": "publicacoes_2025.csv"},
        ]
    }
    assert doe.select_csv_resource(package)["id"] == "b"
    assert doe.select_csv_resource(package, year=2024)["id"] == "a"


def test_parse_and_normalize_procurement_publication() -> None:
    raw = (
        "DATA_PUBLICACAO;PUBLICACAO;CATEGORIA;ASSUNTO;EDICAO;TITULO_PUBLICACAO\n"
        "01/04/2025;1068775;Fundações Estaduais;CONTRATOS;22483;EXTRATO DO CONTRATO 02/2025\n"
    ).encode()
    rows = doe.parse_publications(raw)
    item = doe.normalize_publication(
        rows[0], resource={"id": "r1", "url": "https://example.test/publicacoes.csv"}
    )
    assert item is not None
    assert item["source"] == "doe_sc_public_ckan"
    assert item["publication_date"] == "2025-04-01"
    assert item["external_id"] == "1068775"
    assert len(item["record_hash"]) == 64


def test_non_procurement_publication_is_ignored() -> None:
    row = {
        "DATA_PUBLICACAO": "01/04/2025",
        "PUBLICACAO": "1",
        "CATEGORIA": "Saúde",
        "ASSUNTO": "PORTARIA",
        "EDICAO": "1",
        "TITULO_PUBLICACAO": "Designa servidor para função",
    }
    assert doe.normalize_publication(row, resource={"id": "r", "url": "https://example.test"}) is None
