"""Launch real stdlib HTTP receptor and POST a signed confenge.outcome.v1 body."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from scripts.warmbly_bridge.hmac_sig import sign_outcome_hmac
from scripts.warmbly_bridge.persist import InMemoryOutcomeStore
from scripts.warmbly_bridge.receptor import ReceptorConfig, serve_forever

SECRET = "http-roundtrip-secret"


def test_http_roundtrip_signed_outcome(outcome_fixture: Path) -> None:
    store = InMemoryOutcomeStore()
    config = ReceptorConfig(
        secret=SECRET,
        store=store,
        client_id="confenge",
        path="/webhooks/warmbly/outcome",
    )
    server = serve_forever(config, host="127.0.0.1", port=0)
    host, port = server.server_address[:2]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = outcome_fixture.read_bytes()
        ts = int(time.time())
        header = sign_outcome_hmac(SECRET, ts, body)
        req = urllib.request.Request(
            f"http://{host}:{port}/webhooks/warmbly/outcome",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Warmbly-Signature": header,
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert 200 <= resp.status < 300
            payload = json.loads(resp.read().decode("utf-8"))
        assert payload["ok"] is True
        assert payload["created"] is True
        key = payload["idempotency_key"]
        assert store.get_outcome_by_idempotency("confenge", key) is not None

        # Replay → still 2xx, no second row
        req2 = urllib.request.Request(
            f"http://{host}:{port}/webhooks/warmbly/outcome",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Warmbly-Signature": header,
            },
        )
        with urllib.request.urlopen(req2, timeout=5) as resp2:
            payload2 = json.loads(resp2.read().decode("utf-8"))
        assert payload2["created"] is False
        assert len(store.rows) == 1

        # Bad signature → non-2xx
        bad = urllib.request.Request(
            f"http://{host}:{port}/webhooks/warmbly/outcome",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Warmbly-Signature": "t=1,v1=00",
            },
        )
        with pytest_raises_http():
            urllib.request.urlopen(bad, timeout=5)
        assert len(store.rows) == 1
    finally:
        server.shutdown()
        server.server_close()


class pytest_raises_http:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError("expected HTTPError")
        if issubclass(exc_type, urllib.error.HTTPError):
            assert exc.code >= 400
            return True
        return False
