"""CLI entry point and live-readonly unavailability path."""

from __future__ import annotations

import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from scripts.official_contract_semantics.cli import main
from scripts.official_contract_semantics.http_client import fetch_official
from scripts.official_contract_semantics.live import run_live_readonly
from tests.official_contract_semantics.conftest import FIXTURE_DIR, SCRIPTS_DIR


def test_cli_extract_validate_reconcile(tmp_path: Path) -> None:
    extract_out = tmp_path / "extract.json"
    assert (
        main(["extract", "--input", str(FIXTURE_DIR / "01_global_unknown_unit.json"), "--out", str(extract_out)]) == 0
    )
    payload = json.loads(extract_out.read_text(encoding="utf-8"))
    assert payload["observations"]
    validate_out = tmp_path / "validate.json"
    assert (
        main(["validate", "--input", str(FIXTURE_DIR / "01_global_unknown_unit.json"), "--out", str(validate_out)]) == 0
    )
    accepted = json.loads(validate_out.read_text(encoding="utf-8"))["accepted"]
    observations = tmp_path / "obs.json"
    observations.write_text(json.dumps({"observations": accepted}, ensure_ascii=False), encoding="utf-8")
    recon_out = tmp_path / "recon.json"
    assert main(["reconcile", "--input", str(observations), "--out", str(recon_out)]) == 0
    reconciled = json.loads(recon_out.read_text(encoding="utf-8"))
    assert reconciled["observations"][0]["status"] == "observed"


def test_http_429_retries_and_is_not_cached(tmp_path: Path) -> None:
    hits = {"n": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            hits["n"] += 1
            if hits["n"] == 1:
                self.send_response(429)
                self.end_headers()
                self.wfile.write(b"slow down")
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"data":[]}')

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/contratos"
        result = fetch_official(url, retries=2, rate_limit_s=0, cache_dir=tmp_path / "cache", sleeper=lambda _s: None)
    finally:
        server.shutdown()
        server.server_close()
    assert result.ok is True
    assert hits["n"] == 2
    assert result.body is not None


def test_http_404_is_unavailability_not_absence() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/official"
        result = fetch_official(url, retries=0, rate_limit_s=0, cache_dir=None)
    finally:
        server.shutdown()
        server.server_close()
    assert result.ok is False
    assert result.unavailability is not None
    assert result.unavailability.recorded_as == "unavailable"
    assert result.unavailability.http_status == 404
    assert result.body is None


def test_live_readonly_records_unavailability_when_dsn_absent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    manifest = run_live_readonly(
        dsn=None,
        limit=2,
        out_dir=tmp_path / "live",
        cache_dir=tmp_path / "cache",
        fetch_pages=False,
        as_of="2026-08-17",
    )
    assert manifest["production_write"] is False
    assert manifest["inferred_from_absence"] is False
    kinds = {item.get("error_kind") for item in manifest["unavailabilities"]}
    assert (
        "dsn_unavailable" in kinds or "network" in kinds or "http_status" in kinds or "dependency_unavailable" in kinds
    )
    man_path = tmp_path / "live" / "live-manifest.json"
    written_bytes = man_path.read_bytes()
    written = json.loads(written_bytes)
    obs_path = tmp_path / "live" / "live-observations.jsonl"
    assert written["artifact_sha256"]["live-observations.jsonl"] == hashlib.sha256(obs_path.read_bytes()).hexdigest()
    assert "live-manifest.json" not in written["artifact_sha256"]
    assert manifest["manifest_file_sha256"] == hashlib.sha256(written_bytes).hexdigest()
    replay = written["replay_command"]
    assert "--skip-pages" in replay
    assert f"--cache-dir {tmp_path / 'cache'}" in replay
    assert f"--out {tmp_path / 'live'}" in replay
    assert written["commands"] == [replay]


def test_live_manifest_hash_matches_final_bytes_and_replay_argv(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    out = tmp_path / "proof"
    cache = tmp_path / "http-cache"
    returned = run_live_readonly(
        dsn=None,
        limit=2,
        out_dir=out,
        cache_dir=cache,
        fetch_pages=False,
        as_of="2026-08-17",
    )
    man_path = out / "live-manifest.json"
    final = man_path.read_bytes()
    on_disk = json.loads(final)
    assert (
        on_disk["artifact_sha256"]["live-observations.jsonl"]
        == hashlib.sha256((out / "live-observations.jsonl").read_bytes()).hexdigest()
    )
    assert "live-manifest.json" not in on_disk["artifact_sha256"]
    assert returned["manifest_file_sha256"] == hashlib.sha256(final).hexdigest()
    from scripts.official_contract_semantics.live import default_live_window

    window_start, window_end = default_live_window(as_of="2026-08-17")
    assert on_disk["replay_command"] == (
        "python3 -m scripts.official_contract_semantics live-readonly "
        f"--limit 2 --as-of 2026-08-17 --start-date {window_start} --end-date {window_end} "
        f"--skip-pages --cache-dir {cache} --out {out}"
    )
    assert on_disk["commands"] == [on_disk["replay_command"]]


def test_no_mock_or_skip_in_new_tests() -> None:
    test_dir = Path(__file__).resolve().parent
    self_name = Path(__file__).name
    for path in test_dir.glob("test_*.py"):
        if path.name == self_name:
            continue
        blob = path.read_text(encoding="utf-8")
        assert "unittest.mock" not in blob
        assert "pytest.skip" not in blob
        assert "pytest.xfail" not in blob


def test_package_stays_on_owned_surface() -> None:
    assert SCRIPTS_DIR.is_dir()
    for path in SCRIPTS_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "scripts.coverage" not in text
        assert "golden_path" not in text
