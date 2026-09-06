"""Optional non-blocking hook after a datalake refresh cycle.

Call from weekly/crawl completion paths without coupling success of ETL to
target-fit. Failures are logged and swallowed by design.

Usage (best-effort)::

    from scripts.confenge_target_fit.hook_after_datalake import notify_datalake_committed
    notify_datalake_committed(dsn)  # never raises to caller for operational failures
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def notify_datalake_committed(
    dsn: str | None = None,
    *,
    drain_worker: bool = False,
) -> dict[str, Any] | None:
    """Enqueue dirty companies after ETL watermark is published.

    Returns stats dict or None on soft failure. Never raises for expected
    operational errors (so ETL callers remain isolated).
    """
    if os.environ.get("TARGET_FIT_HOOK_DISABLED", "").strip() in {"1", "true", "yes"}:
        return {"skipped": True, "reason": "TARGET_FIT_HOOK_DISABLED"}
    try:
        from scripts.confenge_target_fit.config import TargetFitRefreshConfig
        from scripts.confenge_target_fit.refresh import run_refresh
        from scripts.ops.confenge_commercial_mutex import acquire_stage_from_env

        cfg = TargetFitRefreshConfig.from_env()
        resolved = dsn or cfg.resolve_state_dsn()
        with acquire_stage_from_env("refresh", scope="stage") as claim:
            stats = run_refresh(
                resolved,
                cfg=cfg,
                drain_worker=drain_worker,
                max_worker_batches=1 if drain_worker else 0,
            )
            if not stats.error:
                claim.complete(stats.as_dict())
        return stats.as_dict()
    except Exception as exc:  # noqa: BLE001 — intentional soft boundary
        logger.warning(
            "target-fit hook soft-failed (datalake remains committed): %s",
            exc,
        )
        return {"error": f"{type(exc).__name__}: {exc}", "soft_fail": True}
