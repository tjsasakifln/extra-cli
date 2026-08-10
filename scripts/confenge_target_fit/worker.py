"""Async worker: claim dirty companies → recompute → atomic publish.

Backpressure via batch_size. Single-writer per company via SKIP LOCKED + TTL.
Never rolls back datalake on failure.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from scripts.confenge_target_fit import (
    MODE_AUTO_PAUSE,
    MODE_SHADOW,
    STATUS_DEAD,
    STATUS_DONE,
    STATUS_REFRESH_FAILED,
    STATUS_RETRY,
    STATUS_SKIPPED,
    TARGET_FIT_VERSION,
)
from scripts.confenge_target_fit.company_key import canary_bucket
from scripts.confenge_target_fit.compute import compute_materialization, should_apply_active
from scripts.confenge_target_fit.config import TargetFitRefreshConfig
from scripts.confenge_target_fit.db import connect
from scripts.confenge_target_fit.loader import load_company_input
from scripts.confenge_target_fit.models import CycleStats
from scripts.confenge_target_fit.store import (
    claim_batch,
    class_distribution,
    finish_cycle,
    get_control,
    get_current,
    mark_dirty_done,
    publish_materialization,
    record_downstream_invalidation_soft,
    set_control,
    set_target_fit_watermark,
    start_cycle,
    try_company_advisory_lock,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _get_shadow_as_previous(conn: Any, company_key: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM confenge_target_fit_shadow WHERE company_key = %s",
            (company_key,),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        return {
            "company_key": d.get("company_key"),
            "cnpj_raiz": d.get("cnpj_raiz"),
            "target_fit_class": d.get("shadow_class"),
            "target_fit_confidence": d.get("shadow_confidence"),
            "target_fit_version": d.get("target_fit_version"),
            "target_fit_reason_codes": d.get("reason_codes") or [],
            "target_fit_evidence": d.get("evidence") or [],
            "input_fingerprint": d.get("input_fingerprint"),
            "source_watermark": d.get("source_watermark"),
            "computed_at": d.get("computed_at"),
            "operational_status": "shadow_only",
        }


def _backoff(attempt: int, cfg: TargetFitRefreshConfig) -> datetime:
    delay = min(
        cfg.max_backoff_seconds,
        cfg.base_backoff_seconds * (2 ** max(0, attempt - 1)),
    )
    return _utcnow() + timedelta(seconds=delay)


def _normalize_json_fields(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    import json

    out = dict(row)
    for k in ("target_fit_reason_codes", "target_fit_evidence"):
        v = out.get(k)
        if isinstance(v, str):
            try:
                out[k] = json.loads(v)
            except json.JSONDecodeError:
                out[k] = []
    return out


def process_one(
    conn: Any,
    item: Any,
    *,
    cfg: TargetFitRefreshConfig,
    mode: str,
) -> dict[str, Any]:
    """Process a single dirty item inside an open transaction on conn."""
    t0 = time.perf_counter()
    result: dict[str, Any] = {
        "company_key": item.company_key,
        "status": STATUS_DONE,
        "skipped_fingerprint": False,
        "upgrade": False,
        "downgrade": False,
        "transition_key": "UNCHANGED",
        "error": None,
        "latency_ms": 0.0,
    }
    try:
        # Belt-and-suspenders single-writer: claim is one-row-per-company, but
        # advisory lock blocks concurrent publish if two dirty rows raced.
        if not try_company_advisory_lock(conn, item.company_key):
            mark_dirty_done(
                conn,
                item.id,
                status=STATUS_RETRY,
                error="company_lock_busy",
                next_retry_at=_utcnow() + timedelta(seconds=5),
            )
            result["status"] = STATUS_RETRY
            result["error"] = "company_lock_busy"
            result["latency_ms"] = (time.perf_counter() - t0) * 1000
            return result

        company = load_company_input(
            conn,
            cnpj_raiz=item.cnpj_raiz,
            source_watermark=item.source_watermark,
        )
        previous = _normalize_json_fields(get_current(conn, item.company_key))
        if previous is None and mode == MODE_SHADOW:
            # In SHADOW, canonical current is not updated — use shadow as baseline
            # so fingerprint skip and transitions remain meaningful.
            previous = _normalize_json_fields(_get_shadow_as_previous(conn, item.company_key))
        mat, event, meta = compute_materialization(
            company,
            previous=previous,
            mode=mode,
            target_fit_version=TARGET_FIT_VERSION,
        )
        result.update(
            {
                "skipped_fingerprint": meta["skipped_fingerprint"],
                "upgrade": meta["upgrade"],
                "downgrade": meta["downgrade"],
                "transition_key": meta["transition_key"],
                "error": meta.get("error"),
            }
        )

        if meta["skipped_fingerprint"]:
            mark_dirty_done(
                conn,
                item.id,
                status=STATUS_SKIPPED,
                fingerprint=mat.input_fingerprint,
            )
            result["status"] = STATUS_SKIPPED
            result["latency_ms"] = (time.perf_counter() - t0) * 1000
            return result

        if mat.target_fit_class == "REFRESH_FAILED":
            # Fail-closed: publish failure state in ACTIVE so send path sees it
            apply = should_apply_active(
                mode=mode,
                company_key=item.company_key,
                canary_percent=cfg.canary_percent,
            )
            event_id = publish_materialization(
                conn, mat, event, shadow_only=not apply
            )
            if item.attempt_count >= cfg.max_attempts:
                mark_dirty_done(
                    conn,
                    item.id,
                    status=STATUS_DEAD,
                    error=meta.get("error") or "refresh_failed",
                    fingerprint=mat.input_fingerprint,
                )
                result["status"] = STATUS_DEAD
            else:
                mark_dirty_done(
                    conn,
                    item.id,
                    status=STATUS_RETRY,
                    error=meta.get("error") or "refresh_failed",
                    fingerprint=mat.input_fingerprint,
                    next_retry_at=_backoff(item.attempt_count, cfg),
                )
                result["status"] = STATUS_RETRY
            result["latency_ms"] = (time.perf_counter() - t0) * 1000
            result["event_id"] = event_id
            return result

        apply = should_apply_active(
            mode=mode,
            company_key=item.company_key,
            canary_percent=cfg.canary_percent,
        )
        # CANARY: companies outside bucket always shadow
        if mode == "CANARY" and canary_bucket(item.company_key) >= cfg.canary_percent:
            apply = False

        event_id = publish_materialization(conn, mat, event, shadow_only=not apply)

        if apply and meta["downgrade"] and event is not None:
            record_downstream_invalidation_soft(
                conn,
                company_key=item.company_key,
                cnpj_raiz=item.cnpj_raiz,
                event_id=event_id,
                old_class=mat.previous_class,
                new_class=mat.target_fit_class,
                notes=f"event={event.event_type}",
            )

        mark_dirty_done(
            conn,
            item.id,
            status=STATUS_DONE,
            fingerprint=mat.input_fingerprint,
        )
        result["status"] = STATUS_DONE
        result["event_id"] = event_id
        result["applied"] = apply
        result["class"] = mat.target_fit_class
    except Exception as exc:  # noqa: BLE001
        logger.exception("target-fit process_one failed company=%s", item.company_key)
        result["error"] = f"{type(exc).__name__}: {exc}"
        if item.attempt_count >= cfg.max_attempts:
            mark_dirty_done(
                conn,
                item.id,
                status=STATUS_DEAD,
                error=result["error"],
            )
            result["status"] = STATUS_DEAD
        else:
            mark_dirty_done(
                conn,
                item.id,
                status=STATUS_RETRY,
                error=result["error"],
                next_retry_at=_backoff(item.attempt_count, cfg),
            )
            result["status"] = STATUS_RETRY
    result["latency_ms"] = (time.perf_counter() - t0) * 1000
    return result


def resolve_mode(conn: Any, cfg: TargetFitRefreshConfig) -> str:
    auto = get_control(conn, "auto_pause")
    if auto.get("paused"):
        return MODE_AUTO_PAUSE
    ctrl = get_control(conn, "async_mode")
    mode = str(ctrl.get("mode") or cfg.async_mode or MODE_SHADOW).upper()
    return mode


def maybe_auto_pause(
    conn: Any,
    *,
    cfg: TargetFitRefreshConfig,
    before: dict[str, int],
    after: dict[str, int],
) -> bool:
    if not cfg.anomaly_auto_pause:
        return False
    total_before = sum(before.values()) or 0
    total_after = sum(after.values()) or 0
    if total_before < cfg.anomaly_min_population:
        return False
    for cls in ("TARGET_CONFIRMED", "TARGET_OUT_OF_SCOPE"):
        b = before.get(cls, 0) / max(total_before, 1)
        a = after.get(cls, 0) / max(total_after, 1)
        if abs(a - b) > cfg.anomaly_class_delta_fraction:
            set_control(
                conn,
                "auto_pause",
                {
                    "paused": True,
                    "reason": f"anomaly_{cls}_delta",
                    "before": before,
                    "after": after,
                    "at": _utcnow().isoformat(),
                },
            )
            set_control(conn, "async_mode", {"mode": MODE_AUTO_PAUSE})
            logger.error("AUTO_PAUSE: class distribution anomaly on %s", cls)
            return True
    return False


def run_worker_cycle(
    dsn: str,
    *,
    cfg: TargetFitRefreshConfig | None = None,
    worker_id: str | None = None,
    max_batches: int = 1,
) -> CycleStats:
    cfg = cfg or TargetFitRefreshConfig.from_env()
    worker_id = worker_id or f"tf-worker-{uuid.uuid4().hex[:8]}"
    cycle_id = f"worker-{_utcnow().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    stats = CycleStats(
        cycle_id=cycle_id,
        cycle_kind="worker",
        mode=cfg.async_mode,
        target_fit_version=TARGET_FIT_VERSION,
    )

    conn = connect(dsn, readonly=False)
    try:
        mode = resolve_mode(conn, cfg)
        stats.mode = mode
        if mode == MODE_AUTO_PAUSE:
            start_cycle(
                conn,
                cycle_id=cycle_id,
                cycle_kind="worker",
                mode=mode,
                target_fit_version=TARGET_FIT_VERSION,
            )
            finish_cycle(
                conn,
                cycle_id=cycle_id,
                status="auto_paused",
                stats=stats.as_dict(),
                error_message="async mode AUTO_PAUSE",
            )
            conn.commit()
            stats.error = "AUTO_PAUSE"
            return stats

        start_cycle(
            conn,
            cycle_id=cycle_id,
            cycle_kind="worker",
            mode=mode,
            target_fit_version=TARGET_FIT_VERSION,
        )
        before = class_distribution(conn)
        conn.commit()

        for _ in range(max_batches):
            items = claim_batch(
                conn,
                worker_id=worker_id,
                batch_size=cfg.batch_size,
                lock_ttl_seconds=cfg.lock_ttl_seconds,
            )
            conn.commit()
            if not items:
                break
            stats.claimed += len(items)
            for item in items:
                # Each company in its own transaction for atomicity
                r = process_one(conn, item, cfg=cfg, mode=mode)
                conn.commit()
                stats.processed += 1
                stats.processing_latency_ms_total += float(r.get("latency_ms") or 0)
                if r.get("skipped_fingerprint"):
                    stats.skipped_same_fingerprint += 1
                elif r.get("status") == STATUS_DONE:
                    if r.get("upgrade"):
                        stats.upgrades += 1
                    elif r.get("downgrade"):
                        stats.downgrades += 1
                    else:
                        stats.unchanged += 1
                    tk = r.get("transition_key") or "UNCHANGED"
                    stats.transitions[tk] = stats.transitions.get(tk, 0) + 1
                elif r.get("status") == STATUS_RETRY:
                    stats.retries += 1
                    stats.failures += 1
                elif r.get("status") == STATUS_DEAD:
                    stats.dead_letter += 1
                    stats.failures += 1
                elif r.get("status") == STATUS_REFRESH_FAILED:
                    stats.failures += 1

        after = class_distribution(conn)
        paused = maybe_auto_pause(conn, cfg=cfg, before=before, after=after)
        # Advance target-fit watermark to CDC watermark when cycle drains work
        cdc = get_control(conn, "cdc_watermark")
        cdc_wm = str(cdc.get("watermark") or "")
        if cdc_wm and stats.processed > 0:
            set_target_fit_watermark(conn, cdc_wm)
            stats.source_watermark = cdc_wm
        finish_cycle(
            conn,
            cycle_id=cycle_id,
            status="auto_paused" if paused else "success",
            stats=stats.as_dict(),
        )
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
    return stats


def run_worker_loop(
    dsn: str,
    *,
    cfg: TargetFitRefreshConfig | None = None,
    idle_sleep_seconds: float = 15.0,
    max_cycles: int | None = None,
) -> None:
    """Long-running worker (systemd Type=simple). Graceful on KeyboardInterrupt."""
    cfg = cfg or TargetFitRefreshConfig.from_env()
    cycles = 0
    logger.info(
        "target-fit worker starting mode=%s batch=%s",
        cfg.async_mode,
        cfg.batch_size,
    )
    try:
        while max_cycles is None or cycles < max_cycles:
            stats = run_worker_cycle(dsn, cfg=cfg)
            cycles += 1
            logger.info(
                "worker cycle done claimed=%s processed=%s up=%s down=%s skip=%s fail=%s",
                stats.claimed,
                stats.processed,
                stats.upgrades,
                stats.downgrades,
                stats.skipped_same_fingerprint,
                stats.failures,
            )
            if stats.claimed == 0:
                time.sleep(idle_sleep_seconds)
            if stats.error == "AUTO_PAUSE":
                time.sleep(max(idle_sleep_seconds, 60.0))
    except KeyboardInterrupt:
        logger.info("target-fit worker graceful shutdown")
