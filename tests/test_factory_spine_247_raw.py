"""Refs #247 — immutable raw HTTP envelope with revalidatable SHA-256."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.factory_spine.store import FactoryStore


def test_issue_247_raw_cas_dedup_redacts_secrets_and_keeps_body_out_of_envelope(tmp_path: Path) -> None:
    store = FactoryStore(tmp_path)
    body = b'{"ok": true, "items": []}'
    first = store.archive_raw(
        source="pncp",
        run_id="run-a",
        request_scope="entity-1:pncp",
        payload=body,
        url="https://pncp.gov.br/api?token=super-secret&pagina=1",
        http_status=200,
        headers={"Authorization": "Bearer super-secret", "Content-Type": "application/json"},
        page=1,
        crawl_job_attempt_id=9,
    )
    second = store.archive_raw(
        source="pncp",
        run_id="run-b",
        request_scope="entity-1:pncp",
        payload=body,
        url="https://pncp.gov.br/api?token=super-secret&pagina=1",
        http_status=200,
        page=1,
    )
    assert first["body_sha256"] == hashlib.sha256(body).hexdigest()
    assert first["body_sha256"] == second["body_sha256"]
    assert first["body_uri"].startswith("cas://raw-http/")
    envelope = json.loads(Path(first["envelope_path"]).read_text(encoding="utf-8"))
    dumped = json.dumps(envelope)
    assert "body" not in envelope
    assert "payload" not in envelope
    assert "super-secret" not in dumped
    assert envelope["sanitized_url"] is not None
    assert "token=" in envelope["sanitized_url"]
    assert "super-secret" not in envelope["sanitized_url"]
    assert "redacted" in envelope["sanitized_url"]
    loaded = store.raw.load_reference(first["envelope_path"])
    cas_body = (
        store.raw.root / "cas" / first["body_sha256"][:2] / first["body_sha256"][2:4] / f"{first['body_sha256']}.body"
    )
    assert cas_body.read_bytes() == body
    assert hashlib.sha256(cas_body.read_bytes()).hexdigest() == first["body_sha256"]
    assert loaded["envelope"]["body_sha256"] == first["body_sha256"]
    assert cas_body.is_relative_to(tmp_path)
    assert "payload" not in json.dumps(envelope)
