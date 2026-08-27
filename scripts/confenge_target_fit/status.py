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
    TARGET_INSUFFICIENT_EVIDENCE,
    TARGET_OUT_OF_SCOPE,
    TARGET_PROBABLE_RESEARCH,
)
from scripts.confenge_target_fit.cdc import datalake_max_ingested_at, watermark_str
from scripts.confenge_target_fit.config import TargetFitRefreshConfig
from scripts.confenge_target_fit.coverage import (
    classify_coverage_mode,
    coverage_ratio,
    load_coverage_control,
)
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
    shadow_class_distribution,
)


def dirty_progress_stale(oldest_age_seconds: float | None, *, slo_minutes: int) -> bool:
    """A dirty queue crossing its configured SLO is already degraded."""
    return bool(
        oldest_age_seconds is not None
        and oldest_age_seconds > max(0, int(slo_minutes)) * 60
    )


def target_fit_progress_watermark(
    *,
    control_watermark: object,
    materialized_watermark: object,
) -> str:
    """Resolve only watermarks proven by target-fit, never the CDC cursor."""
    return str(control_watermark or materialized_watermark or "")


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
        tf_ctrl = get_control(conn, "target_fit_watermark")
        tf_wm = target_fit_progress_watermark(
            control_watermark=tf_ctrl.get("watermark"),
            materialized_watermark=max_current_watermark(conn),
        )

        lag: float | None = None
        try:
            if dl_wm and tf_wm:
                d1 = datetime.fromisoformat(dl_wm.replace("Z", "+00:00"))
                d2 = datetime.fromisoformat(tf_wm.replace("Z", "+00:00"))
                # Watermark lag = how far target-fit trails the datalake.
                # If TF watermark is ahead (clock/sample artifacts), report 0 not negative.
                lag = max(0.0, (d1 - d2).total_seconds())
        except ValueError:
            lag = None

        dirty = int(q.get("pending", 0)) + int(q.get("retry", 0))
        processing = int(q.get("processing", 0))
        retry = int(q.get("retry", 0))
        dead = int(q.get("dead", 0))
        oldest = oldest_dirty_age_seconds(conn)
        last_ok = last_success_at(conn)
        shadow_dist = shadow_class_distribution(conn)

        # In SHADOW, live population is shadow table; current may be empty/stale.
        if mode == "SHADOW" and sum(shadow_dist.values()) > 0:
            confirmed = int(shadow_dist.get(TARGET_CONFIRMED, 0))
            probable = int(shadow_dist.get(TARGET_PROBABLE_RESEARCH, 0))
            out = int(shadow_dist.get(TARGET_OUT_OF_SCOPE, 0))
            insufficient = int(shadow_dist.get(TARGET_INSUFFICIENT_EVIDENCE, 0))
            pop_source = "shadow"
        else:
            confirmed = int(dist.get(TARGET_CONFIRMED, 0))
            probable = int(dist.get(TARGET_PROBABLE_RESEARCH, 0))
            out = int(dist.get(TARGET_OUT_OF_SCOPE, 0))
            insufficient = int(dist.get(TARGET_INSUFFICIENT_EVIDENCE, 0))
            pop_source = "current"

        status = HEALTH_HEALTHY
        if auto.get("paused") or mode == "AUTO_PAUSE":
            status = HEALTH_FAILED
        elif dead > 0 and dirty > cfg.batch_size * 10:
            status = HEALTH_FAILED
        elif lag is not None and lag > cfg.max_watermark_lag_seconds:
            status = HEALTH_STALE
        elif dirty_progress_stale(oldest, slo_minutes=cfg.reclass_slo_minutes):
            status = HEALTH_DEGRADED
        elif dirty > cfg.cdc_max_companies_per_cycle:
            status = HEALTH_DEGRADED
        elif last_ok is None and confirmed + probable + out + insufficient == 0:
            status = HEALTH_DEGRADED

        materialized = confirmed + probable + out + insufficient
        cov_ctrl = load_coverage_control(conn)
        canonical = int(cov_ctrl.get("canonical_company_count") or 0)
        # Prefer live population as numerator; fall back to stored snapshot
        mat_count = materialized or int(cov_ctrl.get("materialized_company_count") or 0)
        if canonical <= 0:
            canonical = int(cov_ctrl.get("expected_company_roots") or 0) or mat_count
        # Clamp coverage to [0,1]; overcount must never report ratio > 1
        ratio = coverage_ratio(
            materialized_company_count=min(mat_count, canonical) if canonical > 0 else mat_count,
            canonical_company_count=canonical,
            clamp=True,
        )
        last_full = cov_ctrl.get("last_full_reconcile_completed_at")
        unexplained = int(
            cov_ctrl.get("last_full_reconcile_unexplained_missing")
            if cov_ctrl.get("last_full_reconcile_unexplained_missing") is not None
            else cov_ctrl.get("unexplained_missing")
            or 0
        )
        pagination_ok = bool(cov_ctrl.get("pagination_exhausted_normally", False))
        coverage_mode = classify_coverage_mode(
            coverage=ratio,
            last_full_reconcile_completed_at=str(last_full) if last_full else None,
            unexplained_missing=unexplained,
            pagination_exhausted_normally=pagination_ok,
            auto_paused=bool(auto.get("paused")),
            dead=dead,
            lag_seconds=lag,
            max_lag_seconds=float(cfg.max_watermark_lag_seconds),
        )
        # Worker can be HEALTHY while only 2% of the national reservoir is populated.
        # Surface that honestly — never equate HEALTHY with FULL_NATIONAL_READY.
        coverage_payload = {
            "canonical_company_count": canonical,
            "materialized_company_count": mat_count,
            "coverage_ratio": ratio,
            "last_full_reconcile_completed_at": last_full,
            "last_full_reconcile_unexplained_missing": unexplained,
            "pagination_exhausted_normally": pagination_ok,
            "coverage_mode": coverage_mode,
            "FULL_NATIONAL_READY": coverage_mode == "FULLY_RECONCILED"
            and unexplained == 0
            and pagination_ok,
            "population_source": pop_source,
        }

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
            confirmed=confirmed,
            probable=probable,
            out=out,
            last_success=last_ok,
            async_mode=mode,
            auto_paused=bool(auto.get("paused")),
            insufficient=insufficient,
            details={
                "queue": q,
                "distribution_current": dist,
                "distribution_shadow": shadow_dist,
                "population_source": pop_source,
                "oldest_dirty_age_seconds": oldest,
                "slo_minutes": cfg.reclass_slo_minutes,
                "as_of": datetime.now(UTC).isoformat(),
                "coverage": coverage_payload,
                "INSUFFICIENT_EVIDENCE": insufficient,
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
    cov = (report.details or {}).get("coverage") or {}
    return {
        "dirty_queue_depth": report.dirty,
        "dirty_oldest_age": report.details.get("oldest_dirty_age_seconds"),
        "watermark_lag": report.lag_seconds,
        "target_fit_distribution": {
            "CONFIRMED": report.confirmed,
            "PROBABLE": report.probable,
            "OUT": report.out,
            "INSUFFICIENT_EVIDENCE": report.insufficient,
        },
        "classifier_version": report.current_version,
        "async_mode": report.async_mode,
        "status": report.status,
        "dead_letter_total": report.dead,
        "retry_total": report.retry,
        "processing": report.processing,
        "coverage_ratio": cov.get("coverage_ratio"),
        "coverage_mode": cov.get("coverage_mode"),
        "canonical_company_count": cov.get("canonical_company_count"),
        "materialized_company_count": cov.get("materialized_company_count"),
        "last_full_reconcile_completed_at": cov.get("last_full_reconcile_completed_at"),
        "last_full_reconcile_unexplained_missing": cov.get(
            "last_full_reconcile_unexplained_missing"
        ),
        "FULL_NATIONAL_READY": cov.get("FULL_NATIONAL_READY"),
    }
