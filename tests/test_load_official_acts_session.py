from scripts.crawl.ingestion.load_official_acts_session import map_doe


def test_map_public_doe_ckan_preserves_identity_and_provenance():
    mapped = map_doe(
        {
            "source": "doe_sc_public_ckan",
            "external_id": "1068775",
            "publication_date": "2025-04-01",
            "edition_number": "22483",
            "orgao_nome": "Fundações Estaduais",
            "source_category": "CONTRATOS",
            "title": "Extrato do Contrato 02/FCEE/2025",
            "source_url": "https://portal.doe.sea.sc.gov.br/repositorio/dadosabertos/publicacoes_2025.csv",
            "resource_id": "resource-1",
            "resource_url": "https://portal.doe.sea.sc.gov.br/file.csv",
            "record_hash": "a" * 64,
            "act_category": "extrato_contrato",
            "act_confidence": 0.719,
        },
        "run-1",
    )

    assert mapped["source"] == "doe_sc_public_ckan"
    assert mapped["external_id"] == "1068775"
    assert mapped["publication_date"] == "2025-04-01"
    assert mapped["orgao_nome"] == "Fundações Estaduais"
    assert mapped["source_url"].startswith("https://portal.doe.sea.sc.gov.br/")
    assert mapped["proveniencia"]["resource_id"] == "resource-1"
