"""Off-site transport for EXTRA-002 — NFS/S3-compatible hop, never the VPS disk.

Reads destination from the already-provisioned vault/env. Secrets and signed
URLs are never logged. A path on the VPS disk is not an off-site target.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from scripts.ops.blob_cas import redact

TargetKind = Literal["nfs_mount", "ssh_hop", "undecided"]
TargetStatus = Literal[
    "ok",
    "configured_unverified",
    "blocked_credential",
    "not_offsite",
]

CONF_CANDIDATES = (
    Path("/etc/backup-database.conf"),
    Path.home() / ".config/extra-consultoria/backup-offsite.env",
    Path.home() / ".config/extra-consultoria/netcup-storagespace.env",
)
VPS_DISK_PREFIXES = (
    "/var/lib/extra-consultoria",
    "/var/lib/postgresql",
    "/var/lib/docker",
)
SAFE_RELPATH = re.compile(r"^[A-Za-z0-9._/-]+$")
DEFAULT_PREFIX = "backups/extra-002"
DEFAULT_MOUNT = "/mnt/storage-box"


class OffsiteTransportError(Exception):
    """Fail-closed off-site transport error."""


class OffsiteCredentialError(OffsiteTransportError):
    """Destination or credential is missing."""


class OffsiteNotIndependentError(OffsiteTransportError):
    """Attempted to treat the VPS disk as off-site."""


Runner = Callable[[list[str], bytes | None], tuple[int, bytes, bytes]]


@dataclass(frozen=True)
class OffsiteTarget:
    kind: TargetKind
    status: TargetStatus
    nfs_host: str | None
    mount_point: str | None
    prefix: str
    hop_configured: bool
    independent_of_vps_disk: bool
    new_paid_plan: bool
    blockers: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_conf() -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in CONF_CANDIDATES:
        if not path.is_file():
            continue
        mode = path.stat().st_mode
        if mode & (stat.S_IROTH | stat.S_IWOTH):
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            key, _, value = line.partition("=")
            merged[key.strip()] = value.strip().strip('"').strip("'")
    for key in (
        "BACKUP_NFS_EXPORT",
        "BACKUP_STORAGE_BOX_SSH",
        "BACKUP_MOUNT_POINT",
        "BACKUP_REMOTE_DIR",
        "EXTRA_OFFSITE_PREFIX",
        "EXTRA_OFFSITE_SSH_HOST",
        "EXTRA_OFFSITE_SSH_PORT",
        "EXTRA_OFFSITE_SSH_USER",
        "EXTRA_OFFSITE_SSH_IDENTITY",
    ):
        value = os.environ.get(key)
        if value:
            merged[key] = value
    return merged


def _host_from_export(raw: str) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("nfs://"):
        text = text[6:]
    if "@" in text:
        text = text.split("@", 1)[1]
    host = text.split(":", 1)[0].split("/", 1)[0]
    return host or None


def _is_vps_disk(path: str) -> bool:
    resolved = path.rstrip("/") or path
    return any(resolved == prefix or resolved.startswith(prefix + "/") for prefix in VPS_DISK_PREFIXES)


def _safe_relpath(relpath: str) -> str:
    cleaned = relpath.replace("\\", "/").lstrip("/")
    if not cleaned or ".." in cleaned.split("/") or not SAFE_RELPATH.match(cleaned):
        raise OffsiteTransportError("refusing unsafe off-site relative path")
    return cleaned


def resolve_target(conf: dict[str, str] | None = None) -> OffsiteTarget:
    """Resolve an already-provisioned off-site destination. Never logs secrets."""
    data = conf if conf is not None else _read_conf()
    export = data.get("BACKUP_NFS_EXPORT") or data.get("BACKUP_STORAGE_BOX_SSH") or ""
    nfs_host = _host_from_export(export)
    mount = data.get("BACKUP_MOUNT_POINT") or DEFAULT_MOUNT
    prefix = data.get("EXTRA_OFFSITE_PREFIX") or DEFAULT_PREFIX
    hop = bool(data.get("EXTRA_OFFSITE_SSH_HOST") or data.get("EXTRA_OFFSITE_SSH_USER"))
    blockers: list[str] = []

    if _is_vps_disk(mount) or _is_vps_disk(prefix):
        return OffsiteTarget(
            kind="undecided",
            status="not_offsite",
            nfs_host=nfs_host,
            mount_point=mount,
            prefix=prefix,
            hop_configured=hop,
            independent_of_vps_disk=False,
            new_paid_plan=False,
            blockers=("VPS disk is not an off-site target",),
        )

    if not nfs_host:
        blockers.append("BACKUP_NFS_EXPORT / BACKUP_STORAGE_BOX_SSH missing")
        return OffsiteTarget(
            kind="undecided",
            status="blocked_credential",
            nfs_host=None,
            mount_point=mount,
            prefix=prefix,
            hop_configured=hop,
            independent_of_vps_disk=True,
            new_paid_plan=False,
            blockers=tuple(blockers),
        )

    if nfs_host in {"127.0.0.1", "localhost", "::1"}:
        return OffsiteTarget(
            kind="undecided",
            status="not_offsite",
            nfs_host=nfs_host,
            mount_point=mount,
            prefix=prefix,
            hop_configured=hop,
            independent_of_vps_disk=False,
            new_paid_plan=False,
            blockers=("loopback host is not off-site",),
        )

    mount_active = bool(mount and os.path.ismount(mount))
    if mount_active:
        kind: TargetKind = "nfs_mount"
        status: TargetStatus = "ok"
    elif hop:
        kind = "ssh_hop"
        status = "configured_unverified"
    else:
        kind = "nfs_mount"
        status = "configured_unverified"
        blockers.append("NFS host known but mount inactive and no SSH hop")

    return OffsiteTarget(
        kind=kind,
        status=status,
        nfs_host=nfs_host,
        mount_point=mount,
        prefix=prefix,
        hop_configured=hop,
        independent_of_vps_disk=True,
        new_paid_plan=False,
        blockers=tuple(blockers),
    )


def _default_runner(argv: list[str], stdin: bytes | None) -> tuple[int, bytes, bytes]:
    result = subprocess.run(  # noqa: S603
        argv,
        input=stdin,
        capture_output=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _ssh_argv(conf: dict[str, str]) -> list[str]:
    host = conf.get("EXTRA_OFFSITE_SSH_HOST")
    if not host:
        raise OffsiteCredentialError("EXTRA_OFFSITE_SSH_HOST missing")
    user = conf.get("EXTRA_OFFSITE_SSH_USER") or "root"
    port = conf.get("EXTRA_OFFSITE_SSH_PORT") or "22"
    identity = conf.get("EXTRA_OFFSITE_SSH_IDENTITY")
    argv = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=20",
        "-p",
        port,
    ]
    if identity:
        argv.extend(["-i", identity])
    argv.append(f"{user}@{host}")
    return argv


def put_bytes(
    target: OffsiteTarget,
    relpath: str,
    data: bytes,
    *,
    conf: dict[str, str] | None = None,
    runner: Runner | None = None,
    staging_root: Path | None = None,
) -> str:
    """Write bytes to the off-site prefix. Returns the remote relative path."""
    if target.status in {"blocked_credential", "not_offsite"} or not target.independent_of_vps_disk:
        raise OffsiteNotIndependentError(target.blockers[0] if target.blockers else "off-site target refused")
    if target.kind == "undecided":
        raise OffsiteCredentialError("off-site destination undecided")
    safe = _safe_relpath(f"{target.prefix.rstrip('/')}/{relpath}")
    execute = runner or _default_runner
    settings = conf if conf is not None else _read_conf()

    if staging_root is not None:
        dest = staging_root / safe
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".partial")
        tmp.write_bytes(data)
        tmp.replace(dest)
        return safe

    if target.kind == "nfs_mount" and target.mount_point and os.path.ismount(target.mount_point):
        dest = Path(target.mount_point) / safe
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".partial")
        tmp.write_bytes(data)
        tmp.replace(dest)
        return safe

    if not target.hop_configured:
        raise OffsiteCredentialError("SSH hop required when NFS is not mounted here")

    remote = f"{target.mount_point.rstrip('/')}/{safe}"
    remote_dir = str(Path(remote).parent)
    command = (
        f"install -d -m 0750 {json.dumps(remote_dir)} && "
        f"cat > {json.dumps(remote + '.partial')} && "
        f"mv {json.dumps(remote + '.partial')} {json.dumps(remote)}"
    )
    argv = [*_ssh_argv(settings), command]
    code, _stdout, stderr = execute(argv, data)
    if code != 0:
        raise OffsiteTransportError(redact((stderr or b"ssh put failed").decode("utf-8", "replace")[:300]))
    return safe


def get_bytes(
    target: OffsiteTarget,
    relpath: str,
    *,
    conf: dict[str, str] | None = None,
    runner: Runner | None = None,
    staging_root: Path | None = None,
) -> bytes:
    """Read bytes from the off-site prefix."""
    if target.status in {"blocked_credential", "not_offsite"}:
        raise OffsiteCredentialError("off-site destination unavailable")
    safe = _safe_relpath(f"{target.prefix.rstrip('/')}/{relpath}")
    execute = runner or _default_runner
    settings = conf if conf is not None else _read_conf()

    if staging_root is not None:
        dest = staging_root / safe
        if not dest.is_file():
            raise OffsiteTransportError(f"off-site object missing: {safe}")
        return dest.read_bytes()

    if target.kind == "nfs_mount" and target.mount_point and os.path.ismount(target.mount_point):
        dest = Path(target.mount_point) / safe
        if not dest.is_file():
            raise OffsiteTransportError(f"off-site object missing: {safe}")
        return dest.read_bytes()

    if not target.hop_configured:
        raise OffsiteCredentialError("SSH hop required when NFS is not mounted here")

    remote = f"{target.mount_point.rstrip('/')}/{safe}"
    argv = [*_ssh_argv(settings), f"cat {json.dumps(remote)}"]
    code, stdout, stderr = execute(argv, None)
    if code != 0:
        raise OffsiteTransportError(redact((stderr or b"ssh get failed").decode("utf-8", "replace")[:300]))
    return stdout


def head_remote(
    target: OffsiteTarget,
    relpath: str,
    *,
    conf: dict[str, str] | None = None,
    runner: Runner | None = None,
    staging_root: Path | None = None,
) -> dict[str, Any]:
    payload = get_bytes(
        target,
        relpath,
        conf=conf,
        runner=runner,
        staging_root=staging_root,
    )
    from hashlib import sha256

    return {
        "relpath": _safe_relpath(f"{target.prefix.rstrip('/')}/{relpath}"),
        "size_bytes": len(payload),
        "sha256": sha256(payload).hexdigest(),
        "exists": True,
    }
