"""Reconciliation path — full sweep without always recomputing.

Detects missed CDC events, drift, orphan records, incomplete version
propagation. Cheap when fingerprints match.
"""

# ruff: noqa: S608  # dynamic SQL over allowlisted table/column identifiers
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from scripts.confenge_target_fit import TARGET_FIT_VERSION
from scripts.confenge_target_fit.cdc import priority_for_reason, watermark_str
from scripts.confenge_target_fit.company_key import company_key_from_raiz, digits_only
from scripts.confenge_target_fit.config import TargetFitRefreshConfig
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
    """Distinct CNPJ roots present in supplier contracts (keyset-friendly pages)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='pncp_supplier_contracts'
            """
        )
        cols = {r["column_name"] for r in (cur.fetchall() or [])}
        cnpj_col = (
            "fornecedor_cnpj"
            if "fornecedor_cnpj" in cols
            else ("ni_fornecedor" if "ni_fornecedor" in cols else None)
        )
        if not cnpj_col:
            return []

        roots: list[str] = []
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


def run_reconcile(
    dsn: str,
    *,
    cfg: TargetFitRefreshConfig | None = None,
    max_enqueue: int | None = None,
) -> CycleStats:
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
        ctrl = get_control(conn, "cdc_watermark")
        wm = str(ctrl.get("watermark") or watermark_str(_utcnow()))
        stats.source_watermark = wm
        start_cycle(
            conn,
            cycle_id=cycle_id,
            cycle_kind="reconcile",
            mode=cfg.async_mode,
            target_fit_version=TARGET_FIT_VERSION,
            source_watermark=wm,
        )
        conn.commit()

        roots = iter_universe_roots(conn, page_size=cfg.reconcile_page_size)
        # Load current materialization set
        with conn.cursor() as cur:
            cur.execute(
                "SELECT company_key, cnpj_raiz, target_fit_version, input_fingerprint, "
                "operational_status FROM confenge_company_target_fit_current"
            )
            current_rows = {r["company_key"]: dict(r) for r in (cur.fetchall() or [])}

        missing = 0
        version_stale = 0
        enqueued = 0
        limit = max_enqueue if max_enqueue is not None else len(roots)

        for raiz in roots:
            if enqueued >= limit:
                break
            ck = company_key_from_raiz(raiz)
            cur_row = current_rows.get(ck)
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
            idem = "reconcile:" + hashlib.sha256(
                f"{ck}|{wm}|{reason}|{TARGET_FIT_VERSION}".encode()
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
        for ck, row in current_rows.items():
            r = digits_only(row.get("cnpj_raiz"))[:8]
            if r and r not in root_set:
                orphan += 1

        stats.dirty_enqueued = enqueued
        payload = stats.as_dict()
        payload.update(
            {
                "universe_roots": len(roots),
                "materialized": len(current_rows),
                "missing": missing,
                "version_stale": version_stale,
                "orphans": orphan,
            }
        )
        finish_cycle(conn, cycle_id=cycle_id, status="success", stats=payload)
        conn.commit()
        logger.info(
            "reconcile done roots=%s missing=%s version_stale=%s enqueued=%s orphans=%s",
            len(roots),
            missing,
            version_stale,
            enqueued,
            orphan,
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
    return stats
