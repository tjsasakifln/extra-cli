"""Durable store for dirty queue, current materialization, history, events.

Uses Postgres row locks (FOR UPDATE SKIP LOCKED) + lock TTL for crash recovery.
Never depends on sticky lockfiles.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from scripts.confenge_target_fit import (
    STATUS_DEAD,
    STATUS_DONE,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_REFRESH_FAILED,
    STATUS_RETRY,
    STATUS_SKIPPED,
    STORE_SCHEMA_VERSION,
)
from scripts.confenge_target_fit.models import (
    DirtyItem,
    MaterializedTargetFit,
    TransitionEvent,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _json_default(obj: Any) -> Any:
    """JSON default for Decimal/date values coming from Postgres rows."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    try:
        from decimal import Decimal

        if isinstance(obj, Decimal):
            return float(obj)
    except Exception:  # noqa: BLE001
        pass
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def _json(value: Any) -> str:
    return json.dumps(
        value if value is not None else [],
        ensure_ascii=False,
        default=_json_default,
    )


def ensure_control_defaults(conn: Any) -> None:
    with conn.cursor() as cur:
        for key, value in (
            ("async_mode", {"mode": "SHADOW"}),
            ("cdc_watermark", {"watermark": "", "observed_at": None}),
            ("auto_pause", {"paused": False, "reason": None}),
        ):
            cur.execute(
                """
                INSERT INTO confenge_target_fit_control (key, value)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (key) DO NOTHING
                """,
                (key, json.dumps(value)),
            )


def get_control(conn: Any, key: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT value FROM confenge_target_fit_control WHERE key = %s",
            (key,),
        )
        row = cur.fetchone()
        if not row:
            return {}
        val = row["value"]
        if isinstance(val, dict):
            return val
        if isinstance(val, str):
            return json.loads(val)
        return dict(val or {})


def set_control(conn: Any, key: str, value: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO confenge_target_fit_control (key, value, updated_at)
            VALUES (%s, %s::jsonb, now())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = now()
            """,
            (key, json.dumps(value)),
        )


def enqueue_dirty(
    conn: Any,
    *,
    company_key: str,
    cnpj_raiz: str,
    reason: str,
    source_entity: str,
    source_id: str | None,
    source_updated_at: datetime | None,
    source_watermark: str,
    priority: int,
    idempotency_key: str,
) -> bool:
    """Insert dirty item. Returns True if newly enqueued (False if idempotent hit)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO confenge_target_fit_dirty (
                company_key, cnpj_raiz, reason, source_entity, source_id,
                source_updated_at, source_watermark, priority, status,
                idempotency_key
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                company_key,
                cnpj_raiz,
                reason,
                source_entity,
                source_id,
                source_updated_at,
                source_watermark or "",
                priority,
                STATUS_PENDING,
                idempotency_key,
            ),
        )
        row = cur.fetchone()
        return row is not None


def requeue_company(
    conn: Any,
    *,
    company_key: str,
    cnpj_raiz: str,
    reason: str = "manual_requeue",
    priority: int = 90,
    source_watermark: str = "",
) -> str:
    key = f"requeue:{company_key}:{uuid.uuid4().hex[:12]}"
    enqueue_dirty(
        conn,
        company_key=company_key,
        cnpj_raiz=cnpj_raiz,
        reason=reason,
        source_entity="manual",
        source_id=None,
        source_updated_at=_utcnow(),
        source_watermark=source_watermark,
        priority=priority,
        idempotency_key=key,
    )
    return key


def reclaim_expired_locks(conn: Any) -> int:
    """Crash recovery: processing rows past lock TTL → pending/retry."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE confenge_target_fit_dirty
            SET status = CASE
                    WHEN attempt_count >= 5 THEN 'dead'
                    ELSE 'retry'
                END,
                next_retry_at = now(),
                locked_by = NULL,
                locked_until = NULL,
                last_error = COALESCE(last_error, '') || ' [lock_expired]',
                updated_at = now()
            WHERE status = 'processing'
              AND locked_until IS NOT NULL
              AND locked_until < now()
            """
        )
        return cur.rowcount or 0


def claim_batch(
    conn: Any,
    *,
    worker_id: str,
    batch_size: int,
    lock_ttl_seconds: int,
) -> list[DirtyItem]:
    """Claim pending/retry items with FOR UPDATE SKIP LOCKED (single-writer per row)."""
    reclaim_expired_locks(conn)
    now = _utcnow()
    lock_until = now + timedelta(seconds=lock_ttl_seconds)
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH cte AS (
                SELECT id
                FROM confenge_target_fit_dirty
                WHERE status IN ('pending', 'retry')
                  AND (next_retry_at IS NULL OR next_retry_at <= now())
                ORDER BY priority DESC, detected_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            UPDATE confenge_target_fit_dirty d
            SET status = 'processing',
                locked_by = %s,
                locked_until = %s,
                attempt_count = d.attempt_count + 1,
                updated_at = now()
            FROM cte
            WHERE d.id = cte.id
            RETURNING d.*
            """,
            (batch_size, worker_id, lock_until),
        )
        rows = cur.fetchall() or []
    return [_row_to_dirty(r) for r in rows]


def mark_dirty_done(
    conn: Any,
    dirty_id: int,
    *,
    status: str = STATUS_DONE,
    error: str | None = None,
    fingerprint: str | None = None,
    next_retry_at: datetime | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE confenge_target_fit_dirty
            SET status = %s,
                last_error = %s,
                input_fingerprint = COALESCE(%s, input_fingerprint),
                next_retry_at = %s,
                locked_by = NULL,
                locked_until = NULL,
                processed_at = CASE WHEN %s IN ('done', 'skipped_same_fingerprint')
                                    THEN now() ELSE processed_at END,
                updated_at = now()
            WHERE id = %s
            """,
            (status, error, fingerprint, next_retry_at, status, dirty_id),
        )


def get_current(conn: Any, company_key: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM confenge_company_target_fit_current WHERE company_key = %s",
            (company_key,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_stale_versions(
    conn: Any,
    *,
    current_version: str,
    limit: int = 500,
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT company_key, cnpj_raiz, target_fit_class, target_fit_version,
                   computed_at, source_watermark
            FROM confenge_company_target_fit_current
            WHERE target_fit_version IS DISTINCT FROM %s
               OR operational_status = 'recompute_required'
            ORDER BY
                CASE target_fit_class
                    WHEN 'TARGET_CONFIRMED' THEN 0
                    WHEN 'TARGET_PROBABLE_RESEARCH' THEN 1
                    ELSE 2
                END,
                computed_at ASC NULLS FIRST
            LIMIT %s
            """,
            (current_version, limit),
        )
        return [dict(r) for r in (cur.fetchall() or [])]


def publish_materialization(
    conn: Any,
    mat: MaterializedTargetFit,
    event: TransitionEvent | None,
    *,
    shadow_only: bool = False,
) -> int | None:
    """Atomic publish: history append + current upsert + optional event.

    When shadow_only=True, writes shadow table only (no current/eligibility change).
    Returns event id when an event was inserted.
    """
    event_id: int | None = None
    if shadow_only:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO confenge_target_fit_shadow (
                    company_key, cnpj_raiz, shadow_class, shadow_confidence,
                    current_class, current_confidence, target_fit_version,
                    input_fingerprint, evidence, reason_codes, transition,
                    source_watermark, computed_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s::jsonb, %s::jsonb, %s,
                    %s, %s, now()
                )
                ON CONFLICT (company_key) DO UPDATE SET
                    shadow_class = EXCLUDED.shadow_class,
                    shadow_confidence = EXCLUDED.shadow_confidence,
                    current_class = EXCLUDED.current_class,
                    current_confidence = EXCLUDED.current_confidence,
                    target_fit_version = EXCLUDED.target_fit_version,
                    input_fingerprint = EXCLUDED.input_fingerprint,
                    evidence = EXCLUDED.evidence,
                    reason_codes = EXCLUDED.reason_codes,
                    transition = EXCLUDED.transition,
                    source_watermark = EXCLUDED.source_watermark,
                    computed_at = EXCLUDED.computed_at,
                    updated_at = now()
                """,
                (
                    mat.company_key,
                    mat.cnpj_raiz,
                    mat.target_fit_class,
                    mat.target_fit_confidence,
                    mat.previous_class,
                    mat.previous_confidence,
                    mat.target_fit_version,
                    mat.input_fingerprint,
                    _json(mat.target_fit_evidence),
                    _json(mat.target_fit_reason_codes),
                    mat.transition_event,
                    mat.source_watermark,
                    mat.computed_at,
                ),
            )
        return None

    with conn.cursor() as cur:
        # Append-only history first
        cur.execute(
            """
            INSERT INTO confenge_company_target_fit_history (
                company_key, cnpj_raiz, target_fit_class, target_fit_confidence,
                target_fit_version, target_fit_reason_codes, target_fit_evidence,
                computed_at, source_watermark, source_max_updated_at,
                input_fingerprint, classifier_sha, schema_version,
                previous_class, previous_confidence, transition_event,
                materialization_mode
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s::jsonb, %s::jsonb,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s
            )
            """,
            (
                mat.company_key,
                mat.cnpj_raiz,
                mat.target_fit_class,
                mat.target_fit_confidence,
                mat.target_fit_version,
                _json(mat.target_fit_reason_codes),
                _json(mat.target_fit_evidence),
                mat.computed_at,
                mat.source_watermark,
                mat.source_max_updated_at,
                mat.input_fingerprint,
                mat.classifier_sha,
                mat.schema_version or STORE_SCHEMA_VERSION,
                mat.previous_class,
                mat.previous_confidence,
                mat.transition_event,
                mat.materialization_mode,
            ),
        )
        # Canonical current (atomic upsert)
        cur.execute(
            """
            INSERT INTO confenge_company_target_fit_current (
                company_key, cnpj_raiz, target_fit_class, target_fit_confidence,
                target_fit_version, target_fit_reason_codes, target_fit_evidence,
                computed_at, source_watermark, source_max_updated_at,
                input_fingerprint, classifier_sha, schema_version,
                operational_status, sector_fit, activity_class,
                relevant_execution_contract_count, relevant_supply_only_count,
                materialization_mode, updated_at
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s::jsonb, %s::jsonb,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, now()
            )
            ON CONFLICT (company_key) DO UPDATE SET
                cnpj_raiz = EXCLUDED.cnpj_raiz,
                target_fit_class = EXCLUDED.target_fit_class,
                target_fit_confidence = EXCLUDED.target_fit_confidence,
                target_fit_version = EXCLUDED.target_fit_version,
                target_fit_reason_codes = EXCLUDED.target_fit_reason_codes,
                target_fit_evidence = EXCLUDED.target_fit_evidence,
                computed_at = EXCLUDED.computed_at,
                source_watermark = EXCLUDED.source_watermark,
                source_max_updated_at = EXCLUDED.source_max_updated_at,
                input_fingerprint = EXCLUDED.input_fingerprint,
                classifier_sha = EXCLUDED.classifier_sha,
                schema_version = EXCLUDED.schema_version,
                operational_status = EXCLUDED.operational_status,
                sector_fit = EXCLUDED.sector_fit,
                activity_class = EXCLUDED.activity_class,
                relevant_execution_contract_count = EXCLUDED.relevant_execution_contract_count,
                relevant_supply_only_count = EXCLUDED.relevant_supply_only_count,
                materialization_mode = EXCLUDED.materialization_mode,
                updated_at = now()
            """,
            (
                mat.company_key,
                mat.cnpj_raiz,
                mat.target_fit_class,
                mat.target_fit_confidence,
                mat.target_fit_version,
                _json(mat.target_fit_reason_codes),
                _json(mat.target_fit_evidence),
                mat.computed_at,
                mat.source_watermark,
                mat.source_max_updated_at,
                mat.input_fingerprint,
                mat.classifier_sha,
                mat.schema_version or STORE_SCHEMA_VERSION,
                mat.operational_status,
                mat.sector_fit,
                mat.activity_class,
                mat.relevant_execution_contract_count,
                mat.relevant_supply_only_count,
                mat.materialization_mode,
            ),
        )
        if event is not None and event.event_type not in {"TARGET_FIT_UNCHANGED", ""}:
            cur.execute(
                """
                INSERT INTO confenge_target_fit_events (
                    event_type, company_key, cnpj_raiz,
                    old_class, new_class, old_confidence, new_confidence,
                    reason_codes, changed_evidence_ids, source_watermark,
                    computed_at, target_fit_version, payload
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb, %s,
                    %s, %s, %s::jsonb
                )
                RETURNING id
                """,
                (
                    event.event_type,
                    event.company_key,
                    event.cnpj_raiz,
                    event.old_class,
                    event.new_class,
                    event.old_confidence,
                    event.new_confidence,
                    _json(event.reason_codes),
                    _json(event.changed_evidence_ids),
                    event.source_watermark,
                    event.computed_at,
                    event.target_fit_version,
                    _json(event.payload),
                ),
            )
            row = cur.fetchone()
            event_id = int(row["id"]) if row else None
    return event_id


def record_downstream_invalidation(
    conn: Any,
    *,
    company_key: str,
    cnpj_raiz: str,
    event_id: int | None,
    old_class: str | None,
    new_class: str | None,
    notes: str = "",
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO confenge_target_fit_downstream_invalidation (
                company_key, cnpj_raiz, event_id, invalidation_type,
                old_class, new_class, email_send_ready_revoked,
                activation_suppressed, notes
            ) VALUES (
                %s, %s, %s, 'TARGET_FIT_DOWNGRADE',
                %s, %s, TRUE, TRUE, %s
            )
            ON CONFLICT (company_key, event_id) DO NOTHING
            """,
            (company_key, cnpj_raiz, event_id, old_class, new_class, notes),
        )
        # Soft-suppress activation projection if table exists (fail-soft)
        try:
            cur.execute(
                """
                UPDATE confenge_activation_projections
                SET activation_state = 'SUPPRESSED',
                    reason_codes = COALESCE(reason_codes, '[]'::jsonb)
                        || '["TARGET_FIT_DOWNGRADE"]'::jsonb,
                    updated_at = now()
                WHERE cnpj14 LIKE %s || '%%'
                  AND activation_state IN ('ACTIONABLE_NOW', 'WATCH')
                """,
                (cnpj_raiz,),
            )
        except Exception:
            # Table may not exist in pure unit envs
            conn.rollback()
            # Re-open transaction context is caller's responsibility when this
            # is nested; callers run invalidation in same tx after publish.
            raise


def record_downstream_invalidation_soft(
    conn: Any,
    *,
    company_key: str,
    cnpj_raiz: str,
    event_id: int | None,
    old_class: str | None,
    new_class: str | None,
    notes: str = "",
) -> None:
    """Like record_downstream_invalidation but swallows missing activation table."""
    with conn.cursor() as cur:
        if event_id is not None:
            cur.execute(
                """
                INSERT INTO confenge_target_fit_downstream_invalidation (
                    company_key, cnpj_raiz, event_id, invalidation_type,
                    old_class, new_class, email_send_ready_revoked,
                    activation_suppressed, notes
                ) VALUES (
                    %s, %s, %s, 'TARGET_FIT_DOWNGRADE',
                    %s, %s, TRUE, TRUE, %s
                )
                ON CONFLICT (company_key, event_id) DO NOTHING
                """,
                (company_key, cnpj_raiz, event_id, old_class, new_class, notes),
            )
        else:
            cur.execute(
                """
                INSERT INTO confenge_target_fit_downstream_invalidation (
                    company_key, cnpj_raiz, event_id, invalidation_type,
                    old_class, new_class, email_send_ready_revoked,
                    activation_suppressed, notes
                ) VALUES (
                    %s, %s, NULL, 'TARGET_FIT_DOWNGRADE',
                    %s, %s, TRUE, TRUE, %s
                )
                """,
                (company_key, cnpj_raiz, old_class, new_class, notes),
            )
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='public' AND table_name='confenge_activation_projections'
            """
        )
        if cur.fetchone():
            cur.execute(
                """
                UPDATE confenge_activation_projections
                SET activation_state = 'SUPPRESSED',
                    reason_codes = COALESCE(reason_codes, '[]'::jsonb)
                        || '["TARGET_FIT_DOWNGRADE"]'::jsonb,
                    updated_at = now()
                WHERE left(cnpj14, 8) = %s
                  AND activation_state IN ('ACTIONABLE_NOW', 'WATCH')
                """,
                (cnpj_raiz,),
            )


def queue_counts(conn: Any) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, COUNT(*)::int AS n
            FROM confenge_target_fit_dirty
            GROUP BY status
            """
        )
        return {r["status"]: int(r["n"]) for r in (cur.fetchall() or [])}


def class_distribution(conn: Any) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT target_fit_class, COUNT(*)::int AS n
            FROM confenge_company_target_fit_current
            GROUP BY target_fit_class
            """
        )
        return {r["target_fit_class"]: int(r["n"]) for r in (cur.fetchall() or [])}


def oldest_dirty_age_seconds(conn: Any) -> float | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXTRACT(EPOCH FROM (now() - MIN(detected_at))) AS age
            FROM confenge_target_fit_dirty
            WHERE status IN ('pending', 'retry', 'processing')
            """
        )
        row = cur.fetchone()
        if not row or row["age"] is None:
            return None
        return float(row["age"])


def _is_iso_watermark(value: str) -> bool:
    if not value or value.startswith("wm-"):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def max_current_watermark(conn: Any) -> str:
    """Best parseable watermark from materialization tables + control plane.

    Ignores synthetic test watermarks (e.g. ``wm-b``) so status lag stays meaningful.
    """
    candidates: list[tuple[datetime, str]] = []
    with conn.cursor() as cur:
        for table, col in (
            ("confenge_company_target_fit_current", "source_watermark"),
            ("confenge_target_fit_shadow", "source_watermark"),
        ):
            try:
                cur.execute(
                    f"""
                    SELECT {col} AS wm, computed_at
                    FROM {table}
                    WHERE {col} IS NOT NULL AND {col} <> ''
                    ORDER BY computed_at DESC NULLS LAST
                    LIMIT 50
                    """
                )
                for row in cur.fetchall() or []:
                    wm = str(row["wm"] or "")
                    if not _is_iso_watermark(wm):
                        continue
                    try:
                        ts = datetime.fromisoformat(wm.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    candidates.append((ts, wm))
            except Exception:  # noqa: BLE001 — table may not exist mid-migration
                pass
        # Control plane CDC watermark
        cur.execute(
            "SELECT value FROM confenge_target_fit_control WHERE key = 'cdc_watermark'"
        )
        row = cur.fetchone()
        if row:
            val = row["value"]
            if isinstance(val, str):
                import json as _json

                try:
                    val = _json.loads(val)
                except Exception:  # noqa: BLE001
                    val = {}
            wm = str((val or {}).get("watermark") or "")
            if _is_iso_watermark(wm):
                try:
                    ts = datetime.fromisoformat(wm.replace("Z", "+00:00"))
                    candidates.append((ts, wm))
                except ValueError:
                    pass
        # Explicit target-fit progress watermark (written by worker)
        cur.execute(
            "SELECT value FROM confenge_target_fit_control WHERE key = 'target_fit_watermark'"
        )
        row = cur.fetchone()
        if row:
            val = row["value"]
            if isinstance(val, str):
                import json as _json

                try:
                    val = _json.loads(val)
                except Exception:  # noqa: BLE001
                    val = {}
            wm = str((val or {}).get("watermark") or "")
            if _is_iso_watermark(wm):
                try:
                    ts = datetime.fromisoformat(wm.replace("Z", "+00:00"))
                    candidates.append((ts, wm))
                except ValueError:
                    pass
    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def shadow_class_distribution(conn: Any) -> dict[str, int]:
    with conn.cursor() as cur:
        try:
            cur.execute(
                """
                SELECT shadow_class, COUNT(*)::int AS n
                FROM confenge_target_fit_shadow
                GROUP BY shadow_class
                """
            )
            return {r["shadow_class"]: int(r["n"]) for r in (cur.fetchall() or [])}
        except Exception:  # noqa: BLE001
            return {}


def set_target_fit_watermark(conn: Any, watermark: str) -> None:
    if not watermark:
        return
    set_control(
        conn,
        "target_fit_watermark",
        {
            "watermark": watermark,
            "updated_at": _utcnow().isoformat(),
        },
    )


def last_success_at(conn: Any) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT finished_at FROM confenge_target_fit_cycle_meta
            WHERE status = 'success'
            ORDER BY finished_at DESC NULLS LAST
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row or not row["finished_at"]:
            return None
        ts = row["finished_at"]
        return ts.isoformat() if hasattr(ts, "isoformat") else str(ts)


def start_cycle(
    conn: Any,
    *,
    cycle_id: str,
    cycle_kind: str,
    mode: str,
    target_fit_version: str,
    source_watermark: str = "",
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO confenge_target_fit_cycle_meta (
                cycle_id, cycle_kind, started_at, source_watermark,
                target_fit_version, mode, status
            ) VALUES (%s, %s, now(), %s, %s, %s, 'running')
            ON CONFLICT (cycle_id) DO NOTHING
            """,
            (cycle_id, cycle_kind, source_watermark, target_fit_version, mode),
        )


def finish_cycle(
    conn: Any,
    *,
    cycle_id: str,
    status: str,
    stats: dict[str, Any],
    error_message: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE confenge_target_fit_cycle_meta
            SET finished_at = now(),
                status = %s,
                stats = %s::jsonb,
                error_message = %s
            WHERE cycle_id = %s
            """,
            (status, json.dumps(stats), error_message, cycle_id),
        )


def history_for_company(conn: Any, company_key: str, *, limit: int = 20) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM confenge_company_target_fit_history
            WHERE company_key = %s
            ORDER BY computed_at DESC
            LIMIT %s
            """,
            (company_key, limit),
        )
        return [dict(r) for r in (cur.fetchall() or [])]


def is_send_suppressed(conn: Any, company_key: str) -> bool:
    """True if a TARGET_FIT_DOWNGRADE invalidation is active and class not reconfirmed."""
    current = get_current(conn, company_key)
    if not current:
        return False
    if current.get("target_fit_class") == "TARGET_CONFIRMED":
        # reconfirmed after downgrade — allow other gates to re-evaluate
        return False
    if current.get("operational_status") in {"refresh_failed", "stale", "recompute_required"}:
        return True
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM confenge_target_fit_downstream_invalidation
            WHERE company_key = %s
            ORDER BY applied_at DESC
            LIMIT 1
            """,
            (company_key,),
        )
        if cur.fetchone() and current.get("target_fit_class") != "TARGET_CONFIRMED":
            return True
    return False


def _row_to_dirty(r: dict[str, Any]) -> DirtyItem:
    return DirtyItem(
        id=int(r["id"]),
        company_key=r["company_key"],
        cnpj_raiz=str(r["cnpj_raiz"]),
        reason=r["reason"],
        source_entity=r.get("source_entity") or "",
        source_id=r.get("source_id"),
        source_updated_at=r.get("source_updated_at"),
        source_watermark=r.get("source_watermark") or "",
        priority=int(r.get("priority") or 50),
        status=r["status"],
        attempt_count=int(r.get("attempt_count") or 0),
        next_retry_at=r.get("next_retry_at"),
        last_error=r.get("last_error"),
        idempotency_key=r["idempotency_key"],
        input_fingerprint=r.get("input_fingerprint"),
    )


# Export status constants used by worker
__all__ = [
    "STATUS_DEAD",
    "STATUS_DONE",
    "STATUS_PENDING",
    "STATUS_PROCESSING",
    "STATUS_REFRESH_FAILED",
    "STATUS_RETRY",
    "STATUS_SKIPPED",
    "claim_batch",
    "class_distribution",
    "enqueue_dirty",
    "ensure_control_defaults",
    "finish_cycle",
    "get_control",
    "get_current",
    "history_for_company",
    "is_send_suppressed",
    "last_success_at",
    "list_stale_versions",
    "mark_dirty_done",
    "max_current_watermark",
    "oldest_dirty_age_seconds",
    "publish_materialization",
    "queue_counts",
    "reclaim_expired_locks",
    "record_downstream_invalidation_soft",
    "requeue_company",
    "set_control",
    "start_cycle",
]
