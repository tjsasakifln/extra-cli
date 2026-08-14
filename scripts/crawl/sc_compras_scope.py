"""SC Compras collection contract: pagination proof and per-entity verdicts.

FOUND / ZERO_CONFIRMED are emitted only after a complete query. A snapshot hash
change invalidates an incompatible checkpoint.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal

SLA_HOURS = 24
WINDOW_START = "2025-01-01"

EntityVerdict = Literal["FOUND", "ZERO_CONFIRMED", "SCOPE_INCOMPLETE"]


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_payload(obj: Any) -> str:
    return hashlib.sha256(_canonical_json(obj).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def digits_only(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def normalize_orgao(*, nome: str, cnpj: str, municipio: str) -> dict[str, str]:
    cnpj14 = digits_only(cnpj)
    if cnpj and len(cnpj14) != 14:
        raise ValueError(f"cnpj_invalido:{cnpj}")
    return {
        "orgao_nome": " ".join((nome or "").split()),
        "orgao_cnpj": cnpj14,
        "municipio": " ".join((municipio or "").split()),
    }


@dataclass(frozen=True)
class CountProof:
    total_elementos: int
    pages: int
    chunks: int
    persisted: int
    rejected: int
    page_size: int

    @property
    def balanced(self) -> bool:
        return self.persisted + self.rejected == self.total_elementos

    @property
    def pages_match(self) -> bool:
        expected = (self.total_elementos + self.page_size - 1) // self.page_size if self.page_size else 0
        return self.pages == expected and self.chunks == self.pages


def reconcile_counts(
    *,
    total_elementos: int,
    pages: int,
    chunks: int,
    persisted: int,
    rejected: int,
    page_size: int = 10,
) -> CountProof:
    if min(total_elementos, pages, chunks, persisted, rejected, page_size) < 0:
        raise ValueError("counts must be non-negative")
    proof = CountProof(total_elementos, pages, chunks, persisted, rejected, page_size)
    if not proof.balanced:
        raise ValueError(f"count_mismatch: persisted({persisted})+rejected({rejected})!=total({total_elementos})")
    if not proof.pages_match:
        raise ValueError(f"pagination_mismatch: pages={pages} chunks={chunks} total={total_elementos} size={page_size}")
    return proof


def entity_verdict(*, query_complete: bool, found_count: int) -> EntityVerdict:
    if not query_complete:
        return "SCOPE_INCOMPLETE"
    if found_count > 0:
        return "FOUND"
    return "ZERO_CONFIRMED"


def checkpoint_compatible(previous_snapshot_hash: str, current_snapshot_hash: str) -> bool:
    if not previous_snapshot_hash or not current_snapshot_hash:
        return False
    return previous_snapshot_hash == current_snapshot_hash


def invalidate_checkpoint(previous_snapshot_hash: str, current_snapshot_hash: str) -> str:
    if checkpoint_compatible(previous_snapshot_hash, current_snapshot_hash):
        return "keep"
    return "invalidate"


@dataclass(frozen=True)
class EntityProof:
    ente_id: str
    orgao: dict[str, str]
    verdict: EntityVerdict
    found_count: int
    raw_sha256: str
    query_complete: bool


def prove_entities(
    rows: list[dict[str, Any]],
    universe: list[dict[str, Any]],
    *,
    snapshot: dict[str, Any],
    previous_checkpoint_hash: str | None,
    query_complete_by_ente: dict[str, bool],
) -> dict[str, Any]:
    snapshot_hash = sha256_payload(snapshot)
    checkpoint = invalidate_checkpoint(previous_checkpoint_hash or "", snapshot_hash)
    by_ente: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        row_ente = str(row.get("ente_id") or row.get("orgao_cnpj") or "")
        by_ente.setdefault(row_ente, []).append(row)
    proofs: list[EntityProof] = []
    for entity in universe:
        ente_id = str(entity["ente_id"])
        complete = bool(query_complete_by_ente.get(ente_id))
        found = by_ente.get(ente_id, [])
        orgao = normalize_orgao(
            nome=str(entity.get("nome") or ""),
            cnpj=str(entity.get("cnpj") or ""),
            municipio=str(entity.get("municipio") or ""),
        )
        proofs.append(
            EntityProof(
                ente_id=ente_id,
                orgao=orgao,
                verdict=entity_verdict(query_complete=complete, found_count=len(found)),
                found_count=len(found),
                raw_sha256=sha256_payload(found),
                query_complete=complete,
            )
        )
    return {
        "snapshot_hash": snapshot_hash,
        "checkpoint": checkpoint,
        "sla_hours": SLA_HOURS,
        "window_start": WINDOW_START,
        "entities": [asdict(p) for p in proofs],
        "generated_at": _utc_now(),
    }
