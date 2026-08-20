"""Deterministic dedupe with stable reason codes."""

from __future__ import annotations

from dataclasses import replace

from scripts.public_integrity.hashing import digest
from scripts.public_integrity.models import ObservedRecord


def _fingerprint(record: ObservedRecord) -> str:
    return digest(
        {
            "source_id": record.source_id,
            "official_id": record.official_id,
            "record_type": record.record_type,
            "authority": record.authority,
            "start_date": record.start_date,
            "end_date": record.end_date,
        }
    )


def _sort_key(record: ObservedRecord) -> tuple[str, str, str, str]:
    return (
        record.source_id,
        record.official_id,
        record.start_date or "",
        _fingerprint(record),
    )


def dedupe_records(
    records: tuple[ObservedRecord, ...] | list[ObservedRecord],
) -> tuple[tuple[ObservedRecord, ...], tuple[str, ...]]:
    seen_ids: set[tuple[str, str]] = set()
    seen_fps: set[str] = set()
    kept: list[ObservedRecord] = []
    dropped: list[str] = []
    for record in sorted(records, key=_sort_key):
        id_key = (record.source_id, record.official_id)
        fingerprint = _fingerprint(record)
        reasons: list[str] = []
        if id_key in seen_ids:
            reasons.append("duplicate_official_id")
        if fingerprint in seen_fps:
            reasons.append("duplicate_normalized_fingerprint")
        if reasons:
            dropped.extend(reasons)
            continue
        seen_ids.add(id_key)
        seen_fps.add(fingerprint)
        kept.append(replace(record, dedupe_reasons=()))
    return tuple(kept), tuple(dict.fromkeys(dropped))
