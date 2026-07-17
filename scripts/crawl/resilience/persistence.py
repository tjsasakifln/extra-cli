"""Canonical persistence services shared by resilient_cycle and monitor."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

_logger = logging.getLogger(__name__)


@dataclass
class PersistResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    matched: int = 0
    unmatched: int = 0
    opportunities_persisted: int = 0
    db_records_committed: int = 0
    ingestion_run_id: int | str | None = None
    errors: list[str] = field(default_factory=list)
    backend: str = "none"
    content_max_timestamp: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


class PersistenceBackend(Protocol):
    def persist_canonical(
        self,
        *,
        source: str,
        records: list[dict[str, Any]],
        run_id: str,
        request_scope: str,
        date_from: str | None,
        date_to: str | None,
        provenance: dict[str, Any],
        fetch_status: str,
        pages_fetched: int,
        pages_expected: int | None,
    ) -> PersistResult: ...


def extract_content_max_timestamp(source: str, records: list[dict[str, Any]]) -> str | None:
    """Best-effort max content timestamp from normalized records. Never uses request time."""
    keys_by_source = {
        "pncp": ("data_publicacao", "dataPublicacaoPncp", "dataAtualizacao", "data_atualizacao", "data_abertura"),
        "ciga_dom": ("data_publicacao", "dataPublicacao", "data_efetiva", "published_at", "data"),
        "sc_compras": ("dataPublicacao", "data_publicacao", "dataAlteracao", "data_alteracao", "updated_at"),
    }
    keys = keys_by_source.get(source, ("data_publicacao", "dataPublicacao", "updated_at", "created_at"))
    best: str | None = None
    for row in records:
        for key in keys:
            value = row.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            if best is None or text > best:
                best = text
    return best


class NullPersistence:
    """Used only for fixture/test mechanics when DB is not required."""

    def persist_canonical(
        self,
        *,
        source: str,
        records: list[dict[str, Any]],
        run_id: str,
        request_scope: str,
        date_from: str | None,
        date_to: str | None,
        provenance: dict[str, Any],
        fetch_status: str,
        pages_fetched: int,
        pages_expected: int | None,
    ) -> PersistResult:
        return PersistResult(
            inserted=0,
            updated=0,
            unchanged=len(records),
            db_records_committed=0,
            backend="null_fixture",
            content_max_timestamp=extract_content_max_timestamp(source, records),
            provenance={"skipped_db": True, "reason": "fixture_or_test_without_require_db"},
            errors=[],
        )


class InMemoryPersistence:
    """Deterministic backend for unit tests (idempotent upsert simulation)."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.runs: list[dict[str, Any]] = []
        self.fail_mode: str | None = None
        self.call_count = 0

    def persist_canonical(
        self,
        *,
        source: str,
        records: list[dict[str, Any]],
        run_id: str,
        request_scope: str,
        date_from: str | None,
        date_to: str | None,
        provenance: dict[str, Any],
        fetch_status: str,
        pages_fetched: int,
        pages_expected: int | None,
    ) -> PersistResult:
        self.call_count += 1
        if self.fail_mode == "unavailable":
            return PersistResult(errors=["database_unavailable"], backend="memory")
        if self.fail_mode == "during_upsert":
            return PersistResult(errors=["upsert_failed:injected"], backend="memory")

        inserted = updated = unchanged = 0
        for record in records:
            key = str(record.get("pncp_id") or record.get("source_id") or record.get("id") or json.dumps(record, sort_keys=True, default=str))
            full_key = f"{source}:{key}"
            if full_key in self.rows:
                if self.rows[full_key] == record:
                    unchanged += 1
                else:
                    self.rows[full_key] = record
                    updated += 1
            else:
                self.rows[full_key] = record
                inserted += 1
        matched = sum(1 for r in records if r.get("orgao_cnpj") or r.get("cnpj"))
        result = PersistResult(
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            matched=matched,
            unmatched=max(0, len(records) - matched),
            opportunities_persisted=0,
            db_records_committed=inserted + updated + unchanged,
            ingestion_run_id=f"mem-{len(self.runs) + 1}",
            backend="memory",
            content_max_timestamp=extract_content_max_timestamp(source, records),
            provenance={"request_scope": request_scope, "run_id": run_id, **provenance},
        )
        self.runs.append(
            {
                "source": source,
                "run_id": run_id,
                "request_scope": request_scope,
                "result": result,
                "at": datetime.now(UTC).isoformat(),
            }
        )
        return result


class PostgresPersistence:
    """Real PostgreSQL path reusing monitor upsert / match / opportunities / evidence."""

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn

    def _conn(self) -> Any:
        from scripts.crawl.monitor import _get_conn

        return _get_conn(self.dsn)

    def persist_canonical(
        self,
        *,
        source: str,
        records: list[dict[str, Any]],
        run_id: str,
        request_scope: str,
        date_from: str | None,
        date_to: str | None,
        provenance: dict[str, Any],
        fetch_status: str,
        pages_fetched: int,
        pages_expected: int | None,
    ) -> PersistResult:
        from scripts.crawl.monitor import (
            _finish_ingestion_run,
            _load_entities,
            _persist_engineering_opportunities,
            _record_evidence,
            _start_ingestion_run,
            _upsert_raw_records,
        )
        from scripts.matching.entity_matcher import match_entities_cascade

        try:
            conn = self._conn()
        except Exception as exc:
            return PersistResult(errors=[f"database_unavailable:{exc}"], backend="postgres")

        result = PersistResult(backend="postgres")
        try:
            db_run_id = _start_ingestion_run(conn, source, mode="incremental")
            result.ingestion_run_id = db_run_id

            upsert_fn = {
                "pncp": "upsert_pncp_raw_bids",
                "sc_compras": "upsert_pncp_raw_bids",
                "ciga_dom": None,  # coverage / official acts path
            }.get(source, "upsert_pncp_raw_bids")

            if upsert_fn and records:
                try:
                    tagged = [{**r, "source": r.get("source") or source} for r in records]
                    inserted, updated, unchanged = _upsert_raw_records(conn, tagged, upsert_fn)
                    result.inserted = inserted
                    result.updated = updated
                    result.unchanged = unchanged
                    result.db_records_committed = inserted + updated + unchanged
                except Exception as exc:
                    conn.rollback()
                    result.errors.append(f"upsert_failed:{exc}")
                    _finish_ingestion_run(conn, db_run_id, len(records), 0, 0, "failed", str(exc))
                    _record_evidence(
                        conn,
                        db_run_id,
                        source,
                        "failed",
                        fetched=len(records),
                        error_message=str(exc),
                        error_code="persist_failed",
                        metadata={"request_scope": request_scope, "provenance": provenance},
                    )
                    conn.commit()
                    return result

            entities = _load_entities(conn, within_200km_only=False)
            pncp_ids = [r.get("pncp_id") for r in records if r.get("pncp_id")]
            match_stats = match_entities_cascade(conn, source, entities, pncp_ids)
            result.matched = match_stats.get("cnpj", 0) + match_stats.get("name_normalized", 0) + match_stats.get("fuzzy", 0)
            result.unmatched = match_stats.get("unmatched", 0)

            if source == "pncp" and records:
                from scripts.crawl.monitor import _build_pncp_opportunities

                opportunities, _stats = _build_pncp_opportunities(
                    conn,
                    records,
                    entities,
                    target=None,
                    engineering_only=False,
                    within_200km_only=False,
                )
                result.opportunities_persisted = _persist_engineering_opportunities(conn, opportunities)

            # Project resilience-aware source evidence (migration 054 columns when present).
            self._project_resilience_evidence(
                conn,
                run_id=str(db_run_id),
                source=source,
                request_scope=request_scope,
                fetch_status=fetch_status,
                pages_fetched=pages_fetched,
                pages_expected=pages_expected,
                provenance=provenance,
                fetched=len(records),
                persisted=result.db_records_committed,
                date_from=date_from,
                date_to=date_to,
                satisfactory=fetch_status in {"success", "empty_confirmed"} and not result.errors,
            )

            _finish_ingestion_run(
                conn,
                db_run_id,
                len(records),
                result.db_records_committed,
                result.matched,
                "completed" if not result.errors else "failed",
            )
            conn.commit()
            result.content_max_timestamp = extract_content_max_timestamp(source, records)
            result.provenance = {"request_scope": request_scope, "ingestion_run_id": db_run_id, **provenance}
            return result
        except Exception as exc:
            try:
                conn.rollback()
            except Exception as rollback_exc:
                _logger.debug("rollback ignored: %s", rollback_exc)
            result.errors.append(f"persist_canonical_failed:{exc}")
            return result
        finally:
            try:
                conn.close()
            except Exception as close_exc:
                _logger.debug("conn close ignored: %s", close_exc)

    def _project_resilience_evidence(
        self,
        conn: Any,
        *,
        run_id: str,
        source: str,
        request_scope: str,
        fetch_status: str,
        pages_fetched: int,
        pages_expected: int | None,
        provenance: dict[str, Any],
        fetched: int,
        persisted: int,
        date_from: str | None,
        date_to: str | None,
        satisfactory: bool,
    ) -> None:
        """Best-effort write including 054 columns when present."""
        import json as _json
        from datetime import date as _date

        cur = conn.cursor()
        try:
            cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'coverage_evidence')")
            if not cur.fetchone()[0]:
                return
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'coverage_evidence'"
            )
            cols = {row[0] for row in cur.fetchall()}
            state = {
                "success": "success_with_data" if fetched > 0 else "success_zero",
                "empty_confirmed": "success_zero",
                "partial": "partial",
                "rate_limited": "partial",
                "auth_blocked": "auth_failed",
                "error": "connection_failed",
            }.get(fetch_status, "partial")
            q_start = _date.fromisoformat(date_from) if date_from else None
            q_end = _date.fromisoformat(date_to) if date_to else None
            cur.execute(
                """DELETE FROM coverage_evidence
                   WHERE entity_id IS NULL AND source = %s AND data_type = %s AND run_id = %s""",
                (source, "bids", run_id),
            )
            if {"request_scope", "satisfactory", "provenance", "pages_fetched", "pages_expected"} <= cols:
                # Only mark satisfactory when CHECK constraint would allow it.
                safe_satisfactory = bool(
                    satisfactory
                    and state in {"success_with_data", "success_zero"}
                    and request_scope
                    and provenance
                    and (pages_expected is None or pages_fetched >= pages_expected)
                )
                cur.execute(
                    """INSERT INTO coverage_evidence
                       (entity_id, source, data_type, queried_start, queried_end,
                        run_id, started_at, completed_at,
                        count_obtained, count_transformed, count_persisted,
                        state, metadata, request_scope, pages_fetched, pages_expected,
                        provenance, satisfactory)
                       VALUES (NULL, %s, 'bids', %s, %s, %s, NOW(), NOW(), %s, %s, %s, %s, %s,
                               %s, %s, %s, %s::jsonb, %s)""",
                    (
                        source,
                        q_start,
                        q_end,
                        run_id,
                        fetched,
                        fetched,
                        persisted,
                        state,
                        _json.dumps({"pipeline": "resilient_cycle"}, ensure_ascii=False),
                        request_scope,
                        pages_fetched,
                        pages_expected,
                        _json.dumps(provenance or {}, ensure_ascii=False),
                        safe_satisfactory,
                    ),
                )
            else:
                cur.execute(
                    """INSERT INTO coverage_evidence
                       (entity_id, source, data_type, queried_start, queried_end,
                        run_id, started_at, completed_at,
                        count_obtained, count_transformed, count_persisted,
                        state, metadata)
                       VALUES (NULL, %s, 'bids', %s, %s, %s, NOW(), NOW(), %s, %s, %s, %s, %s)""",
                    (
                        source,
                        q_start,
                        q_end,
                        run_id,
                        fetched,
                        fetched,
                        persisted,
                        state,
                        _json.dumps({"pipeline": "resilient_cycle", "request_scope": request_scope}, ensure_ascii=False),
                    ),
                )
        finally:
            cur.close()


def build_persistence_backend(*, require_db: bool, prefer_memory: bool = False) -> PersistenceBackend:
    if prefer_memory:
        return InMemoryPersistence()
    if not require_db:
        return NullPersistence()
    dsn = os.getenv("DATABASE_URL") or os.getenv("LOCAL_DATALAKE_DSN")
    if not dsn:
        # Fail-closed for live: caller should treat missing DSN as error.
        return PostgresPersistence(dsn=None)
    return PostgresPersistence(dsn=dsn)
