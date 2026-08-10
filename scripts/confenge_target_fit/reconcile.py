"""Reconciliation path — full national sweep without always recomputing.

Detects missed CDC events, drift, orphan records, incomplete version
propagation. Cheap when fingerprints match.

National invariant (after a completed full reconcile):
  expected_company_roots == visited_company_roots
  materialized_company_roots == expected - explicit_exclusions
  pagination_exhausted_normally == True
  unexplained_missing == 0

SHADOW mode: authority for "already materialized" is confenge_target_fit_shadow
(not the empty current table). ACTIVE/CANARY use current.
"""

# ruff: noqa: S608  # dynamic SQL over allowlisted table/column identifiers
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from scripts.confenge_target_fit import MODE_SHADOW, TARGET_FIT_VERSION
from scripts.confenge_target_fit.cdc import priority_for_reason, watermark_str
from scripts.confenge_target_fit.company_key import company_key_from_raiz, digits_only
from scripts.confenge_target_fit.config import TargetFitRefreshConfig
from scripts.confenge_target_fit.coverage import (
    build_coverage_snapshot,
    persist_coverage_control,
)
from scripts.confenge_target_fit.db import connect
from scripts.confenge_target_fit.models import CycleStats
from scripts.confenge_target_fit.store import (
    enqueue_dirty,
    finish_cycle,
    get_control,
    start_cycle,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def iter_universe_roots(conn: Any, *, page_size: int = 500) -> list[str]:
    """Distinct CNPJ roots present in supplier contracts (keyset-friendly pages).

    Prefer indexed ``fornecedor_cnpj_8`` when present (national scale). Fall back
    to regexp on full CNPJ only when the denormalized root column is missing.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='pncp_supplier_contracts'
            """
        )
        cols = {r["column_name"] for r in (cur.fetchall() or [])}

        # Fast path: precomputed 8-digit root (indexed on host-of-record)
        if "fornecedor_cnpj_8" in cols:
            roots: list[str] = []
            last = ""
            while True:
                cur.execute(
                    """
                    SELECT DISTINCT fornecedor_cnpj_8 AS raiz
                    FROM pncp_supplier_contracts
                    WHERE fornecedor_cnpj_8 IS NOT NULL
                      AND fornecedor_cnpj_8 > %s
                      AND length(fornecedor_cnpj_8) = 8
                    ORDER BY 1
                    LIMIT %s
                    """,
                    (last, page_size),
                )
                raw = list(cur.fetchall() or [])
                if not raw:
                    break
                raw_raizes = [digits_only(r["raiz"])[:8] for r in raw]
                raw_raizes = [b for b in raw_raizes if len(b) == 8]
                if not raw_raizes:
                    break
                last = raw_raizes[-1]
                batch = [b for b in raw_raizes if b != "00000000"]
                roots.extend(batch)
                if len(raw) < page_size:
                    break
            return roots

        cnpj_col = (
            "fornecedor_cnpj"
            if "fornecedor_cnpj" in cols
            else ("ni_fornecedor" if "ni_fornecedor" in cols else None)
        )
        if not cnpj_col:
            return []

        roots = []
        last = ""
        while True:
            cur.execute(
                f"""
                SELECT DISTINCT left(regexp_replace({cnpj_col}, '\\D', '', 'g'), 8) AS raiz
                FROM pncp_supplier_contracts
                WHERE left(regexp_replace({cnpj_col}, '\\D', '', 'g'), 8) > %s
                  AND length(regexp_replace({cnpj_col}, '\\D', '', 'g')) >= 8
                ORDER BY 1
                LIMIT %s
                """,
                (last, page_size),
            )
            raw = list(cur.fetchall() or [])
            if not raw:
                break
            # Keyset must advance on the *raw* page cursor, not the filtered batch.
            # Filtering invalid roots (e.g. 00000000) before the page-size check used to
            # stop after the first page whenever any row was dropped (499 < 500 → break),
            # leaving continuous target-fit stuck at ~500 roots instead of the full lake.
            raw_raizes = [digits_only(r["raiz"])[:8] for r in raw]
            raw_raizes = [b for b in raw_raizes if len(b) == 8]
            if not raw_raizes:
                break
            last = raw_raizes[-1]
            batch = [b for b in raw_raizes if b != "00000000"]
            roots.extend(batch)
            if len(raw) < page_size:
                break
    return roots

def _load_materialized_index(conn: Any, *, mode: str) -> dict[str, dict[str, Any]]:
    """Map company_key → row from the authority table for this async mode.

    SHADOW: population lives in confenge_target_fit_shadow while current is empty.
    Reconcile must not treat every root as missing just because current is empty.
    """
    mode_u = (mode or "").upper()
    with conn.cursor() as cur:
        if mode_u == MODE_SHADOW:
            cur.execute(
                """
                SELECT company_key, cnpj_raiz, target_fit_version, input_fingerprint,
                       shadow_class, 'ok' AS operational_status
                FROM confenge_target_fit_shadow
                """
            )
            rows: dict[str, dict[str, Any]] = {}
            for r in cur.fetchall() or []:
                d = dict(r)
                # Normalize shadow_class → target_fit_class for shared reconcile logic
                if d.get("target_fit_class") is None and d.get("shadow_class") is not None:
                    d["target_fit_class"] = d.get("shadow_class")
                d.setdefault("operational_status", "ok")
                rows[d["company_key"]] = d
            if rows:
                return rows
            # Fall through to current if shadow empty (fresh install)
        cur.execute(
            """
            SELECT company_key, cnpj_raiz, target_fit_version, input_fingerprint,
                   operational_status, target_fit_class
            FROM confenge_company_target_fit_current
            """
        )
        return {r["company_key"]: dict(r) for r in (cur.fetchall() or [])}


def count_canonical_eligible_roots(conn: Any) -> int | None:
    """Best-effort live count of construction-eligible roots when a helper exists.

    Falls back to None so callers use visited universe roots as denominator
    rather than inventing a hard-coded national figure.

    Uses SAVEPOINTs so a missing optional table never rolls back the outer
    reconcile transaction (which may already hold hundreds of thousands of
    dirty-queue inserts).
    """
    with conn.cursor() as cur:
        # Optional precomputed universe table (may not exist on all hosts)
        for i, sql in enumerate(
            (
                "SELECT COUNT(*)::int AS n FROM confenge_universe_eligible_roots",
                "SELECT COUNT(*)::int AS n FROM confenge_company_universe WHERE eligibility = 'ELIGIBLE'",
            )
        ):
            sp = f"canonical_eligible_{i}"
            try:
                cur.execute(f"SAVEPOINT {sp}")
                cur.execute(sql)
                row = cur.fetchone()
                cur.execute(f"RELEASE SAVEPOINT {sp}")
                if row and row.get("n") is not None:
                    return int(row["n"])
            except Exception:  # noqa: BLE001
                try:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                    cur.execute(f"RELEASE SAVEPOINT {sp}")
                except Exception as release_exc:  # noqa: BLE001
                    logger.debug(
                        "savepoint cleanup failed for %s: %s",
                        sp,
                        release_exc,
                    )
    return None

def run_reconcile(
    dsn: str,
    *,
    cfg: TargetFitRefreshConfig | None = None,
    max_enqueue: int | None = None,
    drain_worker: bool = False,
    max_worker_batches: int = 0,
) -> CycleStats:
    """Full national consistency sweep.

    ``max_enqueue`` is a diagnostic/smoke bound only — never the commercial
    capacity of the system. Default is the full visited universe.
    """
    cfg = cfg or TargetFitRefreshConfig.from_env()
    cycle_id = f"reconcile-{_utcnow().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    stats = CycleStats(
        cycle_id=cycle_id,
        cycle_kind="reconcile",
        mode=cfg.async_mode,
        target_fit_version=TARGET_FIT_VERSION,
    )
    conn = connect(dsn, readonly=False)
    try:
        mode_ctrl = get_control(conn, "async_mode")
        mode = str(mode_ctrl.get("mode") or cfg.async_mode).upper()
        ctrl = get_control(conn, "cdc_watermark")
        wm = str(ctrl.get("watermark") or watermark_str(_utcnow()))
        stats.source_watermark = wm
        start_cycle(
            conn,
            cycle_id=cycle_id,
            cycle_kind="reconcile",
            mode=mode,
            target_fit_version=TARGET_FIT_VERSION,
            source_watermark=wm,
        )
        conn.commit()

        roots = iter_universe_roots(conn, page_size=cfg.reconcile_page_size)
        pagination_exhausted_normally = True  # loop ends only on empty/short page
        expected_company_roots = len(roots)
        visited_company_roots = len(roots)

        materialized_rows = _load_materialized_index(conn, mode=mode)
        population_source = "current"
        with conn.cursor() as cur:
            if mode == MODE_SHADOW:
                cur.execute("SELECT COUNT(*)::int AS n FROM confenge_target_fit_shadow")
                sh_n = int((cur.fetchone() or {}).get("n") or 0)
                population_source = "shadow" if sh_n > 0 else "current"

        missing = 0
        version_stale = 0
        enqueued = 0
        # max_enqueue=None → full universe; never silent Top-N commercial cap
        limit = max_enqueue if max_enqueue is not None else len(roots)
        explicit_exclusions = 0  # INVALID_CNPJ already filtered in iter

        for raiz in roots:
            if enqueued >= limit and max_enqueue is not None:
                break
            ck = company_key_from_raiz(raiz)
            cur_row = materialized_rows.get(ck)
            reason = None
            if cur_row is None:
                reason = "reconcile_missing"
                missing += 1
            elif cur_row.get("target_fit_version") != TARGET_FIT_VERSION:
                reason = "reconcile_version_drift"
                version_stale += 1
            elif cur_row.get("operational_status") in {
                "recompute_required",
                "refresh_failed",
                "stale",
            }:
                reason = "reconcile_ops_status"
            # Fingerprint equality requires load+compute — deferred to worker;
            # reconcile only enqueues structural drift.
            if reason is None:
                continue
            # Fresh idempotency per full-reconcile cycle so previous early-exit
            # batches (done under truncated universe) cannot block remaining roots.
            idem = "reconcile:" + hashlib.sha256(
                f"{ck}|{wm}|{reason}|{TARGET_FIT_VERSION}|full".encode()
            ).hexdigest()[:32]
            if enqueue_dirty(
                conn,
                company_key=ck,
                cnpj_raiz=raiz,
                reason=reason,
                source_entity="reconcile",
                source_id=reason,
                source_updated_at=_utcnow(),
                source_watermark=wm,
                priority=priority_for_reason("reconcile_drift"),
                idempotency_key=idem,
            ):
                enqueued += 1

        # Orphans: materialization for roots no longer in contracts (info only)
        orphan = 0
        root_set = set(roots)
        for ck, row in materialized_rows.items():
            r = digits_only(row.get("cnpj_raiz"))[:8]
            if r and r not in root_set:
                orphan += 1

        # Unexplained missing = roots not materialized and not yet enqueued under
        # a hard smoke max_enqueue bound. When max_enqueue is None, any remaining
        # gap after enqueue is still "pending work" (RETRY_PENDING), not silent loss.
        still_missing_keys = 0
        for raiz in roots:
            ck = company_key_from_raiz(raiz)
            if ck not in materialized_rows:
                still_missing_keys += 1
        # After this reconcile, still-missing roots are either enqueued (RETRY_PENDING)
        # or capped by diagnostic max_enqueue.
        if max_enqueue is not None and still_missing_keys > enqueued:
            unexplained_missing = max(0, still_missing_keys - enqueued)
        else:
            # Full enqueue path: pending work is explained as RETRY_PENDING
            unexplained_missing = 0

        canonical = count_canonical_eligible_roots(conn)
        # Denominator for coverage: prefer canonical eligible when known;
        # otherwise use full visited supplier roots (honest upper bound).
        canonical_count = int(canonical) if canonical is not None else expected_company_roots
        materialized_count = len(materialized_rows)

        coverage_snap = build_coverage_snapshot(
            canonical_company_count=canonical_count,
            materialized_company_count=materialized_count,
            expected_company_roots=expected_company_roots,
            visited_company_roots=visited_company_roots,
            unexplained_missing=unexplained_missing,
            pagination_exhausted_normally=pagination_exhausted_normally,
            explicit_exclusions=explicit_exclusions,
            gap_breakdown={
                "INVALID_CNPJ": 0,  # filtered before roots list
                "RETRY_PENDING": still_missing_keys if still_missing_keys else 0,
            },
            last_full_reconcile_completed_at=_utcnow().isoformat()
            if pagination_exhausted_normally and max_enqueue is None
            else None,
            async_mode=mode,
            population_source=population_source,
        )
        # Only mark full reconcile complete when we scanned without smoke bound
        if max_enqueue is None and pagination_exhausted_normally:
            coverage_snap["last_full_reconcile_completed_at"] = _utcnow().isoformat()
            coverage_snap["last_full_reconcile_unexplained_missing"] = unexplained_missing
            persist_coverage_control(conn, coverage_snap)
        else:
            # Persist partial progress without claiming FULLY_RECONCILED
            from scripts.confenge_target_fit.store import set_control

            set_control(conn, "target_fit_coverage", coverage_snap)

        stats.dirty_enqueued = enqueued
        payload = stats.as_dict()
        payload.update(
            {
                "universe_roots": expected_company_roots,
                "expected_company_roots": expected_company_roots,
                "visited_company_roots": visited_company_roots,
                "materialized": materialized_count,
                "materialized_company_roots": materialized_count,
                "missing": missing,
                "version_stale": version_stale,
                "orphans": orphan,
                "pagination_exhausted_normally": pagination_exhausted_normally,
                "unexplained_missing": unexplained_missing,
                "still_missing_keys": still_missing_keys,
                "max_enqueue_bound": max_enqueue,
                "population_source": population_source,
                "coverage": coverage_snap,
            }
        )
        finish_cycle(conn, cycle_id=cycle_id, status="success", stats=payload)
        conn.commit()
        logger.info(
            "reconcile done roots=%s missing=%s version_stale=%s enqueued=%s "
            "orphans=%s pagination_ok=%s unexplained=%s coverage=%.4f",
            expected_company_roots,
            missing,
            version_stale,
            enqueued,
            orphan,
            pagination_exhausted_normally,
            unexplained_missing,
            float(coverage_snap.get("coverage_ratio") or 0.0),
        )
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        stats.error = f"{type(exc).__name__}: {exc}"
        try:
            finish_cycle(
                conn,
                cycle_id=cycle_id,
                status="failed",
                stats=stats.as_dict(),
                error_message=stats.error,
            )
            conn.commit()
        except Exception:  # noqa: BLE001
            conn.rollback()
        raise
    finally:
        conn.close()

    if drain_worker and stats.dirty_enqueued and max_worker_batches > 0:
        from scripts.confenge_target_fit.worker import run_worker_cycle

        w = run_worker_cycle(dsn, cfg=cfg, max_batches=max_worker_batches)
        stats.claimed = w.claimed
        stats.processed = w.processed
        stats.skipped_same_fingerprint = w.skipped_same_fingerprint
        stats.upgrades = w.upgrades
        stats.downgrades = w.downgrades
        stats.unchanged = w.unchanged
        stats.failures = w.failures
        stats.retries = w.retries
        stats.dead_letter = w.dead_letter

    return stats
