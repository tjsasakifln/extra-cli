"""Unit tests for sc_compras_crawler.smoke() (mocked network)."""

from __future__ import annotations

from unittest.mock import patch

from scripts.crawl import sc_compras_crawler as sc


class TestScComprasSmoke:
    def test_smoke_ok(self):
        payload = {
            "conteudo": [
                {
                    "id": 1,
                    "processo": "0001/2026",
                    "tipo": "Pregão Eletrônico",
                    "orgaoSigla": "SED",
                    "orgaoNome": "Secretaria de Estado da Educação",
                    "objeto": "Teste",
                    "entregaProposta": None,
                    "abertura": None,
                    "situacao": "Aberto",
                }
            ],
            "totalElementos": 1,
            "pagina": 1,
            "porPagina": 5,
            "totalPaginas": 1,
        }
        with patch.object(sc, "_api_request", return_value=payload):
            result = sc.smoke(ano=2026)
        assert result["ok"] is True
        assert result["count"] == 1
        assert result["total_elementos"] == 1
        assert result["sample_ids"] == [1]
        assert result["public_json"] is True
        assert "api/editais" in result["url"]

    def test_smoke_failure(self):
        with patch.object(sc, "_api_request", return_value=None):
            result = sc.smoke(ano=2026)
        assert result["ok"] is False
        assert result["error"]

    def test_crawl_smoke_mode_list_only(self):
        list_payload = [
            {
                "id": 10,
                "processo": "0010/2026",
                "tipo": "Dispensa",
                "orgaoSigla": "PM",
                "orgaoNome": "PM SC",
                "objeto": "Obj",
                "entregaProposta": None,
                "abertura": None,
                "situacao": "Homologado",
            }
        ]
        with (
            patch.object(
                sc,
                "smoke",
                return_value={"ok": True, "ano": 2026, "error": None},
            ),
            patch.object(sc, "_fetch_api_list", return_value=list_payload),
            patch.object(sc, "_fetch_api_detail") as detail_mock,
        ):
            records = sc.crawl(mode="smoke")
        assert len(records) == 1
        assert records[0]["api_id"] == 10
        detail_mock.assert_not_called()
