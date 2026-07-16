"""Unit tests for CIGA CKAN transform (DOM-SC public path).

No network. Fixtures mirror autopublicacoes JSON from dados.ciga.sc.gov.br.
"""

from __future__ import annotations

from scripts.crawl.ciga_ckan_crawler import (
    PROCUREMENT_CATEGORIES,
    SOURCE_PURPOSE,
    transform,
    transform_record,
)
from scripts.crawl.credential_validator import validate_source_credentials
from scripts.crawl.registry import lookup

FIXTURE_LICITACAO = {
    "codigo": "7780704",
    "titulo": "EDITAL DE PREGÃO ELETRÔNICO Nº 12/2025",
    "data": "2025-12-01 06:00:01",
    "cod_registro_info_sfinge": None,
    "municipio": "Orleans",
    "entidade": "Prefeitura municipal de Orleans",
    "categoria": "Licitações",
    "link": "https://diariomunicipal.sc.gov.br/?q=id:7780704",
    "texto": "<html><body><p>Objeto: reforma de escola municipal</p></body></html>",
    "url": "https://diariomunicipal.sc.gov.br/?q=id:7780704",
}

FIXTURE_PORTARIA = {
    **FIXTURE_LICITACAO,
    "codigo": "999",
    "categoria": "Portarias",
    "titulo": "PORTARIA Nº 1/2025",
}


def test_source_purpose_is_hybrid_not_coverage_only():
    assert SOURCE_PURPOSE == "hybrid"


def test_registry_ciga_ckan_public_no_credentials():
    info = lookup("ciga_ckan")
    assert info is not None
    assert info.module == "ciga_ckan_crawler"
    assert "open_tenders" in info.capabilities
    assert not info.credentials
    assert not info.credential_names
    ok, missing = validate_source_credentials("ciga_ckan")
    assert ok is True
    assert missing == []


def test_registry_alias_dom_ciga():
    assert lookup("dom-ciga") is not None
    assert lookup("dom-ciga").name == "ciga_ckan"


def test_transform_record_licitacao():
    t = transform_record(FIXTURE_LICITACAO)
    assert t is not None
    assert t["source_id"] == "7780704"
    assert t["source"] == "ciga_ckan"
    assert t["uf"] == "SC"
    assert t["municipio"] == "Orleans"
    assert t["orgao_razao_social"] == "Prefeitura municipal de Orleans"
    assert t["orgao_cnpj"] is None  # never invent CNPJ
    assert t["valor_total_estimado"] is None  # never invent value
    assert t["link_pncp"].startswith("https://diariomunicipal.sc.gov.br")
    assert "Licitações" in (t["modalidade_nome"] or "")
    assert t["data_publicacao"] == "2025-12-01"
    assert t["pncp_id"]
    assert t["content_hash"]
    assert "reforma" in (t["objeto_compra"] or "").lower() or "EDITAL" in (t["objeto_compra"] or "")


def test_transform_skips_non_procurement_category():
    assert transform_record(FIXTURE_PORTARIA) is None


def test_transform_batch():
    out = transform([FIXTURE_LICITACAO, FIXTURE_PORTARIA, {"codigo": None}])
    assert len(out) == 1
    assert out[0]["source_id"] == "7780704"


def test_procurement_categories_include_expected():
    for cat in (
        "Contratos",
        "Licitações",
        "Ata de registro de preços",
        "Extrato de Contrato",
        "Convênios",
    ):
        assert cat in PROCUREMENT_CATEGORIES


def test_transform_missing_codigo():
    assert transform_record({"titulo": "x", "categoria": "Licitações"}) is None
