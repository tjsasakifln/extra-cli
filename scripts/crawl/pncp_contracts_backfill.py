"""Per-entity / per-window PNCP contracts backfill.

Each window ends complete or failed. Pagination, raw URI, hashes and
obtained/rejected/persisted reconcile. Values distinguish estimado,
homologado, contratado and pago. Buyer intelligence only uses rows with
provenance. 429/5xx are retryable.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

WINDOW_START = "2025-01-01"
RETRYABLE = frozenset({408, 429, 500, 502, 503, 504})
VALUE_KINDS = ("estimado", "homologado", "contratado", "pago")
WindowStatus = Literal["complete", "failed"]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class PageEvidence:
    page: int
    url: str
    status: int
    raw_uri: str
    sha256: str
    records: int
    retryable: bool


@dataclass(frozen=True)
class ContractObservation:
    ente_id: str
    contract_id: str
    value_kind: str
    amount: float
    provenance: dict[str, Any]


@dataclass
class WindowJob:
    ente_id: str
    window_start: str
    window_end: str
    status: WindowStatus | None = None
    checkpoint_after_persist: bool = False
    pages: list[PageEvidence] = field(default_factory=list)
    persisted: list[ContractObservation] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)
    fetched: int = 0
    error: str | None = None

    @property
    def balanced(self) -> bool:
        return self.fetched == len(self.persisted) + len(self.rejected)


def classify_value(kind: str, amount: Any) -> tuple[str, float] | str:
    key = (kind or "").strip().lower()
    if key not in VALUE_KINDS:
        return "unknown_value_kind"
    try:
        number = float(amount)
    except (TypeError, ValueError):
        return "invalid_amount"
    if number < 0:
        return "negative_amount"
    return key, number


def record_page(*, page: int, url: str, status: int, body: bytes, records: int) -> PageEvidence:
    digest = sha256_bytes(body)
    return PageEvidence(
        page=page,
        url=url,
        status=status,
        raw_uri=f"cas://pncp-contracts/{digest}",
        sha256=digest,
        records=records,
        retryable=status in RETRYABLE,
    )


def ingest_window(
    job: WindowJob,
    *,
    pages: list[PageEvidence],
    rows: list[dict[str, Any]],
    query_complete: bool,
    persist_ok: bool,
) -> WindowJob:
    job.pages = list(pages)
    job.fetched = len(rows)
    job.persisted = []
    job.rejected = []
    job.error = None
    job.checkpoint_after_persist = False
    job.status = None
    if any(p.retryable and p.status != 200 for p in pages) and not query_complete:
        job.status = "failed"
        job.error = "retryable_http"
        job.checkpoint_after_persist = False
        return job
    if not query_complete:
        job.status = "failed"
        job.error = "scope_incomplete"
        return job
    if not persist_ok:
        job.status = "failed"
        job.error = "persist_failed"
        job.checkpoint_after_persist = False
        return job
    for row in rows:
        classified = classify_value(str(row.get("value_kind") or ""), row.get("amount"))
        if isinstance(classified, str):
            job.rejected.append({"contract_id": str(row.get("contract_id") or ""), "reason": classified})
            continue
        kind, amount = classified
        provenance = {
            "page": row.get("page"),
            "raw_uri": row.get("raw_uri"),
            "sha256": row.get("sha256"),
            "source": "pncp_contratos",
        }
        if not provenance["raw_uri"] or not provenance["sha256"]:
            job.rejected.append({"contract_id": str(row.get("contract_id") or ""), "reason": "missing_provenance"})
            continue
        job.persisted.append(
            ContractObservation(
                ente_id=job.ente_id,
                contract_id=str(row["contract_id"]),
                value_kind=kind,
                amount=amount,
                provenance=provenance,
            )
        )
    if not job.balanced:
        job.status = "failed"
        job.error = "count_mismatch"
        return job
    job.status = "complete"
    job.checkpoint_after_persist = True
    job.error = None
    return job


def zero_proof(job: WindowJob) -> dict[str, Any]:
    if job.status != "complete":
        return {"ente_id": job.ente_id, "verdict": "SCOPE_INCOMPLETE", "count": len(job.persisted)}
    if job.persisted:
        return {"ente_id": job.ente_id, "verdict": "FOUND", "count": len(job.persisted)}
    if job.fetched > 0 or job.rejected:
        return {
            "ente_id": job.ente_id,
            "verdict": "REJECTED_ALL",
            "count": 0,
            "fetched": job.fetched,
            "rejected": len(job.rejected),
        }
    return {"ente_id": job.ente_id, "verdict": "ZERO_CONFIRMED", "count": 0}


def buyer_intel_rows(jobs: list[WindowJob]) -> list[ContractObservation]:
    """Buyer intelligence uses only persisted rows that carry provenance."""
    rows: list[ContractObservation] = []
    for job in jobs:
        for item in job.persisted:
            if item.provenance.get("raw_uri") and item.provenance.get("sha256"):
                rows.append(item)
    return rows


def job_report(job: WindowJob) -> dict[str, Any]:
    return {
        "ente_id": job.ente_id,
        "window_start": job.window_start,
        "window_end": job.window_end,
        "status": job.status,
        "checkpoint_after_persist": job.checkpoint_after_persist,
        "fetched": job.fetched,
        "persisted": len(job.persisted),
        "rejected": len(job.rejected),
        "balanced": job.balanced,
        "zero": zero_proof(job),
        "pages": [asdict(p) for p in job.pages],
        "error": job.error,
        "policy_window_start": WINDOW_START,
        "generated_at": _utc_now(),
    }
