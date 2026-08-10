"""Feed contract helpers for confenge.outreach.v1 compatibility.

Warmbly must consume published target-fit decisions — never re-score locally.
Used by warmbly_bridge.mapping and outreach exporters.
"""

from __future__ import annotations

from typing import Any

from scripts.confenge_target_fit.freshness import (
    evaluate_freshness,
    feed_fields_from_current,
)
from scripts.confenge_target_fit.models import FreshnessDecision
from scripts.confenge_target_fit.published import (
    attach_published_fields,
    evaluate_published_send_gate,
    map_class_to_send_tier,
)


def enrich_outreach_row(
    row: dict[str, Any],
    *,
    current: dict[str, Any] | None,
    datalake_watermark: str,
    suppressed: bool = False,
) -> dict[str, Any]:
    """Attach target-fit freshness fields to an outreach feed row (pure)."""
    company_key = (
        row.get("company_key")
        or (current or {}).get("company_key")
        or row.get("cnpj_root")
        or ""
    )
    fresh = evaluate_freshness(
        company_key=str(company_key),
        current=current,
        datalake_watermark=datalake_watermark,
        suppressed=suppressed,
    )
    fields = feed_fields_from_current(current, fresh)
    out = attach_published_fields(dict(row), published=current, freshness=fresh)
    out.update(fields)
    blocks, reasons, _ = evaluate_published_send_gate(
        published=current,
        datalake_watermark=datalake_watermark,
        suppressed=suppressed,
    )
    out["target_fit_send_tier"] = map_class_to_send_tier(
        (current or {}).get("target_fit_class") if current else None
    )
    out["email_send_ready_target_fit_ok"] = not blocks
    out["target_fit_block_reasons"] = reasons
    if blocks and out.get("email_send_ready") is True:
        out["email_send_ready"] = False
    return out


def assert_warmbly_contract(row: dict[str, Any]) -> list[str]:
    """Return list of fail-closed violations for Warmbly consumption."""
    errors: list[str] = []
    if row.get("target_fit_class") != "TARGET_CONFIRMED":
        errors.append("target_fit_class_not_confirmed")
    if not row.get("target_fit_fresh"):
        errors.append("target_fit_not_fresh")
    if not row.get("target_fit_version"):
        errors.append("target_fit_version_missing")
    if not row.get("target_fit_source_watermark"):
        errors.append("target_fit_source_watermark_missing")
    if row.get("email_send_ready") and row.get("target_fit_class") != "TARGET_CONFIRMED":
        errors.append("email_send_ready_without_confirmed")
    return errors


def readiness_blocks_from_freshness(decision: FreshnessDecision) -> list[str]:
    if not decision.blocks_send:
        return []
    return [decision.reason or "TARGET_FIT_NOT_READY"]
