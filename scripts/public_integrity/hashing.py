"""Deterministic content hashing for private payloads."""

from __future__ import annotations

import hashlib
import json
from typing import Any

CONTENT_HASH_EXCLUDED = frozenset({"content_hash"})


def canonical_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical_dumps(obj).encode("utf-8")).hexdigest()


def content_hash(payload: dict[str, Any]) -> str:
    filtered = {key: value for key, value in payload.items() if key not in CONTENT_HASH_EXCLUDED}
    return digest(filtered)


def attach_hash(payload: dict[str, Any]) -> dict[str, Any]:
    body = {key: value for key, value in payload.items() if key != "content_hash"}
    return {**body, "content_hash": content_hash(body)}
