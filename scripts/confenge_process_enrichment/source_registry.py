"""Lazy per-organ process source registry (versioned knowledge cache)."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_process_enrichment.identifiers import normalize_cnpj


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class ProcessSourceEntry:
    contracting_entity_cnpj: str
    entity_name: str | None = None
    uf: str | None = None
    municipality: str | None = None
    process_system_family: str = "unknown"
    search_base_url: str | None = None
    query_mechanism: str | None = None  # process_number_path | query_param | html_search | api
    supports_process_number: bool = False
    supports_document_listing: bool = False
    supports_direct_download: bool = False
    authentication_required: bool = False
    captcha_required: bool = False
    robots_access_constraints: str | None = None
    last_verified_at: str | None = None
    success_count: int = 0
    failure_count: int = 0
    confidence: float = 0.5
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProcessSourceEntry:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


class ProcessSourceRegistry:
    """In-memory + optional JSON persistence; keyed by organ CNPJ."""

    SCHEMA = "confenge_process_source_registry.v1"

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._by_cnpj: dict[str, ProcessSourceEntry] = {}
        if path and path.is_file():
            self.load(path)

    def load(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("entries") if isinstance(data, dict) else data
        with self._lock:
            for row in entries or []:
                if not isinstance(row, dict):
                    continue
                e = ProcessSourceEntry.from_dict(row)
                c = normalize_cnpj(e.contracting_entity_cnpj)
                if c:
                    e.contracting_entity_cnpj = c
                    self._by_cnpj[c] = e

    def save(self, path: Path | None = None) -> None:
        path = path or self.path
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            payload = {
                "schema_id": self.SCHEMA,
                "updated_at": _now(),
                "entries": [e.to_dict() for e in self._by_cnpj.values()],
            }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, orgao_cnpj: str) -> ProcessSourceEntry | None:
        c = normalize_cnpj(orgao_cnpj)
        with self._lock:
            return self._by_cnpj.get(c)

    def upsert(self, entry: ProcessSourceEntry) -> ProcessSourceEntry:
        c = normalize_cnpj(entry.contracting_entity_cnpj)
        entry.contracting_entity_cnpj = c
        entry.last_verified_at = entry.last_verified_at or _now()
        with self._lock:
            existing = self._by_cnpj.get(c)
            if existing:
                # merge counters
                entry.success_count = max(entry.success_count, existing.success_count)
                entry.failure_count = max(entry.failure_count, existing.failure_count)
            self._by_cnpj[c] = entry
        return entry

    def record_success(self, orgao_cnpj: str, **updates: Any) -> None:
        c = normalize_cnpj(orgao_cnpj)
        with self._lock:
            e = self._by_cnpj.get(c) or ProcessSourceEntry(contracting_entity_cnpj=c)
            e.success_count += 1
            e.last_verified_at = _now()
            e.confidence = min(1.0, e.confidence + 0.05)
            for k, v in updates.items():
                if hasattr(e, k) and v is not None:
                    setattr(e, k, v)
            self._by_cnpj[c] = e

    def record_failure(self, orgao_cnpj: str, *, note: str | None = None) -> None:
        c = normalize_cnpj(orgao_cnpj)
        with self._lock:
            e = self._by_cnpj.get(c) or ProcessSourceEntry(contracting_entity_cnpj=c)
            e.failure_count += 1
            e.last_verified_at = _now()
            e.confidence = max(0.1, e.confidence - 0.05)
            if note:
                e.notes = note
            self._by_cnpj[c] = e

    def list_entries(self) -> list[ProcessSourceEntry]:
        with self._lock:
            return list(self._by_cnpj.values())


# Seed: PNCP is always a known family for federal transparency of contracts
def seed_pncp_family(registry: ProcessSourceRegistry, orgao_cnpj: str, *, uf: str | None = None) -> None:
    registry.upsert(
        ProcessSourceEntry(
            contracting_entity_cnpj=orgao_cnpj,
            process_system_family="pncp",
            search_base_url="https://pncp.gov.br/api/pncp/v1",
            query_mechanism="api",
            supports_process_number=False,
            supports_document_listing=True,
            supports_direct_download=True,
            authentication_required=False,
            captcha_required=False,
            confidence=0.9,
            uf=uf,
            notes="National PNCP arquivos API for compras",
        )
    )
