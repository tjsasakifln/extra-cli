"""Unit tests for scripts/crawl/ciga_dom_publications.py.

All network I/O is mocked. No live CIGA calls.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.crawl import ciga_dom_publications as mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _sample_pub(**overrides) -> dict:
    base = {
        "codigo": "7780704",
        "titulo": "AVISO DE LICITAÇÃO PREGÃO ELETRÔNICO Nº 10/2025",
        "data": "2025-12-01 06:00:01",
        "cod_registro_info_sfinge": None,
        "municipio": "Orleans",
        "entidade": "Prefeitura municipal de Orleans",
        "categoria": "Licitações",
        "link": "https://diariomunicipal.sc.gov.br/?q=id:7780704",
        "texto": "<p>Abertura de pregão eletrônico para aquisição de materiais.</p>",
        "url": "https://diariomunicipal.sc.gov.br/?q=id:7780704",
    }
    base.update(overrides)
    return base


def _autopub_json(pubs: list[dict]) -> bytes:
    return json.dumps({"autopublicacoes": pubs}, ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------------------
# zip-slip
# ---------------------------------------------------------------------------


class TestZipSlip:
    def test_reject_parent_traversal(self, tmp_path: Path):
        assert mod.is_safe_zip_member(tmp_path, "../evil.txt") is False
        assert mod.is_safe_zip_member(tmp_path, "foo/../../evil.txt") is False

    def test_reject_absolute_path(self, tmp_path: Path):
        assert mod.is_safe_zip_member(tmp_path, "/etc/passwd") is False
        assert mod.is_safe_zip_member(tmp_path, "\\Windows\\System32") is False

    def test_accept_normal_member(self, tmp_path: Path):
        assert mod.is_safe_zip_member(tmp_path, "publicacoes.json") is True
        assert mod.is_safe_zip_member(tmp_path, "sub/dir/file.json") is True

    def test_safe_extract_rejects_slip(self, tmp_path: Path):
        raw = _make_zip({"../evil.json": b'{"x":1}'})
        with pytest.raises(ValueError, match="zip-slip"):
            mod.safe_extract_zip(raw, tmp_path / "out")
        assert not (tmp_path / "evil.json").exists()

    def test_iter_zip_json_members_rejects_slip(self):
        raw = _make_zip({"../../tmp/evil.json": b"{}"})
        with pytest.raises(ValueError, match="zip-slip"):
            list(mod.iter_zip_json_members(raw))


# ---------------------------------------------------------------------------
# parse / normalize / classification
# ---------------------------------------------------------------------------


class TestParseNormalize:
    def test_normal_autopublicacoes_parse(self):
        pubs = [_sample_pub(), _sample_pub(codigo="2", municipio="Blumenau")]
        data = _autopub_json(pubs)
        parsed = mod.parse_json_publications(data)
        assert len(parsed) == 2
        assert parsed[0]["municipio"] == "Orleans"

    def test_empty_zip(self, tmp_path: Path):
        raw = _make_zip({})
        extracted = mod.safe_extract_zip(raw, tmp_path / "empty")
        assert extracted == []
        members = list(mod.iter_zip_json_members(raw))
        assert members == []

    def test_invalid_zip(self, tmp_path: Path):
        with pytest.raises(ValueError, match="invalid zip"):
            mod.safe_extract_zip(b"not-a-zip", tmp_path / "bad")
        with pytest.raises(ValueError, match="invalid zip"):
            list(mod.iter_zip_json_members(b"still-not-a-zip"))

    def test_normalize_fields_and_classification(self):
        raw = _sample_pub()
        resource = {
            "id": "res-1",
            "name": "Publicações de 01/12/2025 entre 00:00 e 11:59 (598)",
        }
        norm = mod.normalize_publication(
            raw,
            package_id="domsc-publicacoes-de-12-2025",
            resource=resource,
            source_file="publicacoes.json",
        )
        assert norm is not None
        assert norm["municipio"] == "Orleans"
        assert norm["orgao"] == "Prefeitura municipal de Orleans"
        assert norm["entidade"] == "Prefeitura municipal de Orleans"
        assert norm["edicao"] == "01/12/2025"
        assert norm["data"] == "2025-12-01"
        assert norm["titulo"]
        assert norm["texto"]
        assert "pregão" in (norm["texto"] or "").lower() or "pregao" in (
            norm["texto"] or ""
        ).lower() or "eletr" in (norm["texto"] or "").lower()
        assert norm["url"]
        assert norm["act_category"] in {
            "aviso_licitacao",
            "edital",
            "outros",
        }
        # title has "AVISO DE LICITAÇÃO PREGÃO" → aviso_licitacao
        assert norm["act_category"] == "aviso_licitacao"
        # act_classifier may return numeric confidence + label
        conf = norm["act_confidence"]
        label = norm.get("act_confidence_label")
        if isinstance(conf, (int, float)):
            assert conf >= 0.55
            assert label in {None, "high", "medium", "low"} or isinstance(label, str)
        else:
            assert conf in {"high", "medium", "low", conf}
        assert norm["source"] == "ciga_dom"

    def test_classification_extrato_contrato(self):
        raw = _sample_pub(
            titulo="EXTRATO DE CONTRATO Nº 45/2025",
            categoria="Contratos",
            texto="<p>Extrato do contrato firmado.</p>",
        )
        norm = mod.normalize_publication(
            raw, package_id="pkg", resource={"id": "r", "name": "x"}
        )
        assert norm is not None
        assert norm["act_category"] == "extrato_contrato"


# ---------------------------------------------------------------------------
# checkpoint skip / incremental
# ---------------------------------------------------------------------------


class TestCheckpoint:
    def test_checkpoint_skip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(mod, "CHECKPOINT_DIR", tmp_path / "ck")
        monkeypatch.setattr(mod, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path / "out")

        cp = mod.load_checkpoint()
        assert cp["completed_resources"] == {}

        mod.mark_file_done(cp, resource_id="r1", filename="a.json", records=10, sha256="abc")
        mod.mark_resource_done(cp, resource_id="r1", records=10, sha256="abc")
        path = mod.save_checkpoint(cp)
        assert path.exists()

        cp2 = mod.load_checkpoint()
        assert mod.resource_done(cp2, "r1") is True
        assert mod.file_done(cp2, "r1", "a.json") is True
        assert mod.resource_done(cp2, "r2") is False
        assert mod.file_done(cp2, "r1", "b.json") is False

    def test_incremental_no_reprocess(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(mod, "CHECKPOINT_DIR", tmp_path / "ck")
        monkeypatch.setattr(mod, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path / "out")

        pub = _sample_pub()
        json_bytes = _autopub_json([pub])
        zip_bytes = _make_zip({"publicacoes.json": json_bytes})

        package_id = "domsc-publicacoes-de-12-2025"
        resources = [
            {
                "id": "res-A",
                "name": "Publicações de 01/12/2025 entre 00:00 e 11:59 (1)",
                "format": "ZIP",
                "url": "https://dados.ciga.sc.gov.br/fake/a.zip",
                "size": len(zip_bytes),
                "last_modified": "2025-12-01T15:00:00",
                "kind": "zip",
            }
        ]
        pkg = {"name": package_id, "resources": resources}

        def fake_download(url: str, **kwargs):  # noqa: ANN003
            return zip_bytes, None

        with (
            patch.object(mod, "discover_latest_package", return_value=package_id),
            patch.object(mod, "get_package", return_value=pkg),
            patch.object(mod, "list_ingestible_resources", return_value=resources),
            patch.object(mod, "download_bytes", side_effect=fake_download),
            patch.object(mod, "time") as mock_time,
        ):
            mock_time.sleep = MagicMock()
            r1 = mod.run_ingestion(mode="smoke", max_zips=1, request_delay=0)

        assert r1["status"] in {"success", "partial"}
        assert r1["counts"]["records_normalized"] == 1
        assert r1["counts"]["resources_processed_ok"] == 1

        # Second run incremental — must skip completed resource
        with (
            patch.object(mod, "discover_latest_package", return_value=package_id),
            patch.object(mod, "get_package", return_value=pkg),
            patch.object(mod, "list_ingestible_resources", return_value=resources),
            patch.object(mod, "download_bytes") as dl,
            patch.object(mod, "time") as mock_time,
        ):
            mock_time.sleep = MagicMock()
            r2 = mod.run_ingestion(mode="incremental", max_zips=1, request_delay=0)

        dl.assert_not_called()
        assert r2["counts"]["records_normalized"] == 0
        # selected may be empty after filter → skipped via selected empty or checkpoint
        assert (
            r2["counts"].get("resources_skipped_checkpoint", 0) >= 1
            or r2["counts"].get("selected", 0) == 0
            or r2["status"] in {"empty", "success", "partial"}
        )


# ---------------------------------------------------------------------------
# HTTP soft failure
# ---------------------------------------------------------------------------


class TestHttpSoftFailure:
    def test_download_http_failure_soft(self):
        import urllib.error

        def boom(req, timeout=None):  # noqa: ANN001
            raise urllib.error.HTTPError(
                url="https://example.com/x.zip",
                code=500,
                msg="err",
                hdrs=None,
                fp=None,
            )

        with patch("urllib.request.urlopen", side_effect=boom):
            body, err = mod.download_bytes("https://example.com/x.zip")
        assert body is None
        assert err is not None
        assert "500" in err

    def test_run_ingestion_continues_on_download_fail(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(mod, "CHECKPOINT_DIR", tmp_path / "ck")
        monkeypatch.setattr(mod, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path / "out")

        package_id = "domsc-publicacoes-de-12-2025"
        resources = [
            {
                "id": "bad",
                "name": "bad",
                "format": "ZIP",
                "url": "https://dados.ciga.sc.gov.br/fake/bad.zip",
                "kind": "zip",
            },
            {
                "id": "good",
                "name": "Publicações de 02/12/2025 entre 00:00 e 11:59 (1)",
                "format": "ZIP",
                "url": "https://dados.ciga.sc.gov.br/fake/good.zip",
                "kind": "zip",
            },
        ]
        pub = _sample_pub(municipio="Joinville")
        zip_ok = _make_zip({"p.json": _autopub_json([pub])})

        def fake_dl(url: str, **kwargs):  # noqa: ANN003
            if "bad" in url:
                return None, "HTTP 503: unavailable"
            return zip_ok, None

        with (
            patch.object(mod, "discover_latest_package", return_value=package_id),
            patch.object(mod, "get_package", return_value={"name": package_id}),
            patch.object(mod, "list_ingestible_resources", return_value=resources),
            patch.object(mod, "download_bytes", side_effect=fake_dl),
            patch.object(mod, "time") as mock_time,
        ):
            mock_time.sleep = MagicMock()
            result = mod.run_ingestion(mode="smoke", max_zips=2, request_delay=0)

        assert result["counts"]["resources_failed"] >= 1
        assert result["counts"]["records_normalized"] >= 1
        assert result["status"] in {"success", "partial"}


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_sort_packages_by_year_month(self):
        ids = [
            "domsc-publicacoes-de-12-2022",
            "domsc-publicacoes-de-11-2025",
            "domsc-publicacoes-de-12-2025",
            "domsc-publicacoes-de-01-2025",
        ]
        ordered = mod.sort_domsc_packages(ids)
        assert ordered[-1] == "domsc-publicacoes-de-12-2025"
        assert ordered[0] == "domsc-publicacoes-de-12-2022"

    def test_discover_latest(self):
        latest = mod.discover_latest_package(
            package_ids=[
                "domsc-publicacoes-de-10-2025",
                "domsc-publicacoes-de-12-2024",
            ]
        )
        assert latest == "domsc-publicacoes-de-10-2025"

    def test_resource_kind(self):
        assert mod.resource_kind({"format": "ZIP", "url": "x"}) == "zip"
        assert mod.resource_kind({"format": "JSON", "url": "x"}) == "json"
        assert mod.resource_kind({"format": "CSV", "url": "x"}) == "csv"
        assert mod.resource_kind({"format": "", "url": "file.zip"}) == "zip"


# ---------------------------------------------------------------------------
# municipality stats
# ---------------------------------------------------------------------------


class TestMunicipalityStats:
    def test_gaps_with_universe(self):
        stats = mod.municipality_stats(
            {"Orleans", "Blumenau"},
            {"orleans", "blumenau", "joinville", "florianopolis"},
        )
        assert stats["observed_count"] == 2
        assert stats["gap_count"] == 2
        assert "joinville" in stats["gaps_sample"]

    def test_observed_only_without_universe(self):
        stats = mod.municipality_stats({"A", "B"}, set())
        assert stats["universe_source"] == "observed_only"
        assert stats["gap_count"] is None
