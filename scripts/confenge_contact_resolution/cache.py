"""Simple filesystem cache with TTL for resolution results (idempotent re-runs)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def cache_key(cnpj14: str, service_context: str, adapters_sig: str) -> str:
    raw = f"{cnpj14}|{service_context}|{adapters_sig}"
    return hashlib.sha256(raw.encode()).hexdigest()


class ResolutionCache:
    def __init__(self, root: Path, *, ttl_seconds: int = 86400) -> None:
        self.root = Path(root)
        self.ttl_seconds = ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        p = self._path(key)
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        ts = data.get("_cached_at")
        if ts is None:
            return None
        if time.time() - float(ts) > self.ttl_seconds:
            return None
        return data.get("payload")

    def set(self, key: str, payload: dict[str, Any]) -> None:
        p = self._path(key)
        blob = {"_cached_at": time.time(), "payload": payload}
        p.write_text(json.dumps(blob, ensure_ascii=False, default=str), encoding="utf-8")
