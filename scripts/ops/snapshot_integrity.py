#!/usr/bin/env python3
"""Active open-tenders snapshot integrity measurement (fail-closed).

Integrity = 100% only when every active open opportunity satisfies structural
rules. Empty active set is NOT 100% integrity for operational claims — it is
measured_zero and fails operational gate unless explicitly allowed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class SnapshotIntegrityReport:
    status: str  # PASS | FAIL | EMPTY
    integrity_pct: float
    active_open_count: int
    intact_count: int
    defect_count: int
    defects: list[dict[str, Any]] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    as_of: str = ""
    source: str = "pncp"
    operational_ok: bool = False
    claims_forbidden: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _connect(dsn: str) -> Any:
    import psycopg2
    import psycopg2.extras

    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def measure_snapshot_integrity(
    dsn: str,
    *,
    source: str = "pncp",
    require_non_empty: bool = True,
) -> SnapshotIntegrityReport:
    """Measure integrity of the active open snapshot for one source."""
    conn = _connect(dsn)
    defects: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    try:
        with conn.cursor() as cur:
            # Table presence
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'opportunity_intel', 'opportunity_runs', 'source_snapshot_membership'
                  )
                """
            )
            tables = {r["table_name"] for r in cur.fetchall()}
        missing_tables = {
            "opportunity_intel",
            "opportunity_runs",
            "source_snapshot_membership",
        } - tables
        checks.append(
            {
                "id": "schema_tables",
                "ok": not missing_tables,
                "detail": {"missing": sorted(missing_tables), "present": sorted(tables)},
            }
        )
        if missing_tables:
            return SnapshotIntegrityReport(
                status="FAIL",
                integrity_pct=0.0,
                active_open_count=0,
                intact_count=0,
                defect_count=1,
                defects=[{"kind": "missing_tables", "tables": sorted(missing_tables)}],
                checks=checks,
                as_of=_utc_now(),
                source=source,
                operational_ok=False,
                notes=["schema incomplete — cannot claim integrity"],
            )

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, source, source_id, numero_controle_pncp, orgao_nome, objeto,
                       status_canonico, link_edital, source_active, is_active,
                       last_seen_source_run_id, run_id, content_hash
                FROM opportunity_intel
                WHERE source = %s
                  AND is_active = TRUE
                  AND COALESCE(source_active, TRUE) = TRUE
                  AND status_canonico IN ('open', 'upcoming')
                """,
                (source,),
            )
            rows = [dict(r) for r in cur.fetchall()]

            # Latest complete run
            cur.execute(
                """
                SELECT id, status, scope_complete, finished_at, records_fetched
                FROM opportunity_runs
                WHERE source IN (%s, 'pncp_opportunities')
                  AND status IN ('completed', 'completed_zero')
                  AND COALESCE(scope_complete, FALSE) = TRUE
                ORDER BY finished_at DESC NULLS LAST, id DESC
                LIMIT 1
                """,
                (source,),
            )
            complete_run = cur.fetchone()
            complete_run = dict(complete_run) if complete_run else None

            membership_count = 0
            if complete_run:
                cur.execute(
                    """
                    SELECT COUNT(*)::int AS n
                    FROM source_snapshot_membership
                    WHERE source_run_id = %s
                    """,
                    (complete_run["id"],),
                )
                membership_count = int(cur.fetchone()["n"])
    finally:
        conn.close()

    checks.append(
        {
            "id": "complete_parent_run",
            "ok": complete_run is not None,
            "detail": {
                "run_id": complete_run["id"] if complete_run else None,
                "membership_count": membership_count,
            },
        }
    )

    intact = 0
    for r in rows:
        issues: list[str] = []
        if not (r.get("numero_controle_pncp") or r.get("source_id")):
            issues.append("missing_identity")
        if not (r.get("link_edital") or r.get("numero_controle_pncp")):
            issues.append("missing_official_reference")
        if not r.get("objeto"):
            issues.append("missing_objeto")
        if r.get("source_active") is False:
            issues.append("inactive_flag")
        if issues:
            defects.append(
                {
                    "id": r.get("id"),
                    "source_id": r.get("source_id"),
                    "issues": issues,
                }
            )
        else:
            intact += 1

    active_n = len(rows)
    if active_n == 0:
        integrity_pct = 0.0 if require_non_empty else 100.0
        status = "EMPTY"
        operational_ok = False if require_non_empty else True
        notes = [
            "active open snapshot empty",
            "EMPTY is not operational integrity 100% when require_non_empty",
        ]
    else:
        integrity_pct = round(100.0 * intact / active_n, 4)
        status = "PASS" if integrity_pct >= 100.0 and complete_run is not None else "FAIL"
        # complete parent run required for operational integrity claim
        if complete_run is None:
            status = "FAIL"
            notes = ["no completed scope_complete parent run — integrity claim blocked"]
        else:
            notes = []
        operational_ok = status == "PASS" and integrity_pct >= 100.0

    checks.append(
        {
            "id": "row_structural_integrity",
            "ok": active_n > 0 and intact == active_n,
            "detail": {
                "active_open_count": active_n,
                "intact_count": intact,
                "defect_count": len(defects),
                "integrity_pct": integrity_pct,
            },
        }
    )

    return SnapshotIntegrityReport(
        status=status,
        integrity_pct=integrity_pct,
        active_open_count=active_n,
        intact_count=intact,
        defect_count=len(defects),
        defects=defects[:100],
        checks=checks,
        as_of=_utc_now(),
        source=source,
        operational_ok=operational_ok,
        claims_forbidden=[
            "integrity 100% from empty snapshot",
            "presence of table as integrity",
            "partial run as reconciliation basis",
        ],
        notes=notes,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Measure open-tenders snapshot integrity")
    p.add_argument("--dsn", default=None)
    p.add_argument("--source", default="pncp")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument(
        "--allow-empty",
        action="store_true",
        help="Do not fail operational gate solely because snapshot is empty",
    )
    args = p.parse_args(argv)
    dsn = (
        args.dsn
        or os.environ.get("LOCAL_DATALAKE_DSN")
        or os.environ.get("DATABASE_URL")
    )
    if not dsn:
        print(json.dumps({"error": "DSN required"}, ensure_ascii=False))
        return 1
    report = measure_snapshot_integrity(
        dsn,
        source=args.source,
        require_non_empty=not args.allow_empty,
    )
    payload = report.to_dict()
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0 if report.operational_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
