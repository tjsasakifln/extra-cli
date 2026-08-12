#!/usr/bin/env python3
"""Daily multi-source collection feeder for the weekly decision pack.

Canonical entry (feeds the lake that ``weekly_cycle`` / decision pack reads):

  make extra-daily-collect
  python3 -m scripts.ops.daily_multi_source_collect
  python3 -m scripts.ops.daily_multi_source_collect --offline --declare-only

Contract (scripts.collect.run_contract):
  - Terminal statuses are explicit.
  - Skip / dry-run / cache-without-SLA / empty-without-query NEVER claim complete success.
  - ``partial`` is never consultively OK for required sources.

Required open-tenders sources (pack feed):
  - pncp_opportunities (required)
  - ciga_ckan (required for municipal dual; ciga_dom is the resilient alias)
  - sc_compras (complementary but always tracked for honesty)
  - pncp_contracts (contracts freshness used by weekly strict exit)

Modes:
  --declare-only / --offline  Inspect lake + prior runs; no live HTTP.
  --live                      Invoke live collectors (network required).
  --strict                    Exit 0 only when all required sources are consultive-ok.

This module does NOT reimplement crawlers: it orchestrates existing entry points
and records CollectionRun rows so the weekly pack can trust freshness honesty.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.collect.run_contract import (  # noqa: E402
    CollectionRun,
    TerminalStatus,
    new_collection_id,
    persist_pipeline_run,
)
from scripts.crawl.run_evidence import get_git_meta  # noqa: E402

COLLECTOR_VERSION = "daily-multi-source/1.0"
DEFAULT_DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://test:test@127.0.0.1:5433/extra_test",
)

# SLAs aligned with DOD editais freshness (≤24h) and weekly_cycle defaults.
PNCP_OPP_SLA_HOURS = int(os.getenv("DAILY_PNCP_SLA_HOURS", os.getenv("WEEKLY_PNCP_SLA_HOURS", "24")))
CIGA_SLA_HOURS = int(os.getenv("DAILY_CIGA_SLA_HOURS", os.getenv("WEEKLY_CIGA_SLA_HOURS", "24")))
SC_COMPRAS_SLA_HOURS = int(
    os.getenv("DAILY_SC_COMPRAS_SLA_HOURS", os.getenv("WEEKLY_SC_COMPRAS_SLA_HOURS", "48"))
)
CONTRACTS_SLA_HOURS = int(
    os.getenv("DAILY_CONTRACTS_SLA_HOURS", os.getenv("WEEKLY_CONTRACTS_SLA_HOURS", "168"))
)

# Required for pack multi-source honesty (open tenders).
REQUIRED_SOURCES: tuple[str, ...] = ("pncp_opportunities", "ciga_ckan")
# Always tracked; complementary role does not block completeness unless --require-complementary.
TRACKED_SOURCES: tuple[str, ...] = (
    "pncp_opportunities",
    "ciga_ckan",
    "sc_compras",
    "pncp_contracts",
)

EXIT_OK = 0
EXIT_TECH = 1
EXIT_INCOMPLETE = 2
EXIT_BLOCKED = 3

CONSULTIVE_OK: frozenset[str] = frozenset({"success", "success_zero", "reused_fresh"})


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime | None = None) -> str:
    d = dt or _utc_now()
    return d.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_dsn(explicit: str | None) -> str:
    for c in (explicit, os.getenv("LOCAL_DATALAKE_DSN"), os.getenv("DATABASE_URL"), DEFAULT_DSN):
        if c and str(c).strip():
            return str(c).strip()
    raise RuntimeError("No DSN: pass --dsn or set LOCAL_DATALAKE_DSN")


def _connect(dsn: str) -> Any:
    import psycopg2
    import psycopg2.extras

    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def _q(conn: Any, sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def _table_exists(conn: Any, name: str) -> bool:
    rows = _q(
        conn,
        """
        SELECT 1 AS ok FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (name,),
    )
    return bool(rows)


def _hours_since(ts: Any) -> float | None:
    if ts is None:
        return None
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if getattr(ts, "tzinfo", None) is None:
        ts = ts.replace(tzinfo=UTC)
    return max(0.0, (_utc_now() - ts).total_seconds() / 3600.0)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Pure completeness logic (unit-tested; no I/O)
# ---------------------------------------------------------------------------


@dataclass
class SourceFeedAssessment:
    """Honest assessment of one source feed for the pack lake."""

    source: str
    role: str  # required | complementary
    level: str  # fresh | stale | never | incomplete | unreliable | unknown
    age_hours: float | None = None
    sla_hours: int = 24
    row_count: int = 0
    last_status: str | None = None
    scope_complete: bool | None = None
    evidence: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def map_assessment_to_terminal(
    assessment: SourceFeedAssessment,
    *,
    skip_without_proof: bool = False,
    offline: bool = False,
) -> tuple[TerminalStatus, dict[str, Any]]:
    """Map lake/freshness assessment → CollectionRun terminal semantics.

    Rules:
    - skip without complete in-SLA proof → partial (never reused_fresh / success)
    - fresh complete prior collect → reused_fresh
    - never / unreliable → failure (or blocked when source unavailable signal)
    - incomplete / stale → partial
    - offline is declared in notes; never upgrades status
    """
    notes = list(assessment.notes)
    if offline:
        notes.append("offline_or_declare_only: no live crawl this invocation")

    if skip_without_proof and assessment.level != "fresh":
        return "partial", {
            "request_completed": True,
            "scope_complete": False,
            "reused_within_sla": False,
            "records_obtained": assessment.row_count,
            "records_persisted": assessment.row_count,
            "error": None,
            "notes": notes
            + [
                f"skip/declare without in-SLA complete proof (level={assessment.level})",
                "partial: cannot claim daily complete collect",
            ],
        }

    if assessment.level == "fresh" and assessment.scope_complete is not False:
        # Prior complete collect within SLA — explicit reuse, not a new collect.
        return "reused_fresh", {
            "request_completed": True,
            "scope_complete": True,
            "reused_within_sla": True,
            "records_obtained": assessment.row_count,
            "records_persisted": assessment.row_count,
            "error": None,
            "notes": notes
            + [
                f"reused complete in-SLA feed level=fresh age_h={assessment.age_hours}",
                f"evidence={assessment.evidence or 'lake'}",
            ],
        }

    if assessment.level == "never":
        return "failure", {
            "request_completed": False,
            "scope_complete": False,
            "reused_within_sla": False,
            "records_obtained": 0,
            "records_persisted": 0,
            "error": f"{assessment.source}: never collected",
            "notes": notes + ["no collection evidence in lake"],
        }

    if assessment.level == "unreliable":
        return "failure", {
            "request_completed": False,
            "scope_complete": False,
            "reused_within_sla": False,
            "records_obtained": assessment.row_count,
            "records_persisted": assessment.row_count,
            "error": f"{assessment.source}: last run unreliable status={assessment.last_status}",
            "notes": notes,
        }

    # stale / incomplete / unknown → partial (never success)
    return "partial", {
        "request_completed": True,
        "scope_complete": False,
        "reused_within_sla": False,
        "records_obtained": assessment.row_count,
        "records_persisted": assessment.row_count,
        "error": None,
        "notes": notes
        + [
            f"level={assessment.level} age_h={assessment.age_hours} sla={assessment.sla_hours}",
            "partial: feed not complete for consultive daily use",
        ],
    }


@dataclass
class DailyFeederReport:
    collection_id: str
    started_at: str
    finished_at: str | None = None
    mode: str = "declare_only"
    exit_code: int = EXIT_TECH
    complete: bool = False
    required_ok: list[str] = field(default_factory=list)
    required_failed: list[str] = field(default_factory=list)
    complementary_status: dict[str, str] = field(default_factory=dict)
    runs: list[dict[str, Any]] = field(default_factory=list)
    assessments: list[dict[str, Any]] = field(default_factory=list)
    claims_forbidden: list[str] = field(
        default_factory=lambda: [
            "LOCAL_READY",
            "VPS_OPERATIONAL",
            "cobertura_95",
            "skip_as_success",
            "empty_without_query_as_success",
        ]
    )
    limitations: list[str] = field(default_factory=list)
    git: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0


def evaluate_feeder_completeness(
    runs: list[CollectionRun],
    *,
    required: tuple[str, ...] = REQUIRED_SOURCES,
    require_complementary: bool = False,
    complementary: tuple[str, ...] = ("sc_compras", "pncp_contracts"),
) -> dict[str, Any]:
    """Fail-closed completeness: required sources must be consultive-ok.

    Incomplete / skipped / partial / failure / blocked → not complete.
    Never treats absence of error as success.
    """
    by_src = {r.source: r for r in runs}
    required_ok: list[str] = []
    required_failed: list[str] = []
    for src in required:
        run = by_src.get(src)
        if run is None:
            required_failed.append(src)
            continue
        if run.terminal_status in CONSULTIVE_OK and run.is_consultive_ok():
            # Extra guard: success_zero with incomplete scope is not OK
            if run.terminal_status == "success_zero" and (
                not run.scope_complete or run.terminal_error
            ):
                required_failed.append(src)
            else:
                required_ok.append(src)
        else:
            required_failed.append(src)

    complementary_status: dict[str, str] = {}
    complementary_failed: list[str] = []
    for src in complementary:
        run = by_src.get(src)
        if run is None:
            complementary_status[src] = "missing"
            if require_complementary:
                complementary_failed.append(src)
            continue
        complementary_status[src] = run.terminal_status
        if require_complementary and run.terminal_status not in CONSULTIVE_OK:
            complementary_failed.append(src)

    complete = not required_failed and not complementary_failed
    blocked = any(
        by_src[s].terminal_status == "blocked"
        for s in required
        if s in by_src
    )
    return {
        "complete": complete,
        "required_ok": required_ok,
        "required_failed": required_failed,
        "complementary_status": complementary_status,
        "complementary_failed": complementary_failed,
        "blocked": blocked,
        "vocabulary": sorted(CONSULTIVE_OK),
        "note": "partial/skip/never never counts as complete for required sources",
    }


# ---------------------------------------------------------------------------
# Lake assessment (DB I/O)
# ---------------------------------------------------------------------------


def assess_pncp_opportunities(conn: Any) -> SourceFeedAssessment:
    if not _table_exists(conn, "opportunity_runs"):
        return SourceFeedAssessment(
            source="pncp_opportunities",
            role="required",
            level="never",
            sla_hours=PNCP_OPP_SLA_HOURS,
            notes=["opportunity_runs table missing"],
        )
    rows = _q(
        conn,
        """
        SELECT id, source, status, started_at, finished_at, records_fetched,
               error_message, scope_complete
        FROM opportunity_runs
        WHERE source LIKE %s
        ORDER BY started_at DESC NULLS LAST
        LIMIT 1
        """,
        ("pncp%",),
    )
    if not rows:
        return SourceFeedAssessment(
            source="pncp_opportunities",
            role="required",
            level="never",
            sla_hours=PNCP_OPP_SLA_HOURS,
            evidence="opportunity_runs",
            notes=["no pncp opportunity_runs"],
        )
    r = rows[0]
    age = _hours_since(r.get("finished_at") or r.get("started_at"))
    st = str(r.get("status") or "").lower()
    scope = r.get("scope_complete")
    err = r.get("error_message")
    # Align with weekly_cycle.classify_opportunity_freshness semantics
    from scripts.ops.weekly_cycle import classify_opportunity_freshness

    level = classify_opportunity_freshness(
        status=st,
        age_hours=age,
        sla_hours=PNCP_OPP_SLA_HOURS,
        scope_complete=scope if scope is not None else None,
        error_message=err,
    )
    return SourceFeedAssessment(
        source="pncp_opportunities",
        role="required",
        level=level,
        age_hours=round(age, 2) if age is not None else None,
        sla_hours=PNCP_OPP_SLA_HOURS,
        row_count=int(r.get("records_fetched") or 0),
        last_status=st,
        scope_complete=bool(scope) if scope is not None else None,
        evidence=f"opportunity_runs/{r.get('id')}",
    )


def assess_ciga(conn: Any) -> SourceFeedAssessment:
    """CIGA/DOM municipal dual feed — official_acts and/or coverage_evidence."""
    notes: list[str] = []
    age: float | None = None
    n = 0
    evidence = ""
    last_status: str | None = None
    scope_complete: bool | None = None

    if _table_exists(conn, "coverage_evidence"):
        ce = _q(
            conn,
            """
            SELECT COUNT(*)::int AS n,
                   MAX(COALESCE(checked_at, completed_at, started_at)) AS last_ts,
                   COUNT(*) FILTER (
                     WHERE state::text IN ('success_zero', 'success_with_data', 'success')
                   )::int AS complete_n
            FROM coverage_evidence
            WHERE source IN ('ciga_ckan', 'ciga_dom', 'dom_sc')
            """,
        )
        if ce and int(ce[0].get("n") or 0) > 0:
            n = int(ce[0]["n"])
            age = _hours_since(ce[0].get("last_ts"))
            evidence = "coverage_evidence"
            complete_n = int(ce[0].get("complete_n") or 0)
            # Entity-scoped projection with success/success_zero → scope complete
            scope_complete = complete_n > 0 and complete_n == n
            last_status = "completed" if complete_n > 0 else "partial"
            notes.append(
                f"coverage_evidence rows={n} complete_states={complete_n} "
                f"scope_complete={scope_complete}"
            )

    if _table_exists(conn, "official_acts") and (n == 0 or age is None):
        try:
            acts = _q(
                conn,
                """
                SELECT COUNT(*)::int AS n,
                       MAX(COALESCE(ingested_at, publication_date::timestamptz)) AS last_ts
                FROM official_acts
                WHERE lower(COALESCE(source, '')) ~ '(ciga|dom)'
                """,
            )
        except Exception as acts_exc:  # noqa: BLE001
            try:
                conn.rollback()
            except Exception as rb_exc:  # noqa: BLE001
                notes.append(f"rollback_after_acts_query:{rb_exc}")
            notes.append(f"official_acts_primary_query_failed:{type(acts_exc).__name__}")
            acts = _q(
                conn,
                """
                SELECT COUNT(*)::int AS n,
                       MAX(publication_date::timestamptz) AS last_ts
                FROM official_acts
                """,
            )
        if acts and int(acts[0].get("n") or 0) > 0:
            n = max(n, int(acts[0]["n"]))
            a2 = _hours_since(acts[0].get("last_ts"))
            if age is None or (a2 is not None and a2 < age):
                age = a2
            evidence = evidence or "official_acts"
            last_status = last_status or "completed"
            # Acts present ≠ full municipal scope complete
            if scope_complete is None:
                scope_complete = False
                notes.append("official_acts present but entity-scope not proven complete")
            notes.append(f"official_acts rows={acts[0]['n']}")

    # pipeline_runs fallback
    if n == 0 and _table_exists(conn, "pipeline_runs"):
        pr = _q(
            conn,
            """
            SELECT run_id, source, status, started_at, completed_at,
                   records_fetched, params
            FROM pipeline_runs
            WHERE source IN ('ciga_ckan', 'ciga_dom', 'dom_sc', 'ciga')
            ORDER BY COALESCE(completed_at, started_at) DESC NULLS LAST
            LIMIT 1
            """,
        )
        if pr:
            r = pr[0]
            age = _hours_since(r.get("completed_at") or r.get("started_at"))
            n = int(r.get("records_fetched") or 0)
            last_status = str(r.get("status") or "")
            evidence = f"pipeline_runs/{r.get('run_id')}"
            params = r.get("params") or {}
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:
                    params = {}
            if isinstance(params, dict):
                ts = params.get("terminal_status")
                if ts:
                    last_status = str(ts)
                sc = params.get("scope_complete")
                if sc is not None:
                    scope_complete = bool(sc)
            notes.append("freshness from pipeline_runs")

    # File artifact fallback (JSONL) — mtime only, never invents completeness
    if n == 0:
        from scripts.ops.multi_source_open_pack.db_loaders import discover_ciga_jsonl

        path = discover_ciga_jsonl()
        if path and path.is_file():
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            age = _hours_since(mtime)
            n = max(1, sum(1 for _ in path.open(encoding="utf-8") if _.strip()) if path.stat().st_size else 0)
            evidence = f"file:{path}"
            last_status = "file_artifact"
            scope_complete = False
            notes.append("file artifact present — scope_complete unproven")

    if n == 0 and age is None:
        return SourceFeedAssessment(
            source="ciga_ckan",
            role="required",
            level="never",
            sla_hours=CIGA_SLA_HOURS,
            evidence=evidence or "none",
            notes=notes + ["no CIGA/DOM evidence in lake or files"],
        )

    if last_status and str(last_status).lower() in {"partial", "failed", "error", "blocked"}:
        level = "incomplete" if "partial" in str(last_status).lower() else "unreliable"
    elif age is not None and age <= CIGA_SLA_HOURS and scope_complete is True:
        level = "fresh"
    elif age is not None and age <= CIGA_SLA_HOURS and scope_complete is False:
        level = "incomplete"
    elif age is not None and age > CIGA_SLA_HOURS:
        level = "stale"
    elif age is not None and age <= CIGA_SLA_HOURS:
        # within SLA but scope unknown → incomplete (fail-closed)
        level = "incomplete"
        notes.append("within SLA but scope_complete unproven → incomplete")
    else:
        level = "unknown"

    return SourceFeedAssessment(
        source="ciga_ckan",
        role="required",
        level=level,
        age_hours=round(age, 2) if age is not None else None,
        sla_hours=CIGA_SLA_HOURS,
        row_count=n,
        last_status=last_status,
        scope_complete=scope_complete,
        evidence=evidence,
        notes=notes,
    )


def assess_sc_compras(conn: Any) -> SourceFeedAssessment:
    notes: list[str] = []
    age: float | None = None
    n = 0
    evidence = ""
    last_status: str | None = None
    scope_complete: bool | None = None

    if _table_exists(conn, "opportunity_intel"):
        try:
            rows = _q(
                conn,
                """
                SELECT COUNT(*)::int AS n,
                       MAX(COALESCE(updated_at, created_at)) AS last_ts
                FROM opportunity_intel
                WHERE lower(COALESCE(source, '')) LIKE 'sc_compras%'
                   OR lower(COALESCE(source, '')) LIKE 'sc-compras%'
                """,
            )
        except Exception as oi_exc:  # noqa: BLE001
            try:
                conn.rollback()
            except Exception as rb_exc:  # noqa: BLE001
                notes.append(f"rollback_after_oi_query:{rb_exc}")
            notes.append(f"opportunity_intel_sc_query_failed:{type(oi_exc).__name__}")
            rows = []
        if rows and int(rows[0].get("n") or 0) > 0:
            n = int(rows[0]["n"])
            age = _hours_since(rows[0].get("last_ts"))
            evidence = "opportunity_intel"
            last_status = "completed"
            scope_complete = False
            notes.append("SC Compras rows in opportunity_intel; entity-scope not proven")

    if n == 0 and _table_exists(conn, "pipeline_runs"):
        pr = _q(
            conn,
            """
            SELECT run_id, source, status, started_at, completed_at,
                   records_fetched, params
            FROM pipeline_runs
            WHERE source IN ('sc_compras', 'sc-compras')
            ORDER BY COALESCE(completed_at, started_at) DESC NULLS LAST
            LIMIT 1
            """,
        )
        if pr:
            r = pr[0]
            age = _hours_since(r.get("completed_at") or r.get("started_at"))
            n = int(r.get("records_fetched") or 0)
            last_status = str(r.get("status") or "")
            evidence = f"pipeline_runs/{r.get('run_id')}"
            params = r.get("params") or {}
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:
                    params = {}
            if isinstance(params, dict) and params.get("scope_complete") is not None:
                scope_complete = bool(params.get("scope_complete"))
            notes.append("freshness from pipeline_runs")

    if n == 0:
        from scripts.ops.multi_source_open_pack.db_loaders import discover_sc_compras_jsonl

        path = discover_sc_compras_jsonl()
        if path and path.is_file():
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            age = _hours_since(mtime)
            n = max(1, path.stat().st_size // 200)  # rough non-zero marker
            evidence = f"file:{path}"
            last_status = "file_artifact"
            scope_complete = False
            notes.append("file artifact — scope_complete unproven")

    if n == 0 and age is None:
        return SourceFeedAssessment(
            source="sc_compras",
            role="complementary",
            level="never",
            sla_hours=SC_COMPRAS_SLA_HOURS,
            evidence=evidence or "none",
            notes=notes + ["no SC Compras evidence"],
        )

    if age is not None and age <= SC_COMPRAS_SLA_HOURS and scope_complete is True:
        level = "fresh"
    elif age is not None and age <= SC_COMPRAS_SLA_HOURS:
        level = "incomplete"
        notes.append("within SLA but scope unproven → incomplete (not success)")
    elif age is not None:
        level = "stale"
    else:
        level = "unknown"

    return SourceFeedAssessment(
        source="sc_compras",
        role="complementary",
        level=level,
        age_hours=round(age, 2) if age is not None else None,
        sla_hours=SC_COMPRAS_SLA_HOURS,
        row_count=n,
        last_status=last_status,
        scope_complete=scope_complete,
        evidence=evidence,
        notes=notes,
    )


def assess_contracts(conn: Any) -> SourceFeedAssessment:
    if not _table_exists(conn, "pncp_supplier_contracts"):
        return SourceFeedAssessment(
            source="pncp_contracts",
            role="complementary",
            level="never",
            sla_hours=CONTRACTS_SLA_HOURS,
            notes=["pncp_supplier_contracts missing"],
        )
    rows = _q(
        conn,
        """
        SELECT MAX(ingested_at) AS last_ingested, COUNT(*)::int AS n
        FROM pncp_supplier_contracts
        WHERE COALESCE(is_active, TRUE)
        """,
    )
    if not rows or not rows[0].get("last_ingested"):
        return SourceFeedAssessment(
            source="pncp_contracts",
            role="complementary",
            level="never",
            sla_hours=CONTRACTS_SLA_HOURS,
            evidence="pncp_supplier_contracts",
        )
    age = _hours_since(rows[0]["last_ingested"])
    n = int(rows[0].get("n") or 0)
    level = "fresh" if age is not None and age <= CONTRACTS_SLA_HOURS else "stale"
    # Contracts lake freshness ≠ full API scope complete
    return SourceFeedAssessment(
        source="pncp_contracts",
        role="complementary",
        level=level,
        age_hours=round(age, 2) if age is not None else None,
        sla_hours=CONTRACTS_SLA_HOURS,
        row_count=n,
        last_status="lake_ingested",
        scope_complete=False,
        evidence="pncp_supplier_contracts",
        notes=["freshness by max(ingested_at); not a full re-collect proof"],
    )


def assess_all_sources(conn: Any) -> list[SourceFeedAssessment]:
    return [
        assess_pncp_opportunities(conn),
        assess_ciga(conn),
        assess_sc_compras(conn),
        assess_contracts(conn),
    ]


def assessment_to_run(
    assessment: SourceFeedAssessment,
    *,
    collection_id: str,
    skip_without_proof: bool = False,
    offline: bool = False,
) -> CollectionRun:
    run = CollectionRun.start(
        source=assessment.source,
        collection_id=collection_id,
        collector_version=COLLECTOR_VERSION,
        parameters={
            "role": assessment.role,
            "level": assessment.level,
            "evidence": assessment.evidence,
            "sla_hours": assessment.sla_hours,
            "mode": "declare_only" if offline or skip_without_proof else "assess",
        },
        period_start=(date.today() - timedelta(days=7)).isoformat(),
        period_end=date.today().isoformat(),
        mode="declare" if offline else "assess",
    )
    status, kwargs = map_assessment_to_terminal(
        assessment,
        skip_without_proof=skip_without_proof,
        offline=offline,
    )
    notes = kwargs.pop("notes", [])
    run.finish(**kwargs, notes=notes, raw_uri=assessment.evidence or None)
    # Force mapped terminal when finish() path would differ (e.g. reused flags)
    if run.terminal_status != status:
        run.terminal_status = status
        run.notes.append(f"terminal_status forced to {status} by feeder map")
    return run


# ---------------------------------------------------------------------------
# Live collect hooks (optional; real entry points)
# ---------------------------------------------------------------------------


def _live_pncp(conn: Any, collection_id: str, dsn: str) -> CollectionRun:
    """Invoke canonical open-tenders path used by weekly_cycle."""
    run = CollectionRun.start(
        source="pncp_opportunities",
        collection_id=collection_id,
        collector_version=COLLECTOR_VERSION,
        parameters={"collect_path": "scripts.opportunity_intel.pncp_audit.run_pncp_open_monitoring"},
        mode="live",
    )
    try:
        from scripts.lib.universe import load_canonical_universe, resolve_default_seed_path
        from scripts.opportunity_intel.pncp_audit import run_pncp_open_monitoring

        seed = resolve_default_seed_path(_PROJECT_ROOT)
        universe = load_canonical_universe(seed_path=seed, conn=conn)
        period_start = date.today() - timedelta(days=7)
        horizon = max(1, min(365, int(os.getenv("PNCP_OPEN_PROPOSAL_HORIZON_DAYS", "30"))))
        period_end = date.today() + timedelta(days=horizon)
        outcome = run_pncp_open_monitoring(
            dsn=dsn,
            external_run_id=f"daily-{collection_id}",
            universe=universe,
            period_start=period_start,
            period_end=period_end,
            mode="full",
            persist=True,
            timeout=max(30, int(os.getenv("OI_READ_TIMEOUT", "90"))),
            max_retries=max(1, int(os.getenv("OI_MAX_RETRIES", "5"))),
            request_delay=float(os.getenv("PNCP_REQUEST_DELAY") or os.getenv("OI_REQUEST_DELAY") or "1.0"),
        )
        fetched = int(outcome.records_fetched or 0)
        persisted = int(outcome.records_inserted or 0) + int(outcome.records_updated or 0)
        scope_complete = bool(outcome.scope_complete)
        status = str(outcome.status or "")
        err = outcome.error_message or outcome.error_code
        if status in {"failed"} or err and not scope_complete and fetched == 0:
            run.finish(
                records_obtained=fetched,
                records_persisted=persisted,
                request_completed=False,
                scope_complete=False,
                error=str(err or status),
                notes=[f"pncp_status={status}"],
            )
        elif not scope_complete or status == "partial":
            run.finish(
                records_obtained=fetched,
                records_persisted=persisted,
                request_completed=True,
                scope_complete=False,
                error=str(err) if err else "partial_open_tenders",
                notes=[f"pncp_status={status}", "partial live collect"],
            )
            run.terminal_status = "partial"
        else:
            run.finish(
                records_obtained=fetched,
                records_persisted=persisted,
                request_completed=True,
                scope_complete=True,
                notes=[f"pncp_status={status}", "live collect complete"],
            )
    except Exception as exc:  # noqa: BLE001
        run.finish(
            request_completed=False,
            scope_complete=False,
            source_available=False,
            error=str(exc),
            interrupted=True,
            notes=[f"exception={type(exc).__name__}"],
        )
    return run


def _live_resilient_source(collection_id: str, source: str) -> CollectionRun:
    """Invoke resilient_cycle for ciga_dom / sc_compras."""
    mapped = "ciga_dom" if source == "ciga_ckan" else source
    run = CollectionRun.start(
        source=source,
        collection_id=collection_id,
        collector_version=COLLECTOR_VERSION,
        parameters={"collect_path": "scripts.ops.resilient_cycle", "resilient_source": mapped},
        mode="live",
    )
    try:
        from scripts.ops.resilient_cycle import run_cycle

        code, summary = run_cycle(live=True, source=mapped, fixture_dir=None, config=None)
        # summary shape varies; be defensive
        if not isinstance(summary, dict):
            summary = {"raw": str(summary)}
        results = summary.get("results") or summary.get("sources") or {}
        src_out = results.get(mapped) or results.get(source)
        if src_out is None:
            src_out = {
                "status": "missing_source_result",
                "terminal_status": "failure",
                "request_completed": False,
                "scope_complete": False,
            }
        if not isinstance(src_out, dict):
            src_out = {"status": str(src_out)}
        st = str(src_out.get("status") or summary.get("status") or "").lower()
        terminal = str(src_out.get("terminal_status") or "").lower()
        request_completed = bool(src_out.get("request_completed", st in {"success", "completed", "ok", "success_zero", "empty"}))
        scope_complete = bool(src_out.get("scope_complete", request_completed and st in {"success", "completed", "ok", "success_zero", "empty"}))
        fetched = int(src_out.get("records_fetched") or src_out.get("fetched") or 0)
        persisted = int(src_out.get("records_persisted") or src_out.get("persisted") or fetched)
        local_success = terminal in {"success", "success_zero"} or (
            not terminal and st in {"success", "completed", "ok", "success_zero", "empty"}
        )
        if local_success and request_completed and scope_complete:
            zero = terminal == "success_zero" or fetched == 0 or st in {"empty", "success_zero"}
            run.finish(
                records_obtained=fetched,
                records_persisted=persisted,
                request_completed=request_completed,
                scope_complete=scope_complete,
                notes=[f"resilient_cycle local={terminal or st} aggregate_rc={code}"],
            )
            if zero and run.terminal_status == "success":
                # empty confirmed complete → success_zero via finish path; force if needed
                if fetched == 0 and persisted == 0:
                    run.terminal_status = "success_zero"
        elif st in {"skipped", "dry-run", "dry_run"}:
            run.finish(
                request_completed=True,
                scope_complete=False,
                notes=[f"resilient status={st} — skip is not success"],
            )
            run.terminal_status = "partial"
        else:
            run.finish(
                records_obtained=fetched,
                records_persisted=persisted,
                request_completed=request_completed,
                scope_complete=scope_complete,
                source_available=terminal != "blocked",
                error=f"resilient_local={terminal or st} aggregate_rc={code}",
                notes=["source-local live collect incomplete"],
            )
            if terminal in {"partial", "failure", "blocked"}:
                run.terminal_status = terminal
            else:
                run.terminal_status = "partial" if fetched > 0 else "failure"
    except Exception as exc:  # noqa: BLE001
        run.finish(
            request_completed=False,
            scope_complete=False,
            source_available=False,
            error=str(exc),
            interrupted=True,
            notes=[f"exception={type(exc).__name__}"],
        )
    return run


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_daily_multi_source_collect(
    *,
    dsn: str | None = None,
    output_json: Path | None = None,
    offline: bool = False,
    declare_only: bool = False,
    live: bool = False,
    strict: bool = True,
    require_complementary: bool = False,
    persist: bool = True,
    skip_collect: bool = False,
) -> DailyFeederReport:
    """Run daily multi-source feeder assessment (and optional live collects)."""
    t0 = datetime.now(UTC)
    collection_id = new_collection_id("daily-ms")
    mode = "live" if live and not offline and not declare_only else "declare_only"
    report = DailyFeederReport(
        collection_id=collection_id,
        started_at=_iso(t0),
        mode=mode,
        git=get_git_meta(),
    )

    resolved = _resolve_dsn(dsn)
    conn = _connect(resolved)
    runs: list[CollectionRun] = []
    try:
        assessments = assess_all_sources(conn)
        report.assessments = [a.to_dict() for a in assessments]
        by_src = {a.source: a for a in assessments}

        if live and not offline and not declare_only and not skip_collect:
            # Live path: try collectors, then re-assess only on failure fallback
            try:
                runs.append(_live_pncp(conn, collection_id, resolved))
            except Exception as exc:  # noqa: BLE001
                r = assessment_to_run(
                    by_src["pncp_opportunities"],
                    collection_id=collection_id,
                    offline=False,
                )
                r.notes.append(f"live_pncp_failed:{exc}")
                r.terminal_status = "failure"
                runs.append(r)

            # Only live-crawl CIGA/SC when not already fresh complete
            ciga_a = by_src["ciga_ckan"]
            if ciga_a.level == "fresh" and ciga_a.scope_complete is True:
                runs.append(
                    assessment_to_run(ciga_a, collection_id=collection_id, offline=False)
                )
            else:
                runs.append(_live_resilient_source(collection_id, "ciga_ckan"))

            sc_a = by_src["sc_compras"]
            if sc_a.level == "fresh" and sc_a.scope_complete is True:
                runs.append(
                    assessment_to_run(sc_a, collection_id=collection_id, offline=False)
                )
            else:
                runs.append(_live_resilient_source(collection_id, "sc_compras"))

            # Contracts: declare lake freshness (writer authority is pncp-contracts.timer)
            runs.append(
                assessment_to_run(
                    by_src["pncp_contracts"],
                    collection_id=collection_id,
                    offline=False,
                )
            )
        else:
            # Declare-only / offline: honest status from lake, never invent success
            for a in assessments:
                runs.append(
                    assessment_to_run(
                        a,
                        collection_id=collection_id,
                        skip_without_proof=skip_collect,
                        offline=offline or declare_only or not live,
                    )
                )

        if persist:
            for run in runs:
                try:
                    persist_pipeline_run(conn, run)
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    run.notes.append(f"persist_pipeline_run warn: {exc}")
                    try:
                        conn.rollback()
                    except Exception as rb_exc:  # noqa: BLE001
                        run.notes.append(f"rollback_after_persist:{rb_exc}")

        completeness = evaluate_feeder_completeness(
            runs,
            required=REQUIRED_SOURCES,
            require_complementary=require_complementary,
        )
        report.complete = bool(completeness["complete"])
        report.required_ok = list(completeness["required_ok"])
        report.required_failed = list(completeness["required_failed"])
        report.complementary_status = dict(completeness["complementary_status"])
        report.runs = [r.to_dict() for r in runs]
        report.limitations = [
            "Daily feeder records terminal statuses; does not invent operational coverage %",
            "reused_fresh requires prior complete in-SLA evidence",
            "skip/declare without proof → partial (never success)",
            "CIGA entity-scope requires coverage_evidence success/success_zero projection",
            "SC Compras complementary by default (source_applicability.yaml)",
        ]
        if offline or declare_only:
            report.limitations.append(
                "declare_only/offline: no live network crawl — statuses are lake honesty only"
            )

        if completeness.get("blocked"):
            report.exit_code = EXIT_BLOCKED
        elif report.complete:
            report.exit_code = EXIT_OK
        elif strict:
            report.exit_code = EXIT_INCOMPLETE
        else:
            report.exit_code = EXIT_INCOMPLETE

        report.finished_at = _iso()
        report.duration_seconds = round((datetime.now(UTC) - t0).total_seconds(), 2)

        if output_json:
            _atomic_json(output_json, asdict(report))

        return report
    finally:
        try:
            conn.close()
        except Exception as close_exc:  # noqa: BLE001
            sys.stderr.write(f"daily_multi_source_collect: conn.close warn: {close_exc}\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="daily_multi_source_collect",
        description=(
            "Feeder diário multi-fonte com contrato terminal explícito "
            "(alimenta o lake do pacote semanal decisório)"
        ),
    )
    p.add_argument("--dsn", default=None, help="PostgreSQL DSN")
    p.add_argument(
        "--output-json",
        default=None,
        help="Path for feeder report JSON",
    )
    p.add_argument(
        "--offline",
        action="store_true",
        help="No live network; lake declare-only honesty",
    )
    p.add_argument(
        "--declare-only",
        action="store_true",
        help="Assess lake/freshness only (default when not --live)",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="Invoke live collectors (pncp_audit + resilient ciga/sc)",
    )
    p.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exit non-zero unless required sources consultive-ok (default: true)",
    )
    p.add_argument(
        "--require-complementary",
        action="store_true",
        help="Also require sc_compras + contracts consultive-ok for exit 0",
    )
    p.add_argument(
        "--skip-collect",
        action="store_true",
        help="Force skip semantics (partial unless in-SLA complete proof)",
    )
    p.add_argument(
        "--no-persist",
        action="store_true",
        help="Do not write pipeline_runs",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.output_json) if args.output_json else None
    # Default to declare-only when not live (safe offline bar for CI/sandbox)
    declare = bool(args.declare_only) or not bool(args.live)
    try:
        report = run_daily_multi_source_collect(
            dsn=args.dsn,
            output_json=out,
            offline=bool(args.offline),
            declare_only=declare,
            live=bool(args.live),
            strict=bool(args.strict),
            require_complementary=bool(args.require_complementary),
            persist=not bool(args.no_persist),
            skip_collect=bool(args.skip_collect),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {exc}", file=sys.stderr)
        traceback.print_exc()
        return EXIT_TECH

    print(
        json.dumps(
            {
                "collection_id": report.collection_id,
                "mode": report.mode,
                "exit_code": report.exit_code,
                "complete": report.complete,
                "required_ok": report.required_ok,
                "required_failed": report.required_failed,
                "complementary_status": report.complementary_status,
                "runs": [
                    {
                        "source": r.get("source"),
                        "terminal_status": r.get("terminal_status"),
                        "scope_complete": r.get("scope_complete"),
                        "records_persisted": r.get("records_persisted"),
                    }
                    for r in report.runs
                ],
                "duration_seconds": report.duration_seconds,
                "claims_forbidden": report.claims_forbidden,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return int(report.exit_code)


if __name__ == "__main__":
    sys.exit(main())
