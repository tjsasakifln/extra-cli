"""Unit tests for scripts/crawl/smoke_pncp_public.py (mocked network)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.crawl import smoke_pncp_public as smoke


def _sample_payload(n: int = 2, uf: str = "SC") -> dict:
    items = []
    for i in range(n):
        items.append(
            {
                "numeroControlePNCP": f"00000000000191-2-00000{i}/2026",
                "unidadeOrgao": {
                    "ufSigla": uf if i == 0 else "PR",
                    "municipioNome": "Florianopolis" if uf == "SC" and i == 0 else "Curitiba",
                    "nomeUnidade": "UG TEST",
                },
                "orgaoEntidade": {"cnpj": "00000000000191", "razaoSocial": "ORGAO"},
            }
        )
    return {
        "data": items,
        "totalRegistros": 99,
        "totalPaginas": 10,
        "numeroPagina": 1,
        "paginasRestantes": 9,
        "empty": False,
    }


class TestUfHelpers:
    def test_uf_from_unidade_ok(self):
        assert smoke.uf_from_unidade({"unidadeOrgao": {"ufSigla": "sc"}}) == "SC"

    def test_uf_from_unidade_missing(self):
        assert smoke.uf_from_unidade({}) is None
        assert smoke.uf_from_unidade({"unidadeOrgao": {}}) is None
        assert smoke.uf_from_unidade({"unidadeOrgao": "bad"}) is None

    def test_filter_items_by_uf(self):
        items = _sample_payload(2, uf="SC")["data"]
        sc = smoke.filter_items_by_uf(items, "SC")
        assert len(sc) == 1
        assert smoke.uf_from_unidade(sc[0]) == "SC"


class TestFetchContratosPage:
    def test_success_with_mock_opener(self):
        payload = _sample_payload()
        body = json.dumps(payload).encode("utf-8")

        def opener(_url: str):
            return (200, body)

        result = smoke.fetch_contratos_page(
            data_inicial="20260101",
            data_final="20260107",
            opener=opener,
        )
        assert result["ok"] is True
        assert result["http_status"] == 200
        assert result["count"] == 2
        assert result["total_registros"] == 99
        assert result["sample_uf"] == "SC"
        assert result["sc_in_page"] == 1
        assert "contratos?" in result["url"]

    def test_http_400_invalid_page_size_message(self):
        err = {"message": "Tamanho de página inválido", "status": "400"}

        def opener(_url: str):
            return (400, json.dumps(err).encode("utf-8"))

        result = smoke.fetch_contratos_page(
            data_inicial="20260101",
            data_final="20260107",
            tamanho_pagina=1,
            opener=opener,
        )
        assert result["ok"] is False
        assert result["http_status"] == 400
        assert "inválido" in (result["error"] or "")

    def test_invalid_json(self):
        def opener(_url: str):
            return (200, b"not-json{")

        result = smoke.fetch_contratos_page(
            data_inicial="20260101",
            data_final="20260107",
            opener=opener,
        )
        assert result["ok"] is False
        assert "JSON" in (result["error"] or "")


class TestRunSmoke:
    def test_writes_output(self, tmp_path: Path):
        payload = _sample_payload()
        out = tmp_path / "pncp-smoke.json"

        def opener(_url: str):
            return (200, json.dumps(payload).encode("utf-8"))

        result = smoke.run_smoke(write_output=True, output_path=out, opener=opener)
        assert result["ok"] is True
        assert out.exists()
        saved = json.loads(out.read_text(encoding="utf-8"))
        assert saved["count"] == 2
        assert saved["source"] == "pncp_consulta_contratos"
