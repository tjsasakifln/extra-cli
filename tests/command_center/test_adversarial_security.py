"""Adversarial security tests for Command Center REAL adapters + paths."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scripts.command_center.app import create_app
from scripts.command_center.capabilities.registry import reset_registry
from scripts.command_center.config import Settings
from scripts.command_center.deliverables.excel_render import neutralize_formula_injection
from scripts.command_center.regenerate import apply_corrections_to_source
from scripts.command_center.security import assert_argv_list
from scripts.command_center.workflows.runner import run_workflow


def test_command_injection_rejected_in_argv_assert() -> None:
    with pytest.raises(Exception):
        assert_argv_list("python -c evil")  # type: ignore[arg-type]
    with pytest.raises(Exception):
        assert_argv_list([])

def test_argument_injection_query_metachar(tmp_path: Path) -> None:
    from scripts.command_center.adapters import get_adapter

    adapter = get_adapter("workflow.process_documents")
    assert adapter is not None
    with pytest.raises(ValueError):
        adapter.build_argv({"query": "`id`"}, out_dir=tmp_path)
    with pytest.raises(ValueError):
        adapter.build_argv({"query": "x$(whoami)"}, out_dir=tmp_path)


def test_path_traversal_artifact_api(tmp_path: Path) -> None:
    data = tmp_path / "cc-data"
    out = tmp_path / "output"
    out.mkdir()
    (out / "ok.json").write_text("{}", encoding="utf-8")
    settings = Settings(
        host="127.0.0.1",
        port=8765,
        data_dir=data,
        open_browser=False,
        spa_dist=None,
        allowed_artifact_roots=(out.resolve(), data.resolve()),
    )
    reset_registry()
    client = TestClient(create_app(settings))
    # CSRF
    csrf = client.get("/api/csrf").json()["csrf_token"]
    r = client.get(
        "/api/artifacts/content",
        params={"path": "../../../etc/passwd"},
        headers={"X-CC-CSRF": csrf},
    )
    # May be 400/403/404 depending on resolver — never 200 with file content
    assert r.status_code in {400, 403, 404}


def test_secret_not_in_fixture_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_DATALAKE_DSN", "postgresql://user:SuperSecretPass@127.0.0.1/db")
    result = run_workflow(
        "workflow.extra.opportunities",
        {"data_mode": "FIXTURE", "max_shortlist": 1},
        out_dir=tmp_path / "sec",
        code_sha="t",
    )
    mf = Path(result["manifest_path"]).read_text(encoding="utf-8")
    assert "SuperSecretPass" not in mf
    assert "postgresql://user:SuperSecretPass" not in mf


def test_formula_injection_neutralized_values() -> None:
    assert neutralize_formula_injection("=cmd|' /C calc'!A0") == "'=cmd|' /C calc'!A0"
    assert neutralize_formula_injection("-2+3") == "'-2+3"


def test_fixture_fallback_absent_on_real_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    result = run_workflow(
        "workflow.confenge.suppliers",
        {"data_mode": "REAL", "uf": "SC"},
        out_dir=tmp_path / "noblock-fallback",
        code_sha="t",
    )
    assert result["data_mode"] == "REAL"
    assert result["status"] != "SUCCEEDED"
    # Must not produce fixture suppliers.json with sample company names claiming success
    assert not (tmp_path / "noblock-fallback" / "suppliers.json").exists() or result["status"] != "SUCCEEDED"


def test_correction_does_not_rewrite_original_source(tmp_path: Path) -> None:
    src = tmp_path / "public_agencies.json"
    original = [{"orgao": "X", "classificacao_juridica_preliminar": "A"}]
    src.write_text(json.dumps(original), encoding="utf-8")
    before = src.read_text(encoding="utf-8")
    corrected = apply_corrections_to_source(
        src,
        [{"orgao": "X", "fields": {"classificacao_juridica_preliminar": "B"}}],
    )
    assert corrected != src
    assert src.read_text(encoding="utf-8") == before
    assert "B" in corrected.read_text(encoding="utf-8")


def test_artifact_outside_allowlist_rejected(tmp_path: Path) -> None:
    data = tmp_path / "cc-data"
    allow = tmp_path / "allow"
    allow.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.json"
    secret.write_text('{"x":1}', encoding="utf-8")
    settings = Settings(
        host="127.0.0.1",
        port=8765,
        data_dir=data,
        open_browser=False,
        spa_dist=None,
        allowed_artifact_roots=(allow.resolve(),),
    )
    reset_registry()
    client = TestClient(create_app(settings))
    r = client.get("/api/artifacts/content", params={"path": str(secret)})
    assert r.status_code in {403, 404}
