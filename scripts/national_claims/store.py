"""Thin persist/replay behind the same claim payload schema.

Prior decisions and LKG rows are appended, never deleted.
"""

from __future__ import annotations

import json
from typing import Any

from scripts.national_claims.identity import classify_row
from scripts.national_claims.models import ClaimRequest, EvidenceRow
from scripts.testing.connection_policy import connection_kind


class StoreError(RuntimeError):
    """Persist/replay refused."""


def _refuse_mock(conn: object) -> None:
    if connection_kind(conn) == "MagicMock":
        raise StoreError("refusing MagicMock as PostgreSQL")


def persist_decision(conn: Any, request: ClaimRequest, payload: dict[str, Any]) -> None:
    _refuse_mock(conn)
    cursor = conn.cursor()
    try:
        _upsert_universes(cursor, request)
        _replace_partitions(cursor, payload)
        _replace_evidence(cursor, request, payload["claim_id"])
        cursor.execute(
            """
            INSERT INTO national_claims_decision (
                claim_id, scope, national_universe_id, catalog_hash,
                authorization_state, nacional_completo, consumer_view,
                numerator, denominator, coverage_pct, missingness_pct,
                partitions_expected, partitions_closed, freshness_status,
                as_of, source_version, method_version, policy_version,
                limitations, reason_codes, lkg_claim_id, invalidation_triggers,
                producer_sha, content_hash, payload
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s::jsonb,
                %s, %s, %s::jsonb
            )
            ON CONFLICT (claim_id) DO UPDATE SET
                authorization_state = EXCLUDED.authorization_state,
                nacional_completo = EXCLUDED.nacional_completo,
                consumer_view = EXCLUDED.consumer_view,
                numerator = EXCLUDED.numerator,
                denominator = EXCLUDED.denominator,
                coverage_pct = EXCLUDED.coverage_pct,
                missingness_pct = EXCLUDED.missingness_pct,
                partitions_expected = EXCLUDED.partitions_expected,
                partitions_closed = EXCLUDED.partitions_closed,
                freshness_status = EXCLUDED.freshness_status,
                as_of = EXCLUDED.as_of,
                limitations = EXCLUDED.limitations,
                reason_codes = EXCLUDED.reason_codes,
                lkg_claim_id = EXCLUDED.lkg_claim_id,
                invalidation_triggers = EXCLUDED.invalidation_triggers,
                producer_sha = EXCLUDED.producer_sha,
                content_hash = EXCLUDED.content_hash,
                payload = EXCLUDED.payload
            """,
            (
                payload["claim_id"],
                payload["scope"],
                payload["national_universe_id"],
                payload["catalog_hash"],
                payload["authorization_state"],
                payload["nacional_completo"],
                payload["consumer_view"],
                payload["numerator"],
                payload["denominator"],
                payload["coverage_pct"],
                payload["missingness_pct"],
                payload["partitions_expected"],
                payload["partitions_closed"],
                payload["freshness_status"],
                payload["as_of"],
                payload["source_version"],
                payload["method_version"],
                payload["policy_version"],
                list(payload["limitations"]),
                list(payload["reason_codes"]),
                (payload.get("lkg_ref") or {}).get("claim_id"),
                json.dumps(payload["invalidation_triggers"]),
                payload["producer_sha"],
                payload["content_hash"],
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        if payload["authorization_state"] == "AUTHORIZED":
            from scripts.national_claims.lkg import lkg_expiry

            cursor.execute(
                """
                INSERT INTO national_claims_lkg (
                    national_universe_id, claim_id, authorized_at, expires_at,
                    catalog_hash, method_version, source_version, content_hash
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (national_universe_id, claim_id) DO NOTHING
                """,
                (
                    payload["national_universe_id"],
                    payload["claim_id"],
                    payload["as_of"],
                    lkg_expiry(authorized_at=str(payload["as_of"])),
                    payload["catalog_hash"],
                    payload["method_version"],
                    payload["source_version"],
                    payload["content_hash"],
                ),
            )
    finally:
        closer = getattr(cursor, "close", None)
        if callable(closer):
            closer()


def replay_decision(conn: Any, claim_id: str) -> dict[str, Any]:
    _refuse_mock(conn)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT payload, content_hash FROM national_claims_decision WHERE claim_id = %s",
            (claim_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise StoreError(f"no persisted decision for {claim_id}")
        payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return payload
    finally:
        closer = getattr(cursor, "close", None)
        if callable(closer):
            closer()


def invalidate_lkg(conn: Any, *, national_universe_id: str, reason: str, as_of: str) -> int:
    """Stamp invalidation. Never deletes the LKG row or prior evidence."""
    _refuse_mock(conn)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE national_claims_lkg
            SET invalidated_at = %s, invalidation_reason = %s
            WHERE national_universe_id = %s AND invalidated_at IS NULL
            """,
            (as_of, reason, national_universe_id),
        )
        return int(cursor.rowcount or 0)
    finally:
        closer = getattr(cursor, "close", None)
        if callable(closer):
            closer()


def _upsert_universes(cursor: Any, request: ClaimRequest) -> None:
    for universe in (
        request.universes.national,
        request.universes.icp_commercial,
        request.universes.extra_1093_monitored,
        request.universes.observed_corpus,
    ):
        cursor.execute(
            """
            INSERT INTO national_claims_universe (
                universe_id, universe_kind, official_source, cutoff, competence,
                catalog_hash, method_version, org_count, unit_count,
                expected_partitions, inclusion_rules, exclusion_rules,
                change_log, owner, review_cadence, payload
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s::jsonb, %s::jsonb,
                %s::jsonb, %s, %s, %s::jsonb
            )
            ON CONFLICT (universe_id) DO NOTHING
            """,
            (
                universe.universe_id,
                universe.universe_kind,
                universe.official_source,
                universe.cutoff,
                universe.competence,
                universe.catalog_hash,
                universe.method_version,
                len(universe.expected_orgs),
                universe.expected_units,
                universe.expected_partitions,
                json.dumps(list(universe.inclusion_rules)),
                json.dumps(list(universe.exclusion_rules)),
                json.dumps(list(universe.version_changes)),
                universe.owner,
                universe.review_cadence,
                json.dumps(
                    {
                        "orgs": [
                            {
                                "org_id": org.org_id,
                                "name": org.name,
                                "unit_count": org.unit_count,
                                "geography": org.geography,
                            }
                            for org in universe.expected_orgs
                        ]
                    }
                ),
            ),
        )


def _replace_partitions(cursor: Any, payload: dict[str, Any]) -> None:
    claim_id = payload["claim_id"]
    cursor.execute(
        "DELETE FROM national_claims_partition WHERE claim_id = %s",
        (claim_id,),
    )
    for item in payload.get("partitions") or []:
        cursor.execute(
            """
            INSERT INTO national_claims_partition (
                national_universe_id, claim_id, partition_id, expected, attempted,
                status, pages_fetched, pages_expected, records, pagination_complete,
                request_complete, raw_ref, evidence_ref, checked_at, as_of,
                freshness_status, identity_mapped, reason, next_action
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                payload["national_universe_id"],
                claim_id,
                item["partition_id"],
                item["expected"],
                item["attempted"],
                item["status"],
                item.get("pages_fetched"),
                item.get("pages_expected"),
                item.get("records"),
                item.get("pagination_complete"),
                item.get("request_complete"),
                item.get("raw_ref"),
                item.get("evidence_ref"),
                item.get("checked_at"),
                item.get("as_of"),
                item.get("freshness_status"),
                item.get("identity_mapped"),
                item.get("reason"),
                item.get("next_action"),
            ),
        )


def _replace_evidence(cursor: Any, request: ClaimRequest, claim_id: str) -> None:
    cursor.execute(
        "DELETE FROM national_claims_aggregate_evidence WHERE claim_id = %s",
        (claim_id,),
    )
    cursor.execute(
        "DELETE FROM national_claims_identity_evidence WHERE claim_id = %s",
        (claim_id,),
    )
    for row in request.evidence:
        _insert_evidence(cursor, claim_id, row)


def _insert_evidence(cursor: Any, claim_id: str, row: EvidenceRow) -> None:
    kind = classify_row(row)
    if kind == "IDENTITY_MAPPED":
        cursor.execute(
            """
            INSERT INTO national_claims_identity_evidence (
                claim_id, entity_id, canonical_entity_key, source,
                identity_class, partition_id, evidence_ref, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                claim_id,
                str(row.entity_id or row.canonical_entity_key),
                row.canonical_entity_key,
                row.source,
                kind,
                row.partition_id,
                row.evidence_ref,
                json.dumps(row.metadata),
            ),
        )
        return
    cursor.execute(
        """
        INSERT INTO national_claims_aggregate_evidence (
            claim_id, source, data_type, state, count_obtained, count_persisted,
            metadata, identity_class, reason_code, raw_ref
        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
        """,
        (
            claim_id,
            row.source,
            row.data_type,
            row.state,
            row.count_obtained,
            row.count_persisted,
            json.dumps(row.metadata),
            kind,
            ("unmappable_evidence_cannot_drop" if kind == "UNMAPPABLE" else "aggregated_evidence_not_entity_coverage"),
            row.raw_ref,
        ),
    )
