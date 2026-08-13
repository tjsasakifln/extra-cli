"""Canonical PostgreSQL document metadata and immutable version contracts."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from scripts.crawl.runtime_queue import connect
from scripts.process_documents.persistence import (
    load_process_lineage,
    persist_document_version,
)
from scripts.process_documents.storage import store_blob


def test_document_schema_keeps_bodies_out_of_postgresql() -> None:
    sql = Path("db/migrations/081_canonical_document_lineage.sql").read_text(encoding="utf-8")
    assert "REFERENCES sc_public_entities(id)" in sql
    assert "REFERENCES process_document_runs(run_id)" in sql
    assert "REFERENCES crawl_job_attempts(id)" in sql
    assert "body_uri" in sql
    assert "BODY BYTEA" not in sql.upper()
    assert "PAYLOAD JSON" not in sql.upper()
    assert "status <> 'success' OR (blob_confirmed AND metadata_confirmed)" in sql
    assert "duplicate (source, canonical_key) groups" in sql
    assert "duplicate document_versions groups" in sql


def test_document_persistence_rejects_unverified_blob(tmp_path: Path) -> None:
    blob = tmp_path / "blob.pdf"
    blob.write_bytes(b"different")
    with pytest.raises(ValueError, match="sha256 mismatch"):
        persist_document_version(
            object(),
            entity_id=1,
            source="pncp",
            official_id="doc-1",
            canonical_key="pncp:doc-1",
            category="notice",
            title="Edital",
            official_url="https://example.test/doc.pdf",
            process_official_id="process-1",
            process_url="https://example.test/process/1",
            source_version="v1",
            sha256="0" * 64,
            size_bytes=len(b"different"),
            body_uri="cas://process_documents/" + "0" * 64,
            blob_path=blob,
        )


def test_document_persistence_rejects_cross_entity_canonical_conflict(tmp_path: Path) -> None:
    blob = store_blob(b"verified", raw_root=tmp_path / "raw")
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.side_effect = [{"id": 10}, None]

    with pytest.raises(ValueError, match="different entity"):
        persist_document_version(
            connection,
            entity_id=2,
            source="pncp",
            official_id="doc-1",
            canonical_key="pncp:shared-doc",
            category="notice",
            title="Edital",
            official_url="https://example.test/doc.pdf",
            process_official_id="process-1",
            process_url="https://example.test/process/1",
            source_version="v1",
            sha256=blob.sha256,
            size_bytes=blob.size_bytes,
            body_uri=blob.raw_uri,
            blob_path=blob.path,
        )

    document_sql = cursor.execute.call_args_list[1].args[0]
    assert "WHERE documents.entity_id = EXCLUDED.entity_id" in document_sql


@pytest.mark.database
@pytest.mark.integration
def test_document_content_change_creates_immutable_version_and_lineage(tmp_path: Path) -> None:
    if not (
        os.getenv("REQUIRE_REAL_DB", "").lower() in {"1", "true", "yes"}
        or os.getenv("RESILIENCE_REQUIRE_DB", "").lower() in {"1", "true", "yes"}
    ):
        pytest.skip("REQUIRE_REAL_DB=1 or RESILIENCE_REQUIRE_DB=1 required")
    dsn = os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    if not dsn:
        pytest.skip("LOCAL_DATALAKE_DSN or DATABASE_URL not set")
    source = f"test_document_lineage_{uuid4().hex}"
    persisted_versions = []
    with connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id FROM sc_public_entities WHERE is_active ORDER BY id LIMIT 1")
        row = cursor.fetchone()
        if not row:
            pytest.fail("real database has no active entity")
        entity_id = int(row["id"])

    first_blob = store_blob(b"version-one", raw_root=tmp_path / "raw", extension="pdf")
    second_blob = store_blob(b"version-two", raw_root=tmp_path / "raw", extension="pdf")
    common = {
        "entity_id": entity_id,
        "source": source,
        "official_id": "official-doc-1",
        "canonical_key": f"test:{entity_id}:official-doc-1",
        "category": "notice",
        "title": "Official notice",
        "official_url": "https://example.test/doc.pdf?token=redacted-by-contract",
        "process_official_id": "process-1",
        "process_url": "https://example.test/process/1",
    }
    try:
        with connect(dsn) as connection:
            first = persist_document_version(
                connection,
                **common,
                source_version="v1",
                sha256=first_blob.sha256,
                size_bytes=first_blob.size_bytes,
                body_uri=first_blob.raw_uri,
                blob_path=first_blob.path,
            )
            persisted_versions.append(first)
        with connect(dsn) as connection:
            unchanged = persist_document_version(
                connection,
                **common,
                source_version="v1-repeat",
                sha256=first_blob.sha256,
                size_bytes=first_blob.size_bytes,
                body_uri=first_blob.raw_uri,
                blob_path=first_blob.path,
            )
            persisted_versions.append(unchanged)
        with connect(dsn) as connection:
            changed = persist_document_version(
                connection,
                **common,
                source_version="v2",
                sha256=second_blob.sha256,
                size_bytes=second_blob.size_bytes,
                body_uri=second_blob.raw_uri,
                blob_path=second_blob.path,
            )
            persisted_versions.append(changed)
            lineage = load_process_lineage(
                connection,
                entity_id=entity_id,
                source=source,
                official_id="process-1",
            )
        assert first.changed is True and first.version_no == 1
        assert unchanged.changed is False and unchanged.document_version_id == first.document_version_id
        assert changed.changed is True and changed.version_no == 2
        assert [row["sha256"] for row in lineage] == [first_blob.sha256, second_blob.sha256]
        assert all(str(row["body_uri"]).startswith("cas://") for row in lineage)
    finally:
        with connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM process_document_links WHERE process_id IN (SELECT id FROM procurement_processes WHERE source = %s)",
                (source,),
            )
            cursor.execute(
                "DELETE FROM document_versions WHERE document_id IN (SELECT id FROM documents WHERE source = %s)",
                (source,),
            )
            cursor.execute("DELETE FROM documents WHERE source = %s", (source,))
            cursor.execute("DELETE FROM procurement_processes WHERE source = %s", (source,))
            if persisted_versions:
                cursor.execute(
                    "DELETE FROM source_fetches WHERE id = ANY(%s)",
                    ([row.source_fetch_id for row in persisted_versions],),
                )
