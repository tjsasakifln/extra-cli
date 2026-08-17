"""EXTRA-002 — joint encrypted backup, off-site transport, isolated restore.

Drives scripts.ops.backup_integrity and scripts.ops.offsite_transport.
Does not claim VPS_OPERATIONAL. Fixture only — not a live NFS transfer.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.ops.backup_integrity import (
    DECISION_ID,
    main,
    recurrence_authorized,
    run_joint,
    seed_fixture,
    sha256_bytes,
)
from scripts.ops.blob_cas import load_job
from scripts.ops.offsite_transport import (
    OffsiteNotIndependentError,
    OffsiteTarget,
    get_bytes,
    put_bytes,
    resolve_target,
)


def _target(*, status: str = "ok", independent: bool = True) -> OffsiteTarget:
    return OffsiteTarget(
        kind="nfs_mount",
        status=status,  # type: ignore[arg-type]
        nfs_host="46.38.248.210",
        mount_point="/mnt/storage-box",
        prefix="backups/extra-002",
        hop_configured=True,
        independent_of_vps_disk=independent,
        new_paid_plan=False,
        blockers=() if independent else ("VPS disk is not an off-site target",),
    )


def test_extra_002_resolve_refuses_vps_disk_and_missing_credential() -> None:
    blocked = resolve_target({"BACKUP_MOUNT_POINT": "/var/lib/extra-consultoria/backups"})
    assert blocked.status == "not_offsite"
    assert blocked.independent_of_vps_disk is False
    missing = resolve_target({})
    assert missing.status == "blocked_credential"
    ok = resolve_target(
        {
            "BACKUP_NFS_EXPORT": "46.38.248.210:/voln1116040a1",
            "BACKUP_MOUNT_POINT": "/mnt/storage-box",
            "EXTRA_OFFSITE_SSH_HOST": "vps.example",
        }
    )
    assert ok.nfs_host == "46.38.248.210"
    assert ok.independent_of_vps_disk is True
    assert ok.new_paid_plan is False
    assert ok.status in {"ok", "configured_unverified"}


def test_extra_002_put_refuses_vps_as_offsite(tmp_path: Path) -> None:
    with pytest.raises(OffsiteNotIndependentError):
        put_bytes(_target(status="not_offsite", independent=False), "x.bin", b"nope", staging_root=tmp_path)


def test_extra_002_joint_encrypted_restore_hash_identical(tmp_path: Path) -> None:
    source = tmp_path / "src"
    restore = tmp_path / "isolated"
    staging = tmp_path / "nfs"
    meta = tmp_path / "meta"
    proof = tmp_path / "proof.json"
    blob = b"%PDF-1.4 extra-002-chosen-blob"
    seed_fixture(
        source,
        dump_bytes=b"PGDUMP-extra-002",
        blob_bytes=blob,
        job_id="job-extra-002",
        manifest={"kind": "joint", "decision": DECISION_ID},
    )
    from scripts.ops.backup_integrity import generate_encrypt_key

    key = generate_encrypt_key()
    report = run_joint(
        source,
        restore,
        key=key,
        job_id="job-extra-002",
        blob_sha256=sha256_bytes(blob),
        push=True,
        target=_target(),
        staging_root=staging,
        proof_path=proof,
        meta_root=meta,
    )
    assert report["vps_operational_claimed"] is False
    assert report["hash_identical"] is True
    assert report["isolated"] is True
    assert report["job_status"] == "success"
    assert report["offsite"]["pushed"] is True
    assert report["offsite"]["independent_of_vps_disk"] is True
    assert report["policy"]["rto_hours"] == 8
    assert report["version"]
    assert report["duration_s"] >= 0
    assert report["object_count"] >= 4
    assert report["bytes"] > 0
    recovered = next((restore / "selected").rglob("doc.bin"))
    assert recovered.read_bytes() == blob
    assert hashlib.sha256(recovered.read_bytes()).hexdigest() == sha256_bytes(blob)
    assert load_job(meta, "job-extra-002").status == "success"
    assert recurrence_authorized(proof) is True
    assert report["recurrence"]["enabled"] is False
    ciphertext = get_bytes(_target(), "joint-package.enc", staging_root=staging)
    assert hashlib.sha256(ciphertext).hexdigest() == report["package"]["ciphertext_sha256"]
    dumped = json.dumps(report)
    assert "BEGIN" not in dumped
    assert DECISION_ID in dumped


def test_extra_002_transport_or_backup_failure_does_not_mark_job_success(tmp_path: Path) -> None:
    source = tmp_path / "src"
    seed_fixture(
        source,
        dump_bytes=b"dump",
        blob_bytes=b"blob",
        job_id="job-fail-002",
        manifest={"ok": True},
    )
    from scripts.ops.backup_integrity import generate_encrypt_key

    key = generate_encrypt_key()
    failed = run_joint(
        source,
        tmp_path / "r1",
        key=key,
        job_id="job-fail-002",
        push=True,
        target=_target(),
        staging_root=tmp_path / "nfs",
        fail="transport",
        meta_root=tmp_path / "meta",
    )
    assert failed["job_status"] == "failed"
    assert failed["alerts"]
    assert load_job(tmp_path / "meta", "job-fail-002").status == "failed"
    assert failed["vps_operational_claimed"] is False
    assert recurrence_authorized(None) is False


def test_extra_002_cli_joint_twice(tmp_path: Path) -> None:
    source = tmp_path / "src"
    blob = b"cli-joint-blob"
    rc = main(
        [
            "seed",
            "--root",
            str(source),
            "--job-id",
            "cli-002",
            "--seed-blob",
            str(_write(tmp_path / "b.bin", blob)),
        ]
    )
    assert rc == 0
    for index in (1, 2):
        out = tmp_path / f"joint-{index}.json"
        rc = main(
            [
                "joint",
                "--root",
                str(source),
                "--restore-root",
                str(tmp_path / f"restore-{index}"),
                "--job-id",
                "cli-002",
                "--blob-sha256",
                sha256_bytes(blob),
                "--push",
                "--staging-root",
                str(tmp_path / f"nfs-{index}"),
                "--key-file",
                str(tmp_path / f"key-{index}"),
                "--proof-file",
                str(tmp_path / f"proof-{index}.json"),
                "--meta-root",
                str(tmp_path / f"meta-{index}"),
                "--output",
                str(out),
            ]
        )
        assert rc == 0
        report = json.loads(out.read_text(encoding="utf-8"))
        assert report["hash_identical"] is True
        assert report["job_status"] == "success"
        assert report["vps_operational_claimed"] is False


def _write(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path
