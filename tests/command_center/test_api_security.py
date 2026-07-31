"""API/security tests for EXTRA Command Center — drive shipped app."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scripts.command_center.app import create_app
from scripts.command_center.capabilities.base import Capability, ParamSpec, RiskLevel
from scripts.command_center.capabilities.registry import reset_registry
from scripts.command_center.config import Settings
from scripts.command_center.redaction import redact_text
from scripts.command_center.status_normalize import normalize_exit


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    data = tmp_path / "cc-data"
    root = Path(__file__).resolve().parents[2]
    out = tmp_path / "output"
    out.mkdir()
    (out / "sample.json").write_text('{"ok": true, "password": "super-secret"}\n', encoding="utf-8")
    settings = Settings(
        host="127.0.0.1",
        port=8765,
        data_dir=data,
        open_browser=False,
        spa_dist=None,
        allowed_artifact_roots=(out.resolve(), data.resolve()),
        max_concurrent_jobs=2,
    )

    def _fixture(params: dict) -> list[str]:
        import sys

        return [sys.executable, "-c", "print('FIXTURE_DONE'); print('ok')"]

    caps = [
        Capability(
            id="cc.fixture.echo",
            name="Fixture",
            description="safe",
            category="ops",
            argv_builder=_fixture,
            params=[ParamSpec("message", "Mensagem", default="x")],
            risk=RiskLevel.READ,
            fixture=True,
        ),
        Capability(
            id="missing.example",
            name="Missing",
            description="gone",
            category="ops",
            argv_builder=lambda p: ["false"],
            required_modules=["scripts.this_module_does_not_exist_zz"],
            expected_pr="future",
        ),
    ]
    reset_registry(caps)
    app = create_app(settings)
    return TestClient(app)


def _csrf(client: TestClient) -> dict[str, str]:
    res = client.get("/api/csrf")
    assert res.status_code == 200
    token = res.json()["csrf_token"]
    return {"X-CC-CSRF": token}


def test_health_bind_and_registry(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["host"] == "127.0.0.1"
    assert body["public_bind"] is False
    assert body["capabilities"]["total"] >= 2
    # secrets not dumped
    assert "postgresql://" not in str(body).lower()
    assert body["env"]["LOCAL_DATALAKE_DSN"] in {"configurada", "ausente", "inválida", "não testada", "configurada"}


def test_capabilities_missing_degrade(client: TestClient) -> None:
    res = client.get("/api/capabilities")
    assert res.status_code == 200
    items = {c["id"]: c for c in res.json()["capabilities"]}
    assert items["cc.fixture.echo"]["availability"] == "available"
    assert items["missing.example"]["availability"] == "missing_module"
    assert "não disponível" in (items["missing.example"]["unavailable_reason"] or "").lower() or "disponível" in (
        items["missing.example"]["unavailable_reason"] or ""
    ).lower()


def test_reject_arbitrary_command_params(client: TestClient) -> None:
    headers = _csrf(client)
    res = client.post(
        "/api/jobs",
        headers=headers,
        json={"capability_id": "cc.fixture.echo", "params": {"command": "id", "message": "x"}},
    )
    assert res.status_code == 400


def test_path_traversal_rejected(client: TestClient) -> None:
    res = client.get("/api/artifacts", params={"path": "../../etc/passwd"})
    assert res.status_code in {400, 403, 404}


def test_fixture_job_lifecycle(client: TestClient) -> None:
    headers = _csrf(client)
    res = client.post(
        "/api/jobs",
        headers=headers,
        json={"capability_id": "cc.fixture.echo", "params": {"message": "hello"}},
    )
    assert res.status_code == 200, res.text
    job_id = res.json()["job"]["job_id"]
    # poll
    import time

    final = None
    deadline = time.time() + 20
    while time.time() < deadline:
        detail = client.get(f"/api/jobs/{job_id}")
        assert detail.status_code == 200
        final = detail.json()["job"]
        if final["status"] not in {"QUEUED", "VALIDATING", "RUNNING", "CANCELLING"}:
            break
        time.sleep(0.1)
    assert final is not None, "job never observed"
    assert final["status"] in {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"}, final
    logs = client.get(f"/api/jobs/{job_id}/logs")
    assert logs.status_code == 200
    messages = " ".join(x["message"] for x in logs.json()["logs"])
    assert "FIXTURE_DONE" in messages or "ok" in messages


def test_secret_redaction_helper() -> None:
    raw = "password=supersecret postgresql://user:pass@localhost/db token=abc"
    clean = redact_text(raw)
    assert "supersecret" not in clean
    assert "user:pass" not in clean
    assert "[REDACTED]" in clean


def test_normalize_human_block() -> None:
    status = normalize_exit(0, stdout="BLOCKED_INSUFFICIENT_HUMAN_LABELS")
    assert status.state.value == "BLOCKED_HUMAN"
    assert "avaliação" in status.human_message.lower() or "humana" in status.human_message.lower()


def test_csrf_required(client: TestClient) -> None:
    res = client.post("/api/jobs", json={"capability_id": "cc.fixture.echo", "params": {}})
    assert res.status_code == 403


def test_decision_accept_requires_phrase(client: TestClient) -> None:
    headers = _csrf(client)
    res = client.post(
        "/api/decisions",
        headers=headers,
        json={
            "item_id": "x1",
            "decision": "ACCEPT",
            "payload": {"sensitive": True, "confirmation_phrase": "SIM EU CONFIRMO"},
        },
    )
    assert res.status_code == 400
    ok = client.post(
        "/api/decisions",
        headers=headers,
        json={
            "item_id": "x1",
            "decision": "ACCEPT",
            "confirmation": "SIM EU CONFIRMO",
            "payload": {"sensitive": True, "confirmation_phrase": "SIM EU CONFIRMO"},
        },
    )
    assert ok.status_code == 200
    assert ok.json()["ok"] is True


def test_dod_accept_blocked(client: TestClient) -> None:
    headers = _csrf(client)
    res = client.post(
        "/api/decisions",
        headers=headers,
        json={
            "item_id": "DOD-1",
            "decision": "ACCEPT",
            "confirmation": "Confirmo que revisei os dados e autorizo apenas a inclusão deste item na fila manual.",
            "payload": {
                "sensitive": True,
                "confirmation_phrase": "Confirmo que revisei os dados e autorizo apenas a inclusão deste item na fila manual.",
            },
        },
    )
    assert res.status_code == 200
    assert res.json().get("blocked") is True
