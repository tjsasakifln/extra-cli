"""Identify the current contract corpus without re-backfill.

Work is bounded to publisher aggregates. Raw 4.5M contract rewrite is refused.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from scripts.national_coverage.hashing import digest
from scripts.national_coverage.models import (
    MAX_INMEMORY_CONTRACT_ROWS,
    CorpusPublisher,
    CorpusSnapshot,
    MappedPublisher,
    MappingStats,
    NationalCoverageError,
    PublishingOrg,
    VersionedUniverse,
)
from scripts.national_coverage.policy import normalize_org_id

CORPUS_SELECT_SQL = """
SELECT
    orgao_cnpj,
    uf,
    COUNT(*)::bigint AS contract_count,
    MIN(data_publicacao)::text AS first_seen,
    MAX(data_publicacao)::text AS last_seen
FROM pncp_supplier_contracts
WHERE orgao_cnpj IS NOT NULL
GROUP BY orgao_cnpj, uf
"""


def snapshot_from_publishers(
    publishers: tuple[CorpusPublisher, ...],
    *,
    as_of: str,
    source: str,
) -> CorpusSnapshot:
    payload = {
        "as_of": as_of,
        "source": source,
        "publishers": [
            {
                "raw_org_id": pub.raw_org_id,
                "contract_count": pub.contract_count,
                "uf": pub.uf,
                "esfera": pub.esfera,
                "first_seen": pub.first_seen,
                "last_seen": pub.last_seen,
                "aliases": list(pub.aliases),
            }
            for pub in publishers
        ],
    }
    snapshot_hash = digest(payload)
    return CorpusSnapshot(
        snapshot_id=f"cs-{snapshot_hash[:16]}",
        snapshot_hash=snapshot_hash,
        as_of=as_of,
        source=source,
        publisher_count=len(publishers),
        contract_count=sum(pub.contract_count for pub in publishers),
        publishers=publishers,
        relation="pncp_supplier_contracts_aggregate",
    )


def aggregate_contract_rows(
    rows: Sequence[dict[str, Any]],
    *,
    as_of: str,
    source: str,
) -> CorpusSnapshot:
    if len(rows) > MAX_INMEMORY_CONTRACT_ROWS:
        raise NationalCoverageError(
            f"inmemory_contract_rewrite_refused:rows={len(rows)} max={MAX_INMEMORY_CONTRACT_ROWS}"
        )
    buckets: dict[tuple[str, str | None], dict[str, Any]] = {}
    for row in rows:
        org_id = normalize_org_id(str(row.get("org_id") or row.get("orgao_cnpj") or ""))
        if not org_id:
            continue
        uf = row.get("uf")
        uf_key = str(uf).strip().upper() if uf else None
        key = (org_id, uf_key)
        bucket = buckets.setdefault(
            key,
            {"count": 0, "first": None, "last": None, "esfera": row.get("esfera")},
        )
        bucket["count"] += 1
        published = row.get("published_at") or row.get("data_publicacao")
        if published:
            text = str(published)
            if bucket["first"] is None or text < bucket["first"]:
                bucket["first"] = text
            if bucket["last"] is None or text > bucket["last"]:
                bucket["last"] = text
    publishers = tuple(
        CorpusPublisher(
            raw_org_id=org_id,
            contract_count=int(data["count"]),
            uf=uf,
            esfera=str(data["esfera"]) if data.get("esfera") else None,
            first_seen=data["first"],
            last_seen=data["last"],
        )
        for (org_id, uf), data in sorted(buckets.items())
    )
    return snapshot_from_publishers(publishers, as_of=as_of, source=source)


def snapshot_from_select(conn: Any, *, as_of: str, source: str = "pncp_supplier_contracts") -> CorpusSnapshot:
    from scripts.testing.connection_policy import connection_kind

    if connection_kind(conn) == "MagicMock":
        raise NationalCoverageError("refusing MagicMock as PostgreSQL")
    cursor = conn.cursor()
    try:
        cursor.execute(CORPUS_SELECT_SQL)
        rows = cursor.fetchall()
    finally:
        closer = getattr(cursor, "close", None)
        if callable(closer):
            closer()
    publishers = tuple(
        CorpusPublisher(
            raw_org_id=normalize_org_id(str(row[0])),
            contract_count=int(row[2] or 0),
            uf=str(row[1]).strip().upper() if row[1] else None,
            first_seen=str(row[3]) if row[3] else None,
            last_seen=str(row[4]) if row[4] else None,
        )
        for row in rows
        if row and row[0]
    )
    return snapshot_from_publishers(publishers, as_of=as_of, source=source)


def _catalog_index(
    orgs: tuple[PublishingOrg, ...],
) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for org in orgs:
        keys = (org.org_id, *org.aliases)
        for key in keys:
            norm = normalize_org_id(key)
            index.setdefault(norm, []).append(org.org_id)
    return index


def map_publishers(snapshot: CorpusSnapshot, universe: VersionedUniverse) -> MappingStats:
    catalog = _catalog_index(universe.expected_orgs)
    # Grain of the SELECT is (org, uf). Repeating the same org across UFs is
    # stock geography, not a duplicate identity. Duplicate is the same (org, uf).
    slice_counts = Counter((normalize_org_id(pub.raw_org_id), pub.uf) for pub in snapshot.publishers)
    records: list[MappedPublisher] = []
    mapped = unmapped = duplicate = conflict = alias = 0
    for pub in snapshot.publishers:
        raw = normalize_org_id(pub.raw_org_id)
        canonicals = list(dict.fromkeys(catalog.get(raw, [])))
        alias_hit = any(normalize_org_id(alias) == raw for org in universe.expected_orgs for alias in org.aliases)
        if slice_counts[(raw, pub.uf)] > 1:
            duplicate += 1
            records.append(
                MappedPublisher(
                    raw_org_id=pub.raw_org_id,
                    canonical_org_id=canonicals[0] if len(canonicals) == 1 else None,
                    status="DUPLICATE",
                    contract_count=pub.contract_count,
                    uf=pub.uf,
                    last_seen=pub.last_seen,
                    reason="duplicate_org_uf_slice",
                )
            )
            continue
        if len(canonicals) > 1:
            conflict += 1
            records.append(
                MappedPublisher(
                    raw_org_id=pub.raw_org_id,
                    canonical_org_id=None,
                    status="CONFLICT",
                    contract_count=pub.contract_count,
                    uf=pub.uf,
                    last_seen=pub.last_seen,
                    reason="multiple_canonicals",
                )
            )
            continue
        if len(canonicals) == 1:
            status = "ALIAS" if alias_hit and canonicals[0] != raw else "MAPPED"
            if status == "ALIAS":
                alias += 1
            else:
                mapped += 1
            records.append(
                MappedPublisher(
                    raw_org_id=pub.raw_org_id,
                    canonical_org_id=canonicals[0],
                    status=status,
                    contract_count=pub.contract_count,
                    uf=pub.uf,
                    last_seen=pub.last_seen,
                    reason=None,
                )
            )
            continue
        unmapped += 1
        records.append(
            MappedPublisher(
                raw_org_id=pub.raw_org_id,
                canonical_org_id=None,
                status="UNMAPPED",
                contract_count=pub.contract_count,
                uf=pub.uf,
                last_seen=pub.last_seen,
                reason="not_in_denominator",
            )
        )
    unresolved = unmapped + conflict
    return MappingStats(
        mapped=mapped,
        unmapped=unmapped,
        duplicate=duplicate,
        conflict=conflict,
        alias=alias,
        unresolved_identities=unresolved,
        records=tuple(records),
    )


def observed_orgs_from_mapping(mapping: MappingStats) -> frozenset[str]:
    return frozenset(
        record.canonical_org_id
        for record in mapping.records
        if record.canonical_org_id and record.status in {"MAPPED", "ALIAS"}
    )
