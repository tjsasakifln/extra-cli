"""Entity source bindings with capability (ADR-028 Option A).

Thin module over ``entity_source_binding`` — multi-capability per entity-source
via UNIQUE (canonical_id, source_id, capability).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any

CAPABILITIES: tuple[str, ...] = ("notices_or_bids", "contracts")
APPLICABILITIES: tuple[str, ...] = ("applicable", "not_applicable", "unknown")
BINDING_STATUSES: tuple[str, ...] = ("active", "blocked", "deprecated")


@dataclass(frozen=True)
class EntitySourceBinding:
    canonical_id: str
    source_id: str
    capability: str
    applicability: str = "unknown"
    acquisition_method: str = "unknown"
    portal_url: str | None = None
    external_org_id: str | None = None
    confidence: float = 0.0
    status: str = "active"
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    last_verified_at: str | None = None
    current_blocker: str | None = None
    next_action: str = "review_binding"
    evidence_ref: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.canonical_id:
            errors.append("canonical_id_required")
        if not self.source_id:
            errors.append("source_id_required")
        if self.capability not in CAPABILITIES:
            errors.append(f"invalid_capability:{self.capability}")
        if self.applicability not in APPLICABILITIES:
            errors.append(f"invalid_applicability:{self.applicability}")
        if self.status not in BINDING_STATUSES:
            errors.append(f"invalid_status:{self.status}")
        return errors


def binding_identity_key(b: EntitySourceBinding) -> tuple[str, str, str]:
    return (b.canonical_id, b.source_id, b.capability)


def detect_invalid_duplicates(
    bindings: Sequence[EntitySourceBinding],
) -> list[tuple[str, str, str]]:
    """Return identity keys that appear more than once."""
    seen: set[tuple[str, str, str]] = set()
    dups: list[tuple[str, str, str]] = []
    for b in bindings:
        key = binding_identity_key(b)
        if key in seen:
            dups.append(key)
        else:
            seen.add(key)
    return dups


def ensure_capability_pair(
    canonical_id: str,
    source_id: str,
    *,
    applicability: str = "unknown",
) -> list[EntitySourceBinding]:
    """Create both capability bindings for an entity-source pair (honest unknown)."""
    return [
        EntitySourceBinding(
            canonical_id=canonical_id,
            source_id=source_id,
            capability=cap,
            applicability=applicability,
        )
        for cap in CAPABILITIES
    ]


def filter_by_capability(
    bindings: Iterable[EntitySourceBinding],
    capability: str,
) -> list[EntitySourceBinding]:
    if capability not in CAPABILITIES:
        raise ValueError(f"unknown capability: {capability}")
    return [b for b in bindings if b.capability == capability]


UPSERT_COLUMNS = (
    "canonical_id",
    "source_id",
    "capability",
    "applicability",
    "acquisition_method",
    "portal_url",
    "external_org_id",
    "confidence",
    "status",
    "last_attempt_at",
    "last_success_at",
    "last_verified_at",
    "current_blocker",
    "next_action",
    "evidence_ref",
    "notes",
)


def binding_to_row(binding: EntitySourceBinding) -> tuple[Any, ...]:
    data = binding.to_dict()
    return tuple(data[c] for c in UPSERT_COLUMNS)


def sync_bindings_to_postgres(
    bindings: Iterable[EntitySourceBinding],
    *,
    dsn: str,
) -> dict[str, int]:
    """Idempotent upsert into entity_source_binding (migration 058)."""
    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("psycopg2 is required for binding sync") from exc

    rows = [binding_to_row(b) for b in bindings]
    if detect_invalid_duplicates(
        [EntitySourceBinding(
            canonical_id=str(r[0]),
            source_id=str(r[1]),
            capability=str(r[2]),
        ) for r in rows]
    ):
        raise ValueError("duplicate (canonical_id, source_id, capability) in batch")

    updates = ", ".join(
        f"{c}=EXCLUDED.{c}"
        for c in UPSERT_COLUMNS
        if c not in {"canonical_id", "source_id", "capability"}
    )
    sql = f"""
        INSERT INTO public.entity_source_binding ({', '.join(UPSERT_COLUMNS)})
        VALUES %s
        ON CONFLICT (canonical_id, source_id, capability) DO UPDATE SET {updates}
    """  # noqa: S608
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            if rows:
                execute_values(cur, sql, rows, page_size=250)
            cur.execute("SELECT COUNT(*) FROM public.entity_source_binding")
            total = int(cur.fetchone()[0])
    return {"submitted": len(rows), "persisted_total": total}
