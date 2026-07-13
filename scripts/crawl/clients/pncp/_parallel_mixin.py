"""STUB: _PNCPParallelMixin for parallel UF fetching.

Minimal definitions to enable imports from clients.pncp._parallel_mixin.
Full implementation lives in scripts/crawl/_parallel_mixin.py.
"""

from __future__ import annotations

STATUS_PNCP_MAP: dict[str, str | None] = {
    "recebendo_proposta": "recebendo_proposta",
    "em_julgamento": "propostas_encerradas",
    "encerrada": "encerrada",
    "todos": None,
}


class _PNCPParallelMixin:
    """STUB: Mixin providing parallel-fetch methods for AsyncPNCPClient.

    Full implementation in scripts/crawl/_parallel_mixin.py.
    """

    pass


__all__ = [
    "_PNCPParallelMixin",
    "STATUS_PNCP_MAP",
]
