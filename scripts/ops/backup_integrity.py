"""#277 — backup inventory, checksum and isolated restore proof.

Does not claim VPS_OPERATIONAL. Human RPO/RTO/retention/destination stay
residual until explicitly approved. Failures emit an alert record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

SCHEMA_VERSION = 1
MODULE_VERSION = "backup-integrity-v1"

ArtifactKind = Literal["postgres_dump", "blob", "manifest", "job"]
GateStatus = Literal["approved", "blocked_human", "failed"]


class BackupIntegrityError(Exception):
    """Fail-closed backup/restore error."""


@dataclass(frozen=True)
class Artifact:
    kind: ArtifactKind
    name: str
    sha256: str
    size_bytes: int
    relpath: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Alert:
    kind: str
    message: str
    at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RestoreProof:
    recovered_job_id: str | None
    recovered_blob_sha256: str | None
    hash_identical: bool
    isolated_root: str
    simulated_vps_loss: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HumanApprovals:
    rpo: GateStatus
    rto: GateStatus
    retention: GateStatus
    destination: GateStatus

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def all_approved(self) -> bool:
        return all(value == "approved" for value in (self.rpo, self.rto, self.retention, self.destination))


@dataclass(frozen=True)
class BackupReport:
    schema_version: int
    version: str
    started_at: str
    finished_at: str
    duration_s: float
    artifacts: tuple[Artifact, ...]
    approvals: HumanApprovals
    restore: RestoreProof | None
    alerts: tuple[Alert, ...]
    vps_operational_claimed: bool

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["artifacts"] = [item.as_dict() for item in self.artifacts]
        payload["approvals"] = self.approvals.as_dict()
        payload["restore"] = None if self.restore is None else self.restore.as_dict()
        payload["alerts"] = [item.as_dict() for item in self.alerts]
        return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def classify_kind(path: Path) -> ArtifactKind:
    name = path.name.casefold()
    if name.endswith((".dump", ".dump.gz", ".sql", ".sql.gz")):
        return "postgres_dump"
    if name.endswith(".job.json") or path.parent.name == "jobs":
        return "job"
    if name.endswith((".json", ".jsonl", ".manifest")):
        return "manifest"
    return "blob"


def inventory(root: Path) -> tuple[Artifact, ...]:
    if not root.is_dir():
        raise BackupIntegrityError(f"inventory root missing: {root}")
    items: list[Artifact] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name.endswith(".partial"):
            continue
        rel = path.relative_to(root).as_posix()
        items.append(
            Artifact(
                kind=classify_kind(path),
                name=path.name,
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
                relpath=rel,
            )
        )
    return tuple(items)


def checksum_matches(root: Path, artifact: Artifact) -> bool:
    path = root / artifact.relpath
    if not path.is_file():
        return False
    return sha256_file(path) == artifact.sha256 and path.stat().st_size == artifact.size_bytes


def evaluate_approvals(
    *,
    rpo_approved_by: str | None,
    rto_approved_by: str | None,
    retention_approved_by: str | None,
    destination_approved_by: str | None,
) -> HumanApprovals:
    def gate(value: str | None) -> GateStatus:
        return "approved" if value and value.strip() else "blocked_human"

    return HumanApprovals(
        rpo=gate(rpo_approved_by),
        rto=gate(rto_approved_by),
        retention=gate(retention_approved_by),
        destination=gate(destination_approved_by),
    )


def emit_alert(kind: str, message: str) -> Alert:
    return Alert(kind=kind, message=message, at=_utc_now())


def _find_artifact(items: tuple[Artifact, ...], kind: ArtifactKind, digest: str | None = None) -> Artifact | None:
    for item in items:
        if item.kind != kind:
            continue
        if digest is None or item.sha256 == digest:
            return item
    return None


def restore_selected(
    source_root: Path,
    dest_root: Path,
    items: tuple[Artifact, ...],
    *,
    blob_sha256: str,
    job_id: str | None,
    simulate_vps_loss: bool = False,
) -> RestoreProof:
    """Restore job metadata and one blob into an isolated root; verify hash."""
    dest_root.mkdir(parents=True, exist_ok=True)
    blob = _find_artifact(items, "blob", blob_sha256)
    if blob is None:
        raise BackupIntegrityError(f"blob {blob_sha256} missing from inventory")
    if not checksum_matches(source_root, blob):
        raise BackupIntegrityError(f"blob checksum failed before restore: {blob_sha256}")

    src_blob = source_root / blob.relpath
    dest_blob = dest_root / blob.relpath
    dest_blob.parent.mkdir(parents=True, exist_ok=True)
    dest_blob.write_bytes(src_blob.read_bytes())
    recovered_hash = sha256_file(dest_blob)
    if recovered_hash != blob_sha256:
        raise BackupIntegrityError("restored blob hash differs from inventory")

    recovered_job: str | None = None
    if job_id:
        job_item = next((item for item in items if item.kind == "job" and job_id in (item.name, item.relpath)), None)
        if job_item is None:
            # fall back to any job whose payload mentions the id
            for item in items:
                if item.kind != "job":
                    continue
                text = (source_root / item.relpath).read_text(encoding="utf-8")
                if job_id in text:
                    job_item = item
                    break
        if job_item is None:
            raise BackupIntegrityError(f"job {job_id} missing from inventory")
        dest_job = dest_root / job_item.relpath
        dest_job.parent.mkdir(parents=True, exist_ok=True)
        dest_job.write_bytes((source_root / job_item.relpath).read_bytes())
        recovered_job = job_id

    if simulate_vps_loss:
        # Isolated restore already lives in dest_root; source is treated as gone.
        if dest_root.resolve() == source_root.resolve():
            raise BackupIntegrityError("VPS-loss simulation requires an isolated restore root")

    return RestoreProof(
        recovered_job_id=recovered_job,
        recovered_blob_sha256=recovered_hash,
        hash_identical=recovered_hash == blob_sha256,
        isolated_root=str(dest_root),
        simulated_vps_loss=simulate_vps_loss,
    )


def run_proof(
    source_root: Path,
    restore_root: Path,
    *,
    blob_sha256: str | None = None,
    job_id: str | None = None,
    rpo_approved_by: str | None = None,
    rto_approved_by: str | None = None,
    retention_approved_by: str | None = None,
    destination_approved_by: str | None = None,
    simulate_vps_loss: bool = True,
    fail: str | None = None,
) -> BackupReport:
    started = time.perf_counter()
    started_at = _utc_now()
    alerts: list[Alert] = []
    restore: RestoreProof | None = None
    try:
        if fail == "backup":
            raise BackupIntegrityError("forced backup failure")
        items = inventory(source_root)
        if not any(item.kind == "postgres_dump" for item in items):
            raise BackupIntegrityError("inventory missing postgres_dump")
        if not any(item.kind == "blob" for item in items):
            raise BackupIntegrityError("inventory missing blob")
        if not any(item.kind == "manifest" for item in items):
            raise BackupIntegrityError("inventory missing manifest")
        broken = [item.relpath for item in items if not checksum_matches(source_root, item)]
        if broken:
            raise BackupIntegrityError("checksum failed: " + ",".join(broken))
        target = blob_sha256 or next(item.sha256 for item in items if item.kind == "blob")
        if fail == "restore":
            raise BackupIntegrityError("forced restore failure")
        restore = restore_selected(
            source_root,
            restore_root,
            items,
            blob_sha256=target,
            job_id=job_id,
            simulate_vps_loss=simulate_vps_loss,
        )
        if not restore.hash_identical:
            raise BackupIntegrityError("restore hash is not identical")
    except BackupIntegrityError as exc:
        alerts.append(emit_alert("backup_restore_failed", str(exc)))
        items = items if "items" in locals() else ()
        finished_at = _utc_now()
        return BackupReport(
            schema_version=SCHEMA_VERSION,
            version=MODULE_VERSION,
            started_at=started_at,
            finished_at=finished_at,
            duration_s=round(time.perf_counter() - started, 6),
            artifacts=items,
            approvals=evaluate_approvals(
                rpo_approved_by=rpo_approved_by,
                rto_approved_by=rto_approved_by,
                retention_approved_by=retention_approved_by,
                destination_approved_by=destination_approved_by,
            ),
            restore=restore,
            alerts=tuple(alerts),
            vps_operational_claimed=False,
        )

    finished_at = _utc_now()
    return BackupReport(
        schema_version=SCHEMA_VERSION,
        version=MODULE_VERSION,
        started_at=started_at,
        finished_at=finished_at,
        duration_s=round(time.perf_counter() - started, 6),
        artifacts=items,
        approvals=evaluate_approvals(
            rpo_approved_by=rpo_approved_by,
            rto_approved_by=rto_approved_by,
            retention_approved_by=retention_approved_by,
            destination_approved_by=destination_approved_by,
        ),
        restore=restore,
        alerts=tuple(alerts),
        vps_operational_claimed=False,
    )


def seed_fixture(
    root: Path,
    *,
    dump_bytes: bytes,
    blob_bytes: bytes,
    job_id: str,
    manifest: dict[str, Any],
) -> dict[str, str]:
    """Write a local backup fixture. Used by tests and the CLI demo path."""
    dump = root / "postgresql" / "daily" / "extra.dump"
    blob = root / "blobs" / "cas" / "doc.bin"
    job = root / "jobs" / f"{job_id}.job.json"
    man = root / "manifests" / "backup.manifest"
    for path in (dump, blob, job, man):
        path.parent.mkdir(parents=True, exist_ok=True)
    dump.write_bytes(dump_bytes)
    blob.write_bytes(blob_bytes)
    job.write_text(json.dumps({"job_id": job_id, "status": "success"}, sort_keys=True) + "\n", encoding="utf-8")
    man.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "dump": str(dump),
        "blob": str(blob),
        "blob_sha256": sha256_bytes(blob_bytes),
        "job": str(job),
        "manifest": str(man),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backup inventory/checksum/restore proof (#277)")
    parser.add_argument("action", choices=("inventory", "report", "seed"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--restore-root")
    parser.add_argument("--blob-sha256")
    parser.add_argument("--job-id")
    parser.add_argument("--rpo-approved-by")
    parser.add_argument("--rto-approved-by")
    parser.add_argument("--retention-approved-by")
    parser.add_argument("--destination-approved-by")
    parser.add_argument("--fail", choices=("backup", "restore"))
    parser.add_argument("--seed-dump")
    parser.add_argument("--seed-blob")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.action == "seed":
        dump = Path(args.seed_dump).read_bytes() if args.seed_dump else b"PGDUMP-FIXTURE"
        blob = Path(args.seed_blob).read_bytes() if args.seed_blob else b"%PDF-1.4 fixture"
        planted = seed_fixture(
            root,
            dump_bytes=dump,
            blob_bytes=blob,
            job_id=args.job_id or "job-restore-1",
            manifest={"kind": "backup-manifest", "version": MODULE_VERSION},
        )
        text = json.dumps(planted, ensure_ascii=False, indent=2) + "\n"
    elif args.action == "inventory":
        text = json.dumps([item.as_dict() for item in inventory(root)], ensure_ascii=False, indent=2) + "\n"
    else:
        restore_root = Path(args.restore_root or (str(root) + "-restore"))
        report = run_proof(
            root,
            restore_root,
            blob_sha256=args.blob_sha256,
            job_id=args.job_id,
            rpo_approved_by=args.rpo_approved_by,
            rto_approved_by=args.rto_approved_by,
            retention_approved_by=args.retention_approved_by,
            destination_approved_by=args.destination_approved_by,
            fail=args.fail,
        )
        text = json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
