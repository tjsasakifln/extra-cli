#!/usr/bin/env python3
"""Entity-level freshness coverage vs SLA (nominal gaps).

Unlike ``scripts.freshness_gate`` (source-level) and the aggregate
``compute_freshness_coverage`` numerator, this module lists **every** active
universe entity and classifies it as fresh | stale | never within a SLA window.

Usage::

    python3 -m scripts.coverage.entity_freshness \\
        --dsn "$LOCAL_DATALAKE_DSN" \\
        --output docs/ops/session-2026-07-18-suite-freshness/

Exit codes:
    0 — measurement completed and report written (even if pct=0 / empty universe)
    1 — technical failure (connect/schema/IO)
    2 — ``--gate`` mode and freshness_pct below ``--min-pct`` (fail-closed)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.coverage.coverage_contract import SLAConfig  # noqa: E402

DEFAULT_DSN = os.environ.get(
    "LOCAL_DATALAKE_DSN",
    os.environ.get("DATABASE_URL", "postgresql://test:test@127.0.0.1:5433/extra_test"),
)


@dataclass(frozen=True)
class EntityFreshnessRow:
    entity_id: int | str
    name: str | None
    last_seen_at: str | None
    hours_since: float | None
    within_sla: bool
    status: str  # fresh | stale | never

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_entity(
    *,
    last_seen_at: datetime | None,
    now: datetime,
    sla_hours: int,
) -> tuple[str, bool, float | None]:
    """Return (status, within_sla, hours_since).

    Pure function — unit-testable without DB.
    """
    if last_seen_at is None:
        return "never", False, None

    ts = last_seen_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    now_aware = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    hours = (now_aware - ts).total_seconds() / 3600.0
    if hours <= float(sla_hours):
        return "fresh", True, hours
    return "stale", False, hours


def _connect(dsn: str) -> Any:
    import psycopg2

    conn = psycopg2.connect(dsn, connect_timeout=15)
    conn.autocommit = True
    return conn


def _table_exists(conn: Any, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
            LIMIT 1
            """,
            (table,),
        )
        return cur.fetchone() is not None


def fetch_entity_freshness_rows(
    conn: Any,
    *,
    sla_hours: int,
    now: datetime | None = None,
) -> tuple[list[EntityFreshnessRow], list[str]]:
    """Load active raio universe with max(last_seen_at) across sources.

    Returns (rows, limitations).
    """
    limitations: list[str] = []
    now = now or datetime.now(UTC)

    if not _table_exists(conn, "sc_public_entities"):
        raise RuntimeError("schema missing public.sc_public_entities")
    if not _table_exists(conn, "entity_coverage"):
        limitations.append(
            "public.entity_coverage missing — all entities classified as never"
        )

    if _table_exists(conn, "entity_coverage"):
        sql = """
            SELECT
                e.id AS entity_id,
                e.razao_social AS name,
                MAX(ec.last_seen_at) AS last_seen_at
            FROM sc_public_entities e
            LEFT JOIN entity_coverage ec ON e.id = ec.entity_id
            WHERE e.is_active IS TRUE
              AND e.raio_200km IS TRUE
            GROUP BY e.id, e.razao_social
            ORDER BY e.id
        """
    else:
        sql = """
            SELECT
                e.id AS entity_id,
                e.razao_social AS name,
                NULL::timestamptz AS last_seen_at
            FROM sc_public_entities e
            WHERE e.is_active IS TRUE
              AND e.raio_200km IS TRUE
            ORDER BY e.id
        """

    with conn.cursor() as cur:
        cur.execute(sql)
        raw = cur.fetchall()

    rows: list[EntityFreshnessRow] = []
    for rec in raw:
        eid, name, last = rec[0], rec[1], rec[2]
        status, within, hours = classify_entity(
            last_seen_at=last, now=now, sla_hours=sla_hours
        )
        last_iso = None
        if last is not None:
            if getattr(last, "tzinfo", None) is None:
                last = last.replace(tzinfo=UTC)
            last_iso = last.isoformat()
        rows.append(
            EntityFreshnessRow(
                entity_id=eid,
                name=name,
                last_seen_at=last_iso,
                hours_since=round(hours, 3) if hours is not None else None,
                within_sla=within,
                status=status,
            )
        )

    limitations.append(
        f"SLA window = {sla_hours}h; last_seen_at = MAX(entity_coverage.last_seen_at) per entity"
    )
    limitations.append(
        "Source-level freshness_gate is intentionally separate; this report is entity-level only"
    )
    return rows, limitations


def build_report(
    rows: list[EntityFreshnessRow],
    *,
    sla_hours: int,
    limitations: list[str],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Aggregate entity rows into a contract-friendly report payload."""
    generated_at = generated_at or datetime.now(UTC)
    denominator = len(rows)
    numerator = sum(1 for r in rows if r.within_sla)
    pct = (100.0 * numerator / denominator) if denominator else 0.0
    gaps = [r.to_dict() for r in rows if not r.within_sla]
    by_status = {
        "fresh": sum(1 for r in rows if r.status == "fresh"),
        "stale": sum(1 for r in rows if r.status == "stale"),
        "never": sum(1 for r in rows if r.status == "never"),
    }

    if denominator == 0:
        measurement_status = "READY_EMPTY_UNIVERSE"
        limitations = [
            *limitations,
            "Active raio universe has 0 entities — measurement ran; seed/import may be required",
        ]
    else:
        measurement_status = "READY"

    return {
        "metric_id": "entity_freshness_coverage",
        "kind": "coverage",
        "label": "Entity freshness coverage within SLA",
        "generated_at": generated_at.isoformat(),
        "sla_hours": sla_hours,
        "denominator": denominator,
        "numerator": numerator,
        "pct": round(pct, 4),
        "within_sla_overall": bool(denominator > 0 and numerator == denominator),
        "measurement_status": measurement_status,
        "by_status": by_status,
        "gaps_count": len(gaps),
        "gaps": gaps,
        "by_entity": [r.to_dict() for r in rows],
        "limitations": limitations,
        "claims_allowed": [
            "Entity-level freshness is measurable against a configured SLA",
            f"Report lists nominal gaps ({len(gaps)}) with entity_id and status",
        ],
        "claims_forbidden": [
            "Operational coverage ≥95% without separate operational stages proof",
            "Source-level freshness gate green (use scripts.freshness_gate)",
            "LOCAL_READY / PRE_VPS_FINAL_READY",
        ],
    }


def write_report(report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "entity-freshness-report.json"
    csv_path = output_dir / "entity-freshness-report.csv"
    gaps_csv = output_dir / "entity-freshness-gaps.csv"

    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    fieldnames = [
        "entity_id",
        "name",
        "last_seen_at",
        "hours_since",
        "within_sla",
        "status",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for row in report.get("by_entity") or []:
            w.writerow({k: row.get(k) for k in fieldnames})

    with gaps_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for row in report.get("gaps") or []:
            w.writerow({k: row.get(k) for k in fieldnames})

    return {"json": json_path, "csv": csv_path, "gaps_csv": gaps_csv}


def run(
    *,
    dsn: str,
    output_dir: Path,
    sla_hours: int | None = None,
    gate: bool = False,
    min_pct: float = 95.0,
) -> int:
    sla = SLAConfig()
    hours = int(sla_hours if sla_hours is not None else sla.default_freshness_hours())
    try:
        conn = _connect(dsn)
    except Exception as exc:
        print(f"ERROR: connect failed: {exc}", file=sys.stderr)
        return 1

    try:
        rows, limitations = fetch_entity_freshness_rows(conn, sla_hours=hours)
        report = build_report(rows, sla_hours=hours, limitations=limitations)
        paths = write_report(report, output_dir)
    except Exception as exc:
        print(f"ERROR: measurement failed: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass

    print(
        f"entity_freshness: num={report['numerator']} den={report['denominator']} "
        f"pct={report['pct']} sla_h={hours} status={report['measurement_status']}"
    )
    print(f"wrote {paths['json']}")
    print(f"wrote {paths['csv']}")
    print(f"wrote {paths['gaps_csv']}")

    if gate and report["pct"] < float(min_pct):
        print(
            f"GATE FAIL: pct {report['pct']} < min_pct {min_pct}",
            file=sys.stderr,
        )
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Entity-level freshness coverage report")
    p.add_argument(
        "--dsn",
        default=DEFAULT_DSN,
        help="PostgreSQL DSN (default LOCAL_DATALAKE_DSN / DATABASE_URL)",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=_PROJECT_ROOT / "output" / "readiness" / "entity-freshness",
        help="Output directory for JSON/CSV",
    )
    p.add_argument(
        "--sla-hours",
        type=int,
        default=None,
        help="SLA window hours (default SLAConfig.open_opportunities_hours=24)",
    )
    p.add_argument(
        "--gate",
        action="store_true",
        help="Fail with exit 2 if pct < --min-pct",
    )
    p.add_argument(
        "--min-pct",
        type=float,
        default=95.0,
        help="Minimum pct for --gate mode (default 95)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(
        dsn=args.dsn,
        output_dir=args.output,
        sla_hours=args.sla_hours,
        gate=args.gate,
        min_pct=args.min_pct,
    )


if __name__ == "__main__":
    raise SystemExit(main())
