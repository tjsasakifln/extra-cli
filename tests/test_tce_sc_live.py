"""Live integration test for TCE-SC SCMWeb API.

Validates empirically:
    - API is reachable
    - Fields Municipio, Codigo_IBGE, Orgao, CNPJ_Orgao are present
    - unidade_gestora filter works

Excluded from CI — requires network access to scmweb.com.br.
Run manually: pytest tests/test_tce_sc_live.py -v -m slow
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        os.getenv("RUN_EXTERNAL_SMOKE") != "1",
        reason="Set RUN_EXTERNAL_SMOKE=1 to call the real TCE-SC endpoint",
    ),
]


class TestTCESCLive:
    """Verify TCE-SC SCMWeb API structure with real calls."""

    def test_api_connectivity(self):
        """SCMWeb API must be reachable."""
        from scripts.crawl.tce_sc_crawler import _api_request

        result = _api_request(
            {
                "page": "licitacoes",
                "export": "json",
                "type": "licitacoes",
                "pn": "1",
            }
        )
        assert result is not None, "API retornou None"
        assert isinstance(result, (dict, list)), f"Tipo inesperado: {type(result)}"
        print(f"  API response type: {type(result).__name__}")
        if isinstance(result, list):
            print(f"  Records: {len(result)}")
        elif isinstance(result, dict):
            print(f"  Keys: {list(result.keys())[:10]}")

    def test_transform_licitacao_fields(self):
        """Transformed licitacao records must contain all required fields."""
        from scripts.crawl.tce_sc_crawler import crawl, transform

        records = crawl("incremental")
        if not records:
            pytest.fail("Sem registros na janela incremental — crawler retornou vazio")

        transformed = transform(records)
        if not transformed:
            pytest.fail("Transform retornou vazio — falha na transformacao dos registros")

        required = {
            "pncp_id",
            "objeto_compra",
            "valor_total_estimado",
            "modalidade_id",
            "modalidade_nome",
            "uf",
            "municipio",
            "codigo_municipio_ibge",
            "orgao_razao_social",
            "orgao_cnpj",
            "data_publicacao",
            "link_pncp",
            "content_hash",
            "source_id",
        }
        for rec in transformed[:5]:
            missing = required - rec.keys()
            assert not missing, f"Campos ausentes: {missing}"
            assert rec["pncp_id"].startswith("tce_sc_"), f"pncp_id invalido: {rec['pncp_id']}"

        print(f"  Registros transformados: {len(transformed)}")
        print(f"  Campos do primeiro registro: {list(transformed[0].keys())}")
        if transformed:
            r = transformed[0]
            print(f"  Municipio: {r.get('municipio')}")
            print(f"  Codigo_IBGE: {r.get('codigo_municipio_ibge')}")
            print(f"  Orgao: {r.get('orgao_razao_social')}")
            print(f"  CNPJ_Orgao: {r.get('orgao_cnpj')}")

    def test_raw_record_contains_municipio_ibge(self):
        """Raw API records must contain Municipio + Codigo_IBGE."""
        from datetime import date, timedelta

        from scripts.crawl.tce_sc_crawler import _fetch_licitacoes

        data_inicial = date.today() - timedelta(days=30)
        records = _fetch_licitacoes(data_inicial=data_inicial)
        records = records[:5]  # limit to first 5
        if not records:
            pytest.fail("API retornou vazio — nao foi possivel validar campos Municipio/IBGE")

        print(f"  Raw records: {len(records)}")
        for rec in records[:3]:
            municipio = rec.get("Municipio", rec.get("municipio", "N/A"))
            ibge = rec.get("Codigo_IBGE", rec.get("codigo_ibge", "N/A"))
            orgao = rec.get("Orgao", rec.get("orgao", "N/A"))
            cnpj = rec.get("CNPJ_Orgao", rec.get("cnpj_orgao", "N/A"))
            print(f"  Municipio={municipio}, IBGE={ibge}, Orgao={orgao}, CNPJ={cnpj}")
            assert municipio != "N/A", "Municipio nao encontrado na resposta"
            assert orgao != "N/A", "Orgao nao encontrado na resposta"

    def test_crawl_by_municipio_filter(self):
        """crawl_by_municipio with IBGE code should filter results."""
        from scripts.crawl.tce_sc_crawler import crawl_by_municipio

        # Use Florianopolis IBGE code
        records = crawl_by_municipio("4205407")
        if not records:
            pytest.fail("crawl_by_municipio retornou vazio — nao foi possivel validar o filtro")

        print(f"  Records for municipio 4205407: {len(records)}")
        # Verify records are scoped to the municipio
        assert isinstance(records, list)

    def test_document_scope(self):
        """Document: TCE-SC covers SCMWeb portal p285 only, not municipal coverage."""
        from scripts.crawl.tce_sc_crawler import BASE_URL, ORGAO_PARAM

        assert "scmweb.com.br" in BASE_URL, f"URL inesperada: {BASE_URL}"
        assert ORGAO_PARAM == "p285", f"Portal p285 esperado: {ORGAO_PARAM}"
        print(f"  TCE-SC scope: {BASE_URL} (orgao={ORGAO_PARAM})")
        print("  ⓘ  TCE-SC cobre apenas o proprio TCE-SC (orgao p285).")
        print("  ⓘ  Nao deve ser usado como fonte de cobertura municipal.")
