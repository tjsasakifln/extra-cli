"""Real pipeline adapters — unit/integration without claiming LIVE from fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scripts.command_center.adapters import (
    AdapterBlockedError,
    DataMode,
    get_adapter,
    list_adapter_workflow_ids,
    resolve_data_mode,
    run_real_adapter,
)
from scripts.command_center.adapters.base import (
    SubprocessResult,
    public_params,
)
from scripts.command_center.app import create_app
from scripts.command_center.capabilities.registry import reset_registry
from scripts.command_center.config import Settings
from scripts.command_center.run_manifest import load_manifest
from scripts.command_center.workflows.runner import run_workflow


def test_resolve_data_mode_explicit_and_compat() -> None:
    assert resolve_data_mode({"data_mode": "REAL"}) is DataMode.REAL
    assert resolve_data_mode({"data_mode": "fixture"}) is DataMode.FIXTURE
    assert resolve_data_mode({"use_fixture": True}) is DataMode.FIXTURE
    assert resolve_data_mode({"use_fixture": False}) is DataMode.REAL
    assert resolve_data_mode({}) is DataMode.FIXTURE
    with pytest.raises(ValueError):
        resolve_data_mode({"data_mode": "LIVE_FAKE"})


def test_four_adapters_registered() -> None:
    """Baseline four workflows remain; consulting chain adapters are additive."""
    ids = list_adapter_workflow_ids()
    for required in (
        "workflow.confenge.public_agencies",
        "workflow.confenge.suppliers",
        "workflow.extra.opportunities",
        "workflow.process_documents",
        "workflow.edital_case",
        "workflow.budget_audit",
        "workflow.technical_acervo",
        "workflow.bid_readiness",
    ):
        assert required in ids


@pytest.mark.parametrize(
    "workflow_id",
    list_adapter_workflow_ids(),
)
def test_argv_is_list_no_shell_metachar_injection(workflow_id: str, tmp_path: Path) -> None:
    adapter = get_adapter(workflow_id)
    assert adapter is not None
    params: dict = {
        "data_mode": "REAL",
        "uf": "SC",
        "query": "ok-query",
        "max_shortlist": 3,
        "max_companies": 3,
        "max_leads": 3,
        "service": "pavimentacao",
        "source": "tests/fixtures/sample",
        "source_dir": "tests/fixtures/sample",
        "requirements": "scripts/bid_readiness/fixtures/golden/requirements.json",
        "documents": "scripts/bid_readiness/fixtures/golden/documents",
        "reference_date": "2026-08-01",
        "quantity": 10,
        "unit": "m2",
    }
    argv = adapter.build_argv(params, out_dir=tmp_path)
    assert isinstance(argv, list)
    assert all(isinstance(a, str) for a in argv)
    assert argv[0] == sys.executable
    assert "-m" in argv
    assert not any(";" in a or "|" in a or "&&" in a for a in argv)


def test_process_documents_rejects_query_injection(tmp_path: Path) -> None:
    adapter = get_adapter("workflow.process_documents")
    assert adapter is not None
    with pytest.raises(ValueError, match="não permitidos"):
        adapter.build_argv({"query": "foo; rm -rf /"}, out_dir=tmp_path)


def test_public_params_redacts_secrets() -> None:
    out = public_params({"dsn": "postgresql://u:secret@h/db", "uf": "SC", "token": "abc"})
    assert out["dsn"] == "[REDACTED]"
    assert out["token"] == "[REDACTED]"
    assert out["uf"] == "SC"
    assert "secret" not in json.dumps(out)


def test_real_preflight_blocks_without_dsn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    adapter = get_adapter("workflow.extra.opportunities")
    assert adapter is not None
    pf = adapter.preflight({}, out_dir=tmp_path)
    assert pf.safe_to_run is False
    assert pf.status.startswith("BLOCKED_")
    with pytest.raises(AdapterBlockedError):
        run_real_adapter(adapter, {}, out_dir=tmp_path)


def test_no_silent_fixture_fallback_on_real_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    result = run_workflow(
        "workflow.extra.opportunities",
        {"data_mode": "REAL", "max_shortlist": 2},
        out_dir=tmp_path / "real-block",
        code_sha="test",
    )
    assert result["data_mode"] == "REAL"
    assert str(result["status"]).startswith("BLOCKED_")
    mf = load_manifest(Path(result["manifest_path"]))
    assert mf["data_mode"] == "REAL"
    snaps = mf.get("source_snapshots") or []
    assert snaps == [] or all(s.get("type") != "fixture" for s in snaps if isinstance(s, dict))
    assert "sample_data" not in json.dumps(mf).lower()
    # Must not claim SUCCEEDED or LIVE
    assert result["status"] != "SUCCEEDED"
    assert mf.get("terminal_claim") not in {"LIVE_READY", "LIVE", "FIXTURE_DEMO"}
    # Must not produce fixture deliverables on REAL block
    assert not (tmp_path / "real-block" / "opportunities.json").exists()
    assert not (tmp_path / "real-block" / "workbook-oportunidades-extra.xlsx").exists()


def test_fixture_mode_explicit_succeeds(tmp_path: Path) -> None:
    result = run_workflow(
        "workflow.extra.opportunities",
        {"data_mode": "FIXTURE", "max_shortlist": 2},
        out_dir=tmp_path / "demo",
        code_sha="test",
    )
    assert result["status"] == "SUCCEEDED"
    assert result["data_mode"] == "FIXTURE"
    mf = load_manifest(Path(result["manifest_path"]))
    assert mf["data_mode"] == "FIXTURE"
    assert any("fixture" in str(s).lower() or s.get("type") == "fixture" for s in mf.get("source_snapshots") or [])


def test_real_harness_exec_produces_real_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Controlled harness: REAL path runs argv + data_mode=REAL without live DSN claim of LIVE_READY."""
    monkeypatch.setenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")

    def fake_exec(argv: list[str], cwd: Path, env: dict | None) -> SubprocessResult:
        assert isinstance(argv, list)
        assert "-m" in argv
        out = tmp_path / "harness-out"
        # Discover out_dir from argv --out / --output-dir / public-agency-out
        target = out
        for flag in ("--out", "--output-dir", "--public-agency-out", "--weekly-dir"):
            if flag in argv:
                idx = argv.index(flag)
                target = Path(argv[idx + 1])
                break
        # For process_documents show there is no --out; write via stdout JSON
        if "process_documents" in " ".join(argv):
            payload = json.dumps(
                {"documents": [{"id": "d1", "nome": "Edital demo harness", "categoria": "edital"}]},
                ensure_ascii=False,
            )
            return SubprocessResult(
                exit_code=0,
                stdout=payload,
                stderr="",
                started_at="2026-07-31T00:00:00+00:00",
                finished_at="2026-07-31T00:00:01+00:00",
                duration_ms=10,
                argv=argv,
            )
        target.mkdir(parents=True, exist_ok=True)
        if "extra" in " ".join(argv) or "weekly" in " ".join(argv) or "decision" in " ".join(argv):
            (target / "opportunities.json").write_text(
                json.dumps(
                    [{"id": "H1", "orgao": "Harness", "objeto": "Obra", "uf": "SC", "evidencia": "h"}],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        elif "suppliers" in " ".join(argv) or "public-agencies" not in " ".join(argv):
            commercial = target if target.name != "commercial" else target
            commercial.mkdir(parents=True, exist_ok=True)
            (commercial / "suppliers.json").write_text(
                json.dumps(
                    {
                        "companies": [
                            {
                                "cnpj": "00.000.000/0001-91",
                                "razao_social": "Harness Ltda",
                                "uf": "SC",
                                "municipio": "Florianópolis",
                                "score": 1,
                                "contratos_36m": 1,
                                "valor_contratos": 1,
                                "cadastro_oficial": "RESOLVED",
                                "sinais": "h",
                                "limitacoes": "harness",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        if "public-agencies" in " ".join(argv):
            pag = target
            pag.mkdir(parents=True, exist_ok=True)
            (pag / "public_agencies.json").write_text(
                json.dumps(
                    [
                        {
                            "orgao": "Prefeitura Harness",
                            "uf": "SC",
                            "classificacao_juridica_preliminar": "PRELIMINAR",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        return SubprocessResult(
            exit_code=0,
            stdout="HARNESS_OK",
            stderr="",
            started_at="2026-07-31T00:00:00+00:00",
            finished_at="2026-07-31T00:00:01+00:00",
            duration_ms=10,
            argv=argv,
        )

    # Patch postgres check to pass under harness without real server
    from scripts.command_center.adapters import base as base_mod

    monkeypatch.setattr(
        base_mod,
        "check_postgres_optional",
        lambda *_a, **_k: base_mod.PreflightCheck(name="postgres", ok=True, detail="harness"),
    )

    for workflow_id, params in [
        ("workflow.extra.opportunities", {"data_mode": "REAL", "max_shortlist": 2, "skip_collect": True}),
        ("workflow.confenge.suppliers", {"data_mode": "REAL", "uf": "SC", "max_companies": 2}),
        ("workflow.confenge.public_agencies", {"data_mode": "REAL", "uf": "SC", "max_leads": 2}),
        ("workflow.process_documents", {"data_mode": "REAL", "query": "demo-harness"}),
    ]:
        out = tmp_path / workflow_id.replace(".", "_")
        result = run_workflow(
            workflow_id,
            params,
            out_dir=out,
            code_sha="harness",
            exec_fn=fake_exec,
        )
        assert result["data_mode"] == "REAL", workflow_id
        assert result["status"] == "SUCCEEDED", (workflow_id, result)
        mf = load_manifest(Path(result["manifest_path"]))
        assert mf["data_mode"] == "REAL"
        assert mf.get("terminal_claim") != "FIXTURE_DEMO"
        body = json.dumps(mf)
        assert "sample_data" not in body
        assert "FIXTURE_DEMO" not in body


def test_preflight_api_fixture_and_real_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    settings = Settings(
        host="127.0.0.1",
        port=8765,
        data_dir=tmp_path / "data",
    )
    reset_registry()
    app = create_app(settings)
    client = TestClient(app)
    r = client.get("/api/workflows/workflow.extra.opportunities/preflight?data_mode=FIXTURE")
    assert r.status_code == 200
    assert r.json()["status"] == "READY"
    assert r.json()["data_mode"] == "FIXTURE"
    r2 = client.get("/api/workflows/workflow.extra.opportunities/preflight?data_mode=REAL")
    assert r2.status_code == 200
    body = r2.json()
    assert body["safe_to_run"] is False
    assert str(body["status"]).startswith("BLOCKED_")


def test_forged_real_status_not_from_fixture_path(tmp_path: Path) -> None:
    """Fixture run must not emit data_mode=REAL."""
    result = run_workflow(
        "workflow.confenge.suppliers",
        {"use_fixture": True, "uf": "SC", "max_companies": 2},
        out_dir=tmp_path / "fix",
        code_sha="t",
    )
    mf = load_manifest(Path(result["manifest_path"]))
    assert mf["data_mode"] == "FIXTURE"
    assert result["data_mode"] == "FIXTURE"
