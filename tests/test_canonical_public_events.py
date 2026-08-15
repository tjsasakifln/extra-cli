"""Real PostgreSQL proofs for canonical multifonte bitemporal events (#273/#289)."""

from __future__ import annotations

import hashlib
import json
import os
from itertools import permutations

import pytest

pytestmark = [
    pytest.mark.real_db,
    pytest.mark.skipif(
        os.getenv("REQUIRE_REAL_DB") != "1",
        reason="Set REQUIRE_REAL_DB=1 for canonical public events proofs",
    ),
]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _connect():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    return psycopg2.connect(os.environ["LOCAL_DATALAKE_DSN"], cursor_factory=RealDictCursor)


def _observation(
    *,
    source: str,
    record: str,
    raw: str,
    process: str = "test-canonical:process:001",
    event_type: str = "tender_publication",
    valid_from: str = "2026-01-01T00:00:00Z",
    facts: dict | None = None,
    source_version: str = "v1",
    document_version: str | None = None,
) -> dict:
    return {
        "source": source,
        "source_record_id": record,
        "source_version": source_version,
        "raw_sha256": _hash(raw),
        "process_key": process,
        "event_type": event_type,
        "observed_at": "2026-08-13T12:00:00Z",
        "valid_from": valid_from,
        "document_version": document_version,
        "snapshot_id": "test-canonical-snapshot",
        "policy_version": "test-canonical-policy-v1",
        "facts": facts
        or {
            "status_code": "PUBLISHED",
            "title": "Aquisição de material escolar",
            "publication_at": "2026-01-01T00:00:00Z",
            "official_number": "PNCP-001",
        },
        "entities": [
            {
                "entity_type": "organ",
                "strong_key": "cnpj:11222333000181",
                "display_name": "Órgão teste",
                "tax_identifier_type": "CNPJ",
                "tax_identifier_export": "11222333000181",
                "relation_type": "buyer",
                "confidence": 1,
            }
        ],
    }


def _ingest(cursor, payload: dict) -> dict:
    cursor.execute(
        "SELECT ingest_canonical_public_observation_v1(%s::JSONB) AS result",
        (json.dumps(payload, sort_keys=True),),
    )
    return dict(cursor.fetchone()["result"])


def _cleanup(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL app.allow_canonical_test_cleanup = 'on'")
        cursor.execute(
            "DELETE FROM canonical_match_conflicts WHERE observation_id IN (SELECT observation_id FROM canonical_public_observations WHERE source LIKE 'test_canonical_%')"
        )
        cursor.execute("DELETE FROM canonical_identity_decisions WHERE decided_by = 'test-canonical'")
        cursor.execute(
            "DELETE FROM canonical_event_entity_links WHERE observation_id IN (SELECT observation_id FROM canonical_public_observations WHERE source LIKE 'test_canonical_%')"
        )
        cursor.execute(
            "DELETE FROM canonical_event_observation_links WHERE observation_id IN (SELECT observation_id FROM canonical_public_observations WHERE source LIKE 'test_canonical_%')"
        )
        cursor.execute(
            "DELETE FROM canonical_event_revisions WHERE created_from_observation_id IN (SELECT observation_id FROM canonical_public_observations WHERE source LIKE 'test_canonical_%')"
        )
        cursor.execute("DELETE FROM canonical_public_observations WHERE source LIKE 'test_canonical_%'")
        cursor.execute("DELETE FROM canonical_public_events_v1 WHERE process_key LIKE 'test-canonical:%'")
        cursor.execute(
            "DELETE FROM canonical_public_entity_aliases_v2 WHERE source LIKE 'test_canonical_%' OR entity_id IN (SELECT entity_id FROM canonical_public_entities_v2 WHERE strong_key LIKE 'test-canonical:%')"
        )
        cursor.execute("DELETE FROM canonical_public_entities_v2 WHERE strong_key LIKE 'test-canonical:%'")
        cursor.execute(
            "DELETE FROM canonical_public_entities_v2 WHERE created_by_policy LIKE 'test-canonical-%' AND NOT EXISTS (SELECT 1 FROM canonical_event_entity_links link WHERE link.entity_id = canonical_public_entities_v2.entity_id)"
        )
    connection.commit()


def _cleanup_snapshots(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL app.allow_canonical_test_cleanup = 'on'")
        cursor.execute("DELETE FROM canonical_snapshot_invalidations WHERE snapshot_id IN (SELECT snapshot_id FROM canonical_public_snapshots WHERE created_by = 'test-canonical-snapshot')")
        cursor.execute("DELETE FROM public_consumer_projections WHERE snapshot_id IN (SELECT snapshot_id FROM canonical_public_snapshots WHERE created_by = 'test-canonical-snapshot')")
        cursor.execute("DELETE FROM canonical_snapshot_dossiers WHERE snapshot_id IN (SELECT snapshot_id FROM canonical_public_snapshots WHERE created_by = 'test-canonical-snapshot')")
        cursor.execute("DELETE FROM canonical_snapshot_documents WHERE snapshot_id IN (SELECT snapshot_id FROM canonical_public_snapshots WHERE created_by = 'test-canonical-snapshot')")
        cursor.execute("DELETE FROM canonical_snapshot_event_revisions WHERE snapshot_id IN (SELECT snapshot_id FROM canonical_public_snapshots WHERE created_by = 'test-canonical-snapshot')")
        cursor.execute("DELETE FROM canonical_snapshot_source_watermarks WHERE snapshot_id IN (SELECT snapshot_id FROM canonical_public_snapshots WHERE created_by = 'test-canonical-snapshot')")
        cursor.execute("DELETE FROM canonical_public_snapshots WHERE created_by = 'test-canonical-snapshot'")
    connection.commit()


def _summary(cursor) -> dict:
    cursor.execute(
        """
        SELECT jsonb_build_object(
            'events', (SELECT count(*) FROM canonical_public_events_v1 WHERE process_key LIKE 'test-canonical:%'),
            'observations', (SELECT count(*) FROM canonical_public_observations WHERE source LIKE 'test_canonical_%'),
            'links', (SELECT count(*) FROM canonical_event_observation_links link JOIN canonical_public_observations obs USING (observation_id) WHERE obs.source LIKE 'test_canonical_%'),
            'revisions', (SELECT count(*) FROM canonical_event_revisions revision JOIN canonical_public_events_v1 event USING (event_id) WHERE event.process_key LIKE 'test-canonical:%'),
            'hash', encode(digest(COALESCE((
                SELECT string_agg(value, '|' ORDER BY value) FROM (
                    SELECT event_id AS value FROM canonical_public_events_v1 WHERE process_key LIKE 'test-canonical:%'
                    UNION ALL SELECT observation_id FROM canonical_public_observations WHERE source LIKE 'test_canonical_%'
                    UNION ALL SELECT revision_id FROM canonical_event_revisions revision JOIN canonical_public_events_v1 event USING (event_id) WHERE event.process_key LIKE 'test-canonical:%'
                ) values_to_hash
            ), ''), 'sha256'), 'hex')
        ) AS result
        """
    )
    return dict(cursor.fetchone()["result"])


def test_multisource_order_duplicates_document_versions_and_second_event_type_are_stable() -> None:
    connection = _connect()
    first = _observation(source="test_canonical_pncp", record="pncp-001", raw="pncp-body")
    second = _observation(source="test_canonical_dom", record="dom-001", raw="dom-body")
    summaries: list[dict] = []
    returned_ids: list[tuple[str, str]] = []
    try:
        for order in permutations((first, second)):
            _cleanup(connection)
            with connection.cursor() as cursor:
                results = [_ingest(cursor, payload) for payload in order]
                # Repeating the exact snapshot is a no-op on IDs/counts/hashes.
                repeated = [_ingest(cursor, payload) for payload in order]
                assert results == repeated
                assert results[0]["event_id"] == results[1]["event_id"]
                assert results[0]["event_id"].startswith("evt_") and len(results[0]["event_id"]) == 36
                assert "client" not in results[0]["event_id"]
                returned_ids.append((results[0]["event_id"], results[0]["revision_id"]))
                summary = _summary(cursor)
                assert summary | {"events": 1, "observations": 2, "links": 2, "revisions": 1} == summary
                summaries.append(summary)
            connection.commit()

        assert summaries[0] == summaries[1]
        assert returned_ids[0] == returned_ids[1]

        with connection.cursor() as cursor:
            contract = _observation(
                source="test_canonical_pncp",
                record="contract-001",
                raw="contract-body",
                event_type="contract_lifecycle",
                facts={
                    "status_code": "SIGNED",
                    "title": "Contrato de material escolar",
                    "contract_value": "12345.67",
                    "official_number": "CONTRACT-001",
                },
            )
            contract_result = _ingest(cursor, contract)
            assert contract_result["event_id"] != returned_ids[0][0]
            cursor.execute(
                "SELECT count(DISTINCT event_type) AS count FROM canonical_public_events_v1 WHERE process_key = 'test-canonical:process:001'"
            )
            assert int(cursor.fetchone()["count"]) == 2
            cursor.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND indexname LIKE 'idx_canonical_%'"
            )
            indexes = {row["indexname"] for row in cursor.fetchall()}
            assert {"idx_canonical_events_process_v1", "idx_canonical_revision_asof", "idx_canonical_observations_source"} <= indexes
            cursor.execute("SET LOCAL enable_seqscan = off")
            cursor.execute(
                "EXPLAIN (FORMAT JSON) SELECT * FROM canonical_public_events_v1 WHERE process_key = 'test-canonical:process:001'"
            )
            assert "idx_canonical_events_process_v1" in json.dumps(cursor.fetchone())

            forbidden = dict(contract)
            forbidden["source_record_id"] = "forbidden-client"
            forbidden["raw_sha256"] = _hash("forbidden-client")
            forbidden["client_id"] = "customer-42"
            cursor.execute("SAVEPOINT forbidden_client")
            with pytest.raises(Exception, match="client_id is forbidden"):
                _ingest(cursor, forbidden)
            cursor.execute("ROLLBACK TO SAVEPOINT forbidden_client")
        connection.commit()
    finally:
        connection.rollback()
        _cleanup(connection)
        connection.close()


def test_bitemporal_asof_ambiguous_conflict_merge_split_and_immutability() -> None:
    import psycopg2

    connection = _connect()
    try:
        with connection.cursor() as cursor:
            open_status = _observation(
                source="test_canonical_pncp",
                record="status-001",
                raw="status-open",
                event_type="tender_status",
                valid_from="2026-01-01T00:00:00Z",
                facts={"status_code": "OPEN", "title": "Processo teste"},
            )
            cancelled = _observation(
                source="test_canonical_pncp",
                record="status-001",
                raw="status-cancelled",
                source_version="v2",
                event_type="tender_status",
                valid_from="2026-02-01T00:00:00Z",
                facts={"status_code": "CANCELLED", "title": "Processo teste retificado"},
            )
            first = _ingest(cursor, open_status)
            second = _ingest(cursor, cancelled)
            assert first["event_id"] == second["event_id"]
            cursor.execute(
                "SELECT status_code FROM canonical_event_revision_as_of_v1(%s, '2026-01-15', NOW())",
                (first["event_id"],),
            )
            assert cursor.fetchone()["status_code"] == "OPEN"
            cursor.execute(
                "SELECT status_code FROM canonical_event_revision_as_of_v1(%s, '2026-02-15', NOW())",
                (first["event_id"],),
            )
            assert cursor.fetchone()["status_code"] == "CANCELLED"

            for version in (1, 2):
                document = _observation(
                    source="test_canonical_dom",
                    record="document-001",
                    raw=f"document-body-v{version}",
                    source_version=f"v{version}",
                    document_version=str(version),
                    event_type="tender_document_change",
                    valid_from=f"2026-0{version}-10T00:00:00Z",
                    facts={
                        "status_code": "PUBLISHED",
                        "title": f"Edital versão {version}",
                        "document_sha256": _hash(f"document-v{version}"),
                    },
                )
                _ingest(cursor, document)
            cursor.execute(
                "SELECT count(*) AS count FROM canonical_event_revisions revision JOIN canonical_public_events_v1 event USING (event_id) WHERE event.event_type = 'tender_document_change' AND event.process_key = 'test-canonical:process:001'"
            )
            assert int(cursor.fetchone()["count"]) == 2

            ambiguous = _observation(
                source="test_canonical_other",
                record="ambiguous-001",
                raw="ambiguous-body",
                process="",
            )
            ambiguous.update(
                {
                    "match_state": "AMBIGUOUS",
                    "candidate_event_ids": [first["event_id"], second["event_id"] + "-candidate"],
                    "reason_codes": ["same_number_different_organs"],
                }
            )
            conflict = _ingest(cursor, ambiguous)
            assert conflict["state"] == "CONFLICT" and conflict["event_id"] is None
            weak = _observation(source="test_canonical_other", record="weak-001", raw="weak-body")
            weak["match_state"] = "WEAK"
            cursor.execute("SAVEPOINT match_state_rejected")
            with pytest.raises(Exception, match="match_state"):
                _ingest(cursor, weak)
            cursor.execute("ROLLBACK TO SAVEPOINT match_state_rejected")
            cursor.execute(
                "SELECT status FROM canonical_match_conflicts WHERE conflict_id = %s",
                (conflict["conflict_id"],),
            )
            assert cursor.fetchone()["status"] == "OPEN"
            cursor.execute(
                "SELECT count(*) AS count FROM canonical_event_observation_links WHERE observation_id = %s",
                (conflict["observation_id"],),
            )
            assert int(cursor.fetchone()["count"]) == 0

            source_entity = first["process_entity_id"]
            target_entity = cursor.execute(
                "SELECT ensure_canonical_public_entity_v2('process', 'test-canonical:merge-target', 'Target', NULL, NULL, 'test_canonical_manual', 'target', 'test-policy') AS id"
            )
            target_entity = cursor.fetchone()["id"]
            merge_id = cursor.execute(
                "SELECT record_canonical_identity_decision_v1('MERGE', %s, %s, '{}', 'confirmed duplicate', ARRAY[%s], 'test-policy', 'test-canonical') AS id",
                (source_entity, target_entity, first["observation_id"]),
            )
            merge_id = cursor.fetchone()["id"]
            cursor.execute(
                "SELECT count(*) AS count FROM canonical_event_entity_links WHERE event_id = %s AND entity_id = %s",
                (first["event_id"], source_entity),
            )
            assert int(cursor.fetchone()["count"]) > 0
            cursor.execute("SELECT state, canonical_successor_id FROM canonical_public_entities_v2 WHERE entity_id = %s", (source_entity,))
            merged_state = cursor.fetchone()
            assert (merged_state["state"], merged_state["canonical_successor_id"]) == ("MERGED", target_entity)

            split_source = cursor.execute(
                "SELECT ensure_canonical_public_entity_v2('organ', 'test-canonical:split-source', 'Split source', NULL, NULL, 'test_canonical_manual', 'split-source', 'test-policy') AS id"
            )
            split_source = cursor.fetchone()["id"]
            split_target = cursor.execute(
                "SELECT ensure_canonical_public_entity_v2('organ', 'test-canonical:split-target', 'Split target', NULL, NULL, 'test_canonical_manual', 'split-target', 'test-policy') AS id"
            )
            split_target = cursor.fetchone()["id"]
            split_id = cursor.execute(
                "SELECT record_canonical_identity_decision_v1('SPLIT', %s, %s, ARRAY['test-canonical:split-source'], 'independent official key', ARRAY[%s], 'test-policy', 'test-canonical') AS id",
                (split_source, split_target, first["observation_id"]),
            )
            split_id = cursor.fetchone()["id"]
            assert merge_id != split_id
            cursor.execute(
                "SELECT count(*) AS count FROM canonical_public_entity_aliases_v2 WHERE alias_value = 'test-canonical:split-source'"
            )
            assert int(cursor.fetchone()["count"]) == 2

            cursor.execute("SAVEPOINT immutable_guard")
            with pytest.raises(psycopg2.errors.ObjectNotInPrerequisiteState):
                cursor.execute(
                    "UPDATE canonical_event_revisions SET status_code = 'FORGED' WHERE revision_id = %s",
                    (first["revision_id"],),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT immutable_guard")
        connection.commit()
    finally:
        connection.rollback()
        _cleanup(connection)
        connection.close()


def test_snapshot_barrier_repeatable_read_projection_invalidation_and_public_role() -> None:
    import psycopg2

    connection = _connect()
    hashes = [_hash(f"snapshot-input-{index}") for index in range(7)]
    try:
        _cleanup_snapshots(connection)
        _cleanup(connection)
        with connection.cursor() as cursor:
            observed = _ingest(
                cursor,
                _observation(
                    source="test_canonical_pncp",
                    record="snapshot-tender-001",
                    raw="snapshot-tender-v1",
                    event_type="tender_status",
                    facts={"status_code": "OPEN", "title": "Snapshot tender"},
                ),
            )
            cursor.execute(
                """
                SELECT begin_canonical_public_snapshot_v1(
                    '2026-08-13T12:00:00-03:00', %s, %s, %s, %s, %s, %s, %s,
                    1, 1, 'test-canonical-snapshot'
                ) AS id
                """,
                tuple(hashes),
            )
            snapshot_id = cursor.fetchone()["id"]
            cursor.execute("SELECT close_canonical_public_snapshot_v1(%s) AS result", (snapshot_id,))
            blocked = cursor.fetchone()["result"]
            assert blocked["state"] == "BLOCKED"
            assert {"missing_source_watermarks", "applicable_pairs_not_evaluated", "relevant_dossiers_not_complete"} <= set(
                blocked["blockers"]
            )

            cursor.execute(
                "SELECT put_canonical_snapshot_watermark_v1(%s, 'pncp', 'run-001', '2026-08-13T11:59:00-03:00', 'FRESH', 'COMPLETE', 1, 1, %s)",
                (snapshot_id, _hash("watermark-evidence")),
            )
            cursor.execute(
                """
                INSERT INTO canonical_snapshot_event_revisions (snapshot_id, event_id, revision_id, fact_hash)
                SELECT %s, event_id, revision_id, fact_hash FROM canonical_event_revisions WHERE revision_id = %s
                """,
                (snapshot_id, observed["revision_id"]),
            )
            cursor.execute(
                "INSERT INTO canonical_snapshot_documents VALUES (%s, %s, %s, 'COMPLETE')",
                (snapshot_id, observed["observation_id"], _hash("snapshot-document")),
            )
            cursor.execute(
                "INSERT INTO canonical_snapshot_dossiers VALUES (%s, 'dossier-001', %s, 'COMPLETE', '{}')",
                (snapshot_id, _hash("dossier-revision")),
            )
            cursor.execute("SELECT close_canonical_public_snapshot_v1(%s) AS result", (snapshot_id,))
            ready = cursor.fetchone()["result"]
            assert ready["state"] == "READY_CANONICAL"
            content_hash = ready["content_hash"]
            cursor.execute(
                """
                SELECT count(*) AS count
                FROM public_read_surface_health_internal
                WHERE enabled AND last_refresh_status = 'VALID' AND refreshed_at IS NOT NULL
                """
            )
            assert int(cursor.fetchone()["count"]) == 6
            cursor.execute(
                """
                SELECT last_refresh_status FROM public_read_surface_health_internal
                WHERE view_name = 'municipalities'
                """
            )
            assert cursor.fetchone()["last_refresh_status"] == "STALE"

            cursor.execute(
                """
                INSERT INTO public_consumer_projections
                    (projection_id, consumer_id, snapshot_id, template_hash, private_profile_hash)
                VALUES ('projection-private', 'smartlic-test-private', %s, %s, %s),
                       ('projection-factual', 'smartlic-test-factual', %s, %s, NULL)
                """,
                (snapshot_id, _hash("template-v1"), _hash("private-v1"), snapshot_id, _hash("template-v1")),
            )
            cursor.execute(
                "SELECT invalidate_consumer_projection_private_v1('projection-private', %s, %s)",
                (_hash("template-v2"), _hash("private-v2")),
            )
            cursor.execute("SELECT state FROM public_consumer_projections WHERE projection_id = 'projection-private'")
            assert cursor.fetchone()["state"] == "STALE_PRIVATE"
            cursor.execute("SELECT state, content_hash FROM canonical_public_snapshots WHERE snapshot_id = %s", (snapshot_id,))
            assert tuple(cursor.fetchone().values()) == ("READY_CANONICAL", content_hash)
        connection.commit()

        reader = _connect()
        writer = _connect()
        try:
            reader.set_session(isolation_level="REPEATABLE READ", readonly=True, autocommit=False)
            with reader.cursor() as cursor:
                cursor.execute("SELECT snapshot_id, content_hash, count(*) OVER () AS rows FROM public_read_v1.current_snapshot")
                before = dict(cursor.fetchone())
                cursor.execute("SELECT count(*) AS count FROM public_read_v1.tenders")
                tender_count_before = int(cursor.fetchone()["count"])

            with writer.cursor() as cursor:
                corrected = _observation(
                    source="test_canonical_pncp",
                    record="snapshot-tender-001",
                    raw="snapshot-tender-v2-after-cutoff",
                    source_version="v2",
                    event_type="tender_status",
                    valid_from="2026-08-14T00:00:00Z",
                    facts={"status_code": "CANCELLED", "title": "Snapshot tender corrected"},
                )
                new_revision = _ingest(cursor, corrected)
            writer.commit()

            with reader.cursor() as cursor:
                cursor.execute("SELECT snapshot_id, content_hash, count(*) OVER () AS rows FROM public_read_v1.current_snapshot")
                after = dict(cursor.fetchone())
                cursor.execute("SELECT count(*) AS count FROM public_read_v1.tenders")
                assert int(cursor.fetchone()["count"]) == tender_count_before
            assert before == after == {"snapshot_id": snapshot_id, "content_hash": content_hash, "rows": 1}
            reader.commit()
        finally:
            reader.close()
            writer.close()

        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) AS count FROM canonical_snapshot_event_revisions WHERE snapshot_id = %s", (snapshot_id,))
            assert int(cursor.fetchone()["count"]) == 1
            cursor.execute("SELECT content_hash FROM canonical_public_snapshots WHERE snapshot_id = %s", (snapshot_id,))
            assert cursor.fetchone()["content_hash"] == content_hash
            cursor.execute("SELECT state FROM public_consumer_projections WHERE projection_id = 'projection-factual'")
            assert cursor.fetchone()["state"] == "STALE_FACTUAL"
            cursor.execute(
                "SELECT count(*) AS count FROM canonical_snapshot_invalidations WHERE snapshot_id = %s AND new_revision_id = %s",
                (snapshot_id, new_revision["revision_id"]),
            )
            assert int(cursor.fetchone()["count"]) == 1

            cursor.execute("SAVEPOINT immutable_snapshot")
            with pytest.raises(psycopg2.errors.ObjectNotInPrerequisiteState):
                cursor.execute(
                    "INSERT INTO canonical_snapshot_event_revisions (snapshot_id, event_id, revision_id, fact_hash) SELECT %s, event_id, revision_id, fact_hash FROM canonical_event_revisions WHERE revision_id = %s",
                    (snapshot_id, new_revision["revision_id"]),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT immutable_snapshot")

            blocked_hashes = list(hashes)
            blocked_hashes[4] = _hash("different-data-hash")
            cursor.execute(
                "SELECT begin_canonical_public_snapshot_v1('2026-08-14T12:00:00-03:00', %s, %s, %s, %s, %s, %s, %s, 1, 1, 'test-canonical-snapshot') AS id",
                tuple(blocked_hashes),
            )
            blocked_snapshot_id = cursor.fetchone()["id"]
            cursor.execute("SELECT close_canonical_public_snapshot_v1(%s)", (blocked_snapshot_id,))
            cursor.execute("SELECT snapshot_id FROM public_read_v1.current_snapshot")
            assert cursor.fetchone()["snapshot_id"] == snapshot_id

            cursor.execute("SELECT schema_hash FROM public_read_v1.contract_releases WHERE version = 'v1.0.0'")
            assert len(cursor.fetchone()["schema_hash"]) == 64
            cursor.execute("SELECT query_family FROM public_read_v1.query_budgets")
            families = {row["query_family"] for row in cursor.fetchall()}
            assert {
                "tenders_by_process",
                "contracts_by_process",
                "entities_by_id",
                "surface_health",
            } <= families

            cursor.execute("SET ROLE smartlic_public_reader")
            cursor.execute("SELECT count(*) AS count FROM public_read_v1.current_snapshot")
            assert int(cursor.fetchone()["count"]) == 1
            for statement in (
                "SELECT count(*) FROM public.canonical_public_snapshots",
                "INSERT INTO public_read_v1.query_budgets VALUES ('attack', 1, 1, 1, 1, 'attack')",
                "UPDATE public_read_v1.query_budgets SET max_rows = 1 WHERE query_family = 'surface_health'",
                "DELETE FROM public_read_v1.query_budgets WHERE query_family = 'surface_health'",
                "CREATE TABLE public_read_v1.attack(id integer)",
                "SELECT ingest_canonical_public_observation_v1('{}'::jsonb)",
                "SELECT upsert_pncp_raw_bids('[]'::jsonb)",
                "SELECT begin_canonical_public_snapshot_v1(NOW(), repeat('a', 64), repeat('b', 64), repeat('c', 64), repeat('d', 64), repeat('e', 64), repeat('f', 64), repeat('0', 64), 0, 0, 'attacker')",
            ):
                cursor.execute("SAVEPOINT permission_denied")
                with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                    cursor.execute(statement)
                cursor.execute("ROLLBACK TO SAVEPOINT permission_denied")
            cursor.execute("SELECT count(*) AS count FROM public_read_v1.municipalities")
            assert int(cursor.fetchone()["count"]) == 0
            cursor.execute("EXPLAIN (FORMAT JSON) SELECT * FROM public_read_v1.tenders WHERE process_key = 'test-canonical:process:001' LIMIT 100")
            assert cursor.fetchone() is not None
            cursor.execute("RESET ROLE")
        connection.commit()
    finally:
        connection.rollback()
        _cleanup_snapshots(connection)
        _cleanup(connection)
        connection.close()
