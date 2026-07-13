"""STUB: PNCP async client types.

Minimal definitions to enable imports from clients.pncp.async_client.
Full implementation lives in scripts/crawl/async_client.py.
"""

from __future__ import annotations

from typing import Any


class PNCPDegradedError(Exception):
    """Raised when PNCP circuit breaker is in degraded state."""

    pass


# Mapping from StatusLicitacao enum values to PNCP API parameter values
STATUS_PNCP_MAP: dict[str, str | None] = {
    "recebendo_proposta": "recebendo_proposta",
    "em_julgamento": "propostas_encerradas",
    "encerrada": "encerrada",
    "todos": None,
}


class AsyncPNCPClient:
    """STUB: Async HTTP client for PNCP API.

    Full implementation in scripts/crawl/async_client.py.
    """

    BASE_URL = "https://pncp.gov.br/api/consulta/v1"

    def __init__(self, config: Any = None, max_concurrent: int = 10):
        raise NotImplementedError("Use scripts/crawl/async_client.py for real implementation")


__all__ = [
    "AsyncPNCPClient",
    "PNCPDegradedError",
    "STATUS_PNCP_MAP",
]
