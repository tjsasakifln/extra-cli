"""File metadata helpers — hash, size, type, origin (DoD §14).

PDFs/attachments are NOT stored in PostgreSQL by default; only metadata
and filesystem/object paths with hashes.
"""
from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Any


def file_metadata(
    path: str | Path,
    *,
    origin: str,
    store_in_postgres: bool = False,
) -> dict[str, Any]:
    """Return hash, size, type, origin for an external file.

    ``store_in_postgres`` must remain False unless an explicit justification
    is provided in ``justification``.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    data = p.read_bytes()
    mime, _ = mimetypes.guess_type(str(p))
    return {
        "path": str(p),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "content_type": mime or "application/octet-stream",
        "origin": origin,
        "stored_in_postgres": bool(store_in_postgres),
        "policy": "pdf_and_attachments_outside_postgres_by_default",
    }


def assert_not_in_postgres(meta: dict[str, Any], *, justification: str | None = None) -> None:
    if meta.get("stored_in_postgres") and not justification:
        raise ValueError(
            "PDFs/anexos não devem ser armazenados no PostgreSQL sem justificativa"
        )
