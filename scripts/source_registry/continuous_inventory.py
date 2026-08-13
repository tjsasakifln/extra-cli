"""PostgreSQL authority for versioned public surfaces and continuous coverage."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from scripts.crawl.resilience.diagnostics import sanitize_mapping, sanitize_url
from scripts.crawl.security import validate_public_url

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
SURFACE_KINDS = frozenset({"institutional", "procurement", "transparency", "gazette", "cited_platform"})
COVERAGE_STATES = frozenset(
    {
        "FOUND",
        "ZERO_CONFIRMED",
        "NOT_APPLICABLE",
        "BLOCKED",
        "FAILED",
        "DISCOVERY_EXHAUSTED_NO_SURFACE",
    }
)


@dataclass(frozen=True)
class SurfaceObservation:
    kind: str
    canonical_url: str | None
    platform: str | None
    anchor_url: str | None
    method: str
    http_status: int | None = None
    response_hint: str | None = None
    redirect_chain: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CoverageAttempt:
    universe_run_id: int
    canonical_entity_key: str
    entity_id: int
    source: str
    capability: str
    status: str
    applicability: bool
    applicability_reason: str
    canonical_url: str | None
    checked_at: datetime
    http_statuses: list[int]
    pages_fetched: int
    pages_expected: int | None
    records_observed: int
    request_completed: bool
    scope_complete: bool
    pagination_reconciled: bool
    raw_uri: str | None
    raw_sha256: str | None
    freshness_deadline: datetime
    next_action: str
    next_check_at: datetime
    run_id: str | None = None
    crawl_job_attempt_id: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


def ordered_ids_sha256(values: Iterable[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(str(value) for value in values)) + "\n").encode()).hexdigest()


def latest_universe(connection: Any) -> tuple[int, list[dict[str, Any]]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT active.universe_run_id, active.canonical_entity_key,
                   COALESCE(active.db_entity_id, entity.id) AS db_entity_id
            FROM v_target_universe_active active
            LEFT JOIN sc_public_entities entity ON entity.cnpj_8 = active.cnpj8
            ORDER BY active.canonical_entity_key
            """
        )
        rows = [dict(row) for row in cursor.fetchall() or []]
    if not rows:
        raise RuntimeError("active target universe is empty")
    run_ids = {int(row["universe_run_id"]) for row in rows}
    if len(run_ids) != 1:
        raise RuntimeError("active target universe contains multiple run IDs")
    if len({str(row["canonical_entity_key"]) for row in rows}) != len(rows):
        raise RuntimeError("active target universe entity mapping is ambiguous")
    if any(row.get("db_entity_id") is None for row in rows):
        raise RuntimeError("active target universe has unresolved database entity IDs")
    return run_ids.pop(), rows


def create_discovery_run(connection: Any, *, mode: str, expected_entity_count: int) -> int:
    if mode not in {"stratified_pilot", "full"}:
        raise ValueError("discovery mode must be stratified_pilot or full")
    universe_run_id, rows = latest_universe(connection)
    if mode == "full" and len(rows) != expected_entity_count:
        raise ValueError(f"full discovery denominator mismatch: expected={expected_entity_count} active={len(rows)}")
    if mode == "stratified_pilot" and expected_entity_count != 30:
        raise ValueError("the first discovery wave must contain exactly 30 entities")
    with connection.cursor() as cursor:
        if mode == "full":
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM discovery_runs
                    WHERE universe_run_id = %s AND mode = 'stratified_pilot'
                      AND expected_entity_count = 30 AND observed_entity_count = 30
                      AND audited AND outcome = 'complete' AND completed_at IS NOT NULL
                ) AS ready
                """,
                (universe_run_id,),
            )
            if not cursor.fetchone()["ready"]:
                raise RuntimeError("audited 30-entity discovery pilot required before full run")
        cursor.execute(
            """
            INSERT INTO discovery_runs (universe_run_id, mode, expected_entity_count)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (universe_run_id, mode, expected_entity_count),
        )
        return int(cursor.fetchone()["id"])


def classify_surface(
    observation: SurfaceObservation,
    *,
    known_domains: set[str],
) -> tuple[str, str | None, str | None]:
    hint = (observation.response_hint or "").lower()
    if observation.http_status in {401, 403} or "captcha" in hint or "login" in hint:
        return "BLOCKED", None, None
    if not observation.canonical_url:
        return "DISCOVERY_EXHAUSTED_NO_SURFACE", None, None
    safe_url = sanitize_url(observation.canonical_url)
    if not safe_url or safe_url == "<invalid-url>":
        return "FAILED", None, None
    validate_public_url(safe_url, resolve_dns=False)
    domain = (urlsplit(safe_url).hostname or "").lower()
    known = any(domain == value or domain.endswith(f".{value}") for value in known_domains)
    return ("FOUND" if known else "UNCLASSIFIED"), safe_url, domain


def record_discovery_result(
    connection: Any,
    *,
    discovery_run_id: int,
    canonical_entity_key: str,
    entity_id: int,
    observations: Iterable[SurfaceObservation],
    known_domains: set[str],
    method: str,
    checked_at: datetime | None = None,
    recheck_hours: int = 168,
) -> dict[str, Any]:
    clock = (checked_at or datetime.now(SAO_PAULO)).astimezone(SAO_PAULO)
    next_check = clock + timedelta(hours=recheck_hours)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT universe_run_id FROM discovery_runs WHERE id = %s FOR UPDATE",
            (discovery_run_id,),
        )
        run = cursor.fetchone()
        if not run:
            raise ValueError(f"unknown discovery run: {discovery_run_id}")
        universe_run_id = int(run["universe_run_id"])
        statuses: list[str] = []
        for observation in observations:
            if observation.kind not in SURFACE_KINDS:
                raise ValueError(f"invalid public surface kind: {observation.kind}")
            status, safe_url, domain = classify_surface(
                observation,
                known_domains=known_domains,
            )
            statuses.append(status)
            cursor.execute(
                """
                SELECT id, version_no, canonical_url, domain, platform
                FROM public_surface_observations
                WHERE universe_run_id = %s AND canonical_entity_key = %s
                  AND surface_kind = %s AND is_current
                FOR UPDATE
                """,
                (universe_run_id, canonical_entity_key, observation.kind),
            )
            prior = cursor.fetchone()
            version = int(prior["version_no"]) + 1 if prior else 1
            if prior:
                changed = any(
                    (
                        prior["canonical_url"] != safe_url,
                        prior["domain"] != domain,
                        prior["platform"] != observation.platform,
                    )
                )
                cursor.execute(
                    """
                    UPDATE public_surface_observations
                    SET is_current = FALSE, invalidated_at = %s,
                        invalidation_reason = %s
                    WHERE id = %s
                    """,
                    (clock, "binding_changed" if changed else "scheduled_revalidation", prior["id"]),
                )
            cursor.execute(
                """
                INSERT INTO public_surface_observations (
                    discovery_run_id, universe_run_id, canonical_entity_key,
                    entity_id, surface_kind, version_no, status,
                    canonical_url, domain, platform, anchor_url,
                    discovery_method, http_status, redirect_chain,
                    last_checked_at, next_check_at, evidence
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s::jsonb,
                    %s, %s, %s::jsonb
                )
                """,
                (
                    discovery_run_id,
                    universe_run_id,
                    canonical_entity_key,
                    entity_id,
                    observation.kind,
                    version,
                    status,
                    safe_url,
                    domain,
                    observation.platform,
                    sanitize_url(observation.anchor_url),
                    observation.method,
                    observation.http_status,
                    json.dumps([sanitize_url(url) for url in observation.redirect_chain]),
                    clock,
                    next_check,
                    json.dumps(sanitize_mapping(observation.evidence), ensure_ascii=False),
                ),
            )
        overall = (
            "FOUND"
            if "FOUND" in statuses
            else "UNCLASSIFIED"
            if "UNCLASSIFIED" in statuses
            else "BLOCKED"
            if "BLOCKED" in statuses
            else "DISCOVERY_EXHAUSTED_NO_SURFACE"
            if statuses and all(value == "DISCOVERY_EXHAUSTED_NO_SURFACE" for value in statuses)
            else "FAILED"
        )
        cursor.execute(
            """
            INSERT INTO entity_discovery_results (
                discovery_run_id, universe_run_id, canonical_entity_key,
                entity_id, status, method, checked_at, next_check_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (discovery_run_id, canonical_entity_key) DO UPDATE
            SET status = EXCLUDED.status, method = EXCLUDED.method,
                checked_at = EXCLUDED.checked_at, next_check_at = EXCLUDED.next_check_at
            """,
            (
                discovery_run_id,
                universe_run_id,
                canonical_entity_key,
                entity_id,
                overall,
                method,
                clock,
                next_check,
            ),
        )
    return {"status": overall, "surface_statuses": statuses, "next_check_at": next_check}


def finalize_discovery_run(connection: Any, run_id: int, *, audited: bool) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT universe_run_id, mode, expected_entity_count FROM discovery_runs WHERE id = %s FOR UPDATE",
            (run_id,),
        )
        run = cursor.fetchone()
        if not run:
            raise ValueError(f"unknown discovery run: {run_id}")
        cursor.execute(
            """
            SELECT canonical_entity_key
            FROM entity_discovery_results
            WHERE discovery_run_id = %s
            ORDER BY canonical_entity_key
            """,
            (run_id,),
        )
        ids = [str(row["canonical_entity_key"]) for row in cursor.fetchall() or []]
        expected = int(run["expected_entity_count"])
        completion_errors: list[str] = []
        if len(ids) != expected or len(set(ids)) != expected:
            completion_errors.append(f"entity_count expected={expected} observed={len(set(ids))} rows={len(ids)}")
        cursor.execute(
            """
            SELECT COUNT(*) AS complete_entities
            FROM (
                SELECT canonical_entity_key
                FROM public_surface_observations
                WHERE discovery_run_id = %s
                GROUP BY canonical_entity_key
                HAVING COUNT(DISTINCT surface_kind) = %s
            ) complete
            """,
            (run_id, len(SURFACE_KINDS)),
        )
        complete_surfaces = int(cursor.fetchone()["complete_entities"])
        if complete_surfaces != expected:
            completion_errors.append(
                "surface_set requires institutional, procurement, transparency, "
                f"gazette and cited-platform observations; complete={complete_surfaces} expected={expected}"
            )
        if run["mode"] == "full":
            _, active = latest_universe(connection)
            active_ids = {str(row["canonical_entity_key"]) for row in active}
            if set(ids) != active_ids:
                completion_errors.append("full discovery IDs do not equal active universe IDs")
        digest = ordered_ids_sha256(ids)
        outcome = "complete" if not completion_errors else "partial"
        cursor.execute(
            """
            UPDATE discovery_runs
            SET observed_entity_count = %s, canonical_ids_sha256 = %s,
                audited = %s, outcome = %s, completed_at = now()
            WHERE id = %s
            """,
            (len(set(ids)), digest, audited and outcome == "complete", outcome, run_id),
        )
    return {
        "run_id": run_id,
        "entity_count": len(set(ids)),
        "canonical_ids_sha256": digest,
        "outcome": outcome,
        "completion_errors": completion_errors,
    }


def record_coverage_attempt(connection: Any, attempt: CoverageAttempt) -> int:
    if attempt.status not in COVERAGE_STATES:
        raise ValueError(f"invalid coverage state: {attempt.status}")
    if attempt.status == "ZERO_CONFIRMED" and not (
        attempt.request_completed
        and attempt.scope_complete
        and attempt.pagination_reconciled
        and attempt.records_observed == 0
        and attempt.raw_uri
        and attempt.raw_sha256
    ):
        raise ValueError("ZERO_CONFIRMED requires complete reconciled request and preserved empty raw")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO entity_source_coverage_attempts (
                universe_run_id, canonical_entity_key, entity_id,
                source, capability, status, applicability, applicability_reason,
                canonical_url, checked_at, http_statuses,
                pages_fetched, pages_expected, records_observed,
                request_completed, scope_complete, pagination_reconciled,
                raw_uri, raw_sha256, freshness_deadline,
                next_action, next_check_at, run_id, crawl_job_attempt_id, evidence
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s::jsonb
            ) RETURNING id
            """,
            (
                attempt.universe_run_id,
                attempt.canonical_entity_key,
                attempt.entity_id,
                attempt.source,
                attempt.capability,
                attempt.status,
                attempt.applicability,
                attempt.applicability_reason,
                sanitize_url(attempt.canonical_url),
                attempt.checked_at,
                attempt.http_statuses,
                attempt.pages_fetched,
                attempt.pages_expected,
                attempt.records_observed,
                attempt.request_completed,
                attempt.scope_complete,
                attempt.pagination_reconciled,
                attempt.raw_uri,
                attempt.raw_sha256,
                attempt.freshness_deadline,
                attempt.next_action,
                attempt.next_check_at,
                attempt.run_id,
                attempt.crawl_job_attempt_id,
                json.dumps(sanitize_mapping(attempt.evidence), ensure_ascii=False),
            ),
        )
        attempt_id = int(cursor.fetchone()["id"])
        cursor.execute(
            """
            INSERT INTO entity_source_coverage_current (
                universe_run_id, canonical_entity_key, entity_id,
                source, capability, latest_attempt_id, status,
                applicability, applicability_reason, canonical_url,
                checked_at, freshness_deadline, next_action, next_check_at
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s
            )
            ON CONFLICT (universe_run_id, canonical_entity_key, source, capability)
            DO UPDATE SET latest_attempt_id = EXCLUDED.latest_attempt_id,
                status = EXCLUDED.status,
                applicability = EXCLUDED.applicability,
                applicability_reason = EXCLUDED.applicability_reason,
                canonical_url = EXCLUDED.canonical_url,
                checked_at = EXCLUDED.checked_at,
                freshness_deadline = EXCLUDED.freshness_deadline,
                next_action = EXCLUDED.next_action,
                next_check_at = EXCLUDED.next_check_at,
                updated_at = now()
            """,
            (
                attempt.universe_run_id,
                attempt.canonical_entity_key,
                attempt.entity_id,
                attempt.source,
                attempt.capability,
                attempt_id,
                attempt.status,
                attempt.applicability,
                attempt.applicability_reason,
                sanitize_url(attempt.canonical_url),
                attempt.checked_at,
                attempt.freshness_deadline,
                attempt.next_action,
                attempt.next_check_at,
            ),
        )
        return attempt_id


def coverage_authority_export(connection: Any, *, expected_entities: int = 1093) -> dict[str, Any]:
    universe_run_id, active = latest_universe(connection)
    active_ids = {str(row["canonical_entity_key"]) for row in active}
    if len(active_ids) != expected_entities:
        raise ValueError(f"coverage denominator mismatch: expected={expected_entities} active={len(active_ids)}")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT current.*, attempt.http_statuses, attempt.pages_fetched,
                   attempt.pages_expected, attempt.records_observed,
                   attempt.raw_uri, attempt.raw_sha256, attempt.evidence
            FROM entity_source_coverage_current current
            JOIN entity_source_coverage_attempts attempt
              ON attempt.id = current.latest_attempt_id
            WHERE current.universe_run_id = %s
            ORDER BY current.canonical_entity_key, current.source, current.capability
            """,
            (universe_run_id,),
        )
        rows = [dict(row) for row in cursor.fetchall() or []]
    covered_entities = {str(row["canonical_entity_key"]) for row in rows}
    missing = sorted(active_ids - covered_entities)
    route_entities = {
        str(row["canonical_entity_key"])
        for row in rows
        if row["capability"] == "open_tenders"
        and row["status"] in COVERAGE_STATES
        and row["next_action"]
        and row["next_check_at"]
    }
    missing_routes = sorted(active_ids - route_entities)
    if missing or missing_routes:
        raise ValueError(
            f"coverage authority incomplete: missing_rows={missing[:10]} missing_routes={missing_routes[:10]}"
        )
    return {
        "schema_version": "entity-source-coverage/v1",
        "universe_run_id": universe_run_id,
        "entity_count": len(active_ids),
        "canonical_ids_sha256": ordered_ids_sha256(active_ids),
        "row_count": len(rows),
        "rows": rows,
    }


def _artifact_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return value


def write_coverage_artifacts(
    connection: Any,
    output_dir: Path,
    *,
    expected_entities: int = 1093,
) -> dict[str, Any]:
    """Write XLSX, manifest and KPI from one in-memory authority snapshot."""
    from openpyxl import Workbook

    authority = coverage_authority_export(
        connection,
        expected_entities=expected_entities,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = authority["rows"]
    columns = sorted({str(key) for row in rows for key in row})
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Cobertura")
    sheet.append(columns)
    for row in rows:
        sheet.append([_artifact_value(row.get(column)) for column in columns])
    workbook_path = output_dir / "entity-source-coverage.xlsx"
    workbook.save(workbook_path)

    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    shared = {
        "schema_version": authority["schema_version"],
        "universe_run_id": authority["universe_run_id"],
        "entity_count": authority["entity_count"],
        "canonical_ids_sha256": authority["canonical_ids_sha256"],
        "row_count": authority["row_count"],
    }
    manifest_path = output_dir / "entity-source-coverage-manifest.json"
    manifest_path.write_text(
        json.dumps(shared, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    kpi_path = output_dir / "entity-source-coverage-kpi.json"
    kpi_path.write_text(
        json.dumps({**shared, "status_counts": status_counts}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        **shared,
        "xlsx": str(workbook_path),
        "manifest": str(manifest_path),
        "kpi": str(kpi_path),
        "reconciled": authority["row_count"] == sum(status_counts.values()),
    }
