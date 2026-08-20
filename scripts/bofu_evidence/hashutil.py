"""Canonical JSON and SHA-256 for public-read-bofu-evidence/1.0."""

from __future__ import annotations

import hashlib
import json
from typing import Any

HASH_FIELD = "content_hash"


def canonical_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_dumps(payload).encode("utf-8")).hexdigest()


def sha256_text(text: str) -> str:
    """SHA-256 of UTF-8 file bytes. Used by SHA256SUMS (not json.dumps of the text)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_without_content_hash(document: dict[str, Any]) -> str:
    payload = {key: value for key, value in document.items() if key != HASH_FIELD}
    return content_hash(payload)


def stamp_hash(document: dict[str, Any]) -> dict[str, Any]:
    stamped = {key: value for key, value in document.items() if key != HASH_FIELD}
    stamped[HASH_FIELD] = hash_without_content_hash(stamped)
    return stamped
