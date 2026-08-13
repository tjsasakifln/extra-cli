"""Tests for the document inventory pipeline (#243)."""

from __future__ import annotations

import io
import zipfile

from scripts.process_documents.inventory_pipeline import (
    EXTRACTOR_VERSION,
    FACT_KEYS,
    InventoryRun,
    close_orphans,
    inventory_report,
    process_document,
)


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def test_inventory_closes_or_lists_blocker() -> None:
    run = InventoryRun(process_id="p1")
    ok = process_document(
        run,
        job_id="edital",
        url="https://example.gov/edital.pdf",
        body=b"%PDF-1.4 consorcio permitido",
        declared_mime="application/pdf",
    )
    assert ok.state == "SUCCEEDED"
    slip = process_document(
        run,
        job_id="pack",
        url="https://example.gov/pack.zip",
        body=_zip_bytes({"../x": b"nope"}),
        declared_mime="application/zip",
    )
    assert slip.state == "BLOCKED"
    assert slip.reason_code == "zip_slip"


def test_fetch_records_url_parent_hash_mime_bytes_method_attempt_pointer() -> None:
    run = InventoryRun(process_id="p2")
    job = process_document(
        run,
        job_id="tr",
        url="https://example.gov/tr.pdf",
        body=b"%PDF-1.4 TR",
        declared_mime="application/pdf",
        parent="edital",
        attempt=2,
        method="GET",
    )
    assert job.fetch is not None
    assert job.fetch.url.endswith("tr.pdf")
    assert job.fetch.parent == "edital"
    assert job.fetch.sha256
    assert job.fetch.mime == "application/pdf"
    assert job.fetch.bytes_len == len(b"%PDF-1.4 TR")
    assert job.fetch.method == "GET"
    assert job.fetch.attempt == 2
    assert job.fetch.blob_pointer.startswith("cas://")


def test_zip_bomb_mime_mismatch_and_unreadable_are_not_complete() -> None:
    run = InventoryRun(process_id="p3")
    bomb = process_document(
        run,
        job_id="bomb",
        url="https://example.gov/b.zip",
        body=_zip_bytes({f"f{i}.txt": b"x" for i in range(50)}),
        declared_mime="application/zip",
    )
    assert bomb.state == "BLOCKED"
    assert bomb.reason_code == "zip_bomb"
    mismatch = process_document(
        run,
        job_id="bad-mime",
        url="https://example.gov/x.pdf",
        body=b"PK\x03\x04not-a-pdf",
        declared_mime="application/pdf",
    )
    assert mismatch.state == "BLOCKED"
    assert mismatch.reason_code == "mime_mismatch"


def test_extraction_has_version_locator_and_factual_pendencies() -> None:
    run = InventoryRun(process_id="p4")
    job = process_document(
        run,
        job_id="txt",
        url="https://example.gov/nota.txt",
        body=b"Edital permite subcontratacao parcial",
        declared_mime="text/plain",
    )
    assert job.extraction is not None
    assert job.extraction.extractor_version == EXTRACTOR_VERSION
    assert job.extraction.locator.startswith("https://example.gov/nota.txt#bytes=")
    assert set(job.extraction.facts) == set(FACT_KEYS)
    assert job.extraction.facts["subcontratacao"] == "mencionado"
    assert job.extraction.facts["cat"] == "pendente"


def test_replay_skips_and_hash_change_invalidates_derived() -> None:
    run = InventoryRun(process_id="p5")
    first = process_document(
        run,
        job_id="doc",
        url="https://example.gov/a.pdf",
        body=b"%PDF-1.4 aaa",
        declared_mime="application/pdf",
    )
    replay = process_document(
        run,
        job_id="doc-2",
        url="https://example.gov/a.pdf",
        body=b"%PDF-1.4 aaa",
        declared_mime="application/pdf",
    )
    assert replay.reason_code == "replay_cache"
    assert replay.fetch is first.fetch
    changed = process_document(
        run,
        job_id="doc",
        url="https://example.gov/a.pdf",
        body=b"%PDF-1.4 bbb",
        declared_mime="application/pdf",
    )
    assert run.jobs["doc"].derived_invalidated is True
    assert run.jobs["doc"].state == "SUPERSEDED"
    assert changed.state == "SUCCEEDED"
    assert changed.job_id.endswith(":v")


def test_run_never_stays_running() -> None:
    run = InventoryRun(process_id="p6")
    from scripts.process_documents.inventory_pipeline import DocumentJob

    run.jobs["x"] = DocumentJob(job_id="x", url="u", state="RUNNING")
    close_orphans(run)
    assert run.jobs["x"].state == "BLOCKED"
    assert run.jobs["x"].reason_code == "orphan_running"
    report = inventory_report(run)
    assert report["terminal"] is True
