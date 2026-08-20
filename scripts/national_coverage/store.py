"""Optional persist/replay of coverage answers. MagicMock is refused."""

from __future__ import annotations

import json
from typing import Any

from scripts.national_coverage.adapters import CONSUMER_SELECT_SQL
from scripts.national_coverage.models import NationalCoverageError
from scripts.testing.connection_policy import connection_kind

REQUIRED_TABLES = (
    "national_coverage_universe",
    "national_coverage_partition",
    "national_coverage_corpus_snapshot",
    "national_coverage_answer",
)


def _refuse_mock(conn: object) -> None:
    if connection_kind(conn) == "MagicMock":
        raise NationalCoverageError("refusing MagicMock as PostgreSQL")


def persist_coverage(conn: Any, payload: dict[str, Any]) -> None:
    _refuse_mock(conn)
    consumer = payload["consumer"]
    universe = payload["universe"]
    corpus = payload.get("corpus") or {}
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO national_coverage_universe (
                universe_id, universe_kind, official_source, official_source_url,
                competence, cutoff, as_of, raw_hash, catalog_hash, method_version,
                schema_version, grain, expected_partitions, expected_units,
                official_status, official_block_cause, inclusion_rules,
                exclusion_rules, owner, next_refresh, payload
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s::jsonb,
                %s::jsonb, %s, %s, %s::jsonb
            )
            ON CONFLICT (universe_id) DO UPDATE SET
                catalog_hash = EXCLUDED.catalog_hash,
                payload = EXCLUDED.payload
            """,
            (
                universe["national_universe_id"],
                universe["universe_kind"],
                universe["official_source"],
                universe.get("official_source_url"),
                universe["competence"],
                universe["cutoff"],
                universe["as_of"],
                universe["raw_hash"],
                universe["catalog_hash"],
                universe["method_version"],
                universe["schema_version"],
                universe["grain"],
                universe["expected_partitions"],
                universe["expected_units"],
                universe["official_status"],
                universe.get("official_block_cause"),
                json.dumps(universe.get("inclusion_rules") or []),
                json.dumps(universe.get("exclusion_rules") or []),
                universe["owner"],
                universe["next_refresh"],
                json.dumps(universe),
            ),
        )
        if corpus:
            cursor.execute(
                """
                INSERT INTO national_coverage_corpus_snapshot (
                    snapshot_id, universe_id, snapshot_hash, as_of, source,
                    publisher_count, contract_count, relation, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (snapshot_id) DO NOTHING
                """,
                (
                    corpus.get("snapshot_id"),
                    universe["national_universe_id"],
                    corpus.get("snapshot_hash"),
                    corpus.get("as_of"),
                    corpus.get("source"),
                    corpus.get("publisher_count"),
                    corpus.get("contract_count"),
                    corpus.get("relation"),
                    json.dumps(corpus),
                ),
            )
        for status, count in (payload.get("partitions") or {}).get("by_status", {}).items():
            cursor.execute(
                """
                INSERT INTO national_coverage_partition (
                    universe_id, partition_id, status, expected, queried, count_in_status
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    universe["national_universe_id"],
                    f"aggregate:{status}",
                    status,
                    True,
                    status != "NOT_APPLICABLE",
                    int(count),
                ),
            )
        cursor.execute(
            """
            INSERT INTO national_coverage_answer (
                universe_id, requested_geography, requested_period, requested_source,
                requested_grain, expected_partitions, closed_partitions, queried_partitions,
                coverage_pct, national_claim_authorized, verdict, reason_codes,
                limitations, provenance, content_hash, payload
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s::jsonb, %s, %s::jsonb
            )
            """,
            (
                consumer["universe_id"],
                consumer["requested_geography"],
                consumer["requested_period"],
                consumer["requested_source"],
                consumer["requested_grain"],
                consumer["expected_partitions"],
                consumer["closed_partitions"],
                consumer["queried_partitions"],
                consumer.get("coverage_pct"),
                consumer["national_claim_authorized"],
                consumer["verdict"],
                list(consumer.get("reason_codes") or []),
                list(consumer.get("limitations") or []),
                json.dumps(consumer.get("provenance") or {}),
                consumer["content_hash"],
                json.dumps(consumer),
            ),
        )
    finally:
        closer = getattr(cursor, "close", None)
        if callable(closer):
            closer()


def select_consumer_answer(
    conn: Any,
    *,
    universe_id: str,
    geography: str,
    period: str,
    source: str,
    grain: str,
) -> dict[str, Any] | None:
    _refuse_mock(conn)
    cursor = conn.cursor()
    try:
        cursor.execute(
            CONSUMER_SELECT_SQL,
            (universe_id, geography, period, source, grain),
        )
        row = cursor.fetchone()
    finally:
        closer = getattr(cursor, "close", None)
        if callable(closer):
            closer()
    if not row:
        return None
    columns = [
        "requested_geography",
        "requested_period",
        "requested_source",
        "requested_grain",
        "universe_id",
        "expected_partitions",
        "closed_partitions",
        "coverage_pct",
        "national_claim_authorized",
        "verdict",
        "reason_codes",
        "limitations",
        "provenance",
        "content_hash",
    ]
    return dict(zip(columns, row, strict=False))
