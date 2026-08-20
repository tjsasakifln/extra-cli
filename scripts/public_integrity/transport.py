"""Injectable HTTP boundary. Tests feed captured/redacted pages and error codes."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from scripts.public_integrity.models import TransportResponse
from scripts.public_integrity.redaction import redact_text

API_BASE = "https://api.portaldatransparencia.gov.br/api-de-dados"
API_KEY_ENV = "PORTAL_TRANSPARENCIA_API_KEY"


class Transport(Protocol):
    def fetch(
        self,
        *,
        source_id: str,
        path: str,
        params: dict[str, Any],
    ) -> TransportResponse: ...


class FixtureTransport:
    """Replay a captured fixture. Never talks to Portal da Transparência."""

    def __init__(self, fixture: dict[str, Any]) -> None:
        self.fixture = fixture
        self.calls: list[dict[str, Any]] = []

    def fetch(
        self,
        *,
        source_id: str,
        path: str,
        params: dict[str, Any],
    ) -> TransportResponse:
        page = str(params.get("pagina", 1))
        self.calls.append({"source_id": source_id, "path": path, "pagina": page})
        sources = self.fixture.get("sources") or {}
        source = sources.get(source_id) or {}
        pages = source.get("pages") or {}
        if page not in pages:
            return TransportResponse(status_code=0, body=None, error_class="source_unavailable")
        entry = pages[page] or {}
        error = entry.get("error")
        status_code = int(entry.get("status_code") or 0)
        headers = {str(key): str(value) for key, value in (entry.get("headers") or {}).items()}
        if error in {"timeout", "network"}:
            return TransportResponse(
                status_code=0,
                body=None,
                error_class=error,
                headers=headers,
            )
        body = entry.get("body", [] if status_code in {200, 204} else None)
        if status_code == 204:
            body = []
        if status_code == 429 and not error:
            error = "rate_limit"
        if status_code >= 500 and not error:
            error = "http_5xx"
        return TransportResponse(
            status_code=status_code,
            body=body,
            error_class=error,
            headers=headers,
        )


class HttpTransport:
    """Live Portal da Transparência client. Auth header stays out of the repo."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 30.0,
        base_url: str = API_BASE,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get(API_KEY_ENV, "")
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")

    def fetch(
        self,
        *,
        source_id: str,
        path: str,
        params: dict[str, Any],
    ) -> TransportResponse:
        del source_id
        import httpx

        url = f"{self._base_url}{path}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "extra-cli-public-integrity/1.0",
        }
        if self._api_key:
            headers["chave-api-dados"] = self._api_key
        try:
            response = httpx.get(url, params=params, headers=headers, timeout=self._timeout)
        except httpx.TimeoutException:
            return TransportResponse(status_code=0, body=None, error_class="timeout")
        except httpx.RequestError as exc:
            return TransportResponse(
                status_code=0,
                body=None,
                error_class="network",
                headers={"detail": redact_text(str(exc)[:200])},
            )
        error = None
        body: Any = None
        if response.status_code == 204:
            body = []
        elif response.status_code == 200:
            try:
                body = response.json()
            except json.JSONDecodeError:
                body = response.text
                error = "schema_drift"
        elif response.status_code == 429:
            error = "rate_limit"
        elif response.status_code >= 500:
            error = "http_5xx"
        return TransportResponse(
            status_code=response.status_code,
            body=body,
            error_class=error,
            headers={"retry-after": response.headers.get("Retry-After", "")},
        )


def load_fixture(path: str | os.PathLike[str]) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("fixture_must_be_object")
    return payload
