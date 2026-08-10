"""Operational healthcheck for target-fit continuous refresh."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from scripts.confenge_target_fit import (
    HEALTH_DEGRADED,
    HEALTH_FAILED,
    HEALTH_HEALTHY,
    HEALTH_STALE,
    TARGET_CONFIRMED,
    TARGET_FIT_VERSION,
    TARGET_OUT_OF_SCOPE,
    TARGET_PROBABLE_RESEARCH,
)
from scripts.confenge_target_fit.cdc import datalake_max_ingested_at, watermark_str
from scripts.confenge_target_fit.config import TargetFitRefreshConfig
from scripts.confenge_target_fit.db import connect
from scripts.confenge_target_fit.models import HealthReport
from scripts.confenge_target_fit.store import (
    class_distribution,
    ensure_control_defaults,
    get_control,
    last_success_at,
    max_current_watermark,
    oldest_dirty_age_seconds,
    queue_counts,
)


def build_health(
    dsn: str,
    *,
    cfg: TargetFitRefreshConfig | None = None,
) -> HealthReport:
    cfg = cfg or TargetFitRefreshConfig.from_env()
    conn = connect(dsn, readonly=False)
    try:
        ensure_control_defaults(conn)
        conn.commit()
        q = queue_counts(conn)
        dist = class_distribution(conn)
        cdc = get_control(conn, "cdc_watermark")
        auto = get_control(conn, "auto_pause")
        mode_ctrl = get_control(conn, "async_mode")
        mode = str(mode_ctrl.get("mode") or cfg.async_mode).upper()

        dl_ts = datalake_max_ingested_at(conn)
        dl_wm = watermark_str(dl_ts) or str(cdc.get("watermark") or "")
        tf_wm = max_current_watermark(conn) or str(cdc.get("watermark") or "")

        lag: float | None = None
        try:
            if dl_wm and tf_wm:
                d1 = datetime.fromisoformat(dl_wm.replace("Z", "+00:00"))
                d2 = datetime.fromisoformat(tf_wm.replace("Z", "+00:00"))
                lag = (d1 - d2).total_seconds()
        except ValueError:
            lag = None

        dirty = int(q.get("pending", 0)) + int(q.get("retry", 0))
        processing = int(q.get("processing", 0))
        retry = int(q.get("retry", 0))
        dead = int(q.get("dead", 0))
        oldest = oldest_dirty_age_seconds(conn)
        last_ok = last_success_at(conn)

        status = HEALTH_HEALTHY
        if auto.get("paused") or mode == "AUTO_PAUSE":
            status = HEALTH_FAILED
        elif dead > 0 and dirty > cfg.batch_size * 10:
            status = HEALTH_FAILED
        elif lag is not None and lag > cfg.max_watermark_lag_seconds:
            status = HEALTH_STALE
        elif oldest is not None and oldest > cfg.reclass_slo_minutes * 60 * 2:
            status = HEALTH_DEGRADED
        elif dirty > cfg.cdc_max_companies_per_cycle:
            status = HEALTH_DEGRADED
        elif last_ok is None and sum(dist.values()) == 0:
            status = HEALTH_DEGRADED

        return HealthReport(
            status=status,
            datalake_watermark=dl_wm,
            target_fit_watermark=tf_wm,
            lag_seconds=lag,
            dirty=dirty,
            processing=processing,
            retry=retry,
            dead=dead,
            current_version=TARGET_FIT_VERSION,
            confirmed=int(dist.get(TARGET_CONFIRMED, 0)),
            probable=int(dist.get(TARGET_PROBABLE_RESEARCH, 0)),
            out=int(dist.get(TARGET_OUT_OF_SCOPE, 0)),
            last_success=last_ok,
            async_mode=mode,
            auto_paused=bool(auto.get("paused")),
            details={
                "queue": q,
                "distribution": dist,
                "oldest_dirty_age_seconds": oldest,
                "slo_minutes": cfg.reclass_slo_minutes,
                "as_of": datetime.now(UTC).isoformat(),
            },
        )
    finally:
        conn.close()


def exit_code_for(report: HealthReport) -> int:
    if report.status in {HEALTH_FAILED, HEALTH_STALE}:
        return 2
    if report.status == HEALTH_DEGRADED:
        return 1
    return 0


def metrics_snapshot(dsn: str) -> dict[str, Any]:
    report = build_health(dsn)
    return {
        "dirty_queue_depth": report.dirty,
        "dirty_oldest_age": report.details.get("oldest_dirty_age_seconds"),
        "watermark_lag": report.lag_seconds,
        "target_fit_distribution": {
            "CONFIRMED": report.confirmed,
            "PROBABLE": report.probable,
            "OUT": report.out,
        },
        "classifier_version": report.current_version,
        "async_mode": report.async_mode,
        "status": report.status,
        "dead_letter_total": report.dead,
        "retry_total": report.retry,
        "processing": report.processing,
    }
