"""Refs #272 — versioned document metadata; job success needs blob + metadata."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.factory_spine.store import FactoryStore, persist_document_metadata


def test_issue_272_content_change_creates_version_without_overwrite(tmp_path: Path) -> None:
    store = FactoryStore(tmp_path)
    first = store.persist_document(
        entity_id=10,
        source="pncp",
        official_id="doc-1",
        body=b"edital-v1",
        official_url="https://pncp.gov.br/docs/doc-1.pdf?token=secret",
        process_official_id="proc-1",
        crawl_job_attempt_id=3,
    )
    same = store.persist_document(
        entity_id=10,
        source="pncp",
        official_id="doc-1",
        body=b"edital-v1",
        official_url="https://pncp.gov.br/docs/doc-1.pdf?token=secret",
        process_official_id="proc-1",
    )
    second = store.persist_document(
        entity_id=10,
        source="pncp",
        official_id="doc-1",
        body=b"edital-v2-changed",
        official_url="https://pncp.gov.br/docs/doc-1.pdf",
        process_official_id="proc-1",
        crawl_job_attempt_id=4,
    )
    assert first["changed"] is True
    assert same["changed"] is False
    assert same["version_no"] == first["version_no"]
    assert second["changed"] is True
    assert second["version_no"] == first["version_no"] + 1
    assert second["sha256"] != first["sha256"]
    assert first["blob_confirmed"] is True
    assert first["metadata_confirmed"] is True
    assert first["body_uri"].startswith("cas://")
    documents = store._read_documents()
    assert len(documents) == 1
    assert len(documents[0]["versions"]) == 2


def test_issue_272_job_cannot_succeed_without_confirmed_blob() -> None:
    with pytest.raises(ValueError, match="confirmed blob"):
        persist_document_metadata(
            [],
            entity_id=1,
            source="pncp",
            official_id="doc-x",
            sha256="a" * 64,
            size_bytes=4,
            body_uri="cas://process_documents/" + "a" * 64,
            blob_confirmed=False,
            official_url="https://example.test/doc.pdf",
            process_official_id="proc-x",
        )
    with pytest.raises(ValueError, match="content-addressed"):
        persist_document_metadata(
            [],
            entity_id=1,
            source="pncp",
            official_id="doc-x",
            sha256="a" * 64,
            size_bytes=4,
            body_uri="postgres://payload",
            blob_confirmed=True,
            official_url="https://example.test/doc.pdf",
            process_official_id="proc-x",
        )
