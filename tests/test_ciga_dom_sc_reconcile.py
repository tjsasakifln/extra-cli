"""Regression tests for the live CIGA/DOM-SC 295-id reconciliation."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.crawl.ciga_dom_sc_reconcile import live_http, main, run_reconcile
from scripts.crawl.ciga_public_discovery import (
    MUNICIPAL_UNIVERSE,
    classify_access_barrier,
    freshness_age_hours,
    freshness_status,
    load_pinned_universe,
    lookup_ibge_id,
    pin_municipal_universe,
    sha256_bytes,
)

IBGE_CACHE = Path("data/ibge_cache.json")
PACKAGE_ID = "domsc-publicacoes-de-08-2026"


def _zip_publications(publications: list[dict]) -> bytes:
    payload = json.dumps({"autopublicacoes": publications}, ensure_ascii=False).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("autopublicacoes.json", payload)
    return buffer.getvalue()


def _zip_members(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _package_body(resources: list[dict]) -> bytes:
    return json.dumps({"success": True, "result": {"name": PACKAGE_ID, "resources": resources}}).encode("utf-8")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://127.0.0.1/internal",
        "https://evil.example/resource.zip",
        "http://dados.ciga.sc.gov.br/resource.zip",
    ],
)
def test_live_transport_rejects_nonofficial_or_nonpublic_targets(url: str) -> None:
    with patch("scripts.crawl.ciga_dom_sc_reconcile.public_get") as get:
        with pytest.raises(RuntimeError, match="network_blocked"):
            live_http(url)
    get.assert_not_called()


def test_live_transport_uses_pinned_public_get_without_redirects() -> None:
    response = SimpleNamespace(status_code=200, content=b"ok")
    with patch("scripts.crawl.ciga_dom_sc_reconcile.public_get", return_value=response) as get:
        status, body, fetched_at = live_http("https://dados.ciga.sc.gov.br/resource.zip")
    assert (status, body) == (200, b"ok")
    assert fetched_at.endswith("Z")
    assert get.call_args.kwargs["max_redirects"] == 0


def test_pinned_universe_is_exactly_295_unique_ibge_ids() -> None:
    binding = load_pinned_universe(IBGE_CACHE)

    assert binding.count == MUNICIPAL_UNIVERSE
    assert len(binding.ibge_ids) == MUNICIPAL_UNIVERSE
    assert len(set(binding.ibge_ids)) == MUNICIPAL_UNIVERSE
    assert binding.sha256 == sha256_bytes(IBGE_CACHE.read_bytes())
    assert binding.version.startswith("ibge_cache:")
    assert lookup_ibge_id("Florianópolis", binding) == binding.id_by_name["florianopolis"]
    assert lookup_ibge_id("Grão Pará", binding) == binding.id_by_name["graopara"]
    assert lookup_ibge_id("Herval d'Oeste", binding) == binding.id_by_name["herval doeste"]


def test_pinned_universe_rejects_wrong_size_and_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="universe_size"):
        pin_municipal_universe({"a": "4200101"}, source_bytes=b"{}")

    mapping = {f"m{i}": f"{4200000 + i:07d}" for i in range(295)}
    mapping["duplicate"] = mapping["m0"]
    with pytest.raises(ValueError, match="duplicate_ibge_id"):
        pin_municipal_universe(mapping, source_bytes=b"duplicate")


def test_runner_exhausts_resources_and_reconciles_all_295(tmp_path: Path) -> None:
    binding = load_pinned_universe(IBGE_CACHE)
    floripa = binding.id_by_name["florianopolis"]
    resource_url = "https://dados.ciga.sc.gov.br/dataset/pkg/resource/r1/download/file.zip"
    raw_zip = _zip_publications(
        [
            {"codigo": "1", "municipio": "Florianópolis", "titulo": "aviso"},
        ]
    )
    package = _package_body(
        [
            {
                "id": "r1",
                "name": "Publicações de 16/08/2026.zip",
                "format": "ZIP",
                "url": resource_url,
                "last_modified": "2026-08-16T15:10:44Z",
            }
        ]
    )

    def http(url: str) -> tuple[int, bytes, str]:
        if "package_show" in url:
            return 200, package, "2026-08-16T18:00:00Z"
        if url == resource_url:
            return 200, raw_zip, "2026-08-16T18:00:01Z"
        return 404, b"missing", "2026-08-16T18:00:00Z"

    report = run_reconcile(
        universe_path=IBGE_CACHE,
        http=http,
        package_id=PACKAGE_ID,
        now="2026-08-16T18:30:00Z",
    )

    assert report["binding"]["count"] == MUNICIPAL_UNIVERSE
    assert report["set_equality"]["ok"] is True
    assert report["scope_exhausted"] is True
    assert report["by_status"] == {"BLOCKED": 0, "FOUND": 1, "ZERO_CONFIRMED": 294}
    assert report["illegal_states"] == []
    assert report["silent_zero"] is False
    assert report["freshness"] == "fresh"
    assert report["completed_at"] == "2026-08-16T18:30:00Z"
    assert report["freshness_hours"] == freshness_age_hours(
        measured_at="2026-08-16T15:10:44Z", now="2026-08-16T18:30:00Z"
    )
    assert report["snapshot_sha256"] == sha256_bytes(sha256_bytes(raw_zip).encode("utf-8"))
    by_id = {row["ibge_id"]: row for row in report["municipalities"]}
    assert set(by_id) == set(binding.ibge_ids)
    assert by_id[floripa]["status"] == "FOUND"
    assert by_id[floripa]["sha256"] == sha256_bytes(raw_zip)
    assert by_id[floripa]["url"] == resource_url
    assert report["unmatched_names"] == []
    assert report["coverage"]["mapping_complete"] is True
    assert report["coverage"]["municipal_coverage_complete"] is False
    assert report["coverage"]["buckets"]["structured"]["rows"] == 1
    assert report["coverage"]["buckets"]["mop_single_match"]["rows"] == 0
    assert all(page["sha256"] and page["fetched_at"] for page in report["pages"])

    out = tmp_path / "reconcile.json"
    with patch("scripts.crawl.ciga_dom_sc_reconcile.live_http", http):
        with patch("scripts.crawl.ciga_dom_sc_reconcile._iso_now", return_value="2026-08-16T18:30:00Z"):
            rc = main(["--out", str(out), "--package-id", PACKAGE_ID, "--universe", str(IBGE_CACHE)])
    assert rc == 0
    assert len(json.loads(out.read_text(encoding="utf-8"))["municipalities"]) == MUNICIPAL_UNIVERSE


def test_unmatched_municipality_blocks_absence_and_returns_nonzero(tmp_path: Path) -> None:
    resource_url = "https://dados.ciga.sc.gov.br/dataset/pkg/resource/r1/download/file.zip"
    raw_zip = _zip_publications(
        [
            {"codigo": "1", "municipio": "Florianópolis", "titulo": "aviso"},
            {"codigo": "2", "municipio": "Cidade Inventada", "titulo": "aviso"},
        ]
    )
    package = _package_body(
        [
            {
                "id": "r1",
                "name": "Publicações de 16/08/2026.zip",
                "format": "ZIP",
                "url": resource_url,
                "last_modified": "2026-08-16T15:10:44Z",
            }
        ]
    )

    def http(url: str) -> tuple[int, bytes, str]:
        if "package_show" in url:
            return 200, package, "2026-08-16T18:00:00Z"
        if url == resource_url:
            return 200, raw_zip, "2026-08-16T18:00:01Z"
        return 404, b"missing", "2026-08-16T18:00:00Z"

    report = run_reconcile(
        universe_path=IBGE_CACHE,
        http=http,
        package_id=PACKAGE_ID,
        now="2026-08-16T18:30:00Z",
    )
    assert report["scope_exhausted"] is True
    assert report["unmatched_names"] == ["cidade inventada"]
    assert report["by_status"] == {"BLOCKED": 294, "FOUND": 1, "ZERO_CONFIRMED": 0}
    by_status = {row["name"]: row for row in report["municipalities"]}
    assert by_status["florianopolis"]["status"] == "FOUND"
    assert all(
        row["blocker"] == "unmatched_municipality_binding"
        for row in report["municipalities"]
        if row["status"] == "BLOCKED"
    )

    out = tmp_path / "unmatched.json"
    with patch("scripts.crawl.ciga_dom_sc_reconcile.live_http", http):
        with patch("scripts.crawl.ciga_dom_sc_reconcile._iso_now", return_value="2026-08-16T18:30:00Z"):
            rc = main(["--out", str(out), "--package-id", PACKAGE_ID, "--universe", str(IBGE_CACHE)])
    assert rc == 2


def test_unclassified_null_municipality_blocks_absence_without_failing_resource() -> None:
    resource_url = "https://dados.ciga.sc.gov.br/dataset/pkg/resource/r1/download/file.zip"
    raw_zip = _zip_publications([{"codigo": "1", "titulo": "sem município"}])
    package = _package_body(
        [
            {
                "id": "r1",
                "name": "Publicações sem município.zip",
                "format": "ZIP",
                "url": resource_url,
            }
        ]
    )

    def http(url: str) -> tuple[int, bytes, str]:
        if "package_show" in url:
            return 200, package, "2026-08-16T18:00:00Z"
        if url == resource_url:
            return 200, raw_zip, "2026-08-16T18:00:01Z"
        return 404, b"missing", "2026-08-16T18:00:00Z"

    report = run_reconcile(
        universe_path=IBGE_CACHE,
        http=http,
        package_id=PACKAGE_ID,
        now="2026-08-16T18:30:00Z",
    )
    assert report["scope_exhausted"] is True
    assert report["by_status"] == {"BLOCKED": 295, "FOUND": 0, "ZERO_CONFIRMED": 0}
    assert all(row["blocker"] == "publication_mapping_incomplete" for row in report["municipalities"])
    assert report["resources"][0]["status"] == 200
    coverage = report["coverage"]
    assert coverage["mapping_complete"] is False
    assert coverage["municipal_coverage_complete"] is False
    assert coverage["buckets"]["null_non_mop_unclassified"]["rows"] == 1


def test_explicit_null_autopublicacoes_is_a_valid_empty_period() -> None:
    resource_url = "https://dados.ciga.sc.gov.br/dataset/pkg/resource/r1/download/file.zip"
    raw_zip = _zip_members(
        {"publicacoes.json": json.dumps({"autopublicacoes": None, "edicoes_ordinarias_exclusivas": [None]}).encode()}
    )
    package = _package_body([{"id": "r1", "name": "Publicações vazias.zip", "format": "ZIP", "url": resource_url}])

    def http(url: str) -> tuple[int, bytes, str]:
        if "package_show" in url:
            return 200, package, "2026-08-16T18:00:00Z"
        if url == resource_url:
            return 200, raw_zip, "2026-08-16T18:00:01Z"
        return 404, b"missing", "2026-08-16T18:00:00Z"

    report = run_reconcile(
        universe_path=IBGE_CACHE,
        http=http,
        package_id=PACKAGE_ID,
        now="2026-08-16T18:30:00Z",
    )
    assert report["scope_exhausted"] is True
    assert report["by_status"] == {"BLOCKED": 0, "FOUND": 0, "ZERO_CONFIRMED": 295}
    assert report["coverage"]["total_rows"] == 0
    assert report["coverage"]["mapping_complete"] is True


def test_strict_mop_mapping_recovers_four_false_zeros_and_refuses_ambiguous_rows() -> None:
    binding = load_pinned_universe(IBGE_CACHE)
    resource_url = "https://dados.ciga.sc.gov.br/dataset/pkg/resource/r1/download/file.zip"
    raw_zip = _zip_publications(
        [
            {"codigo": "a", "titulo": "MOP26CIGA-ARAQUARI-fornecedor-aviso"},
            {"codigo": "c", "titulo": "MOP26CIGA-CAMPO ERÊ-fornecedor-aviso"},
            {"codigo": "l", "titulo": "MOP26CIGA-LAURENTINO-fornecedor-aviso"},
            {"codigo": "p", "titulo": "MOP26CIGA-PONTE ALTA-fornecedor-aviso"},
            {
                "codigo": "amb",
                "titulo": (
                    "MOP26CIGA-SERVIÇO INTERMUNICIPAL DE ÁGUA E ESGOTO "
                    "JOAÇABA HERVAL D'OESTE E LUZERNA-fornecedor-aviso"
                ),
            },
            {"codigo": "unmapped", "titulo": "MOP26CIGA-CINCATARINA-fornecedor-aviso"},
            {"codigo": "plain", "titulo": "Publicação supra-municipal", "entidade": "CIGA"},
        ]
    )
    package = _package_body(
        [
            {
                "id": "r1",
                "name": "Publicações de 16/08/2026.zip",
                "format": "ZIP",
                "url": resource_url,
                "last_modified": "2026-08-16T15:10:44Z",
            }
        ]
    )

    def http(url: str) -> tuple[int, bytes, str]:
        if "package_show" in url:
            return 200, package, "2026-08-16T18:00:00Z"
        if url == resource_url:
            return 200, raw_zip, "2026-08-16T18:00:01Z"
        return 404, b"missing", "2026-08-16T18:00:00Z"

    report = run_reconcile(
        universe_path=IBGE_CACHE,
        http=http,
        package_id=PACKAGE_ID,
        now="2026-08-16T18:30:00Z",
    )

    assert report["scope_exhausted"] is True
    assert report["by_status"] == {"BLOCKED": 291, "FOUND": 4, "ZERO_CONFIRMED": 0}
    by_id = {row["ibge_id"]: row for row in report["municipalities"]}
    for name in ("araquari", "campo ere", "laurentino", "ponte alta"):
        assert by_id[binding.id_by_name[name]]["status"] == "FOUND"
    assert by_id[binding.id_by_name["ponte alta do norte"]]["status"] == "BLOCKED"

    coverage = report["coverage"]
    assert coverage["mapping_complete"] is False
    assert coverage["municipal_coverage_complete"] is False
    assert coverage["buckets"]["mop_single_match"]["rows"] == 4
    assert coverage["buckets"]["unmapped_participant"]["rows"] == 1
    assert coverage["buckets"]["null_non_mop_unclassified"]["rows"] == 1
    ambiguous = coverage["buckets"]["ambiguous_participant"]
    assert ambiguous["rows"] == 1
    assert {candidate["name"] for candidate in ambiguous["segments"][0]["candidates"]} == {
        "herval doeste",
        "joacaba",
        "luzerna",
    }


@pytest.mark.parametrize(
    ("raw_zip", "blocker"),
    [
        (
            _zip_members(
                {
                    "publicacoes.json": json.dumps(
                        {"publicacoes": [{"codigo": "1", "municipio": "Florianópolis"}]}
                    ).encode()
                }
            ),
            "archive_or_parse:unrecognized_publication_schema",
        ),
        (
            _zip_members({"readme.txt": b"sem dados estruturados"}),
            "archive_or_parse:archive_without_publication_members",
        ),
    ],
)
def test_unknown_or_memberless_archive_blocks_all_absence(raw_zip: bytes, blocker: str) -> None:
    resource_url = "https://dados.ciga.sc.gov.br/dataset/pkg/resource/r1/download/file.zip"
    package = _package_body(
        [
            {
                "id": "r1",
                "name": "Publicações com drift.zip",
                "format": "ZIP",
                "url": resource_url,
            }
        ]
    )

    def http(url: str) -> tuple[int, bytes, str]:
        if "package_show" in url:
            return 200, package, "2026-08-16T18:00:00Z"
        if url == resource_url:
            return 200, raw_zip, "2026-08-16T18:00:01Z"
        return 404, b"missing", "2026-08-16T18:00:00Z"

    report = run_reconcile(
        universe_path=IBGE_CACHE,
        http=http,
        package_id=PACKAGE_ID,
        now="2026-08-16T18:30:00Z",
    )
    assert report["scope_exhausted"] is False
    assert report["by_status"] == {"BLOCKED": 295, "FOUND": 0, "ZERO_CONFIRMED": 0}
    assert all(row["blocker"] == blocker for row in report["municipalities"])


def test_truncated_run_blocks_absence_and_returns_nonzero(tmp_path: Path) -> None:
    first_url = "https://dados.ciga.sc.gov.br/a.zip"
    second_url = "https://dados.ciga.sc.gov.br/b.zip"
    raw_zip = _zip_publications([{"codigo": "1", "municipio": "Blumenau"}])
    package = _package_body(
        [
            {"id": "a", "name": "a.zip", "format": "ZIP", "url": first_url},
            {"id": "b", "name": "b.zip", "format": "ZIP", "url": second_url},
        ]
    )

    def http(url: str) -> tuple[int, bytes, str]:
        if "package_show" in url:
            return 200, package, "2026-08-16T12:00:00Z"
        if url == first_url:
            return 200, raw_zip, "2026-08-16T12:00:01Z"
        raise AssertionError(f"truncated run fetched unexpected resource: {url}")

    report = run_reconcile(
        universe_path=IBGE_CACHE,
        http=http,
        package_id=PACKAGE_ID,
        max_resources=1,
        now="2026-08-16T12:30:00Z",
    )
    assert report["scope_exhausted"] is False
    assert report["resolved"]["truncated"] is True
    assert report["by_status"] == {"BLOCKED": 294, "FOUND": 1, "ZERO_CONFIRMED": 0}
    assert next(row for row in report["municipalities"] if row["name"] == "blumenau")["status"] == "FOUND"

    out = tmp_path / "blocked.json"
    with patch("scripts.crawl.ciga_dom_sc_reconcile.live_http", http):
        with patch("scripts.crawl.ciga_dom_sc_reconcile._iso_now", return_value="2026-08-16T12:30:00Z"):
            rc = main(
                [
                    "--out",
                    str(out),
                    "--package-id",
                    PACKAGE_ID,
                    "--universe",
                    str(IBGE_CACHE),
                    "--max-resources",
                    "1",
                ]
            )
    assert rc == 2


def test_403_and_captcha_are_blocked_not_zero(tmp_path: Path) -> None:
    def forbidden(_url: str) -> tuple[int, bytes, str]:
        return 403, b"forbidden", "2026-08-16T12:00:00Z"

    report = run_reconcile(
        universe_path=IBGE_CACHE,
        http=forbidden,
        package_id=PACKAGE_ID,
        now="2026-08-16T12:00:00Z",
    )
    assert report["by_status"] == {"BLOCKED": 295, "FOUND": 0, "ZERO_CONFIRMED": 0}
    assert all(row["blocker"] == "http_403" for row in report["municipalities"])
    assert report["silent_zero"] is False
    assert classify_access_barrier(403) == "http_403"

    out = tmp_path / "forbidden.json"
    with patch("scripts.crawl.ciga_dom_sc_reconcile.live_http", forbidden):
        rc = main(["--out", str(out), "--package-id", PACKAGE_ID, "--universe", str(IBGE_CACHE)])
    assert rc == 2

    captcha = b"<html><body><div class='hcaptcha'></div></body></html>"

    def challenged(_url: str) -> tuple[int, bytes, str]:
        return 200, captcha, "2026-08-16T12:00:00Z"

    report = run_reconcile(
        universe_path=IBGE_CACHE,
        http=challenged,
        package_id=PACKAGE_ID,
        now="2026-08-16T12:00:00Z",
    )
    assert report["by_status"] == {"BLOCKED": 295, "FOUND": 0, "ZERO_CONFIRMED": 0}
    assert all(row["blocker"] == "captcha" for row in report["municipalities"])


def test_freshness_is_measured_not_inferred() -> None:
    age = freshness_age_hours(measured_at="2026-08-15T12:00:00Z", now="2026-08-16T18:00:00Z")
    assert age == 30.0
    assert freshness_status(age) == "stale"
    assert freshness_status(24.0) == "fresh"
    assert freshness_status(24.01) == "stale"
