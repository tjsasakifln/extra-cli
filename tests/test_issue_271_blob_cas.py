"""Refs #271 — store/get/head CAS, corruption, metadata survival, redaction.

Drives scripts.ops.blob_cas. Does not claim off-site or VPS_OPERATIONAL.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import pytest

from scripts.ops.blob_cas import (
    BackendUnavailableError,
    CorruptionError,
    DestinationUndecidedError,
    get,
    head,
    load_job,
    log_event,
    main,
    redact,
    store,
)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_issue_271_store_get_head_read_after_write(tmp_path: Path) -> None:
    payload = b"%PDF-1.4 edital fixture for sha256 addressing"
    digest = _digest(payload)
    root = tmp_path / "blobs"
    meta_root = tmp_path / "meta"
    stored = store(payload, root=root, meta_root=meta_root, job_id="job-271-a", content_type="application/pdf")
    assert stored.sha256 == digest
    assert stored.postgres_stored is False
    assert stored.git_stored is False
    assert stored.backend == "filesystem"
    assert get(digest, root=root) == payload
    info = head(digest, root=root, meta_root=meta_root)
    assert info.exists is True
    assert info.intact is True
    assert info.metadata_present is True
    assert info.sha256 == digest
    job = load_job(meta_root, "job-271-a")
    assert job.status == "success"
    assert job.sha256 == digest


def test_issue_271_corruption_is_detected(tmp_path: Path) -> None:
    payload = b"intact-bytes-271"
    digest = _digest(payload)
    root = tmp_path / "blobs"
    meta_root = tmp_path / "meta"
    store(payload, root=root, meta_root=meta_root)
    cas = root / "cas" / digest[:2] / digest[2:4] / digest
    cas.write_bytes(b"tampered-bytes-that-must-not-pass")
    with pytest.raises(CorruptionError, match="corruption"):
        get(digest, root=root)
    with pytest.raises(CorruptionError, match="corruption"):
        head(digest, root=root, meta_root=meta_root)


def test_issue_271_unavailability_keeps_metadata_and_fails_job(tmp_path: Path) -> None:
    payload = b"blob-while-backend-down"
    digest = _digest(payload)
    root = tmp_path / "blobs"
    meta_root = tmp_path / "meta"
    with pytest.raises(BackendUnavailableError):
        store(payload, root=root, meta_root=meta_root, job_id="job-271-down", available=False)
    meta_file = meta_root / "meta" / digest[:2] / digest[2:4] / f"{digest}.json"
    recorded = json.loads(meta_file.read_text(encoding="utf-8"))
    assert recorded["sha256"] == digest
    assert recorded["job_id"] == "job-271-down"
    job = load_job(meta_root, "job-271-down")
    assert job.status == "failed"
    assert job.status != "success"
    assert not (root / "cas" / digest[:2] / digest[2:4] / digest).exists()


def test_issue_271_object_storage_blocked_without_human_destination(tmp_path: Path) -> None:
    with pytest.raises(DestinationUndecidedError, match="human destination"):
        store(
            b"needs-offsite",
            root=tmp_path / "blobs",
            meta_root=tmp_path / "meta",
            backend="object_storage",
        )


def test_issue_271_refuses_postgres_uri() -> None:
    from scripts.ops.blob_cas import BlobStoreError, _refuse_postgres_or_git

    with pytest.raises(BlobStoreError, match="PostgreSQL"):
        _refuse_postgres_or_git("postgresql://user:pass@127.0.0.1/extra")
    with pytest.raises(BlobStoreError, match="Git"):
        _refuse_postgres_or_git("/var/repo/.git/objects/ab")


def test_issue_271_redacts_signed_urls_and_secrets(caplog: pytest.LogCaptureFixture) -> None:
    raw = (
        "put https://bucket.s3.amazonaws.com/obj?X-Amz-Signature=abc123secret"
        " AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI Bearer super-token-value"
    )
    cleaned = redact(raw)
    assert "abc123secret" not in cleaned
    assert "wJalrXUtnFEMI" not in cleaned
    assert "super-token-value" not in cleaned
    assert "[REDACTED]" in cleaned
    logger = logging.getLogger("blob_cas_test")
    with caplog.at_level(logging.INFO, logger="blob_cas_test"):
        log_event(logger, raw)
    assert "abc123secret" not in caplog.text
    assert "super-token-value" not in caplog.text


def test_issue_271_offsite_replica_verified_or_fails_job(tmp_path: Path) -> None:
    payload = b"replica-bytes-271"
    digest = _digest(payload)
    root = tmp_path / "blobs"
    meta_root = tmp_path / "meta"
    offsite = tmp_path / "nfs-cas"
    stored = store(
        payload,
        root=root,
        meta_root=meta_root,
        job_id="job-271-replica",
        offsite_root=offsite,
        destination_approved_by="PREAPPROVED-EXTRA-002-2026-08-17",
        credentials_present=True,
    )
    assert stored.replica == "offsite-verified"
    assert get(digest, root=offsite) == payload
    assert load_job(meta_root, "job-271-replica").status == "success"

    blocked = tmp_path / "not-a-dir" / "missing"
    blocked.parent.mkdir(parents=True, exist_ok=True)
    blocked.write_text("not-a-directory", encoding="utf-8")
    with pytest.raises(BackendUnavailableError):
        store(
            b"replica-fail-271",
            root=tmp_path / "blobs2",
            meta_root=tmp_path / "meta2",
            job_id="job-271-replica-fail",
            offsite_root=blocked,
        )
    assert load_job(tmp_path / "meta2", "job-271-replica-fail").status == "failed"


def test_issue_271_object_storage_needs_offsite_root(tmp_path: Path) -> None:
    with pytest.raises(DestinationUndecidedError, match="offsite_root"):
        store(
            b"needs-root",
            root=tmp_path / "blobs",
            meta_root=tmp_path / "meta",
            backend="object_storage",
            destination_approved_by="PREAPPROVED-EXTRA-002-2026-08-17",
            credentials_present=True,
        )


def test_issue_271_cli_store_get_head(tmp_path: Path) -> None:
    payload = b"cli-roundtrip-271"
    digest = _digest(payload)
    src = tmp_path / "in.bin"
    src.write_bytes(payload)
    root = tmp_path / "cas-root"
    meta = tmp_path / "meta-root"
    rc = main(
        [
            "store",
            "--root",
            str(root),
            "--meta-root",
            str(meta),
            "--data-file",
            str(src),
            "--job-id",
            "cli-271",
        ]
    )
    assert rc == 0
    rc = main(["head", "--root", str(root), "--meta-root", str(meta), "--sha256", digest])
    assert rc == 0
    rc = main(["get", "--root", str(root), "--meta-root", str(meta), "--sha256", digest])
    assert rc == 0
