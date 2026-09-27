"""Durable PNCP truth-label persistence for the contracts collector.

This module deliberately stays in the ingestion plane.  The commercial truth
classifier is frozen evidence; storage freshness and SQL compatibility are
operational concerns and must not mutate that classifier's evidence surface.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from typing import Any

_MIN_SOURCE_CLOCK = datetime.min.replace(tzinfo=UTC)
_MIN_UPDATE_DATE = date.min


def _parse_source_clock(value: Any) -> datetime | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, date):
            parsed = datetime.combine(value, datetime.min.time(), tzinfo=UTC)
        else:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        # The upsert RPC rejects malformed clocks before this step.  Keep a
        # deterministic order if this helper is called directly.
        return None


def _parse_update_date(value: Any) -> date | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value).strip()[:10])
    except (TypeError, ValueError):
        return None


def _freshness_rank(
    raw: Mapping[str, Any], ordinal: int
) -> tuple[int, datetime, int, date, int]:
    """Mirror migration 108's DISTINCT ON ordering exactly.

    A non-null source timestamp always outranks a null timestamp.  The source
    date is only a tie-breaker after the timestamp, followed by input ordinal.
    """

    source_clock = _parse_source_clock(raw.get("source_updated_at"))
    update_date = _parse_update_date(raw.get("data_atualizacao_fonte"))
    return (
        int(source_clock is not None),
        source_clock or _MIN_SOURCE_CLOCK,
        int(update_date is not None),
        update_date or _MIN_UPDATE_DATE,
        ordinal,
    )


def stamp_contract_truth_labels(conn: Any, records: Iterable[Mapping[str, Any]]) -> int:
    """Persist labels without letting stale or duplicate observations win."""

    winners: dict[
        str, tuple[tuple[int, datetime, int, date, int], dict[str, Any]]
    ] = {}
    for ordinal, raw in enumerate(records):
        contrato_id = str(raw.get("contrato_id") or "").strip()
        if not contrato_id:
            continue
        item = {
            "contrato_id": contrato_id,
            "status_raw": raw.get("status_raw"),
            "status_normalized": raw.get("status_normalized"),
            "status_rule_version": raw.get("status_rule_version"),
            "status_source": raw.get("status_source"),
            "quality_state": raw.get("quality_state"),
            "quality_reasons": raw.get("quality_reasons") or [],
            "quality_rule_version": raw.get("quality_rule_version"),
            "canonical_contract_id": raw.get("canonical_contract_id"),
            "source": raw.get("source"),
            "source_contract_id": raw.get("source_contract_id"),
            "parent_procurement_id": raw.get("parent_procurement_id"),
            "source_updated_at": raw.get("source_updated_at"),
            "data_atualizacao_fonte": raw.get("data_atualizacao_fonte"),
        }
        rank = _freshness_rank(item, ordinal)
        previous = winners.get(contrato_id)
        if previous is None or rank > previous[0]:
            winners[contrato_id] = (rank, item)

    payload = [winner[1] for winner in winners.values()]
    if not payload:
        return 0

    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE public.pncp_supplier_contracts AS target
            SET status_raw = stamp.status_raw,
                status_normalized = stamp.status_normalized,
                status_rule_version = stamp.status_rule_version,
                status_source = stamp.status_source,
                quality_state = stamp.quality_state,
                quality_reasons = stamp.quality_reasons::jsonb,
                quality_rule_version = stamp.quality_rule_version,
                canonical_contract_id = stamp.canonical_contract_id,
                source = COALESCE(stamp.source, target.source),
                source_contract_id = stamp.source_contract_id,
                parent_procurement_id = stamp.parent_procurement_id
            FROM jsonb_to_recordset(%s::jsonb) AS stamp(
                contrato_id TEXT,
                status_raw TEXT,
                status_normalized TEXT,
                status_rule_version TEXT,
                status_source TEXT,
                quality_state TEXT,
                quality_reasons JSONB,
                quality_rule_version TEXT,
                canonical_contract_id TEXT,
                source TEXT,
                source_contract_id TEXT,
                parent_procurement_id TEXT,
                source_updated_at TIMESTAMPTZ,
                data_atualizacao_fonte DATE
            )
            WHERE target.contrato_id = stamp.contrato_id
              AND public.fn_contract_observation_not_older(
                  target.source_updated_at,
                  target.data_atualizacao_fonte,
                  stamp.source_updated_at,
                  stamp.data_atualizacao_fonte
              )
            """,
            (json.dumps(payload, default=str),),
        )
        return int(cur.rowcount or 0)
    finally:
        close = getattr(cur, "close", None)
        if callable(close):
            close()
