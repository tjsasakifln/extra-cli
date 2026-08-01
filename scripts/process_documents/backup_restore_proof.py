"""External backup + restore proof for process-documents meta/raw (not local-only copy).

Produces a structured report. Live off-site upload/restore is attempted only when
``PROCESS_DOCUMENTS_BACKUP_REMOTE`` (rsync/scp target) or existing offsite tooling
is configured. Never claims green without verification steps.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.process_documents.storage import ensure_roots, write_json


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def pack_meta_snapshot(meta: Path, dest_tar: Path) -> dict[str, Any]:
    dest_tar.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest_tar, "w:gz") as tar:
        # Prefer small operational state, not full raw CAS
        for name in (
            "checkpoints",
            "process_cards",
            "daily_reports",
            "document-incremental-manifest.json",
            "ops-health-latest.json",
            "collect-batch-latest.json",
            "entity_queue.json",
        ):
            p = meta / name
            if p.exists():
                tar.add(p, arcname=name)
    digest = _sha256_file(dest_tar)
    return {
        "archive": str(dest_tar),
        "sha256": digest,
        "size_bytes": dest_tar.stat().st_size,
    }


def restore_snapshot_verify(archive: Path, expected_sha256: str) -> dict[str, Any]:
    actual = _sha256_file(archive)
    if actual != expected_sha256:
        return {"ok": False, "error": "sha256 mismatch", "expected": expected_sha256, "actual": actual}
    with tempfile.TemporaryDirectory(prefix="pd-restore-") as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(tmp_path, filter="data")  # controlled archive we just created
        restored = list(tmp_path.rglob("*"))
        return {
            "ok": True,
            "sha256_verified": True,
            "restored_entries": len(restored),
            "sample": [str(p.relative_to(tmp_path)) for p in restored[:20]],
        }


def attempt_remote_copy(archive: Path, remote: str) -> dict[str, Any]:
    """Best-effort rsync/scp to remote. Fails closed with structured error."""
    try:
        # rsync preferred
        cmd = ["rsync", "-a", str(archive), remote]
        proc = subprocess.run(  # noqa: S603 — fixed argv, remote from ops config
            cmd, capture_output=True, text=True, timeout=120, check=False
        )
        if proc.returncode == 0:
            return {"ok": True, "method": "rsync", "remote": remote, "stdout": proc.stdout[-500:]}
        return {
            "ok": False,
            "method": "rsync",
            "remote": remote,
            "returncode": proc.returncode,
            "stderr": (proc.stderr or "")[-800:],
        }
    except FileNotFoundError:
        try:
            cmd = ["scp", str(archive), remote]
            proc = subprocess.run(  # noqa: S603
                cmd, capture_output=True, text=True, timeout=120, check=False
            )
            if proc.returncode == 0:
                return {"ok": True, "method": "scp", "remote": remote}
            return {
                "ok": False,
                "method": "scp",
                "remote": remote,
                "returncode": proc.returncode,
                "stderr": (proc.stderr or "")[-800:],
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def run_backup_restore_proof(
    *,
    meta_root: Path | None = None,
    raw_root: Path | None = None,
    remote: str | None = None,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """Pack meta snapshot, verify local restore by hash, optionally copy off-host."""
    _, meta = ensure_roots(raw_root=raw_root, meta_root=meta_root)
    remote = remote or os.environ.get("PROCESS_DOCUMENTS_BACKUP_REMOTE")
    work = Path(work_dir or (meta / "backup_proof"))
    work.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive = work / f"process_documents_meta_{stamp}.tar.gz"

    pack = pack_meta_snapshot(meta, archive)
    restore = restore_snapshot_verify(archive, pack["sha256"])

    remote_result: dict[str, Any]
    if remote:
        remote_result = attempt_remote_copy(archive, remote)
    else:
        remote_result = {
            "ok": False,
            "skipped": True,
            "reason": "PROCESS_DOCUMENTS_BACKUP_REMOTE not set — local restore verified only",
        }

    # Also surface existing project offsite backup status if available
    offsite_status: dict[str, Any] | None = None
    try:
        from scripts.ops.campaign_offsite_backup_status import main as _offsite_main  # type: ignore

        offsite_status = {"note": "see scripts.ops.campaign_offsite_backup_status for DB offsite"}
        _ = _offsite_main
    except Exception:
        offsite_status = None

    report = {
        "generated_at": _now_iso(),
        "pack": pack,
        "local_restore": restore,
        "remote_copy": remote_result,
        "external_backup_proven": bool(remote_result.get("ok")),
        "local_restore_proven": bool(restore.get("ok")),
        "claims": {
            "VPS_OPERATIONAL": False,
            "external_backup_restore": bool(remote_result.get("ok") and restore.get("ok")),
        },
        "offsite_status_note": offsite_status,
    }
    write_json(work / "backup-restore-proof-latest.json", report)
    write_json(meta / "backup-restore-proof-latest.json", report)
    return report
