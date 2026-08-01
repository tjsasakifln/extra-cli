"""Adversarial security tests for Command Center REAL adapters + paths."""

from __future__ import annotations

import json
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
    out = tmp_path / "noblock-fallback"
    result = run_workflow(
        "workflow.confenge.suppliers",
        {"data_mode": "REAL", "uf": "SC"},
        out_dir=out,
        code_sha="t",
    )
    assert result["data_mode"] == "REAL"
    assert result["status"] != "SUCCEEDED"
    assert str(result["status"]).startswith("BLOCKED_")
    # Must not produce fixture suppliers.json / workbook from sample_data
    assert not (out / "suppliers.json").exists()
    assert not (out / "planilha-comercial-fornecedores.xlsx").exists()
    assert not (out / "relatorio-executivo-fornecedores.pdf").exists()
    mf = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    snaps = mf.get("source_snapshots") or []
    assert all(not (isinstance(s, dict) and s.get("type") == "fixture") for s in snaps)


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


def test_symlink_escape_rejected(tmp_path: Path) -> None:
    """Symlink under allowlist that points outside must not be served."""
    data = tmp_path / "cc-data"
    allow = tmp_path / "allow"
    allow.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("LEAK", encoding="utf-8")
    link = allow / "escape-link.txt"
    try:
        link.symlink_to(secret)
    except OSError as exc:  # pragma: no cover — env without symlink support
        pytest.skip(f"symlink unavailable: {exc}")
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
    r = client.get("/api/artifacts/content", params={"path": str(link)})
    # Must not return secret content (403/404 preferred; 400 also ok)
    assert r.status_code in {400, 403, 404}
    if r.status_code == 200:  # pragma: no cover
        assert "LEAK" not in r.text


def test_process_documents_no_cwd_global_artifact_leak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """REAL interpret must not attach files from repo-relative output/process_documents."""
    from scripts.command_center.adapters.base import PreflightResult, SubprocessResult
    from scripts.command_center.adapters.process_documents import ProcessDocumentsAdapter

    planted = Path("output/process_documents")
    planted.mkdir(parents=True, exist_ok=True)
    leak = planted / "LEAK_FROM_CWD.json"
    leak.write_text('{"leak": true}\n', encoding="utf-8")
    try:
        adapter = ProcessDocumentsAdapter()
        out = tmp_path / "run-out"
        out.mkdir()
        pf = PreflightResult(status="READY", safe_to_run=True, checks=[], limitations=[])
        proc = SubprocessResult(
            exit_code=0,
            stdout=json.dumps({"documents": []}),
            stderr="",
            started_at="t0",
            finished_at="t1",
            duration_ms=1,
            argv=["python", "-m", "scripts.process_documents", "show", "q"],
        )
        ar = adapter.interpret({}, out_dir=out, proc=proc, preflight=pf)
        assert ar.coverage.get("documents") == 0
        assert ar.rows == []
        assert not any("LEAK_FROM_CWD" in str(p) for p in ar.artifacts)
        assert not any(str(p).endswith("LEAK_FROM_CWD.json") for p in ar.artifacts)
    finally:
        leak.unlink(missing_ok=True)


def test_workspace_filters_jobs(tmp_path: Path) -> None:
    from scripts.command_center.store import JobRecord, Store, workspace_for_capability

    store = Store(tmp_path / "cc.sqlite3")
    wid_extra, cid_extra = workspace_for_capability("workflow.extra.opportunities")
    wid_sup, cid_sup = workspace_for_capability("workflow.confenge.suppliers")
    store.create_job(
        JobRecord(
            job_id="j1",
            capability_id="workflow.extra.opportunities",
            action="Extra",
            params={},
            workspace_id=wid_extra,
            client_id=cid_extra,
        )
    )
    store.create_job(
        JobRecord(
            job_id="j2",
            capability_id="workflow.confenge.suppliers",
            action="Suppliers",
            params={},
            workspace_id=wid_sup,
            client_id=cid_sup,
        )
    )
    all_jobs = store.list_jobs(limit=10)
    assert len(all_jobs) == 2
    only_extra = store.list_jobs(limit=10, workspace_id="extra-construtora")
    assert len(only_extra) == 1
    assert only_extra[0].job_id == "j1"


def test_regen_overlay_preserves_real_data_mode(tmp_path: Path) -> None:
    """Correction overlay on REAL parent must not rewrite data_mode to FIXTURE."""
    from scripts.command_center.regenerate import regenerate_workflow_version

    prior = tmp_path / "public_agencies.json"
    prior.write_text(
        json.dumps(
            [
                {
                    "orgao": "Prefeitura Harness",
                    "uf": "SC",
                    "tipo": "municipio",
                    "classificacao_juridica_preliminar": "PRELIMINAR",
                    "risco_fracionamento": "medio",
                    "conflito_interesse": "nao",
                    "objeto_recente": "obra harness",
                    "limitacoes": "harness",
                }
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "regen"
    result = regenerate_workflow_version(
        workflow_id="workflow.confenge.public_agencies",
        params={"data_mode": "REAL", "uf": "SC", "max_leads": 1},
        out_dir=out,
        code_sha="t",
        job_id="regen1",
        parent_run_id="parent1",
        corrections=[
            {
                "orgao": "Prefeitura Harness",
                "fields": {"classificacao_juridica_preliminar": "CORRIGIDA_OVERLAY"},
            }
        ],
        prior_source=prior,
    )
    assert result["data_mode"] == "REAL"
    mf = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert mf["data_mode"] == "REAL"
    snaps = mf.get("source_snapshots") or []
    assert any(isinstance(s, dict) and s.get("type") == "correction_overlay" for s in snaps)
    assert not any(isinstance(s, dict) and s.get("type") == "fixture" for s in snaps)
    body = (out / "public_agencies.json").read_text(encoding="utf-8")
    assert "CORRIGIDA_OVERLAY" in body
