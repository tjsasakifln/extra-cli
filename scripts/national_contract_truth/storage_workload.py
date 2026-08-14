"""#315 — versioned physical-design workload contract for national contracts.

A design is PROVEN only when a representative corpus (>= 3.7M facts) ran
the versioned SQL workload and recorded EXPLAIN/latency/WAL evidence.
Otherwise the seal stays UNPROVEN. This module never invents a 3.7M run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

SCHEMA_VERSION = "storage-workload/1.0"
WORKLOAD_VERSION = "national-contracts-sql-v1"
MIN_REPRESENTATIVE_FACTS = 3_700_000
SERIAL_MAX = 2_147_483_647

Seal = Literal["PROVEN", "UNPROVEN"]

WORKLOAD_QUERIES: tuple[dict[str, str], ...] = (
    {"id": "upsert_conflict", "sql": "INSERT INTO national_contracts AS t (...) ON CONFLICT (source, source_contract_id) DO UPDATE ..."},
    {"id": "temporal_range", "sql": "SELECT * FROM national_contracts WHERE source_event_date BETWEEN %s AND %s"},
    {"id": "by_buyer", "sql": "SELECT * FROM national_contracts WHERE orgao_cnpj = %s"},
    {"id": "by_supplier", "sql": "SELECT * FROM national_contracts WHERE supplier_identifier = %s"},
    {"id": "by_id", "sql": "SELECT * FROM national_contracts WHERE canonical_contract_id = %s"},
    {"id": "versions", "sql": "SELECT * FROM national_contract_versions WHERE canonical_contract_id = %s"},
    {"id": "aggregates", "sql": "SELECT orgao_cnpj, count(*), sum(valor_total) FROM national_contracts GROUP BY 1"},
)


class StorageWorkloadError(ValueError):
    """Physical-design proof cannot be sealed."""


def sha256_payload(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class WorkloadEvidence:
    query_id: str
    explain_analyze: str | None
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    wal_bytes: int | None
    buffers: dict[str, int] | None = None


@dataclass(frozen=True)
class DesignCandidate:
    name: str
    partitioning: str
    pk_type: str
    notes: str


def evaluate_pk_headroom(pk_type: str, current_rows: int) -> dict[str, Any]:
    if pk_type.upper() == "SERIAL":
        remaining = SERIAL_MAX - current_rows
        return {
            "pk_type": pk_type,
            "supports_national_growth": False,
            "remaining": remaining,
            "blocker": "SERIAL_EXHAUSTION_RISK",
        }
    if pk_type.upper() in {"BIGSERIAL", "BIGINT", "UUID"}:
        return {
            "pk_type": pk_type,
            "supports_national_growth": True,
            "remaining": None,
            "blocker": None,
        }
    raise StorageWorkloadError(f"unknown_pk_type:{pk_type}")


def seal_workload(
    *,
    corpus_facts: int,
    incremental_churn: int,
    evidence: tuple[WorkloadEvidence, ...],
    candidate: DesignCandidate,
    current_rows: int,
    disk_wal_budget: dict[str, int] | None = None,
    rollback_rehearsed: bool = False,
) -> dict[str, Any]:
    """Return the versioned contract. UNPROVEN unless the corpus actually ran."""
    required_ids = {q["id"] for q in WORKLOAD_QUERIES}
    seen = {e.query_id for e in evidence}
    blockers: list[str] = []
    if corpus_facts < MIN_REPRESENTATIVE_FACTS:
        blockers.append(f"corpus_below_representative:{corpus_facts}<{MIN_REPRESENTATIVE_FACTS}")
    if incremental_churn < 0:
        blockers.append("negative_churn")
    missing = required_ids - seen
    if missing:
        blockers.append(f"missing_workload:{sorted(missing)}")
    incomplete = [
        e.query_id
        for e in evidence
        if not e.explain_analyze or e.p50_ms is None or e.p95_ms is None or e.p99_ms is None
    ]
    if incomplete:
        blockers.append(f"incomplete_metrics:{incomplete}")
    pk = evaluate_pk_headroom(candidate.pk_type, current_rows)
    if pk["blocker"]:
        blockers.append(str(pk["blocker"]))
    if disk_wal_budget is None:
        blockers.append("disk_wal_budget_unrecorded")
    if not rollback_rehearsed:
        blockers.append("rollback_not_rehearsed")

    seal: Seal = "PROVEN" if not blockers else "UNPROVEN"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "workload_version": WORKLOAD_VERSION,
        "workload": list(WORKLOAD_QUERIES),
        "candidate": {
            "name": candidate.name,
            "partitioning": candidate.partitioning,
            "pk_type": candidate.pk_type,
            "notes": candidate.notes,
        },
        "corpus_facts": corpus_facts,
        "incremental_churn": incremental_churn,
        "pk": pk,
        "seal": seal,
        "blockers": blockers,
        "claim_nacional_physical_design_proven": seal == "PROVEN",
    }
    payload["contract_hash"] = sha256_payload(
        {k: v for k, v in payload.items() if k != "contract_hash"}
    )
    return payload
