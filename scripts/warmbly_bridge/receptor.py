"""Optional local HTTP receptor for confenge.outcome.v1 (Warmbly HMAC webhook)."""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from scripts.warmbly_bridge import DEFAULT_HMAC_SKEW_SECONDS, DEFAULT_MAX_BODY_BYTES
from scripts.warmbly_bridge.hmac_sig import redact_for_log, verify_outcome_hmac
from scripts.warmbly_bridge.outcome_mapping import OutcomeValidationError
from scripts.warmbly_bridge.persist import OutcomeStore, persist_outcome

logger = logging.getLogger("warmbly_bridge.receptor")


class ReceptorConfig:
    def __init__(
        self,
        *,
        secret: str,
        store: OutcomeStore,
        client_id: str = "confenge",
        max_skew_seconds: int = DEFAULT_HMAC_SKEW_SECONDS,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        path: str = "/webhooks/warmbly/outcome",
    ) -> None:
        self.secret = secret
        self.store = store
        self.client_id = client_id
        self.max_skew_seconds = max_skew_seconds
        self.max_body_bytes = max_body_bytes
        self.path = path


def process_outcome_request(
    *,
    body: bytes,
    signature_header: str,
    config: ReceptorConfig,
    now: float | None = None,
) -> tuple[int, dict[str, Any]]:
    """Shared verify+persist path used by HTTP handler and tests.

    Returns (http_status, response_json). 2xx only after durable idempotent persist.
    """
    if len(body) > config.max_body_bytes:
        return 413, {"ok": False, "error": "payload_too_large", "max_bytes": config.max_body_bytes}

    ok_sig, reason = verify_outcome_hmac(
        config.secret,
        signature_header,
        body,
        now=now,
        max_skew_seconds=config.max_skew_seconds,
    )
    if not ok_sig:
        logger.warning("outcome_rejected reason=%s", reason)
        status = 401 if reason in {"bad_signature", "malformed_signature_header", "missing_secret"} else 400
        if reason.startswith("timestamp_skew"):
            status = 401
        return status, {"ok": False, "error": reason}

    try:
        envelope = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return 400, {"ok": False, "error": f"invalid_json:{exc}"}

    if not isinstance(envelope, dict):
        return 400, {"ok": False, "error": "payload_not_object"}

    logger.info(
        "outcome_received %s",
        json.dumps(redact_for_log(envelope), ensure_ascii=False, default=str),
    )

    try:
        result = persist_outcome(envelope, store=config.store, client_id=config.client_id)
    except OutcomeValidationError as exc:
        logger.warning("outcome_validation_failed error=%s", exc)
        return 422, {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — surface as 500, do not claim 2xx
        logger.exception("outcome_persist_failed")
        return 500, {"ok": False, "error": f"persist_failed:{exc}"}

    # 2xx only after successful durable persist (including idempotent duplicate).
    return 200, {
        "ok": True,
        "created": result.get("created"),
        "status": result.get("status"),
        "idempotency_key": result.get("idempotency_key"),
        "opportunity_key": result.get("opportunity_key"),
        "dm_outcome_type": result.get("dm_outcome_type"),
        "suggested_commercial_state": result.get("suggested_commercial_state"),
    }


def make_handler(config: ReceptorConfig) -> type[BaseHTTPRequestHandler]:
    class OutcomeHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            logger.info("%s - " + fmt, self.address_string(), *args)

        def _read_body(self) -> bytes | None:
            length = int(self.headers.get("Content-Length") or "0")
            if length > config.max_body_bytes:
                return None
            return self.rfile.read(length)

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path in {config.path, "/health", "/healthz"}:
                self._send(200, {"ok": True, "service": "warmbly-outcome-receptor"})
                return
            self._send(404, {"ok": False, "error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != config.path:
                self._send(404, {"ok": False, "error": "not_found"})
                return
            length = int(self.headers.get("Content-Length") or "0")
            if length > config.max_body_bytes:
                self._send(413, {"ok": False, "error": "payload_too_large"})
                return
            body = self.rfile.read(length)
            sig = self.headers.get("X-Warmbly-Signature") or self.headers.get("x-warmbly-signature") or ""
            status, payload = process_outcome_request(
                body=body,
                signature_header=sig,
                config=config,
            )
            self._send(status, payload)

    return OutcomeHandler


def serve_forever(
    config: ReceptorConfig,
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
) -> ThreadingHTTPServer:
    handler = make_handler(config)
    server = ThreadingHTTPServer((host, port), handler)
    logger.info(
        "warmbly outcome receptor listening on http://%s:%s%s",
        host,
        port,
        config.path,
    )
    return server
