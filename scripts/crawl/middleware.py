"""STUB: Request middleware for distributed tracing.

Minimal definitions to enable imports from middleware.
Full implementation deferred.
"""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


__all__ = [
    "request_id_var",
]
