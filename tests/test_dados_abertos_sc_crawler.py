"""Unit tests for scripts/crawl/dados_abertos_sc_crawler.py.

All network I/O is mocked. Fixtures under tests/fixtures/ckan/ are sanitized
captures from live discovery (no secrets).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.crawl import dados_abertos_sc_crawler as das

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ckan"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def fixture_search_diario() -> dict:
    return _load("dados_sc_package_search_diario.json")


@pytest.fixture
def fixture_show_publicacoes() -> dict:
    return _load("dados_sc_package_show_publicacoes.json")


@pytest.fixture
def fixture_status() -> dict:
    return _load("dados_sc_status_show.json")


def _mock_urlopen_sequence(responses: list[dict]):
    """Build a side_effect for urllib.request.urlopen returning JSON bodies."""
    calls = iter(responses)

    def _open(req, timeout=None):  # noqa: ANN001
        payload = next(calls)
        body = json.dumps(payload).encode("utf-8")
        cm = MagicMock()
        cm.read.return_value = body
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.status = 200
        cm.headers = {"Content-Type": "application/json"}
        return cm

    return _open


def _mock_file_download(csv_bytes: bytes, *, etag: str = '"abc"', last_mod: str = "Mon, 01 Jan 2025 00:00:00 GMT"):
    """urlopen side_effect that serves CKAN JSON once then CSV body."""

    def factory(json_payloads: list[dict]):
        json_iter = iter(json_payloads)
        state = {"n": 0}

        def _open(req, timeout=None):  # noqa: ANN001
            url = getattr(req, "full_url", None) or str(req)
            method = getattr(req, "get_method", lambda: "GET")()
            cm = MagicMock()
            cm.__enter__.return_value = cm
            cm.__exit__.return_value = False
            cm.status = 200

            if "api/3/action" in url:
                payload = next(json_iter)
                body = json.dumps(payload).encode("utf-8")
                cm.read.return_value = body
                cm.headers = {"Content-Type": "application/json"}
                return cm

            # HEAD or GET for file
            if method == "HEAD":
                cm.read.return_value = b""
                cm.headers = {
                    "ETag": etag,
                    "Last-Modified": last_mod,
                    "Content-Length": str(len(csv_bytes)),
                }
                return cm

            # Streamable body for GET
            remaining = {"data": csv_bytes}

            def _read(n=-1):
                data = remaining["data"]
                if n is None or n < 0:
                    remaining["data"] = b""
                    return data
                chunk, remaining["data"] = data[:n], data[n:]
                return chunk

            cm.read.side_effect = _read
            cm.headers = {
                "ETag": etag,
                "Last-Modified": last_mod,
                "Content-Length": str(len(csv_bytes)),
                "Content-Type": "text/csv",
            }
            state["n"] += 1
            return cm

        return _open

    return factory


SAMPLE_CSV_UTF8 = (
    "\ufeffDATA_PUBLICACAO;PUBLICACAO;CATEGORIA;ASSUNTO;EDICAO;TITULO_PUBLICACAO\r\n"
    "01/04/2025;1067736;Secretaria de Administração;EDITAL;22483;"
    "EDITAL DE LICITAÇÃO Pregão Eletrônico nº 10/2025 para aquisição de materiais\r\n"
    "02/04/2025;1067737;Secretaria de Saúde;EXTRATO DE CONTRATO;22484;"
    "EXTRATO DO CONTRATO nº 55/2025 firmado com empresa XYZ\r\n"
    "03/04/2025;1067738;Outro Órgão;COMUNICADO;22485;Aviso genérico sem padrão\r\n"
).encode("utf-8")

SAMPLE_CSV_LATIN1 = (
    "DATA_PUBLICACAO;PUBLICACAO;CATEGORIA;ASSUNTO;EDICAO;TITULO_PUBLICACAO\r\n"
    "01/04/2025;99;Administração;EDITAL;1;Edital de licitação com acentuação: órgão\r\n"
).encode("latin-1")


class TestCkanClient:
    def test_package_search_returns_result(self, fixture_search_diario):
        with patch("urllib.request.urlopen", side_effect=_mock_urlopen_sequence([fixture_search_diario])):
            result = das.package_search("diario", rows=3)
        assert result is not None
        assert result["count"] == fixture_search_diario["result"]["count"]
        names = [p["name"] for p in result["results"]]
        assert "diario-oficial-sc-publicacoes" in names

    def test_package_show_lists_resources(self, fixture_show_publicacoes):
        with patch(
            "urllib.request.urlopen",
            side_effect=_mock_urlopen_sequence([fixture_show_publicacoes]),
        ):
            pkg = das.package_show("diario-oficial-sc-publicacoes")
        assert pkg is not None
        assert pkg["name"] == "diario-oficial-sc-publicacoes"
        resources = das.list_resources(pkg)
        assert len(resources) >= 2
        formats = {r["format"] for r in resources}
        assert "CSV" in formats or "XLSX" in formats
        assert all(r.get("id") and r.get("url") for r in resources)

    def test_status_show(self, fixture_status):
        with patch("urllib.request.urlopen", side_effect=_mock_urlopen_sequence([fixture_status])):
            status = das.status_show()
        assert status is not None

    def test_ckan_get_http_error(self):
        import urllib.error

        def _raise(req, timeout=None):  # noqa: ANN001
            raise urllib.error.HTTPError(req.full_url, 500, "err", hdrs=None, fp=None)  # type: ignore[arg-type]

        with patch("urllib.request.urlopen", side_effect=_raise):
            assert das.package_show("x") is None


class TestPreferCsvAndPeriod:
    def test_prefer_csv_over_xlsx_same_period(self):
        resources = [
            {"id": "1", "name": "publicacoes_2024.xlsx", "format": "XLSX", "url": "u1"},
            {"id": "2", "name": "publicacoes_2024.csv", "format": "CSV", "url": "u2"},
            {"id": "3", "name": "publicacoes_2025.xlsx", "format": "XLSX", "url": "u3"},
            {"id": "4", "name": "publicacoes_2025.csv", "format": "CSV", "url": "u4"},
        ]
        preferred = das.prefer_csv_resources(resources)
        assert [r["id"] for r in preferred] == ["2", "4"]
        assert all(r["format"] == "CSV" for r in preferred)

    def test_detect_period(self):
        assert das.detect_period("publicacoes_2025.csv") == "2025"
        assert das.detect_period("no-year.csv") is None

    def test_select_smoke_most_recent(self):
        preferred = [
            {"id": "a", "name": "publicacoes_2024.csv", "format": "CSV"},
            {"id": "b", "name": "publicacoes_2025.csv", "format": "CSV"},
        ]
        assert das.select_resources_for_mode(preferred, "smoke")[0]["id"] == "b"

    def test_select_empty(self):
        assert das.select_resources_for_mode([], "smoke") == []


class TestCrawlSmokeDiscovery:
    def test_crawl_smoke_lists_resources(
        self,
        fixture_status,
        fixture_search_diario,
        fixture_show_publicacoes,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(das, "CHECKPOINT_DIR", tmp_path)
        monkeypatch.setattr(das, "REQUEST_DELAY", 0)

        # status + search + package_show
        seq = [fixture_status, fixture_search_diario, fixture_show_publicacoes]
        with patch("urllib.request.urlopen", side_effect=_mock_urlopen_sequence(seq)):
            records = das.crawl(mode="smoke", dry_run=True)

        types = {r.get("record_type") for r in records}
        assert "ckan_status" in types
        assert "package_search" in types
        assert "ckan_resource" in types

        resources = [r for r in records if r["record_type"] == "ckan_resource"]
        assert len(resources) == len(fixture_show_publicacoes["result"]["resources"])
        assert all(r.get("resource_id") for r in resources)
        assert all(r.get("url") for r in resources)

        # checkpoint written
        cps = list(tmp_path.glob("*.json"))
        assert cps
        cp = json.loads(cps[0].read_text(encoding="utf-8"))
        assert cp["source"] == das.SOURCE_NAME
        assert cp["resource_count"] == len(resources)

    def test_crawl_incremental_primary_only(
        self, fixture_show_publicacoes, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(das, "CHECKPOINT_DIR", tmp_path)
        monkeypatch.setattr(das, "REQUEST_DELAY", 0)
        with patch(
            "urllib.request.urlopen",
            side_effect=_mock_urlopen_sequence([fixture_show_publicacoes]),
        ):
            records = das.crawl(mode="incremental", dry_run=True)
        assert all(
            r.get("record_type") != "package_search" for r in records
        )  # incremental skips search
        resources = [r for r in records if r.get("record_type") == "ckan_resource"]
        assert len(resources) > 0


class TestLiveIngestMocked:
    def test_normal_response_downloads_and_classifies(
        self, fixture_show_publicacoes, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(das, "CHECKPOINT_DIR", tmp_path / "cp")
        monkeypatch.setattr(das, "RAW_ROOT", tmp_path / "raw")
        monkeypatch.setattr(das, "NORMALIZED_ROOT", tmp_path / "norm")
        monkeypatch.setattr(das, "OUTPUT_DIR", tmp_path / "out")
        monkeypatch.setattr(das, "REQUEST_DELAY", 0)

        factory = _mock_file_download(SAMPLE_CSV_UTF8)
        with patch(
            "urllib.request.urlopen",
            side_effect=factory([fixture_show_publicacoes]),
        ):
            records = das.crawl(
                mode="smoke",
                dry_run=False,
                max_rows=10,
                run_id="test-run-normal",
            )

        assert len(records) == 3
        assert all(r["record_type"] == "publication" for r in records)
        assert all(r["fonte"] == das.SOURCE_NAME for r in records)
        assert all(r["portal"] == das.PORTAL for r in records)
        assert all(r.get("act_category") for r in records)
        # First row is edital / aviso_licitacao
        cats = {r["act_category"] for r in records}
        assert "edital" in cats or "aviso_licitacao" in cats
        assert any(r["act_category"] == "extrato_contrato" for r in records)
        assert all(r.get("record_hash") for r in records)
        assert all(r.get("numero_publicacao") for r in records)

        # raw zone + meta
        rid = records[0]["resource_id"]
        meta_path = das.raw_meta_path(rid)
        assert meta_path.is_file()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["sha256"]
        assert meta["url"]

        # terminal artifact
        arts = list((tmp_path / "out").glob("smoke-test-run-normal.json"))
        assert arts
        report = json.loads(arts[0].read_text(encoding="utf-8"))
        assert report["live_fetch"] is True
        assert report["run_id"] == "test-run-normal"
        assert report["counts"]["rows_normalized"] == 3

    def test_empty_resources(self, tmp_path, monkeypatch):
        monkeypatch.setattr(das, "CHECKPOINT_DIR", tmp_path / "cp")
        monkeypatch.setattr(das, "RAW_ROOT", tmp_path / "raw")
        monkeypatch.setattr(das, "NORMALIZED_ROOT", tmp_path / "norm")
        monkeypatch.setattr(das, "OUTPUT_DIR", tmp_path / "out")
        monkeypatch.setattr(das, "REQUEST_DELAY", 0)

        empty_pkg = {
            "success": True,
            "result": {
                "id": "x",
                "name": das.PRIMARY_PACKAGE,
                "title": "empty",
                "resources": [],
            },
        }
        with patch(
            "urllib.request.urlopen",
            side_effect=_mock_urlopen_sequence([empty_pkg]),
        ):
            records = das.crawl(mode="smoke", dry_run=False, run_id="test-empty")
        assert records == []

    def test_skip_identical_hash(self, fixture_show_publicacoes, tmp_path, monkeypatch):
        monkeypatch.setattr(das, "CHECKPOINT_DIR", tmp_path / "cp")
        monkeypatch.setattr(das, "RAW_ROOT", tmp_path / "raw")
        monkeypatch.setattr(das, "NORMALIZED_ROOT", tmp_path / "norm")
        monkeypatch.setattr(das, "OUTPUT_DIR", tmp_path / "out")
        monkeypatch.setattr(das, "REQUEST_DELAY", 0)

        factory = _mock_file_download(SAMPLE_CSV_UTF8)

        with patch(
            "urllib.request.urlopen",
            side_effect=factory([fixture_show_publicacoes]),
        ):
            first = das.crawl(
                mode="smoke", dry_run=False, max_rows=10, run_id="run-a"
            )
        assert len(first) == 3

        # Second run: should skip re-download (same bytes)
        with patch(
            "urllib.request.urlopen",
            side_effect=factory([fixture_show_publicacoes]),
        ):
            # download_resource_to_raw will short-circuit before GET when local hash matches
            second_dl_calls = []

            original_download = das.download_resource_to_raw

            def wrapped(res, *, force=False):
                out = original_download(res, force=force)
                second_dl_calls.append(out)
                return out

            with patch.object(das, "download_resource_to_raw", side_effect=wrapped):
                with patch(
                    "urllib.request.urlopen",
                    side_effect=factory([fixture_show_publicacoes]),
                ):
                    _ = das.crawl(
                        mode="smoke",
                        dry_run=False,
                        max_rows=10,
                        run_id="run-b",
                    )

        assert second_dl_calls
        assert second_dl_calls[0].get("skipped_identical") is True
        assert second_dl_calls[0].get("downloaded") is False

    def test_csv_encoding_latin1(self, tmp_path, monkeypatch):
        monkeypatch.setattr(das, "RAW_ROOT", tmp_path / "raw")
        rid = "res-latin1"
        body = das.raw_body_path(rid, "publicacoes_2025.csv")
        body.parent.mkdir(parents=True, exist_ok=True)
        body.write_bytes(SAMPLE_CSV_LATIN1)

        enc = das.detect_encoding(body)
        assert enc in {"latin-1", "cp1252", "utf-8", "utf-8-sig"}

        rows = list(das.iter_csv_rows(body, encoding="latin-1"))
        assert len(rows) == 1
        assert "órgão" in rows[0].get("TITULO_PUBLICACAO", "") or "org" in rows[0].get(
            "TITULO_PUBLICACAO", ""
        ).lower()

        recs, metrics = das.process_resource_csv(
            {"path": str(body), "resource_id": rid, "name": "publicacoes_2025.csv"},
            max_rows=10,
        )
        assert metrics["rows_normalized"] == 1
        assert recs[0]["act_category"] in {"edital", "aviso_licitacao"}

    def test_checkpoint_resume(self, fixture_show_publicacoes, tmp_path, monkeypatch):
        monkeypatch.setattr(das, "CHECKPOINT_DIR", tmp_path / "cp")
        monkeypatch.setattr(das, "RAW_ROOT", tmp_path / "raw")
        monkeypatch.setattr(das, "NORMALIZED_ROOT", tmp_path / "norm")
        monkeypatch.setattr(das, "OUTPUT_DIR", tmp_path / "out")
        monkeypatch.setattr(das, "REQUEST_DELAY", 0)

        factory = _mock_file_download(SAMPLE_CSV_UTF8)
        with patch(
            "urllib.request.urlopen",
            side_effect=factory([fixture_show_publicacoes]),
        ):
            das.crawl(
                mode="incremental",
                dry_run=False,
                max_rows=10,
                run_id="run-inc-1",
            )

        cp = das.load_checkpoint(das.checkpoint_name_for_mode("incremental"))
        assert cp is not None
        assert cp["processed_resources"]
        rid = next(iter(cp["processed_resources"]))
        assert cp["processed_resources"][rid]["sha256"]
        assert rid in cp["completed_resource_ids"]

        # Resume: same hash → skip re-process path via checkpoint
        with patch(
            "urllib.request.urlopen",
            side_effect=factory([fixture_show_publicacoes]),
        ):
            records = das.crawl(
                mode="incremental",
                dry_run=False,
                max_rows=10,
                run_id="run-inc-2",
            )
        # resumed skip yields no new records
        assert records == []

    def test_classification_applied(self):
        row = {
            "DATA_PUBLICACAO": "01/04/2025",
            "PUBLICACAO": "1",
            "CATEGORIA": "SEFAZ",
            "ASSUNTO": "EDITAL",
            "EDICAO": "100",
            "TITULO_PUBLICACAO": "EDITAL DE LICITAÇÃO Pregão Eletrônico 01/2025",
        }
        rec = das.normalize_publication_row(row, resource_id="rid-1")
        assert rec["act_category"] in {"edital", "aviso_licitacao"}
        # Classifier may return numeric confidence or legacy label string
        conf = rec["act_confidence"]
        if isinstance(conf, (int, float)):
            assert conf > 0.5
            assert rec.get("act_confidence_label") in {
                "high",
                "medium",
                "low",
                None,
            }
        else:
            assert conf in {"high", "medium", "low"}
        assert rec["data_publicacao"] == "2025-04-01"
        assert rec["numero_publicacao"] == "1"
        assert rec["orgao"] == "SEFAZ"

    def test_http_error_on_download(self, fixture_show_publicacoes, tmp_path, monkeypatch):
        import urllib.error

        monkeypatch.setattr(das, "CHECKPOINT_DIR", tmp_path / "cp")
        monkeypatch.setattr(das, "RAW_ROOT", tmp_path / "raw")
        monkeypatch.setattr(das, "NORMALIZED_ROOT", tmp_path / "norm")
        monkeypatch.setattr(das, "OUTPUT_DIR", tmp_path / "out")
        monkeypatch.setattr(das, "REQUEST_DELAY", 0)

        json_once = iter([fixture_show_publicacoes])

        def _open(req, timeout=None):  # noqa: ANN001
            url = getattr(req, "full_url", None) or str(req)
            if "api/3/action" in url:
                payload = next(json_once)
                body = json.dumps(payload).encode("utf-8")
                cm = MagicMock()
                cm.read.return_value = body
                cm.__enter__.return_value = cm
                cm.__exit__.return_value = False
                cm.status = 200
                cm.headers = {"Content-Type": "application/json"}
                return cm
            raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)  # type: ignore[arg-type]

        with patch("urllib.request.urlopen", side_effect=_open):
            records = das.crawl(
                mode="smoke", dry_run=False, max_rows=5, run_id="run-http-err"
            )
        assert records == []
        arts = list((tmp_path / "out").glob("smoke-run-http-err.json"))
        assert arts
        report = json.loads(arts[0].read_text(encoding="utf-8"))
        assert report["status"] == "error"
        assert report["errors"]


class TestTransform:
    def test_transform_resource_row(self):
        raw = {
            "record_type": "ckan_resource",
            "resource_id": "abc-123",
            "name": "publicacoes_2025.csv",
            "format": "CSV",
            "package_id": "diario-oficial-sc-publicacoes",
            "url": "https://portal.doe.sea.sc.gov.br/repositorio/dadosabertos/publicacoes_2025.csv",
            "last_modified": "2025-07-21T00:00:00",
        }
        out = das.transform_record(raw)
        assert out is not None
        assert out["source"] == das.SOURCE_NAME
        assert out["pncp_id"]
        assert out["uf"] == "SC"
        assert out["esfera_id"] == das.ESFERA_ID_ESTADUAL
        assert "publicacoes_2025" in out["objeto_compra"]
        assert out["metadata_only"] is True

    def test_transform_skips_invalid(self):
        assert das.transform_record({}) is None
        assert das.transform_record({"record_type": "ckan_resource"}) is None

    def test_transform_batch(self):
        records = [
            {
                "record_type": "ckan_resource",
                "resource_id": "1",
                "name": "a.csv",
                "format": "CSV",
                "package_id": "diario-oficial-sc-publicacoes",
                "url": "https://example.com/a.csv",
            },
            {"record_type": "package_search", "q": "diario", "count": 7},
        ]
        out = das.transform(records)
        assert len(out) == 2
        assert out[0]["source_id"] == "1"
        assert out[1]["metadata_only"] is True

    def test_transform_publication(self):
        raw = {
            "record_type": "publication",
            "fonte": das.SOURCE_NAME,
            "resource_id": "r1",
            "numero_publicacao": "10",
            "titulo": "EDITAL DE LICITAÇÃO",
            "record_hash": "abc",
            "act_category": "edital",
            "act_confidence": "high",
            "data_publicacao": "2025-04-01",
            "orgao": "SEAD",
        }
        out = das.transform_record(raw)
        assert out is not None
        assert out["metadata_only"] is False
        assert out["act_category"] == "edital"
        assert out["orgao_razao_social"] == "SEAD"


class TestConstants:
    def test_source_name(self):
        assert das.SOURCE_NAME == "dados_abertos_sc"

    def test_primary_package(self):
        assert das.PRIMARY_PACKAGE == "diario-oficial-sc-publicacoes"

    def test_user_agent_imported(self):
        assert "Extra-Consultoria" in das.USER_AGENT


class TestHashHelpers:
    def test_record_hash_stable(self):
        a = das.record_hash_for({"a": 1, "b": 2})
        b = das.record_hash_for({"b": 2, "a": 1})
        assert a == b
        assert len(a) == 64
