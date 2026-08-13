"""Transactional canonical document/version metadata over off-database CAS blobs."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.crawl.resilience.diagnostics import sanitize_url


@dataclass(frozen=True)
class PersistedDocumentVersion:
    document_id: str
    document_version_id: str
    version_no: int
    source_fetch_id: int
    process_id: int
    changed: bool
    blob_confirmed: bool
    metadata_confirmed: bool


def _verify_blob(path: Path, *, expected_sha256: str, expected_size: int) -> None:
    body = path.read_bytes()
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected_sha256:
        raise ValueError(f"document blob sha256 mismatch: expected={expected_sha256} actual={actual}")
    if len(body) != expected_size:
        raise ValueError(f"document blob size mismatch: expected={expected_size} actual={len(body)}")
    if not body:
        raise ValueError("document blob must not be empty")


def persist_document_version(
    connection: Any,
    *,
    entity_id: int,
    source: str,
    official_id: str | None,
    canonical_key: str,
    category: str,
    title: str | None,
    official_url: str,
    process_official_id: str,
    process_url: str | None,
    source_version: str,
    sha256: str,
    size_bytes: int,
    body_uri: str,
    blob_path: Path,
    mime_type: str | None = None,
    document_run_id: str | None = None,
    crawl_job_attempt_id: int | None = None,
    http_status: int | None = 200,
    fetched_at: datetime | None = None,
) -> PersistedDocumentVersion:
    if not body_uri.startswith("cas://"):
        raise ValueError("document body_uri must be content-addressed")
    _verify_blob(blob_path, expected_sha256=sha256, expected_size=size_bytes)
    observed = (fetched_at or datetime.now(UTC)).astimezone(UTC)
    safe_url = sanitize_url(official_url)
    if not safe_url or safe_url == "<invalid-url>":
        raise ValueError("document official_url must be a valid sanitized URL")

    document_key = hashlib.sha256(f"{source}|{canonical_key}".encode()).hexdigest()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO procurement_processes (
                entity_id, source, official_id, canonical_url
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (entity_id, source, official_id) DO UPDATE
            SET canonical_url = COALESCE(EXCLUDED.canonical_url, procurement_processes.canonical_url),
                updated_at = now()
            RETURNING id
            """,
            (entity_id, source, process_official_id, sanitize_url(process_url)),
        )
        process_id = int(cursor.fetchone()["id"])
        cursor.execute(
            """
            INSERT INTO documents (
                id, entity_id, source, official_id, canonical_key,
                category, title, official_url, metadata_complete
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE)
            ON CONFLICT (source, canonical_key) DO UPDATE
            SET official_id = COALESCE(EXCLUDED.official_id, documents.official_id),
                category = EXCLUDED.category,
                title = COALESCE(EXCLUDED.title, documents.title),
                official_url = EXCLUDED.official_url,
                updated_at = now()
            WHERE documents.entity_id = EXCLUDED.entity_id
            RETURNING id
            """,
            (
                document_key,
                entity_id,
                source,
                official_id,
                canonical_key,
                category,
                title,
                safe_url,
            ),
        )
        document_row = cursor.fetchone()
        if not document_row:
            raise ValueError(
                "document canonical key already belongs to a different entity: "
                f"source={source} canonical_key={canonical_key}"
            )
        document_id = str(document_row["id"])
        cursor.execute("SELECT current_version FROM documents WHERE id = %s FOR UPDATE", (document_id,))
        current_version = int(cursor.fetchone()["current_version"])
        cursor.execute(
            """
            INSERT INTO source_fetches (
                source, sanitized_url, document_run_id, crawl_job_attempt_id,
                status, http_status, blob_confirmed, metadata_confirmed, fetched_at
            ) VALUES (%s, %s, %s, %s, 'failed', %s, TRUE, FALSE, %s)
            RETURNING id
            """,
            (source, safe_url, document_run_id, crawl_job_attempt_id, http_status, observed),
        )
        source_fetch_id = int(cursor.fetchone()["id"])
        cursor.execute(
            """
            SELECT id, version
            FROM document_versions
            WHERE document_id = %s AND sha256 = %s
            """,
            (document_id, sha256),
        )
        existing = cursor.fetchone()
        changed = existing is None
        if existing:
            version_id = str(existing["id"])
            version_no = int(existing["version"])
        else:
            version_no = current_version + 1
            version_id = f"{document_id}:v{version_no}:{sha256[:16]}"
            cursor.execute(
                """
                INSERT INTO document_versions (
                    id, document_id, version, source_version, sha256,
                    size_bytes, body_uri, mime_type, source_fetch_id,
                    fetched_at, metadata_complete
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                """,
                (
                    version_id,
                    document_id,
                    version_no,
                    source_version,
                    sha256,
                    size_bytes,
                    body_uri,
                    mime_type,
                    source_fetch_id,
                    observed,
                ),
            )
        cursor.execute(
            """
            UPDATE documents
            SET current_version = GREATEST(current_version, %s),
                metadata_complete = TRUE, updated_at = now()
            WHERE id = %s
            """,
            (version_no, document_id),
        )
        cursor.execute(
            """
            INSERT INTO process_document_links (
                process_id, document_id, document_version_id, relationship
            ) VALUES (%s, %s, %s, 'attachment')
            ON CONFLICT (process_id, document_version_id) DO NOTHING
            """,
            (process_id, document_id, version_id),
        )
        cursor.execute(
            """
            UPDATE source_fetches
            SET status = 'success', metadata_confirmed = TRUE
            WHERE id = %s AND blob_confirmed = TRUE
            """,
            (source_fetch_id,),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("document metadata confirmation failed")
    return PersistedDocumentVersion(
        document_id=document_id,
        document_version_id=version_id,
        version_no=version_no,
        source_fetch_id=source_fetch_id,
        process_id=process_id,
        changed=changed,
        blob_confirmed=True,
        metadata_confirmed=True,
    )


def load_process_lineage(connection: Any, *, entity_id: int, source: str, official_id: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id AS process_id, p.entity_id, p.source,
                   p.official_id AS process_official_id,
                   d.id AS document_id, d.official_id AS document_official_id,
                   d.canonical_key, d.category, d.official_url,
                   v.id AS document_version_id, v.version AS version_no,
                   v.source_version, v.sha256, v.size_bytes, v.body_uri,
                   v.fetched_at, f.document_run_id, f.crawl_job_attempt_id
            FROM procurement_processes p
            JOIN process_document_links link ON link.process_id = p.id
            JOIN documents d ON d.id = link.document_id
            JOIN document_versions v ON v.id = link.document_version_id
            JOIN source_fetches f ON f.id = v.source_fetch_id
            WHERE p.entity_id = %s AND p.source = %s AND p.official_id = %s
            ORDER BY d.id, v.version
            """,
            (entity_id, source, official_id),
        )
        return [dict(row) for row in cursor.fetchall() or []]
