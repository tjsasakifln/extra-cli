"""Freshness policy for target-fit vs datalake watermark.

Uses watermark semantics when available; wall-clock age is secondary.
Stale / failed critical data must fail-closed for EMAIL_SEND_READY.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from scripts.confenge_target_fit.config import TargetFitRefreshConfig
from scripts.confenge_target_fit.models import FreshnessDecision
from scripts.confenge_target_fit.store import get_control, get_current, is_send_suppressed


def _parse_wm(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def evaluate_freshness(
    *,
    company_key: str,
    current: dict[str, Any] | None,
    datalake_watermark: str,
    config: TargetFitRefreshConfig | None = None,
    suppressed: bool = False,
) -> FreshnessDecision:
    cfg = config or TargetFitRefreshConfig.from_env()
    now = datetime.now(UTC)

    if not current:
        return FreshnessDecision(
            company_key=company_key,
            target_fit_fresh=False,
            target_fit_age_seconds=None,
            target_fit_computed_at=None,
            target_fit_source_watermark="",
            datalake_watermark=datalake_watermark or "",
            reason="TARGET_FIT_MISSING",
            blocks_send=True,
        )

    op = current.get("operational_status") or "ok"
    cls = current.get("target_fit_class") or ""
    computed = current.get("computed_at")
    if isinstance(computed, str):
        computed = _parse_wm(computed)
    tf_wm = str(current.get("source_watermark") or "")
    age = None
    if isinstance(computed, datetime):
        if computed.tzinfo is None:
            computed = computed.replace(tzinfo=UTC)
        age = (now - computed).total_seconds()

    if op in {"refresh_failed"} or cls == "REFRESH_FAILED":
        return FreshnessDecision(
            company_key=company_key,
            target_fit_fresh=False,
            target_fit_age_seconds=age,
            target_fit_computed_at=computed if isinstance(computed, datetime) else None,
            target_fit_source_watermark=tf_wm,
            datalake_watermark=datalake_watermark or "",
            reason="TARGET_FIT_REFRESH_FAILED",
            blocks_send=True,
        )

    if op == "missing" or cls == "TARGET_FIT_MISSING":
        return FreshnessDecision(
            company_key=company_key,
            target_fit_fresh=False,
            target_fit_age_seconds=age,
            target_fit_computed_at=computed if isinstance(computed, datetime) else None,
            target_fit_source_watermark=tf_wm,
            datalake_watermark=datalake_watermark or "",
            reason="TARGET_FIT_MISSING",
            blocks_send=True,
        )

    if op == "stale":
        return FreshnessDecision(
            company_key=company_key,
            target_fit_fresh=False,
            target_fit_age_seconds=age,
            target_fit_computed_at=computed if isinstance(computed, datetime) else None,
            target_fit_source_watermark=tf_wm,
            datalake_watermark=datalake_watermark or "",
            reason="TARGET_FIT_STALE",
            blocks_send=True,
        )

    if op in {"recompute_required"} or cls == "RECOMPUTE_REQUIRED":
        return FreshnessDecision(
            company_key=company_key,
            target_fit_fresh=False,
            target_fit_age_seconds=age,
            target_fit_computed_at=computed if isinstance(computed, datetime) else None,
            target_fit_source_watermark=tf_wm,
            datalake_watermark=datalake_watermark or "",
            reason="TARGET_FIT_RECOMPUTE_REQUIRED",
            blocks_send=True,
        )

    if suppressed:
        return FreshnessDecision(
            company_key=company_key,
            target_fit_fresh=True,
            target_fit_age_seconds=age,
            target_fit_computed_at=computed if isinstance(computed, datetime) else None,
            target_fit_source_watermark=tf_wm,
            datalake_watermark=datalake_watermark or "",
            reason="TARGET_FIT_DOWNGRADE",
            blocks_send=True,
        )

    dl = _parse_wm(datalake_watermark)
    tf = _parse_wm(tf_wm)
    if dl is not None and tf is not None:
        lag = (dl - tf).total_seconds()
        if lag > cfg.max_watermark_lag_seconds:
            return FreshnessDecision(
                company_key=company_key,
                target_fit_fresh=False,
                target_fit_age_seconds=age,
                target_fit_computed_at=computed if isinstance(computed, datetime) else None,
                target_fit_source_watermark=tf_wm,
                datalake_watermark=datalake_watermark or "",
                reason="TARGET_FIT_STALE",
                blocks_send=bool(cfg.stale_blocks_send),
            )

    if cls != "TARGET_CONFIRMED":
        return FreshnessDecision(
            company_key=company_key,
            target_fit_fresh=True,
            target_fit_age_seconds=age,
            target_fit_computed_at=computed if isinstance(computed, datetime) else None,
            target_fit_source_watermark=tf_wm,
            datalake_watermark=datalake_watermark or "",
            reason="TARGET_FIT_NOT_CONFIRMED",
            blocks_send=True,
        )

    return FreshnessDecision(
        company_key=company_key,
        target_fit_fresh=True,
        target_fit_age_seconds=age,
        target_fit_computed_at=computed if isinstance(computed, datetime) else None,
        target_fit_source_watermark=tf_wm,
        datalake_watermark=datalake_watermark or "",
        reason="TARGET_FIT_FRESH",
        blocks_send=False,
    )


def freshness_for_company(
    conn: Any,
    company_key: str,
    *,
    config: TargetFitRefreshConfig | None = None,
) -> FreshnessDecision:
    current = get_current(conn, company_key)
    ctrl = get_control(conn, "cdc_watermark")
    dl_wm = str(ctrl.get("watermark") or "")
    suppressed = is_send_suppressed(conn, company_key)
    return evaluate_freshness(
        company_key=company_key,
        current=current,
        datalake_watermark=dl_wm,
        config=config,
        suppressed=suppressed,
    )


def feed_fields_from_current(
    current: dict[str, Any] | None,
    freshness: FreshnessDecision,
) -> dict[str, Any]:
    """Fields to embed in confenge.outreach.v1-compatible feed rows."""
    if not current:
        return {
            "target_fit_class": None,
            "target_fit_confidence": None,
            "target_fit_version": None,
            "target_fit_computed_at": None,
            "target_fit_source_watermark": None,
            "target_fit_fresh": False,
            "target_fit_evidence_ids": [],
            "target_fit_freshness_reason": freshness.reason,
        }
    evidence = current.get("target_fit_evidence") or []
    ids = []
    if isinstance(evidence, list):
        for e in evidence:
            if isinstance(e, dict) and e.get("id") is not None:
                ids.append(str(e["id"]))
    computed = current.get("computed_at")
    if hasattr(computed, "isoformat"):
        computed = computed.isoformat()
    return {
        "target_fit_class": current.get("target_fit_class"),
        "target_fit_confidence": current.get("target_fit_confidence"),
        "target_fit_version": current.get("target_fit_version"),
        "target_fit_computed_at": computed,
        "target_fit_source_watermark": current.get("source_watermark"),
        "target_fit_fresh": freshness.target_fit_fresh,
        "target_fit_evidence_ids": ids,
        "target_fit_freshness_reason": freshness.reason,
    }
