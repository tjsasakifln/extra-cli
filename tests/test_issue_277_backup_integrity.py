"""Refs #277 — inventory, checksum, restore hash, VPS-loss sim, alerts.

Drives scripts.ops.backup_integrity. Never claims VPS_OPERATIONAL.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.ops.backup_integrity import (
    checksum_matches,
    evaluate_approvals,
    main,
    run_proof,
    seed_fixture,
    sha256_bytes,
)


def test_issue_277_restore_recovers_job_metadata_and_blob_hash(tmp_path: Path) -> None:
    source = tmp_path / "backup"
    restore = tmp_path / "isolated-restore"
    dump = b"PGDUMP-bytes-for-277"
    blob = b"%PDF-1.4 chosen-blob-277"
    planted = seed_fixture(
        source,
        dump_bytes=dump,
        blob_bytes=blob,
        job_id="job-277-restore",
        manifest={"window": "2026-08-16", "kind": "joint-backup"},
    )
    report = run_proof(
        source,
        restore,
        blob_sha256=planted["blob_sha256"],
        job_id="job-277-restore",
        simulate_vps_loss=True,
    )
    assert report.vps_operational_claimed is False
    assert report.version
    assert report.duration_s >= 0
    kinds = {item.kind for item in report.artifacts}
    assert kinds >= {"postgres_dump", "blob", "manifest", "job"}
    assert report.restore is not None
    assert report.restore.hash_identical is True
    assert report.restore.recovered_blob_sha256 == hashlib.sha256(blob).hexdigest()
    assert report.restore.recovered_job_id == "job-277-restore"
    assert report.restore.simulated_vps_loss is True
    restored_blob = next(restore.rglob("doc.bin"))
    assert restored_blob.read_bytes() == blob
    assert hashlib.sha256(restored_blob.read_bytes()).hexdigest() == planted["blob_sha256"]
    restored_job = next(restore.rglob("job-277-restore.job.json"))
    assert "job-277-restore" in restored_job.read_text(encoding="utf-8")
    for artifact in report.artifacts:
        assert checksum_matches(source, artifact) is True


def test_issue_277_human_rpo_rto_retention_blocked_without_approval() -> None:
    gates = evaluate_approvals(
        rpo_approved_by=None,
        rto_approved_by=None,
        retention_approved_by=None,
        destination_approved_by=None,
    )
    assert gates.rpo == "blocked_human"
    assert gates.rto == "blocked_human"
    assert gates.retention == "blocked_human"
    assert gates.destination == "blocked_human"
    assert gates.all_approved is False


def test_issue_277_backup_or_restore_failure_emits_alert(tmp_path: Path) -> None:
    source = tmp_path / "backup"
    seed_fixture(
        source,
        dump_bytes=b"dump",
        blob_bytes=b"blob",
        job_id="job-alert",
        manifest={"ok": True},
    )
    failed_backup = run_proof(source, tmp_path / "r1", fail="backup")
    assert failed_backup.alerts
    assert failed_backup.alerts[0].kind == "backup_restore_failed"
    assert failed_backup.vps_operational_claimed is False
    failed_restore = run_proof(source, tmp_path / "r2", fail="restore")
    assert failed_restore.alerts
    assert "restore" in failed_restore.alerts[0].message


def test_issue_277_cli_inventory_and_report(tmp_path: Path) -> None:
    source = tmp_path / "seeded"
    restore = tmp_path / "restore"
    blob = b"cli-blob-277"
    rc = main(
        [
            "seed",
            "--root",
            str(source),
            "--job-id",
            "cli-277",
            "--seed-blob",
            str(_write(tmp_path / "blob.bin", blob)),
        ]
    )
    assert rc == 0
    out_inv = tmp_path / "inv.json"
    rc = main(["inventory", "--root", str(source), "--output", str(out_inv)])
    assert rc == 0
    items = json.loads(out_inv.read_text(encoding="utf-8"))
    assert {row["kind"] for row in items} >= {"postgres_dump", "blob", "manifest", "job"}
    out_rep = tmp_path / "report.json"
    rc = main(
        [
            "report",
            "--root",
            str(source),
            "--restore-root",
            str(restore),
            "--blob-sha256",
            sha256_bytes(blob),
            "--job-id",
            "cli-277",
            "--output",
            str(out_rep),
        ]
    )
    assert rc == 0
    report = json.loads(out_rep.read_text(encoding="utf-8"))
    assert report["vps_operational_claimed"] is False
    assert report["restore"]["hash_identical"] is True
    assert report["version"]
    assert "duration_s" in report
    assert report["artifacts"]


def _write(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path
