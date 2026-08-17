"""#271 — content-addressed blob store with store/get/head integrity.

Filesystem is the in-repo approved backend. Object-storage is a declared
backend that stays blocked until a human destination and credentials exist.
Blobs never enter PostgreSQL or Git. Unavailability must not drop metadata
or mark a job successful.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

Backend = Literal["filesystem", "object_storage"]
JobStatus = Literal["success", "failed", "blocked"]

SCHEMA_VERSION = 1
CAS_PREFIX = "cas"
META_PREFIX = "meta"
JOB_PREFIX = "jobs"
FORBIDDEN_URI_SCHEMES = ("postgresql://", "postgres://", "git://")

_SIGNED_QS = re.compile(
    r"([?&](?:X-Amz-Signature|X-Amz-Credential|Signature|sig|token|Expires)=)[^&\s]+",
    re.IGNORECASE,
)
_SECRET = re.compile(
    r"(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|Bearer\s+\S+|AWS_SECRET_ACCESS_KEY=\S+)",
    re.IGNORECASE,
)


class BlobStoreError(Exception):
    """Fail-closed blob store error."""


class CorruptionError(BlobStoreError):
    """Stored bytes no longer match the SHA-256 address."""


class BackendUnavailableError(BlobStoreError):
    """Blob backend cannot be reached; metadata must still survive."""


class DestinationUndecidedError(BlobStoreError):
    """Object-storage destination or credentials still need a human."""


@dataclass(frozen=True)
class BlobMeta:
    sha256: str
    size_bytes: int
    content_type: str
    stored_at: str
    backend: Backend
    replica: str | None
    job_id: str | None
    postgres_stored: bool
    git_stored: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BlobHead:
    sha256: str
    size_bytes: int
    backend: Backend
    exists: bool
    intact: bool
    metadata_present: bool
    replica: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    sha256: str | None
    status: JobStatus
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def redact(text: str) -> str:
    """Strip signed-URL query values and obvious secrets before logging."""
    cleaned = _SIGNED_QS.sub(r"\1[REDACTED]", text)
    return _SECRET.sub("[REDACTED]", cleaned)


def cas_path(root: Path, digest: str) -> Path:
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise BlobStoreError("sha256 must be a 64-char lowercase hex digest")
    return root / CAS_PREFIX / digest[:2] / digest[2:4] / digest


def meta_path(meta_root: Path, digest: str) -> Path:
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise BlobStoreError("sha256 must be a 64-char lowercase hex digest")
    return meta_root / META_PREFIX / digest[:2] / digest[2:4] / f"{digest}.json"


def job_path(meta_root: Path, job_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", job_id).strip("._-") or "job"
    return meta_root / JOB_PREFIX / f"{safe}.json"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial")
    tmp.write_bytes(data)
    tmp.replace(path)


def _refuse_postgres_or_git(uri: str | None) -> None:
    if not uri:
        return
    folded = uri.strip().casefold()
    if any(folded.startswith(scheme) for scheme in FORBIDDEN_URI_SCHEMES):
        raise BlobStoreError("docs/PDFs must stay outside PostgreSQL and Git")
    if "/.git/" in folded or folded.endswith(".git"):
        raise BlobStoreError("docs/PDFs must stay outside PostgreSQL and Git")


def resolve_backend(
    requested: Backend,
    *,
    destination_approved_by: str | None,
    credentials_present: bool,
) -> tuple[Backend, str | None]:
    """Filesystem is approved in-repo. Object storage needs a human destination."""
    if requested == "filesystem":
        replica = None
        if destination_approved_by and credentials_present:
            replica = "offsite-pending-verify"
        return "filesystem", replica
    if not destination_approved_by or not credentials_present:
        raise DestinationUndecidedError("object_storage backend blocked: human destination and credentials required")
    return "object_storage", "offsite-declared"


def store(
    data: bytes,
    *,
    root: Path,
    meta_root: Path,
    backend: Backend = "filesystem",
    content_type: str = "application/octet-stream",
    job_id: str | None = None,
    destination_approved_by: str | None = None,
    credentials_present: bool = False,
    available: bool = True,
    offsite_root: Path | None = None,
) -> BlobMeta:
    """Address by SHA-256, write atomically, verify read-after-write."""
    if not data:
        raise BlobStoreError("refusing to store empty blob")
    _refuse_postgres_or_git(str(root))
    _refuse_postgres_or_git(str(meta_root))
    if offsite_root is not None:
        _refuse_postgres_or_git(str(offsite_root))
    digest = sha256_bytes(data)
    chosen, replica = resolve_backend(
        backend,
        destination_approved_by=destination_approved_by,
        credentials_present=credentials_present,
    )
    if chosen == "object_storage" and offsite_root is None:
        raise DestinationUndecidedError("object_storage backend blocked: offsite_root required")
    if not available:
        meta = BlobMeta(
            sha256=digest,
            size_bytes=len(data),
            content_type=content_type,
            stored_at=_utc_now(),
            backend=chosen,
            replica=replica,
            job_id=job_id,
            postgres_stored=False,
            git_stored=False,
        )
        _atomic_write(meta_path(meta_root, digest), _canonical_bytes(meta.as_dict()))
        if job_id:
            record_job(meta_root, job_id, digest, verified=False, reason="backend unavailable")
        raise BackendUnavailableError("blob backend unavailable; metadata preserved, job not success")

    dest = cas_path(root, digest)
    _atomic_write(dest, data)
    reread = dest.read_bytes()
    if sha256_bytes(reread) != digest:
        dest.unlink(missing_ok=True)
        if job_id:
            record_job(meta_root, job_id, digest, verified=False, reason="read-after-write mismatch")
        raise CorruptionError("read-after-write hash mismatch")

    replica_label = replica
    if offsite_root is not None:
        replica_dest = cas_path(offsite_root, digest)
        try:
            _atomic_write(replica_dest, data)
            if sha256_bytes(replica_dest.read_bytes()) != digest:
                replica_dest.unlink(missing_ok=True)
                raise CorruptionError("offsite replica read-after-write mismatch")
            replica_label = "offsite-verified"
        except OSError as exc:
            if job_id:
                record_job(meta_root, job_id, digest, verified=False, reason="offsite replica failed")
            raise BackendUnavailableError("offsite replica unavailable; job not success") from exc
        except CorruptionError:
            if job_id:
                record_job(meta_root, job_id, digest, verified=False, reason="offsite replica corrupt")
            raise

    meta = BlobMeta(
        sha256=digest,
        size_bytes=len(data),
        content_type=content_type,
        stored_at=_utc_now(),
        backend=chosen,
        replica=replica_label,
        job_id=job_id,
        postgres_stored=False,
        git_stored=False,
    )
    _atomic_write(meta_path(meta_root, digest), _canonical_bytes(meta.as_dict()))
    if job_id:
        record_job(meta_root, job_id, digest, verified=True, reason="read-after-write ok")
    return meta


def get(digest: str, *, root: Path) -> bytes:
    path = cas_path(root, digest)
    if not path.is_file():
        raise BlobStoreError(f"blob not found: {digest}")
    payload = path.read_bytes()
    actual = sha256_bytes(payload)
    if actual != digest:
        raise CorruptionError(f"corruption detected: expected {digest}, got {actual}")
    return payload


def head(digest: str, *, root: Path, meta_root: Path) -> BlobHead:
    meta_file = meta_path(meta_root, digest)
    metadata_present = meta_file.is_file()
    recorded: dict[str, Any] = {}
    if metadata_present:
        recorded = json.loads(meta_file.read_text(encoding="utf-8"))
    path = cas_path(root, digest)
    exists = path.is_file()
    intact = False
    size = int(recorded.get("size_bytes") or 0)
    if exists:
        payload = path.read_bytes()
        size = len(payload)
        intact = sha256_bytes(payload) == digest
        if not intact:
            raise CorruptionError(f"corruption detected on head: {digest}")
    backend: Backend = recorded.get("backend") or "filesystem"
    return BlobHead(
        sha256=digest,
        size_bytes=size,
        backend=backend if backend in {"filesystem", "object_storage"} else "filesystem",
        exists=exists,
        intact=intact,
        metadata_present=metadata_present,
        replica=recorded.get("replica"),
    )


def record_job(
    meta_root: Path,
    job_id: str,
    digest: str | None,
    *,
    verified: bool,
    reason: str,
) -> JobRecord:
    """Job success is allowed only after verified store."""
    status: JobStatus = "success" if verified else "failed"
    record = JobRecord(job_id=job_id, sha256=digest, status=status, reason=reason)
    _atomic_write(job_path(meta_root, job_id), _canonical_bytes(record.as_dict()))
    return record


def load_job(meta_root: Path, job_id: str) -> JobRecord:
    payload = json.loads(job_path(meta_root, job_id).read_text(encoding="utf-8"))
    return JobRecord(
        job_id=str(payload["job_id"]),
        sha256=payload.get("sha256"),
        status=payload["status"],
        reason=str(payload.get("reason") or ""),
    )


def _canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def log_event(logger: logging.Logger, message: str, **fields: Any) -> None:
    safe = {key: redact(str(value)) for key, value in fields.items()}
    logger.info(redact(message), extra=safe)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Content-addressed blob CAS (#271)")
    parser.add_argument("action", choices=("store", "get", "head"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--meta-root", required=True)
    parser.add_argument("--data-file")
    parser.add_argument("--sha256")
    parser.add_argument("--backend", default="filesystem", choices=("filesystem", "object_storage"))
    parser.add_argument("--job-id")
    parser.add_argument("--destination-approved-by")
    parser.add_argument("--credentials-present", action="store_true")
    parser.add_argument("--unavailable", action="store_true")
    parser.add_argument("--content-type", default="application/octet-stream")
    parser.add_argument("--offsite-root")
    args = parser.parse_args(argv)
    root = Path(args.root)
    meta_root = Path(args.meta_root)
    try:
        if args.action == "store":
            if not args.data_file:
                raise BlobStoreError("--data-file is required for store")
            data = Path(args.data_file).read_bytes()
            meta = store(
                data,
                root=root,
                meta_root=meta_root,
                backend=args.backend,
                content_type=args.content_type,
                job_id=args.job_id,
                destination_approved_by=args.destination_approved_by or os.environ.get("BLOB_DESTINATION_APPROVED_BY"),
                credentials_present=args.credentials_present or bool(os.environ.get("BLOB_OFFSITE_CREDENTIALS")),
                available=not args.unavailable,
                offsite_root=Path(args.offsite_root) if args.offsite_root else None,
            )
            sys.stdout.write(json.dumps(meta.as_dict(), ensure_ascii=False, indent=2) + "\n")
            return 0
        if not args.sha256:
            raise BlobStoreError("--sha256 is required for get/head")
        if args.action == "get":
            payload = get(args.sha256, root=root)
            sys.stdout.buffer.write(payload)
            return 0
        info = head(args.sha256, root=root, meta_root=meta_root)
        sys.stdout.write(json.dumps(info.as_dict(), ensure_ascii=False, indent=2) + "\n")
        return 0
    except DestinationUndecidedError as exc:
        sys.stderr.write(redact(str(exc)) + "\n")
        return 3
    except BackendUnavailableError as exc:
        sys.stderr.write(redact(str(exc)) + "\n")
        return 4
    except CorruptionError as exc:
        sys.stderr.write(redact(str(exc)) + "\n")
        return 5
    except BlobStoreError as exc:
        sys.stderr.write(redact(str(exc)) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
