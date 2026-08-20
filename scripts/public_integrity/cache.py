"""TTL cache. Expired entries are never labeled current."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CacheLookup:
    hit: bool
    expired: bool
    is_current: bool
    stored_at: datetime | None
    expires_at: datetime | None
    payload: dict[str, Any] | None


@dataclass
class IntegrityCache:
    entries: dict[str, tuple[datetime, datetime, dict[str, Any]]] = field(default_factory=dict)

    def get(self, queried_cnpj: str, *, now: datetime) -> CacheLookup:
        stored = self.entries.get(queried_cnpj)
        if stored is None:
            return CacheLookup(
                hit=False,
                expired=False,
                is_current=False,
                stored_at=None,
                expires_at=None,
                payload=None,
            )
        stored_at, expires_at, payload = stored
        expired = now >= expires_at
        return CacheLookup(
            hit=True,
            expired=expired,
            is_current=not expired,
            stored_at=stored_at,
            expires_at=expires_at,
            payload=payload,
        )

    def put(
        self,
        queried_cnpj: str,
        payload: dict[str, Any],
        *,
        stored_at: datetime,
        expires_at: datetime,
    ) -> None:
        self.entries[queried_cnpj] = (stored_at, expires_at, payload)


def cache_from_fixture(fixture: dict[str, Any], *, now: datetime) -> tuple[IntegrityCache, CacheLookup | None]:
    raw = fixture.get("cache")
    cache = IntegrityCache()
    if not isinstance(raw, dict):
        return cache, None
    cnpj = str(raw.get("queried_cnpj") or "")
    stored_at = datetime.fromisoformat(str(raw["stored_at"]).replace("Z", "+00:00"))
    expires_at = datetime.fromisoformat(str(raw["expires_at"]).replace("Z", "+00:00"))
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    if cnpj:
        cache.put(cnpj, payload, stored_at=stored_at, expires_at=expires_at)
        return cache, cache.get(cnpj, now=now)
    return cache, CacheLookup(
        hit=True,
        expired=now >= expires_at,
        is_current=now < expires_at,
        stored_at=stored_at,
        expires_at=expires_at,
        payload=payload,
    )
