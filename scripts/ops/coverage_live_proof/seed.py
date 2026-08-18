"""Deterministic coverage_evidence seed for scenarios A–C (replay-safe)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from scripts.ops.coverage_live_proof import SEED_COMPLETED_AT, SEED_RUN_ID
from scripts.ops.coverage_live_proof.errors import SeedError

# Fixed identity used by scenario B. Not a planilha member; identity proof
# goes through dual_coverage_evidence_gate, not universe membership.
ENTITY_ID = 10
CANONICAL_ENTITY_KEY = "ent-10"
SOURCE = "pncp"
DATA_TYPE = "bids"
CAPABILITY = "open_tenders"


@dataclass(frozen=True)
class SeedRow:
    scenario: str
    entity_id: int | None
    canonical_entity_key: str | None
    source: str
    data_type: str
    capability: str
    run_id: str
    state: str
    count_obtained: int
    count_persisted: int
    metadata: dict[str, Any]


def seed_rows() -> tuple[SeedRow, ...]:
    """Minimal fixture: source-wide (A), entity-scoped (B), unmappable (C)."""
    source_wide_meta = {
        "pipeline": "resilient_cycle",
        "live_proof_scenario": "A",
        "grain": "source_wide",
    }
    return (
        SeedRow(
            scenario="A",
            entity_id=None,
            canonical_entity_key=None,
            source=SOURCE,
            data_type=DATA_TYPE,
            capability=CAPABILITY,
            run_id=SEED_RUN_ID,
            state="success_with_data",
            count_obtained=800,
            count_persisted=800,
            metadata=source_wide_meta,
        ),
        SeedRow(
            scenario="B",
            entity_id=ENTITY_ID,
            canonical_entity_key=CANONICAL_ENTITY_KEY,
            source=SOURCE,
            data_type=DATA_TYPE,
            capability=CAPABILITY,
            run_id=SEED_RUN_ID,
            state="success_with_data",
            count_obtained=3,
            count_persisted=3,
            metadata={"live_proof_scenario": "B", "grain": "entity"},
        ),
        SeedRow(
            scenario="C",
            entity_id=99,
            canonical_entity_key="ghost-unmappable",
            source=SOURCE,
            data_type=DATA_TYPE,
            capability=CAPABILITY,
            run_id=SEED_RUN_ID,
            state="success_with_data",
            count_obtained=1,
            count_persisted=1,
            metadata={
                "identity_status": "unmappable",
                "live_proof_scenario": "C",
                "grain": "incompatible",
            },
        ),
    )


def seed_fixture_payload() -> dict[str, Any]:
    return {
        "run_id": SEED_RUN_ID,
        "completed_at": SEED_COMPLETED_AT,
        "rows": [asdict(row) for row in seed_rows()],
    }


def seed_fixture_sha256() -> str:
    payload = json.dumps(seed_fixture_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _row_exists(cur: Any, row: SeedRow) -> bool:
    if row.entity_id is None and row.canonical_entity_key is None:
        cur.execute(
            """
            SELECT 1 FROM coverage_evidence
             WHERE source = %s AND data_type = %s AND run_id = %s
               AND entity_id IS NULL AND canonical_entity_key IS NULL
             LIMIT 1
            """,
            (row.source, row.data_type, row.run_id),
        )
    elif row.canonical_entity_key:
        cur.execute(
            """
            SELECT 1 FROM coverage_evidence
             WHERE canonical_entity_key = %s AND source = %s
               AND data_type = %s AND run_id = %s
             LIMIT 1
            """,
            (row.canonical_entity_key, row.source, row.data_type, row.run_id),
        )
    else:
        cur.execute(
            """
            SELECT 1 FROM coverage_evidence
             WHERE entity_id = %s AND source = %s AND data_type = %s AND run_id = %s
               AND canonical_entity_key IS NULL
             LIMIT 1
            """,
            (row.entity_id, row.source, row.data_type, row.run_id),
        )
    return cur.fetchone() is not None


def apply_seed(conn: Any) -> dict[str, int]:
    """Insert the fixture idempotently. Returns inserted/skipped counts."""
    from psycopg2.extras import Json

    cur = conn.cursor()
    inserted = 0
    skipped = 0
    try:
        for row in seed_rows():
            if _row_exists(cur, row):
                skipped += 1
                continue
            try:
                cur.execute(
                    """
                    INSERT INTO coverage_evidence (
                        entity_id, canonical_entity_key, source, data_type,
                        capability, run_id, state, count_obtained, count_transformed,
                        count_persisted, metadata, queried_start, queried_end,
                        completed_at, checked_at, applicability, freshness_status
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s::timestamptz, %s::timestamptz, %s, %s
                    )
                    """,
                    (
                        row.entity_id,
                        row.canonical_entity_key,
                        row.source,
                        row.data_type,
                        row.capability,
                        row.run_id,
                        row.state,
                        row.count_obtained,
                        row.count_persisted,
                        row.count_persisted,
                        Json(row.metadata),
                        date(2026, 7, 1),
                        date(2026, 7, 31),
                        SEED_COMPLETED_AT,
                        SEED_COMPLETED_AT,
                        "applicable",
                        "unknown",
                    ),
                )
            except Exception as exc:
                raise SeedError(f"seed insert failed for scenario {row.scenario}: {exc}") from exc
            inserted += 1
        commit = getattr(conn, "commit", None)
        if callable(commit):
            commit()
    finally:
        close = getattr(cur, "close", None)
        if callable(close):
            close()
    return {"inserted": inserted, "skipped": skipped, "fixture_rows": len(seed_rows())}


def load_seed_rows(conn: Any) -> list[dict[str, Any]]:
    """Load seeded coverage_evidence rows as mappings for the shipped gate."""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT entity_id, canonical_entity_key, source, data_type, state::text,
                   run_id, count_obtained, count_persisted, metadata, capability, id
              FROM coverage_evidence
             WHERE run_id = %s
             ORDER BY id
            """,
            (SEED_RUN_ID,),
        )
        fetched = cur.fetchall() or []
    finally:
        close = getattr(cur, "close", None)
        if callable(close):
            close()

    rows: list[dict[str, Any]] = []
    for item in fetched:
        metadata = item[8] if isinstance(item[8], dict) else {}
        if not isinstance(metadata, dict):
            try:
                metadata = json.loads(str(item[8] or "{}"))
            except json.JSONDecodeError:
                metadata = {}
        rows.append(
            {
                "entity_id": item[0],
                "canonical_entity_key": item[1],
                "source": item[2],
                "data_type": item[3],
                "state": item[4],
                "run_id": item[5],
                "count_obtained": item[6],
                "count_persisted": item[7],
                "metadata": metadata,
                "capability": item[9],
                "evidence_id": item[10],
            }
        )
    return rows


def count_seed_rows(conn: Any) -> int:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT count(*) FROM coverage_evidence WHERE run_id = %s",
            (SEED_RUN_ID,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        close = getattr(cur, "close", None)
        if callable(close):
            close()
