"""Build a research-flagship payload from live contracts or a READY snapshot.

Fixtures stay a test-only input. This module never labels live rows as fixture
proof and never substitutes Extra 1093 for the national denominator.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.public_read.models import (
    PartitionSpec,
    ResearchPayload,
    SeriesRow,
    UniverseSpec,
    parse_decimal,
)
from scripts.public_read.payload import payload_from_mapping

ENGINEERING_ARCHETYPE = "obras-engenharia"


def load_json_payload(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_contracts_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _as_of(raw: dict[str, Any]) -> str:
    value = raw.get("as_of") or raw.get("cutoff")
    if value:
        return str(value)
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _row_from_contract(item: dict[str, Any]) -> SeriesRow:
    process_key = str(
        item.get("process_key")
        or item.get("contrato_id")
        or item.get("source_record_id")
        or ""
    )
    if not process_key:
        raise ValueError("live contract missing identity")
    value = item.get("contract_value_brl")
    if value is None:
        value = item.get("valor_total")
    status = str(item.get("value_status") or ("KNOWN" if value is not None else "UNKNOWN"))
    return SeriesRow(
        process_key=process_key,
        uf=str(item.get("uf") or "UNKNOWN"),
        archetype_id=str(item.get("archetype_id") or ENGINEERING_ARCHETYPE),
        contract_value_brl=parse_decimal(value),
        source_id=str(item.get("source") or item.get("source_id") or "pncp"),
        source_record_id=str(item.get("source_id") or process_key),
        observed_at=str(item.get("observed_at") or item.get("last_seen_at") or item.get("ingested_at") or ""),
        lineage=tuple(str(part) for part in item.get("lineage", (item.get("source") or "pncp", process_key))),
        value_status=status,
        lineage_resolution=item.get("lineage_resolution"),
    )


def payload_from_live_corpus(
    *,
    contracts: list[dict[str, Any]],
    denominator: dict[str, Any],
    as_of: str,
    competence: str,
    publication_age_hours: float,
    publication_lag_p99_hours: float,
    payload_id: str,
) -> ResearchPayload:
    """Map official live rows + a #302 report into the shipped research payload."""
    orgs = []
    for org in denominator.get("orgs") or ():
        orgs.append(
            {
                "org_id": org["org_id"],
                "source": org.get("source") or denominator.get("source") or "pncp",
                "competence": org.get("competence") or competence,
                "name": org.get("name") or org["org_id"],
                "unit_count": int(org.get("unit_count") or 1),
            }
        )
    partitions = []
    for part in denominator.get("partitions") or ():
        partitions.append(
            {
                "partition_id": part["partition_id"],
                "status": part["status"],
                "evidence": part.get("evidence"),
            }
        )
    mapping = {
        "fixture_id": payload_id,
        "as_of": as_of,
        "competence": competence,
        "universe": {
            "source": str(denominator.get("source") or "pncp"),
            "competence": competence,
            "cutoff": str(denominator.get("cutoff") or as_of),
            "method": str(denominator.get("method") or "pncp-orgaos-publicantes-v1"),
            "orgs": orgs,
        },
        "partitions": partitions,
        "freshness": {
            "publication_age_hours": publication_age_hours,
            "publication_lag_p99_hours": publication_lag_p99_hours,
        },
        "series_rows": [
            {
                "process_key": row.process_key,
                "uf": row.uf,
                "archetype_id": row.archetype_id,
                "contract_value_brl": None if row.contract_value_brl is None else format(row.contract_value_brl, "f"),
                "source_id": row.source_id,
                "source_record_id": row.source_record_id,
                "observed_at": row.observed_at,
                "lineage": list(row.lineage),
                "value_status": row.value_status,
                "lineage_resolution": row.lineage_resolution,
            }
            for row in (_row_from_contract(item) for item in contracts)
        ],
        "use_extra_1093_as_denominator": False,
        "denominator_kind": "publishing_org",
        "claimed_geography": "BR" if denominator.get("nacional_completo") else None,
    }
    payload = payload_from_mapping(mapping)
    if payload.use_extra_1093_as_denominator:
        raise ValueError("live payload refused Extra 1093 as denominator")
    return payload


def snapshot_is_ready(snapshot: dict[str, Any]) -> bool:
    state = str(snapshot.get("state") or snapshot.get("status") or "")
    return state in {"READY", "READY_CANONICAL"}


def payload_from_snapshot_document(snapshot: dict[str, Any]) -> ResearchPayload:
    if not snapshot_is_ready(snapshot):
        raise ValueError(f"snapshot_not_ready:{snapshot.get('state') or snapshot.get('status') or 'missing'}")
    if "series_rows" in snapshot:
        return payload_from_mapping(snapshot)
    contracts = list(snapshot.get("contracts") or snapshot.get("records") or ())
    denominator = snapshot.get("denominator") or {}
    return payload_from_live_corpus(
        contracts=contracts,
        denominator=denominator,
        as_of=_as_of(snapshot),
        competence=str(snapshot.get("competence") or denominator.get("competence") or "unknown"),
        publication_age_hours=float((snapshot.get("freshness") or {}).get("publication_age_hours") or 0),
        publication_lag_p99_hours=float((snapshot.get("freshness") or {}).get("publication_lag_p99_hours") or 0),
        payload_id=str(snapshot.get("snapshot_id") or snapshot.get("payload_id") or "live-snapshot"),
    )


def universe_spec_from_denominator(denominator: dict[str, Any]) -> UniverseSpec:
    return UniverseSpec(
        source=str(denominator.get("source") or "pncp"),
        competence=str(denominator.get("competence") or ""),
        cutoff=str(denominator.get("cutoff") or ""),
        method=str(denominator.get("method") or "pncp-orgaos-publicantes-v1"),
        orgs=tuple(dict(org) for org in denominator.get("orgs") or ()),
    )


def partition_specs(denominator: dict[str, Any]) -> tuple[PartitionSpec, ...]:
    return tuple(
        PartitionSpec(
            partition_id=str(part["partition_id"]),
            status=str(part["status"]),
            evidence=part.get("evidence"),
        )
        for part in denominator.get("partitions") or ()
    )
