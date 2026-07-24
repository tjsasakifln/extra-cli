"""Auditable PNCP open-proposals crawl across every official modality."""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import psycopg2

from scripts.crawl.pncp_contract import DEFAULT_MODALIDADES
from scripts.lib.universe import CanonicalUniverse, normalize_cnpj8
from scripts.opportunity_intel.models import CrawlRequest, FetchResult
from scripts.opportunity_intel.pncp_crawler import PncpOpportunityCrawler
from scripts.opportunity_intel.reconciliation import SourceSnapshotReconciler
from scripts.opportunity_intel.transformer import normalize_record

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScopeOutcome:
    scope_key: str
    modalidade: int
    pages_expected: int | None
    pages_processed: int
    records_expected: int | None
    records_fetched: int
    scope_complete: bool
    completion_rule: str | None
    http_status: int | None
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True)
class PncpRunOutcome:
    external_run_id: str
    db_run_id: int | None
    status: str
    scope_complete: bool
    pages_expected: int | None
    pages_processed: int
    records_expected: int | None
    records_fetched: int
    records_inserted: int
    records_updated: int
    error_code: str | None
    error_message: str | None
    scopes: tuple[ScopeOutcome, ...]
    records: tuple[dict[str, Any], ...]

    def manifest(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("records")
        return payload


def run_pncp_open_monitoring(
    *,
    dsn: str,
    external_run_id: str,
    universe: CanonicalUniverse,
    period_start: date,
    period_end: date,
    mode: str = "full",
    max_pages: int | None = None,
    max_records: int | None = None,
    persist: bool = True,
    timeout: int | None = None,
    max_retries: int | None = None,
    request_delay: float | None = None,
) -> PncpRunOutcome:
    """Crawl modalities 1–19 as scopes of one PNCP source run."""
    if mode not in {"full", "incremental", "dry-run"}:
        raise ValueError(f"Unsupported crawl mode: {mode}")
    if persist and mode == "dry-run":
        raise ValueError("dry-run cannot persist records or evidence")

    conn = _connect_postgres(dsn) if persist else None
    db_run_id = _start_run(conn, external_run_id, period_start, period_end, mode) if conn else None
    crawler = PncpOpportunityCrawler(
        dsn=dsn,
        timeout=timeout,
        max_retries=max_retries,
        request_delay=request_delay,
        max_pages=max_pages,
    )
    scopes: list[ScopeOutcome] = []
    raw_records: list[dict[str, Any]] = []
    remaining_records = max_records

    try:
        source_blocker: ScopeOutcome | None = None
        for modalidade in DEFAULT_MODALIDADES:
            if source_blocker is not None:
                scopes.append(
                    ScopeOutcome(
                        scope_key=f"uf=SC;modalidade={modalidade}",
                        modalidade=modalidade,
                        pages_expected=None,
                        pages_processed=0,
                        records_expected=None,
                        records_fetched=0,
                        scope_complete=False,
                        completion_rule="source_halted_after_blocker",
                        http_status=None,
                        error_code="BLOCKED_BY_PREVIOUS_SCOPE",
                        error_message=(
                            "Source crawl halted after blocker in "
                            f"{source_blocker.scope_key}: {source_blocker.error_code}"
                        ),
                    )
                )
                continue
            if remaining_records is not None and remaining_records <= 0:
                scopes.append(
                    ScopeOutcome(
                        scope_key=f"uf=SC;modalidade={modalidade}",
                        modalidade=modalidade,
                        pages_expected=None,
                        pages_processed=0,
                        records_expected=None,
                        records_fetched=0,
                        scope_complete=False,
                        completion_rule="max_records_before_scope",
                        http_status=None,
                        error_code="MAX_RECORDS",
                        error_message="Global record limit reached before this scope",
                    )
                )
                continue

            request = CrawlRequest(
                source="pncp",
                target=f"modalidade:{modalidade}",
                date_from=period_start,
                date_to=period_end,
                mode=mode,
                max_pages=max_pages,
                max_records=remaining_records,
                page_size=crawler.page_size,
            )
            results = crawler.crawl(request)
            for result in results:
                for raw in result.raw_data:
                    record = dict(raw)
                    record["_qw01_status_evidence"] = "pncp_open_proposals_endpoint"
                    raw_records.append(record)

            scope_outcome = _summarize_scope(modalidade, results, max_pages, remaining_records)
            scopes.append(scope_outcome)
            if scope_outcome.error_code and scope_outcome.error_code.startswith(("HTTP_", "NETWORK")):
                source_blocker = scope_outcome
            if remaining_records is not None:
                remaining_records -= scope_outcome.records_fetched

        deduplicated = _deduplicate_raw_records(raw_records)
        inserted = 0
        updated = 0
        if persist and db_run_id is not None and deduplicated:
            inserted, updated = _persist_records(conn, deduplicated, db_run_id, external_run_id)

        scope_complete = len(scopes) == len(DEFAULT_MODALIDADES) and all(scope.scope_complete for scope in scopes)
        pages_processed = sum(s.pages_processed for s in scopes)
        if scope_complete and all(s.pages_expected is not None for s in scopes):
            pages_expected: int | None = sum(int(s.pages_expected) for s in scopes)  # type: ignore[arg-type, misc]
        else:
            pages_expected = None
        if scope_complete and all(s.records_expected is not None for s in scopes):
            records_expected: int | None = sum(int(s.records_expected) for s in scopes)  # type: ignore[arg-type, misc]
        else:
            records_expected = None
        records_fetched = len(deduplicated)
        failed_scopes = [scope for scope in scopes if not scope.scope_complete]
        if scope_complete and records_fetched == 0:
            status = "completed_zero"
        elif scope_complete:
            status = "completed"
        elif records_fetched == 0 and all(scope.pages_processed == 0 or scope.error_code for scope in scopes):
            status = "failed"
        else:
            status = "partial"
        error_code = failed_scopes[0].error_code if failed_scopes else None
        error_message = failed_scopes[0].error_message if failed_scopes else None

        outcome = PncpRunOutcome(
            external_run_id=external_run_id,
            db_run_id=db_run_id,
            status=status,
            scope_complete=scope_complete,
            pages_expected=pages_expected,
            pages_processed=pages_processed,
            records_expected=records_expected,
            records_fetched=records_fetched,
            records_inserted=inserted,
            records_updated=updated,
            error_code=error_code,
            error_message=error_message,
            scopes=tuple(scopes),
            records=tuple(deduplicated),
        )
        if conn is not None and db_run_id is not None:
            _finish_run(conn, db_run_id, outcome)
            # Coverage evidence projection is audit support — never overwrite a
            # finished crawl status if projection fails (fail-open for evidence,
            # fail-closed remains on crawl/reconcile gates).
            try:
                _project_coverage_evidence(
                    conn=conn,
                    universe=universe,
                    outcome=outcome,
                    period_start=period_start,
                    period_end=period_end,
                )
            except Exception as proj_err:  # noqa: BLE001
                _logger.error(
                    "Coverage evidence projection failed for run %s (crawl status kept=%s): %s",
                    db_run_id,
                    outcome.status,
                    proj_err,
                    exc_info=True,
                )
            # Story 1.4: Trigger snapshot reconciliation for completed runs
            if scope_complete and outcome.status in ("completed", "completed_zero"):
                try:
                    reconciler = SourceSnapshotReconciler(dsn)
                    recon_result = reconciler.reconcile(
                        run_id=db_run_id,
                        source="pncp",
                        records=list(deduplicated) if deduplicated else None,
                    )
                    _logger.info(
                        "Snapshot reconciliation for run %d: %s",
                        db_run_id,
                        "skipped"
                        if recon_result.skipped
                        else f"active_before={recon_result.active_before}, "
                        f"inactivated={recon_result.inactivated}, "
                        f"reactivated={recon_result.reactivated}",
                    )
                except Exception as recon_err:
                    _logger.error(
                        "Snapshot reconciliation failed for run %d: %s",
                        db_run_id,
                        recon_err,
                        exc_info=True,
                    )
        return outcome
    except Exception as exc:
        if conn is not None and db_run_id is not None:
            _fail_run(conn, db_run_id, exc)
        raise
    finally:
        crawler.close()
        if conn is not None:
            conn.close()


def _summarize_scope(
    modalidade: int,
    results: list[FetchResult],
    max_pages: int | None,
    max_records: int | None,
) -> ScopeOutcome:
    pages_processed = len(results)
    records_fetched = sum(len(result.raw_data) for result in results if result.success)
    last = results[-1] if results else None
    total_pages = next((result.total_pages for result in results if result.total_pages is not None), None)
    total_records = next((result.total_records for result in results if result.total_records is not None), None)
    all_success = bool(results) and all(result.success for result in results)
    last_page = bool(last and last.is_last_page)
    hit_page_limit = bool(max_pages and pages_processed >= max_pages and not last_page)
    hit_record_limit = bool(max_records is not None and records_fetched >= max_records and not last_page)
    scope_complete = all_success and last_page and not hit_page_limit and not hit_record_limit

    error_code = None
    error_message = None
    if last and last.error:
        error_code = f"HTTP_{last.status}" if last.status else "NETWORK_ERROR"
        error_message = last.error
    elif hit_page_limit:
        error_code = "MAX_PAGES"
        error_message = "max_pages reached before pagination completion"
    elif hit_record_limit:
        error_code = "MAX_RECORDS"
        error_message = "max_records reached before pagination completion"
    elif not results:
        error_code = "NO_PAGE_ATTEMPT"
        error_message = "No page was attempted"
    elif not scope_complete:
        error_code = "PAGINATION_UNPROVEN"
        error_message = "Pagination completion could not be proven"

    expected_pages = total_pages
    if scope_complete and expected_pages is None:
        expected_pages = pages_processed
    return ScopeOutcome(
        scope_key=f"uf=SC;modalidade={modalidade}",
        modalidade=modalidade,
        pages_expected=expected_pages,
        pages_processed=pages_processed,
        records_expected=total_records,
        records_fetched=records_fetched,
        scope_complete=scope_complete,
        completion_rule=last.completion_rule if last else None,
        http_status=last.status if last else None,
        error_code=error_code,
        error_message=error_message,
    )


def _deduplicate_raw_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduplicated: dict[str, dict[str, Any]] = {}
    for record in records:
        source_id = str(record.get("numeroControlePNCP") or record.get("id") or "")
        if not source_id:
            raise ValueError("PNCP source record is missing its official identity")
        deduplicated[source_id] = record
    return list(deduplicated.values())


def _persist_records(
    conn: Any,
    records: list[dict[str, Any]],
    db_run_id: int,
    external_run_id: str,
) -> tuple[int, int]:
    payload: list[dict[str, Any]] = []
    for raw in records:
        normalized = normalize_record(raw, "pncp")
        normalized.run_id = db_run_id
        normalized.crawl_batch_id = external_run_id
        payload.append(normalized.to_db_dict())

    inserted = 0
    updated = 0
    batch_size = 500
    with conn.cursor() as cursor:
        for offset in range(0, len(payload), batch_size):
            cursor.execute(
                "SELECT * FROM upsert_qw01_pncp_opportunities(%s::jsonb)",
                (json.dumps(payload[offset : offset + batch_size], default=str),),
            )
            for action, _, _ in cursor.fetchall():
                if action == "insert":
                    inserted += 1
                else:
                    updated += 1
    return inserted, updated


def _start_run(conn: Any, external_run_id: str, period_start: date, period_end: date, mode: str) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO opportunity_runs (
                source, scope_key, status, external_run_id, source_strategy,
                period_start, period_end, metadata
            ) VALUES (
                'pncp', 'uf=SC;modalidades=1-19', 'running', %s,
                'pncp_open_proposals', %s, %s, %s::jsonb
            ) RETURNING id
            """,
            (
                external_run_id,
                period_start,
                period_end,
                json.dumps({"mode": mode, "modalidades": list(DEFAULT_MODALIDADES)}),
            ),
        )
        return int(cursor.fetchone()[0])


def _finish_run(conn: Any, db_run_id: int, outcome: PncpRunOutcome) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE opportunity_runs
            SET finished_at = NOW(), status = %s, records_fetched = %s,
                records_new = %s, records_updated = %s, pages_processed = %s,
                pages_expected = %s, records_expected = %s, scope_complete = %s,
                completion_reason = %s, error_code = %s, error_message = %s,
                metadata = metadata || %s::jsonb
            WHERE id = %s
            """,
            (
                outcome.status,
                outcome.records_fetched,
                outcome.records_inserted,
                outcome.records_updated,
                outcome.pages_processed,
                outcome.pages_expected,
                outcome.records_expected,
                outcome.scope_complete,
                "all_modalities_complete" if outcome.scope_complete else "one_or_more_scopes_incomplete",
                outcome.error_code,
                outcome.error_message,
                json.dumps({"scopes": [asdict(scope) for scope in outcome.scopes]}, default=str),
                db_run_id,
            ),
        )


def _fail_run(conn: Any, db_run_id: int, exc: Exception) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE opportunity_runs
            SET finished_at = NOW(), status = 'failed', scope_complete = FALSE,
                error_code = 'TECHNICAL_ERROR', error_message = %s,
                completion_reason = 'unhandled_technical_failure'
            WHERE id = %s
            """,
            (str(exc), db_run_id),
        )


def _project_coverage_evidence(
    *,
    conn: Any,
    universe: CanonicalUniverse,
    outcome: PncpRunOutcome,
    period_start: date,
    period_end: date,
) -> None:
    root_counts = Counter(normalize_cnpj8(_raw_org_cnpj(record)) for record in outcome.records if _raw_org_cnpj(record))
    scope_key = f"uf=SC;modalidades=1-19;{period_start.isoformat()}:{period_end.isoformat()}"
    scopes_payload = [asdict(scope) for scope in outcome.scopes]
    completion_rule = "reported_total_pages" if outcome.scope_complete else "scope_incomplete"
    records: list[tuple[Any, ...]] = []

    for entity in universe.conservative_monitoring_population:
        applicability = "applicable" if entity.within_radius is True else "unknown"
        if entity.within_radius is None:
            state = "blocked"
            error_code = "UNRESOLVED_RADIUS"
            error_message = "Radius decision unresolved; entity remains in conservative denominator"
        elif not outcome.scope_complete:
            state = "partial" if outcome.pages_processed > 0 else "error"
            error_code = outcome.error_code or "INCOMPLETE_SCOPE"
            error_message = outcome.error_message or "PNCP source scope incomplete"
        else:
            state = "success" if root_counts.get(entity.cnpj8, 0) > 0 else "success_zero"
            error_code = None
            error_message = None

        count = int(root_counts.get(entity.cnpj8, 0))
        metadata = {
            "completion_rule": completion_rule,
            "source_strategy": "pncp_open_proposals",
            "modalities": list(DEFAULT_MODALIDADES),
            "scope_complete": outcome.scope_complete,
            "duplicate_root": entity.duplicate_root,
            "scopes": scopes_payload,
        }
        records.append(
            (
                entity.db_entity_id,
                entity.entity_id,
                applicability,
                scope_key,
                period_start,
                period_end,
                outcome.external_run_id,
                state,
                outcome.pages_expected,
                outcome.pages_processed,
                outcome.records_fetched,
                count,
                count,
                "fresh" if outcome.scope_complete else "unknown",
                error_code,
                error_message,
                json.dumps(metadata, default=str),
            )
        )

    # Deduplicate by canonical key (primary) / db entity_id within the batch.
    # Unique indexes after migration 059:
    #   uq_ce_canonical_entity_run (canonical_entity_key, source, data_type, run_id)
    #     WHERE canonical_entity_key IS NOT NULL
    #   uq_ce_legacy_entity_run (entity_id, source, data_type, run_id)
    #     WHERE canonical_entity_key IS NULL AND entity_id IS NOT NULL
    deduped: dict[Any, tuple[Any, ...]] = {}
    for rec in records:
        entity_id = rec[0]
        canon = rec[1]
        key = ("canon", canon) if canon is not None else ("legacy", entity_id)
        deduped[key] = rec
    records = list(deduped.values())

    # Canonical path (preferred): every monitoring population row has entity_id string key.
    sql_canonical = """
        INSERT INTO coverage_evidence (
            entity_id, canonical_entity_key, source, data_type, applicability,
            scope_key, queried_start, queried_end, run_id, started_at,
            completed_at, checked_at, count_obtained, count_transformed,
            count_persisted, state, pages_expected, pages_processed,
            records_fetched, open_records, freshness_status, error_code,
            error_message, metadata, evidence_metadata
        ) VALUES (
            %s, %s, 'pncp', 'bids', %s, %s, %s, %s, %s, NOW(), NOW(), NOW(),
            %s, %s, %s, %s::evidence_state, %s, %s, %s, %s, %s, %s, %s,
            %s::jsonb, %s::jsonb
        )
        ON CONFLICT (canonical_entity_key, source, data_type, run_id)
            WHERE canonical_entity_key IS NOT NULL
        DO UPDATE SET
            entity_id = COALESCE(EXCLUDED.entity_id, coverage_evidence.entity_id),
            checked_at = EXCLUDED.checked_at,
            completed_at = EXCLUDED.completed_at,
            state = EXCLUDED.state,
            pages_expected = EXCLUDED.pages_expected,
            pages_processed = EXCLUDED.pages_processed,
            records_fetched = EXCLUDED.records_fetched,
            open_records = EXCLUDED.open_records,
            freshness_status = EXCLUDED.freshness_status,
            error_code = EXCLUDED.error_code,
            error_message = EXCLUDED.error_message,
            metadata = EXCLUDED.metadata,
            evidence_metadata = EXCLUDED.evidence_metadata
    """
    sql_legacy = """
        INSERT INTO coverage_evidence (
            entity_id, canonical_entity_key, source, data_type, applicability,
            scope_key, queried_start, queried_end, run_id, started_at,
            completed_at, checked_at, count_obtained, count_transformed,
            count_persisted, state, pages_expected, pages_processed,
            records_fetched, open_records, freshness_status, error_code,
            error_message, metadata, evidence_metadata
        ) VALUES (
            %s, NULL, 'pncp', 'bids', %s, %s, %s, %s, %s, NOW(), NOW(), NOW(),
            %s, %s, %s, %s::evidence_state, %s, %s, %s, %s, %s, %s, %s,
            %s::jsonb, %s::jsonb
        )
        ON CONFLICT (entity_id, source, data_type, run_id)
            WHERE canonical_entity_key IS NULL AND entity_id IS NOT NULL
        DO UPDATE SET
            checked_at = EXCLUDED.checked_at,
            completed_at = EXCLUDED.completed_at,
            state = EXCLUDED.state,
            pages_expected = EXCLUDED.pages_expected,
            pages_processed = EXCLUDED.pages_processed,
            records_fetched = EXCLUDED.records_fetched,
            open_records = EXCLUDED.open_records,
            freshness_status = EXCLUDED.freshness_status,
            error_code = EXCLUDED.error_code,
            error_message = EXCLUDED.error_message,
            metadata = EXCLUDED.metadata,
            evidence_metadata = EXCLUDED.evidence_metadata
    """
    with conn.cursor() as cursor:
        for record in records:
            (
                db_entity_id,
                canonical_key,
                applicability,
                row_scope_key,
                row_period_start,
                row_period_end,
                run_id,
                state,
                pages_expected,
                pages_processed,
                records_fetched,
                open_records,
                count_obtained,
                freshness_status,
                error_code,
                error_message,
                metadata_json,
            ) = record
            if canonical_key:
                cursor.execute(
                    sql_canonical,
                    (
                        db_entity_id,
                        canonical_key,
                        applicability,
                        row_scope_key,
                        row_period_start,
                        row_period_end,
                        run_id,
                        count_obtained,
                        count_obtained,
                        count_obtained,
                        state,
                        pages_expected,
                        pages_processed,
                        records_fetched,
                        open_records,
                        freshness_status,
                        error_code,
                        error_message,
                        metadata_json,
                        metadata_json,
                    ),
                )
            elif db_entity_id is not None:
                cursor.execute(
                    sql_legacy,
                    (
                        db_entity_id,
                        applicability,
                        row_scope_key,
                        row_period_start,
                        row_period_end,
                        run_id,
                        count_obtained,
                        count_obtained,
                        count_obtained,
                        state,
                        pages_expected,
                        pages_processed,
                        records_fetched,
                        open_records,
                        freshness_status,
                        error_code,
                        error_message,
                        metadata_json,
                        metadata_json,
                    ),
                )


def _raw_org_cnpj(record: dict[str, Any]) -> str:
    orgao_val = record.get("orgaoEntidade")
    orgao = orgao_val if isinstance(orgao_val, dict) else {}
    return str(record.get("orgaoCNPJ") or record.get("orgaoCnpj") or orgao.get("cnpj") or "")


def _connect_postgres(dsn: str) -> Any:
    if not dsn.startswith(("postgresql://", "postgres://")):
        raise ValueError("QW-01 readiness requires PostgreSQL; SQLite fallback is forbidden")
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    return conn
