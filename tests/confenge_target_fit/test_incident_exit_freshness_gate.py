"""Injected stale|partial|error|unknown must not become EMAIL_SEND_READY."""

from __future__ import annotations

from datetime import UTC, datetime

from scripts.confenge_target_fit import TARGET_CONFIRMED
from scripts.confenge_target_fit.freshness import evaluate_freshness
from scripts.confenge_target_fit.published import evaluate_published_send_gate, map_class_to_send_tier


def _confirmed(**overrides) -> dict[str, object]:
    row: dict[str, object] = {
        "company_key": "cnpj_root:11222333",
        "target_fit_class": TARGET_CONFIRMED,
        "operational_status": "ok",
        "computed_at": datetime(2026, 9, 1, tzinfo=UTC),
        "source_watermark": "2026-09-01T00:00:00Z",
    }
    row.update(overrides)
    return row


def test_injected_stale_partial_error_unknown_block_send() -> None:
    for status in ("stale", "partial", "error", "unknown"):
        fresh = evaluate_freshness(
            company_key="cnpj_root:11222333",
            current=_confirmed(operational_status=status),
            datalake_watermark="2026-09-01T00:00:00Z",
        )
        assert fresh.blocks_send is True, status
        assert fresh.target_fit_fresh is False, status
        blocks, reasons, _ = evaluate_published_send_gate(
            published=_confirmed(operational_status=status),
            datalake_watermark="2026-09-01T00:00:00Z",
        )
        assert blocks is True, status
        assert reasons, status


def test_injected_class_labels_are_not_promoted_to_automatic() -> None:
    for cls in ("PARTIAL", "ERROR", "UNKNOWN", "STALE", "TARGET_OUT_OF_SCOPE"):
        assert map_class_to_send_tier(cls) != "A_AUTOMATIC"
        blocks, reasons, _ = evaluate_published_send_gate(
            published=_confirmed(target_fit_class=cls, operational_status="ok"),
            datalake_watermark="2026-09-01T00:00:00Z",
        )
        assert blocks is True, cls
        assert any("target_fit_class" in r or "UNTRUSTED" in r or "STALE" in r for r in reasons), (
            cls,
            reasons,
        )
