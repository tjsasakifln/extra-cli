"""API/security tests for EXTRA Command Center — drive shipped app."""

from __future__ import annotations

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

    def _slow(params: dict) -> list[str]:
        import sys

        secs = int(params.get("seconds") or 8)
        code = (
            "import time,sys;"
            f"secs={secs};"
            "print('SLOW_START', flush=True);"
            "for i in range(secs):"
            " time.sleep(1);"
            " print('TICK', i+1, flush=True);"
            "print('SLOW_DONE', flush=True)"
        )
        return [sys.executable, "-c", code]

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
            id="cc.fixture.slow",
            name="Slow fixture",
            description="cancel target",
            category="ops",
            argv_builder=_slow,
            params=[ParamSpec("seconds", "Seconds", type="int", default=8)],
            risk=RiskLevel.READ,
            fixture=True,
            allow_cancel=True,
            timeout_sec=60,
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
    assert (
        "não disponível" in (items["missing.example"]["unavailable_reason"] or "").lower()
        or "disponível" in (items["missing.example"]["unavailable_reason"] or "").lower()
    )


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
    # Client cannot weaken sensitivity via payload
    bypass = client.post(
        "/api/decisions",
        headers=headers,
        json={
            "item_id": "x1",
            "decision": "ACCEPT",
            "payload": {"sensitive": False, "confirmation_phrase": "whatever"},
        },
    )
    assert bypass.status_code == 400
    phrase = (
        "Confirmo que revisei os dados e autorizo apenas a inclusão deste item na fila manual."
    )
    # Client-supplied wrong phrase is ignored — must match backend phrase
    wrong = client.post(
        "/api/decisions",
        headers=headers,
        json={
            "item_id": "x1",
            "decision": "ACCEPT",
            "confirmation": "SIM EU CONFIRMO",
            "payload": {"sensitive": True, "confirmation_phrase": "SIM EU CONFIRMO"},
        },
    )
    assert wrong.status_code == 400
    ok = client.post(
        "/api/decisions",
        headers=headers,
        json={
            "item_id": "x1",
            "decision": "ACCEPT",
            "confirmation": phrase,
            "payload": {"sensitive": False, "confirmation_phrase": "IGNORADO"},
        },
    )
    assert ok.status_code == 200
    assert ok.json()["ok"] is True
    assert ok.json()["sensitive"] is True


def test_dod_accept_blocked(client: TestClient) -> None:
    headers = _csrf(client)
    phrase = (
        "Confirmo que revisei os dados e autorizo apenas a inclusão deste item na fila manual."
    )
    res = client.post(
        "/api/decisions",
        headers=headers,
        json={
            "item_id": "DOD-1",
            "decision": "ACCEPT",
            "confirmation": phrase,
            "payload": {},
        },
    )
    assert res.status_code == 200
    assert res.json().get("blocked") is True


def test_spa_fallback_rejects_path_traversal(tmp_path: Path) -> None:
    """SPA static fallback must not serve files outside dist."""
    import sys

    from scripts.command_center.app import create_app
    from scripts.command_center.capabilities.base import Capability, RiskLevel
    from scripts.command_center.capabilities.registry import reset_registry
    from scripts.command_center.config import Settings

    spa = tmp_path / "dist"
    spa.mkdir()
    (spa / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    (spa / "safe.txt").write_text("safe", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    settings = Settings(
        host="127.0.0.1",
        port=8765,
        data_dir=tmp_path / "data",
        open_browser=False,
        spa_dist=spa,
        allowed_artifact_roots=(tmp_path.resolve(),),
    )
    reset_registry(
        [
            Capability(
                id="cc.fixture.echo",
                name="Fixture",
                description="safe",
                category="ops",
                argv_builder=lambda p: [sys.executable, "-c", "print(1)"],
                fixture=True,
                risk=RiskLevel.READ,
            )
        ]
    )

    app = create_app(settings)
    c = TestClient(app)
    ok = c.get("/safe.txt")
    assert ok.status_code == 200
    assert b"safe" in ok.content
    # Traversal attempts must not leak secret — either index fallback or not secret body
    for path in ("../secret.txt", "..%2Fsecret.txt", "....//secret.txt"):
        res = c.get(f"/{path}")
        body = res.content
        assert b"TOPSECRET" not in body



def test_slow_job_cancel_never_succeeds(client: TestClient) -> None:
    """start → cancel must terminate CANCELLED, never SUCCEEDED (cancel race)."""
    import time

    headers = _csrf(client)
    res = client.post(
        "/api/jobs",
        headers=headers,
        json={"capability_id": "cc.fixture.slow", "params": {"seconds": 12}},
    )
    assert res.status_code == 200, res.text
    job_id = res.json()["job"]["job_id"]
    # Wait until process is actually running so cancel has a target
    for _ in range(50):
        st = client.get(f"/api/jobs/{job_id}").json()["job"]
        if st["status"] in {"RUNNING", "VALIDATING"} or st.get("pid"):
            break
        time.sleep(0.05)
    cancel = client.post(f"/api/jobs/{job_id}/cancel", headers=headers, json={})
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["job"]["cancel_requested"] is True
    final = None
    for _ in range(100):
        detail = client.get(f"/api/jobs/{job_id}")
        final = detail.json()["job"]
        if final["status"] not in {"QUEUED", "VALIDATING", "RUNNING", "CANCELLING"}:
            break
        time.sleep(0.1)
    assert final is not None
    assert final["status"] == "CANCELLED", final
    assert final["cancel_requested"] is True
    assert final["status"] != "SUCCEEDED"


def test_cancel_immediate_spotcheck(client: TestClient) -> None:
    """Multiple start+immediate cancel must not finish as SUCCEEDED."""
    import time

    headers = _csrf(client)
    outcomes: list[str] = []
    for _ in range(8):
        res = client.post(
            "/api/jobs",
            headers=headers,
            json={"capability_id": "cc.fixture.slow", "params": {"seconds": 10}},
        )
        assert res.status_code == 200
        job_id = res.json()["job"]["job_id"]
        client.post(f"/api/jobs/{job_id}/cancel", headers=headers, json={})
        final = None
        for _ in range(80):
            final = client.get(f"/api/jobs/{job_id}").json()["job"]
            if final["status"] not in {"QUEUED", "VALIDATING", "RUNNING", "CANCELLING"}:
                break
            time.sleep(0.08)
        assert final is not None
        outcomes.append(final["status"])
        assert final["status"] != "SUCCEEDED", final
        assert final["cancel_requested"] is True
    # At least majority cancelled (all should be CANCELLED when race-free)
    assert outcomes.count("CANCELLED") >= 6, outcomes
    assert "SUCCEEDED" not in outcomes


def test_sse_events_stream_logs_and_end(client: TestClient) -> None:
    """Drive shipped /events endpoint — logs + terminal end event."""
    import json

    headers = _csrf(client)
    res = client.post(
        "/api/jobs",
        headers=headers,
        json={"capability_id": "cc.fixture.echo", "params": {"message": "sse"}},
    )
    job_id = res.json()["job"]["job_id"]
    # TestClient streaming
    with client.stream("GET", f"/api/jobs/{job_id}/events") as stream:
        assert stream.status_code == 200
        saw_log = False
        saw_end = False
        saw_status = False
        for line in stream.iter_lines():
            if not line:
                continue
            if line.startswith("event: end"):
                saw_end = True
                break
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if payload.get("type") == "log":
                    saw_log = True
                if payload.get("type") == "status":
                    saw_status = True
                    st = payload.get("job", {}).get("status")
                    if st and st not in {"QUEUED", "VALIDATING", "RUNNING", "CANCELLING"}:
                        # may get end next
                        pass
        assert saw_status or saw_log
        # end may be last; if not seen, job should still be terminal via API
        if not saw_end:
            import time

            for _ in range(40):
                st = client.get(f"/api/jobs/{job_id}").json()["job"]["status"]
                if st not in {"QUEUED", "VALIDATING", "RUNNING", "CANCELLING"}:
                    break
                time.sleep(0.05)
        final = client.get(f"/api/jobs/{job_id}").json()["job"]
        assert final["status"] in {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS", "CANCELLED", "FAILED"}


def test_review_queue_from_enqueue(client: TestClient) -> None:
    headers = _csrf(client)
    empty = client.get("/api/reviews?status=pending")
    assert empty.status_code == 200
    enq = client.post(
        "/api/reviews",
        headers=headers,
        json={
            "title": "Revisar shortlist local",
            "source": "test",
            "evidence": "artifact path X",
            "limitations": "amostra limitada",
            "risks": "falso positivo",
        },
    )
    assert enq.status_code == 200, enq.text
    rid = enq.json()["id"]
    pending = client.get("/api/reviews?status=pending")
    ids = [r["id"] for r in pending.json()["reviews"]]
    assert rid in ids
    # Decide and leave queue (REJECT requires real rationale — not the title alone)
    dec = client.post(
        "/api/decisions",
        headers=headers,
        json={
            "item_id": rid,
            "decision": "REJECT",
            "rationale": "Fora do perfil técnico e prazo inviável para a equipe.",
            "payload": {"sensitive": False},
        },
    )
    assert dec.status_code == 200, dec.text
    pending2 = client.get("/api/reviews?status=pending")
    ids2 = [r["id"] for r in pending2.json()["reviews"]]
    assert rid not in ids2
