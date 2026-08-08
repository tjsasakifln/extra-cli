"""Filesystem cache with provenance for resolution results (idempotent re-runs).

Provenance fields: source, fetched_at, expires_at, content_hash.
Network-mode isolation stays in cache_key (adapters_sig includes net=0|1).
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def cache_key(cnpj14: str, service_context: str, adapters_sig: str) -> str:
    raw = f"{cnpj14}|{service_context}|{adapters_sig}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _content_hash(payload: Any) -> str:
    body = json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ResolutionCache:
    def __init__(
        self,
        root: Path,
        *,
        ttl_seconds: int = 86400,
        source: str = "confenge_contact_resolution",
    ) -> None:
        self.root = Path(root)
        self.ttl_seconds = ttl_seconds
        self.source = source
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

        # Prefer expires_at; fall back to legacy _cached_at + ttl
        expires_at = data.get("expires_at")
        fetched_at = data.get("fetched_at") or data.get("_cached_at")
        now = time.time()
        if expires_at is not None:
            try:
                # ISO or epoch
                if isinstance(expires_at, (int, float)):
                    if now > float(expires_at):
                        return None
                else:
                    exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                    if datetime.now(UTC) > exp:
                        return None
            except (TypeError, ValueError):
                return None
        elif fetched_at is not None:
            try:
                ts = float(fetched_at) if not isinstance(fetched_at, str) else None
                if ts is None and isinstance(fetched_at, str) and fetched_at.replace(".", "", 1).isdigit():
                    ts = float(fetched_at)
                if ts is None:
                    # ISO string without expires_at: use ttl from file mtime fallback
                    ts = p.stat().st_mtime
                if now - float(ts) > self.ttl_seconds:
                    return None
            except (TypeError, ValueError, OSError):
                return None
        else:
            return None

        payload = data.get("payload")
        if payload is None:
            return None
        # Optional integrity check
        stored_hash = data.get("content_hash")
        if stored_hash and _content_hash(payload) != stored_hash:
            return None
        return payload

    def set(
        self,
        key: str,
        payload: dict[str, Any],
        *,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Store payload with provenance; returns the envelope written."""
        p = self._path(key)
        now = time.time()
        fetched_iso = _now_iso()
        expires_epoch = now + self.ttl_seconds
        expires_iso = (
            datetime.fromtimestamp(expires_epoch, tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        ch = _content_hash(payload)
        envelope = {
            "source": source or self.source,
            "fetched_at": fetched_iso,
            "expires_at": expires_iso,
            "content_hash": ch,
            "_cached_at": now,  # legacy readers
            "payload": payload,
        }
        p.write_text(json.dumps(envelope, ensure_ascii=False, default=str), encoding="utf-8")
        return envelope

    def get_envelope(self, key: str) -> dict[str, Any] | None:
        """Return full cache envelope including provenance (or None if miss/expired)."""
        p = self._path(key)
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if self.get(key) is None:
            return None
        return data
