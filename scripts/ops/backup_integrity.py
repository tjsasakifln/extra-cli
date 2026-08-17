"""#277 / EXTRA-002 — backup inventory, checksum, encrypted off-site joint restore.

Does not claim VPS_OPERATIONAL. Failures emit an alert record. Recurrence stays
off until a hash-identical isolated restore is recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from scripts.ops.blob_cas import record_job, redact
from scripts.ops.offsite_transport import (
    OffsiteTarget,
    OffsiteTransportError,
    get_bytes,
    put_bytes,
    resolve_target,
)

SCHEMA_VERSION = 1
MODULE_VERSION = "backup-integrity-v1"
JOINT_VERSION = "joint-offsite-v1"
DECISION_ID = "PREAPPROVED-EXTRA-002-2026-08-17"
PACKAGE_NAME = "joint-package.enc"
PACKAGE_META_NAME = "joint-package.json"
SIDECAR_KEY_NAME = "sidecar/joint.key"
INVENTORY_SKIP_NAMES = {PACKAGE_NAME, PACKAGE_META_NAME, "joint.key"}
OPENSSL_PBKDF2_ITERS = 100_000
KEY_BYTES = 32
PG_CUSTOM_MAGIC = b"PGDMP"
FAKE_DUMP_PREFIXES = (b"PGDUMP-", b"PGDUMP-FIXTURE", b"PGDUMP-EXTRA")
VAULT_KEY_ENV = "EXTRA_JOINT_KEY_FILE"
DEFAULT_VAULT_KEY = Path.home() / ".config/extra-consultoria/joint-offsite.key"
DEFAULT_DUMP_DIRS = (
    Path("/var/lib/extra-consultoria/backups/postgresql"),
    Path("/mnt/storage-box/backups/postgresql/daily"),
)
DEFAULT_CAS_DIRS = (
    Path("/opt/extra-consultoria/data/raw/process_documents"),
    Path("/opt/extra-consultoria/extra-cli/data/raw/process_documents"),
)
RECOVERY_POLICY: dict[str, Any] = {
    "decision_id": DECISION_ID,
    "owner": "CONFENGE owner",
    "rpo_hours": 24,
    "rto_hours": 8,
    "retention_daily": 14,
    "retention_weekly": 8,
    "retention_monthly": 12,
    "restore_cadence": "quarterly",
    "purge_before_restore": False,
}

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
        if path.name.endswith(".partial") or path.name.endswith(".fernet") or path.name.endswith(".enc"):
            continue
        if path.name in INVENTORY_SKIP_NAMES:
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


def approved_policy(
    *,
    rpo_approved_by: str | None,
    rto_approved_by: str | None,
    retention_approved_by: str | None,
    destination_approved_by: str | None,
) -> HumanApprovals:
    """Record the EXTRA-002 executive policy when the decision id is the approver."""
    return evaluate_approvals(
        rpo_approved_by=rpo_approved_by,
        rto_approved_by=rto_approved_by,
        retention_approved_by=retention_approved_by,
        destination_approved_by=destination_approved_by,
    )


def is_real_postgres_dump(path: Path) -> bool:
    """Accept pg_dump custom/gzip/sql. Refuse the ASCII EXTRA-002 fixtures."""
    if not path.is_file() or path.stat().st_size < 5:
        return False
    with path.open("rb") as handle:
        head = handle.read(8)
    if head.startswith(FAKE_DUMP_PREFIXES):
        return False
    if head.startswith(PG_CUSTOM_MAGIC):
        return True
    if head.startswith(b"\x1f\x8b"):
        import gzip

        try:
            with gzip.open(path, "rb") as handle:
                inner = handle.read(16)
        except OSError:
            return False
        return inner.startswith(PG_CUSTOM_MAGIC) or inner.startswith((b"--", b"SET ", b"CREATE"))
    return False


def vault_key_path() -> Path:
    override = os.environ.get(VAULT_KEY_ENV)
    if override:
        return Path(override)
    return DEFAULT_VAULT_KEY


def load_or_create_vault_key(path: Path | None = None) -> tuple[bytes, Path]:
    """Persist the encrypt key in the off-VPS vault. Never use restore_root as sole copy."""
    dest = path or vault_key_path()
    if dest.is_file():
        return load_encrypt_key(dest, None), dest
    key = generate_encrypt_key()
    write_key(dest, key)
    return key, dest


def generate_encrypt_key() -> bytes:
    return os.urandom(KEY_BYTES)


def load_encrypt_key(key_path: Path | None, provided: str | None) -> bytes:
    if provided:
        key = bytes.fromhex(provided.strip())
        if len(key) != KEY_BYTES:
            raise BackupIntegrityError("encrypt key must be 32 bytes hex")
        return key
    if key_path is not None and key_path.is_file():
        raw = key_path.read_bytes().strip()
        if len(raw) == KEY_BYTES:
            return raw
        try:
            decoded = bytes.fromhex(raw.decode("ascii"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise BackupIntegrityError("encrypt key file is not 32 raw bytes or hex") from exc
        if len(decoded) != KEY_BYTES:
            raise BackupIntegrityError("encrypt key must be 32 bytes")
        return decoded
    return generate_encrypt_key()


def write_key(path: Path, key: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    path.chmod(0o600)


def _openssl_bin() -> str:
    path = shutil.which("openssl")
    if not path:
        raise BackupIntegrityError("openssl is required to encrypt/decrypt the joint package")
    return path


def encrypt_payload(plaintext: bytes, key: bytes) -> bytes:
    """AES-256-CBC + HMAC-SHA256. Key is passed via a 0600 file, never argv."""
    openssl = _openssl_bin()
    with tempfile.TemporaryDirectory(prefix="extra002-enc-") as tmp:
        tmp_path = Path(tmp)
        key_file = tmp_path / "key"
        src = tmp_path / "plain"
        dest = tmp_path / "cipher"
        key_file.write_bytes(key.hex().encode("ascii"))
        key_file.chmod(0o600)
        src.write_bytes(plaintext)
        result = subprocess.run(  # noqa: S603
            [
                openssl,
                "enc",
                "-aes-256-cbc",
                "-pbkdf2",
                "-iter",
                str(OPENSSL_PBKDF2_ITERS),
                "-salt",
                "-in",
                str(src),
                "-out",
                str(dest),
                "-pass",
                f"file:{key_file}",
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not dest.is_file():
            raise BackupIntegrityError("openssl enc failed")
        ciphertext = dest.read_bytes()
    mac = hmac.new(key, ciphertext, hashlib.sha256).digest()
    return mac + ciphertext


def decrypt_payload(ciphertext: bytes, key: bytes) -> bytes:
    if len(ciphertext) < 32:
        raise BackupIntegrityError("decrypt failed: ciphertext too short")
    mac, body = ciphertext[:32], ciphertext[32:]
    expected = hmac.new(key, body, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise BackupIntegrityError("decrypt failed: hmac mismatch")
    openssl = _openssl_bin()
    with tempfile.TemporaryDirectory(prefix="extra002-dec-") as tmp:
        tmp_path = Path(tmp)
        key_file = tmp_path / "key"
        src = tmp_path / "cipher"
        dest = tmp_path / "plain"
        key_file.write_bytes(key.hex().encode("ascii"))
        key_file.chmod(0o600)
        src.write_bytes(body)
        result = subprocess.run(  # noqa: S603
            [
                openssl,
                "enc",
                "-d",
                "-aes-256-cbc",
                "-pbkdf2",
                "-iter",
                str(OPENSSL_PBKDF2_ITERS),
                "-in",
                str(src),
                "-out",
                str(dest),
                "-pass",
                f"file:{key_file}",
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not dest.is_file():
            raise BackupIntegrityError("openssl dec failed")
        return dest.read_bytes()


def tar_inventory(root: Path, items: tuple[Artifact, ...]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for item in items:
            path = root / item.relpath
            archive.add(path, arcname=item.relpath)
    return buffer.getvalue()


def untar_payload(payload: bytes, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        archive.extractall(dest, filter="data")


def write_encrypted_package(
    root: Path,
    dest_dir: Path,
    key: bytes,
    *,
    require_real_dump: bool = False,
) -> dict[str, Any]:
    items = inventory(root)
    if not any(item.kind == "postgres_dump" for item in items):
        raise BackupIntegrityError("inventory missing postgres_dump")
    if not any(item.kind == "blob" for item in items):
        raise BackupIntegrityError("inventory missing blob")
    if not any(item.kind == "manifest" for item in items):
        raise BackupIntegrityError("inventory missing manifest")
    if require_real_dump:
        dumps = [item for item in items if item.kind == "postgres_dump"]
        if not any(is_real_postgres_dump(root / item.relpath) for item in dumps):
            raise BackupIntegrityError("inventory postgres_dump is not a real pg_dump")
    plaintext = tar_inventory(root, items)
    ciphertext = encrypt_payload(plaintext, key)
    dest_dir.mkdir(parents=True, exist_ok=True)
    enc_path = dest_dir / PACKAGE_NAME
    meta_path = dest_dir / PACKAGE_META_NAME
    enc_path.write_bytes(ciphertext)
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "version": JOINT_VERSION,
        "decision_id": DECISION_ID,
        "cipher": "aes-256-cbc-hmac-sha256",
        "ciphertext_sha256": sha256_bytes(ciphertext),
        "plaintext_sha256": sha256_bytes(plaintext),
        "object_count": len(items),
        "bytes": len(ciphertext),
        "artifacts": [item.as_dict() for item in items],
        "vps_operational_claimed": False,
    }
    meta_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return envelope


def restore_encrypted_package(enc_path: Path, dest: Path, key: bytes) -> tuple[Artifact, ...]:
    ciphertext = enc_path.read_bytes()
    plaintext = decrypt_payload(ciphertext, key)
    untar_payload(plaintext, dest)
    return inventory(dest)


def _dump_dirs_from_env() -> tuple[Path, ...]:
    extra = os.environ.get("EXTRA_JOINT_DUMP_DIR")
    if extra:
        return (Path(extra), *DEFAULT_DUMP_DIRS)
    return DEFAULT_DUMP_DIRS


def _cas_dirs_from_env() -> tuple[Path, ...]:
    extra = os.environ.get("EXTRA_JOINT_CAS_ROOT") or os.environ.get("PROCESS_DOCUMENTS_RAW_ROOT")
    if extra:
        return (Path(extra), *DEFAULT_CAS_DIRS)
    return DEFAULT_CAS_DIRS


def _newest_real_dump(dirs: tuple[Path, ...]) -> Path | None:
    found: list[Path] = []
    for root in dirs:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            name = path.name.casefold()
            if not name.endswith((".dump", ".dump.gz", ".sql", ".sql.gz")):
                continue
            if is_real_postgres_dump(path):
                found.append(path)
    if not found:
        return None
    return max(found, key=lambda item: item.stat().st_mtime)


def _collect_cas_blobs(dirs: tuple[Path, ...], *, limit: int = 8) -> list[Path]:
    blobs: list[Path] = []
    for root in dirs:
        cas = root / "cas" if (root / "cas").is_dir() else root
        if not cas.is_dir():
            continue
        for path in sorted(p for p in cas.rglob("*") if p.is_file()):
            if path.name.endswith(".partial"):
                continue
            blobs.append(path)
            if len(blobs) >= limit:
                return blobs
    return blobs


def assemble_joint_source(
    dest: Path,
    *,
    dump_dirs: tuple[Path, ...] | None = None,
    cas_dirs: tuple[Path, ...] | None = None,
    job_id: str = "joint-assembled",
) -> dict[str, Any]:
    """Copy a real pg_dump + CAS blobs + manifests into dest. Fail-closed."""
    dump = _newest_real_dump(dump_dirs if dump_dirs is not None else _dump_dirs_from_env())
    if dump is None:
        raise BackupIntegrityError("assemble failed: no real postgres dump found")
    blobs = _collect_cas_blobs(cas_dirs if cas_dirs is not None else _cas_dirs_from_env())
    if not blobs:
        raise BackupIntegrityError("assemble failed: no CAS blobs found")
    dest.mkdir(parents=True, exist_ok=True)
    dump_dest = dest / "postgresql" / "daily" / dump.name
    dump_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dump, dump_dest)
    copied_blobs: list[str] = []
    for blob in blobs:
        rel = Path("blobs") / "cas" / blob.name
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(blob, target)
        copied_blobs.append(rel.as_posix())
    planted = {
        "job_id": job_id,
        "status": "assembled",
        "dump": dump.name,
        "dump_sha256": sha256_file(dump_dest),
        "blob_count": len(copied_blobs),
        "require_real_dump": True,
    }
    job = dest / "jobs" / f"{job_id}.job.json"
    man = dest / "manifests" / "backup.manifest"
    job.parent.mkdir(parents=True, exist_ok=True)
    man.parent.mkdir(parents=True, exist_ok=True)
    job.write_text(json.dumps(planted, sort_keys=True) + "\n", encoding="utf-8")
    man.write_text(
        json.dumps(
            {
                "kind": "joint-assembled",
                "version": JOINT_VERSION,
                "decision_id": DECISION_ID,
                "dump": dump.name,
                "blobs": copied_blobs,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if not is_real_postgres_dump(dump_dest):
        raise BackupIntegrityError("assemble failed: copied dump failed real-pg_dump check")
    return {
        "dest": str(dest),
        "dump": str(dump_dest),
        "dump_sha256": planted["dump_sha256"],
        "blob_count": len(copied_blobs),
        "job_id": job_id,
        "real_postgres_dump": True,
    }


def recurrence_authorized(proof_path: Path | None) -> bool:
    if proof_path is None or not proof_path.is_file():
        return False
    payload = json.loads(proof_path.read_text(encoding="utf-8"))
    return bool(payload.get("hash_identical")) and payload.get("isolated") is True


def recurrence_status(proof_path: Path | None) -> dict[str, Any]:
    if recurrence_authorized(proof_path):
        return {
            "recurrence": "authorized",
            "enabled": False,
            "reason": "hash-identical isolated restore recorded; timer unit stays disabled until deploy",
        }
    return {
        "recurrence": "disabled",
        "enabled": False,
        "reason": "hash-identical isolated restore proof missing",
    }


def run_joint(
    source_root: Path,
    restore_root: Path,
    *,
    key: bytes,
    job_id: str | None = None,
    blob_sha256: str | None = None,
    rpo_approved_by: str | None = DECISION_ID,
    rto_approved_by: str | None = DECISION_ID,
    retention_approved_by: str | None = DECISION_ID,
    destination_approved_by: str | None = DECISION_ID,
    simulate_vps_loss: bool = True,
    push: bool = False,
    target: OffsiteTarget | None = None,
    staging_root: Path | None = None,
    runner: Any = None,
    fail: str | None = None,
    proof_path: Path | None = None,
    meta_root: Path | None = None,
    remote_name: str = PACKAGE_NAME,
    require_real_dump: bool = False,
    persist_sidecar: bool = False,
) -> dict[str, Any]:
    """Encrypt DB+blobs+manifests, optionally push off-site, restore in isolation."""
    started = time.perf_counter()
    started_at = _utc_now()
    alerts: list[Alert] = []
    restore: RestoreProof | None = None
    envelope: dict[str, Any] | None = None
    offsite: dict[str, Any] = {
        "pushed": False,
        "pulled": False,
        "status": "skipped",
        "sidecar_persisted": False,
    }
    job_status = "failed"
    items: tuple[Artifact, ...] = ()
    work = source_root / ".joint-work"
    try:
        if fail == "backup":
            raise BackupIntegrityError("forced backup failure")
        items = inventory(source_root)
        envelope = write_encrypted_package(
            source_root,
            work,
            key,
            require_real_dump=require_real_dump,
        )
        chosen = blob_sha256 or next(item.sha256 for item in items if item.kind == "blob")
        resolved = target if target is not None else resolve_target()
        if push:
            if fail == "transport":
                raise OffsiteTransportError("forced transport failure")
            put_bytes(
                resolved,
                remote_name,
                (work / PACKAGE_NAME).read_bytes(),
                runner=runner,
                staging_root=staging_root,
            )
            if persist_sidecar:
                put_bytes(
                    resolved,
                    SIDECAR_KEY_NAME,
                    key,
                    runner=runner,
                    staging_root=staging_root,
                )
            pulled = get_bytes(
                resolved,
                remote_name,
                runner=runner,
                staging_root=staging_root,
            )
            if sha256_bytes(pulled) != envelope["ciphertext_sha256"]:
                raise BackupIntegrityError("off-site ciphertext hash mismatch")
            offsite = {
                "pushed": True,
                "pulled": True,
                "status": "ok",
                "nfs_host": resolved.nfs_host,
                "kind": "staging_isolated" if staging_root is not None else resolved.kind,
                "live_nfs": staging_root is None,
                "independent_of_vps_disk": resolved.independent_of_vps_disk,
                "object": remote_name,
                "bytes": envelope["bytes"],
                "sidecar_persisted": persist_sidecar,
                "sidecar_object": SIDECAR_KEY_NAME if persist_sidecar else None,
            }
            pulled_path = work / "pulled.fernet"
            pulled_path.write_bytes(pulled)
            items = restore_encrypted_package(pulled_path, restore_root, key)
        else:
            items = restore_encrypted_package(work / PACKAGE_NAME, restore_root, key)
            offsite["status"] = "local_only"
        if fail == "restore":
            raise BackupIntegrityError("forced restore failure")
        restore = restore_selected(
            restore_root,
            restore_root / "selected",
            items,
            blob_sha256=chosen,
            job_id=job_id,
            simulate_vps_loss=simulate_vps_loss,
        )
        if not restore.hash_identical:
            raise BackupIntegrityError("restore hash is not identical")
        if dest_is_source := restore_root.resolve() == source_root.resolve():
            raise BackupIntegrityError("restore dest must differ from source")
        del dest_is_source
        job_status = "success"
    except (BackupIntegrityError, OffsiteTransportError) as exc:
        alerts.append(emit_alert("backup_restore_failed", redact(str(exc))))
        job_status = "failed"
        offsite["status"] = offsite.get("status") if offsite.get("pushed") else "failed"

    if meta_root is not None and job_id:
        record_job(
            meta_root,
            job_id,
            restore.recovered_blob_sha256 if restore else None,
            verified=job_status == "success",
            reason="joint restore hash identical" if job_status == "success" else "joint backup/restore failed",
        )

    if proof_path is not None and job_status == "success" and restore is not None:
        proof_path.parent.mkdir(parents=True, exist_ok=True)
        proof_path.write_text(
            json.dumps(
                {
                    "hash_identical": True,
                    "isolated": restore_root.resolve() != source_root.resolve(),
                    "recovered_blob_sha256": restore.recovered_blob_sha256,
                    "recovered_job_id": restore.recovered_job_id,
                    "decision_id": DECISION_ID,
                    "vps_operational_claimed": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    report = {
        "schema_version": SCHEMA_VERSION,
        "version": JOINT_VERSION,
        "decision_id": DECISION_ID,
        "policy": RECOVERY_POLICY,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "duration_s": round(time.perf_counter() - started, 6),
        "artifacts": [item.as_dict() for item in items],
        "object_count": len(items),
        "bytes": envelope["bytes"] if envelope else 0,
        "approvals": approved_policy(
            rpo_approved_by=rpo_approved_by,
            rto_approved_by=rto_approved_by,
            retention_approved_by=retention_approved_by,
            destination_approved_by=destination_approved_by,
        ).as_dict(),
        "restore": None if restore is None else restore.as_dict(),
        "hash_identical": bool(restore and restore.hash_identical),
        "isolated": restore_root.resolve() != source_root.resolve(),
        "offsite": offsite,
        "package": envelope,
        "alerts": [item.as_dict() for item in alerts],
        "job_status": job_status,
        "recurrence": recurrence_status(proof_path),
        "require_real_dump": require_real_dump,
        "key_source": "vault_or_caller",
        "key_written_to_restore_root": False,
        "vps_operational_claimed": False,
    }
    return report


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
    parser.add_argument("action", choices=("inventory", "report", "seed", "joint", "policy", "assemble"))
    parser.add_argument("--root")
    parser.add_argument("--restore-root")
    parser.add_argument("--blob-sha256")
    parser.add_argument("--job-id")
    parser.add_argument("--rpo-approved-by")
    parser.add_argument("--rto-approved-by")
    parser.add_argument("--retention-approved-by")
    parser.add_argument("--destination-approved-by")
    parser.add_argument("--fail", choices=("backup", "restore", "transport"))
    parser.add_argument("--seed-dump")
    parser.add_argument("--seed-blob")
    parser.add_argument("--output")
    parser.add_argument("--key-file")
    parser.add_argument("--proof-file")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--staging-root")
    parser.add_argument("--meta-root")
    parser.add_argument("--dump-dir")
    parser.add_argument("--cas-dir")
    parser.add_argument("--require-real-dump", action="store_true")
    parser.add_argument("--persist-sidecar", action="store_true")
    parser.add_argument("--assemble", action="store_true")
    args = parser.parse_args(argv)
    if args.action == "policy":
        text = (
            json.dumps(
                {
                    "policy": RECOVERY_POLICY,
                    "recurrence": recurrence_status(Path(args.proof_file) if args.proof_file else None),
                    "vps_operational_claimed": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    elif args.action == "assemble":
        dest = Path(args.root or "")
        if not dest.parts:
            raise SystemExit("error: --root is required for assemble")
        planted = assemble_joint_source(
            dest,
            dump_dirs=(Path(args.dump_dir),) if args.dump_dir else None,
            cas_dirs=(Path(args.cas_dir),) if args.cas_dir else None,
            job_id=args.job_id or "joint-assembled",
        )
        text = json.dumps(planted, ensure_ascii=False, indent=2) + "\n"
    else:
        if not args.root:
            raise SystemExit("error: --root is required")
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
        elif args.action == "joint":
            restore_root = Path(args.restore_root or (str(root) + "-restore"))
            if args.assemble:
                assemble_joint_source(
                    root,
                    dump_dirs=(Path(args.dump_dir),) if args.dump_dir else None,
                    cas_dirs=(Path(args.cas_dir),) if args.cas_dir else None,
                    job_id=args.job_id or "joint-assembled",
                )
            key, key_path = load_or_create_vault_key(Path(args.key_file) if args.key_file else None)
            if key_path.resolve() == restore_root.resolve() or restore_root in key_path.parents:
                raise SystemExit("error: encrypt key must live in the off-VPS vault, not restore-root")
            staging = Path(args.staging_root) if args.staging_root else None
            isolated_target = None
            if staging is not None:
                isolated_target = resolve_target(
                    {
                        "BACKUP_NFS_EXPORT": os.environ.get("BACKUP_NFS_EXPORT") or "46.38.248.210:/voln1116040a1",
                        "BACKUP_MOUNT_POINT": "/mnt/storage-box",
                        "EXTRA_OFFSITE_PREFIX": "backups/extra-002",
                        "EXTRA_OFFSITE_SSH_HOST": os.environ.get("EXTRA_OFFSITE_SSH_HOST") or "staging",
                    }
                )
            report = run_joint(
                root,
                restore_root,
                key=key,
                job_id=args.job_id,
                blob_sha256=args.blob_sha256,
                rpo_approved_by=args.rpo_approved_by or DECISION_ID,
                rto_approved_by=args.rto_approved_by or DECISION_ID,
                retention_approved_by=args.retention_approved_by or DECISION_ID,
                destination_approved_by=args.destination_approved_by or DECISION_ID,
                push=args.push,
                target=isolated_target,
                staging_root=staging,
                fail=args.fail,
                proof_path=Path(args.proof_file) if args.proof_file else None,
                meta_root=Path(args.meta_root) if args.meta_root else None,
                require_real_dump=args.require_real_dump,
                persist_sidecar=args.persist_sidecar,
            )
            text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        else:
            restore_root = Path(args.restore_root or (str(root) + "-restore"))
            report_obj = run_proof(
                root,
                restore_root,
                blob_sha256=args.blob_sha256,
                job_id=args.job_id,
                rpo_approved_by=args.rpo_approved_by,
                rto_approved_by=args.rto_approved_by,
                retention_approved_by=args.retention_approved_by,
                destination_approved_by=args.destination_approved_by,
                fail=args.fail if args.fail in {"backup", "restore"} else None,
            )
            text = json.dumps(report_obj.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
