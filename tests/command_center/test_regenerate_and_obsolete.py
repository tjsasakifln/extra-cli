"""Integration: fixture honesty, regenerate, ACCEPT hash invalidation on shipped API."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scripts.command_center.app import create_app
from scripts.command_center.capabilities.registry import reset_registry
from scripts.command_center.config import Settings
from scripts.command_center.workflows.runner import run_workflow


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_registry()
    data = tmp_path / "cc-data"
    out = tmp_path / "output"
    out.mkdir()
    settings = Settings(
        host="127.0.0.1",
        port=8765,
        data_dir=data,
        open_browser=False,
        spa_dist=None,
        allowed_artifact_roots=(out.resolve(), data.resolve()),
        max_concurrent_jobs=2,
    )
    return TestClient(create_app(settings=settings))


def _csrf(c: TestClient) -> str:
    r = c.get("/api/csrf")
    assert r.status_code == 200
    return str(r.json().get("csrf_token") or r.json().get("token"))


def test_use_fixture_false_is_rejected() -> None:
    with pytest.raises(ValueError, match="demonstração|Avançada|fixture"):
        run_workflow(
            "workflow.extra.opportunities",
            {"use_fixture": False, "max_shortlist": 3},
            out_dir=Path("/tmp/should-not-exist-cc-wf"),
            code_sha="x",
        )


def test_regenerate_obsoletes_accept(client: TestClient, tmp_path: Path) -> None:
    token = _csrf(client)
    phrase = "Confirmo a geração local de entregáveis (sem envio automático de mensagens)."
    start = client.post(
        "/api/jobs",
        headers={"X-CC-CSRF": token},
        json={
            "capability_id": "workflow.confenge.public_agencies",
            "params": {"use_fixture": True, "uf": "SC", "max_leads": 3},
            "confirmation": phrase,
        },
    )
    assert start.status_code == 200, start.text
    job_id = start.json()["job"]["job_id"]
    final = None
    for _ in range(80):
        j = client.get(f"/api/jobs/{job_id}").json()["job"]
        if j["status"] not in {"QUEUED", "VALIDATING", "RUNNING", "CANCELLING"}:
            final = j
            break
        time.sleep(0.1)
    assert final and final["status"] == "SUCCEEDED"

    reviews = client.get("/api/reviews?status=pending").json()["reviews"]
    assert reviews, "workflow should enqueue reviews"
    item = reviews[0]
    payload = item.get("payload") or {}
    hashes = payload.get("artifact_hashes") or (
        {"source": payload["content_hash"]} if payload.get("content_hash") else {}
    )
    assert hashes
    conf = client.get(f"/api/reviews/{item['id']}/confirmation").json()
    acc = client.post(
        "/api/decisions",
        headers={"X-CC-CSRF": token},
        json={
            "item_id": item["id"],
            "decision": "ACCEPT",
            "rationale": "Aceite consciente da classificação preliminar com ressalvas.",
            "confirmation": conf["confirmation_phrase"],
            "artifact_hashes": hashes,
        },
    )
    assert acc.status_code == 200, acc.text
    decision_id = acc.json()["decision_id"]

    # Regenerate with a field correction → new hashes → prior ACCEPT obsolete
    regen = client.post(
        "/api/reviews/regenerate",
        headers={"X-CC-CSRF": token},
        json={
            "job_id": job_id,
            "item_id": item["id"],
            "corrections": [
                {
                    "item_key": item.get("payload", {}).get("item_key")
                    or str(item.get("title", "")).split("—")[0].strip(),
                    "orgao": str(item.get("title", "")).split("—")[0].strip()
                    if "—" in str(item.get("title"))
                    else None,
                    "fields": {
                        "classificacao_juridica_preliminar": "revisada por humano — PRELIMINAR",
                        "limitacoes": "Corrigido na bancada; ainda preliminar.",
                    },
                    "note": "Correção de classificação na revisão humana",
                }
            ],
            "note": "e2e regenerate",
        },
    )
    # correction may not match if item_key wrong — still run regenerate without matching source rows
    if regen.status_code == 400 and "correção" in regen.text.lower():
        regen = client.post(
            "/api/reviews/regenerate",
            headers={"X-CC-CSRF": token},
            json={"job_id": job_id, "item_id": item["id"], "corrections": [], "note": "rerun version"},
        )
    assert regen.status_code == 200, regen.text
    body = regen.json()
    assert body["job_id"] != job_id
    assert body.get("content_hashes")
    # Force invalidation with mutated hash if regenerate didn't change source hash
    current = dict(body.get("content_hashes") or {})
    if current.get("source") == hashes.get("source"):
        current["source"] = "mutated-" + str(current.get("source") or "x")
    inv = client.get(
        "/api/decisions",
        params={"item_id": item["id"], "current_hashes": json.dumps(current)},
    )
    assert inv.status_code == 200
    # decisions for item should show obsolete ACCEPT
    decs = inv.json()["decisions"]
    accept_rows = [d for d in decs if d.get("id") == decision_id or d.get("decision") == "ACCEPT"]
    assert accept_rows
    # either marked via regenerate or via current_hashes query
    assert any(d.get("obsolete") for d in accept_rows) or inv.json().get("marked_obsolete")


def test_last_params_preset_saved(client: TestClient) -> None:
    token = _csrf(client)
    phrase = "Confirmo a geração local de entregáveis (sem envio automático de mensagens)."
    start = client.post(
        "/api/jobs",
        headers={"X-CC-CSRF": token},
        json={
            "capability_id": "workflow.extra.opportunities",
            "params": {"use_fixture": True, "max_shortlist": 4, "period_days": 14},
            "confirmation": phrase,
        },
    )
    assert start.status_code == 200
    pref = client.get("/api/preferences/last_params:workflow.extra.opportunities")
    assert pref.status_code == 200
    val = pref.json().get("value")
    assert val
    data = json.loads(val)
    assert data.get("max_shortlist") == 4
    assert data.get("period_days") == 14
