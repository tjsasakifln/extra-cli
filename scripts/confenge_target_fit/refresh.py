"""Fast path: CDC enqueue after datalake cycle + optional immediate worker drain."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from scripts.confenge_target_fit import TARGET_FIT_VERSION
from scripts.confenge_target_fit.cdc import enqueue_version_backfill, run_cdc_enqueue
from scripts.confenge_target_fit.config import TargetFitRefreshConfig
from scripts.confenge_target_fit.db import connect
from scripts.confenge_target_fit.models import CycleStats
from scripts.confenge_target_fit.store import finish_cycle, start_cycle
from scripts.confenge_target_fit.worker import run_worker_cycle

logger = logging.getLogger(__name__)


def run_refresh(
    dsn: str,
    *,
    cfg: TargetFitRefreshConfig | None = None,
    drain_worker: bool = True,
    max_worker_batches: int = 5,
) -> CycleStats:
    """Detect dirty companies from datalake watermark, enqueue, optionally drain."""
    cfg = cfg or TargetFitRefreshConfig.from_env()
    cycle_id = (
        f"refresh-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid.uuid4().hex[:6]}"
    )
    stats = CycleStats(
        cycle_id=cycle_id,
        cycle_kind="refresh",
        mode=cfg.async_mode,
        target_fit_version=TARGET_FIT_VERSION,
    )
    conn = connect(dsn, readonly=False)
    try:
        start_cycle(
            conn,
            cycle_id=cycle_id,
            cycle_kind="refresh",
            mode=cfg.async_mode,
            target_fit_version=TARGET_FIT_VERSION,
        )
        cdc = run_cdc_enqueue(
            conn,
            lookback_minutes=cfg.cdc_lookback_minutes,
            max_companies=cfg.cdc_max_companies_per_cycle,
        )
        backfill = enqueue_version_backfill(
            conn,
            current_version=TARGET_FIT_VERSION,
            limit=min(200, cfg.batch_size * 2),
        )
        stats.dirty_enqueued = int(cdc.get("enqueued") or 0) + backfill
        stats.source_watermark = str(cdc.get("watermark") or "")
        payload = stats.as_dict()
        payload["cdc"] = cdc
        payload["version_backfill"] = backfill
        finish_cycle(conn, cycle_id=cycle_id, status="success", stats=payload)
        conn.commit()
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

    if drain_worker and stats.dirty_enqueued:
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
        stats.transitions = w.transitions
        stats.processing_latency_ms_total = w.processing_latency_ms_total

    logger.info(
        "refresh done enqueued=%s processed=%s up=%s down=%s",
        stats.dirty_enqueued,
        stats.processed,
        stats.upgrades,
        stats.downgrades,
    )
    return stats
