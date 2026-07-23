#!/usr/bin/env python3
"""Report off-site backup readiness without fabricating green status.

Exit 0 only when off-site destination is configured AND last transfer verified.
Missing credentials → status blocked_credential (not pass).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_VPS_PROBE = r"""
import json
import os
from pathlib import Path
vals = {}
p = Path('/etc/backup-database.conf')
if p.is_file():
    for line in p.read_text(encoding='utf-8', errors='replace').splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k, _, v = line.partition('=')
            vals[k.strip()] = v.strip()
sshv = vals.get('BACKUP_STORAGE_BOX_SSH', '')
nfs = vals.get('BACKUP_NFS_EXPORT', '')
mount = vals.get('BACKUP_MOUNT_POINT', '/mnt/storage-box')
remote_dir = vals.get('BACKUP_REMOTE_DIR', 'backups/postgresql')
configured = bool(sshv or nfs)
mount_active = bool(mount and os.path.ismount(mount))
off_dir = Path(mount) / remote_dir if remote_dir else Path(mount)
off_dumps = (
    sorted(off_dir.glob('daily/*.dump.gz'), key=lambda x: x.stat().st_mtime, reverse=True)
    if off_dir.is_dir()
    else []
)
d = Path('/var/lib/extra-consultoria/backups/postgresql')
dumps = (
    sorted(d.glob('*.dump'), key=lambda x: x.stat().st_mtime, reverse=True)
    if d.is_dir()
    else []
)
if not configured:
    status = 'blocked_credential'
elif not mount_active:
    status = 'configured_unverified'
elif off_dumps:
    status = 'ok'
else:
    status = 'configured_unverified'
out = {
    'offsite_configured': configured,
    'nfs_export': bool(nfs),
    'mount_point': mount,
    'mount_active': mount_active,
    'local_dumps': len(dumps),
    'last_local': str(dumps[0]) if dumps else None,
    'offsite_dumps': len(off_dumps),
    'last_offsite': str(off_dumps[0]) if off_dumps else None,
    'status': status,
}
print(json.dumps(out))
"""


def probe() -> dict[str, Any]:
    conf_paths = [
        Path("/etc/backup-database.conf"),
        Path(os.path.expanduser("~/.config/extra-consultoria/backup-offsite.env")),
    ]
    conf: dict[str, str] = {}
    for p in conf_paths:
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                conf[k.strip()] = v.strip()

    remote = (
        conf.get("BACKUP_STORAGE_BOX_SSH")
        or os.environ.get("BACKUP_STORAGE_BOX_SSH")
        or ""
    )
    nfs = conf.get("BACKUP_NFS_EXPORT") or os.environ.get("BACKUP_NFS_EXPORT") or ""
    mount = conf.get("BACKUP_MOUNT_POINT") or os.environ.get("BACKUP_MOUNT_POINT") or ""
    remote_dir = (
        conf.get("BACKUP_REMOTE_DIR")
        or os.environ.get("BACKUP_REMOTE_DIR")
        or "backups/postgresql"
    )
    configured = bool(remote or nfs)
    report: dict[str, Any] = {
        "as_of": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "offsite_configured": configured,
        "nfs_export": bool(nfs) or remote.startswith("nfs://"),
        "mount_point": mount or None,
        "mount_active": bool(mount and os.path.ismount(mount)),
        "last_local_dump": None,
        "last_offsite_verify": None,
        "status": "unknown",
        "blockers": [],
    }

    local_dir = Path("/var/lib/extra-consultoria/backups/postgresql")
    if local_dir.is_dir():
        dumps = sorted(
            local_dir.glob("*.dump"), key=lambda x: x.stat().st_mtime, reverse=True
        )
        if dumps:
            report["last_local_dump"] = {
                "path": str(dumps[0]),
                "mtime": datetime.fromtimestamp(dumps[0].stat().st_mtime, tz=UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "size_bytes": dumps[0].stat().st_size,
            }

    if mount and report["mount_active"]:
        off_base = Path(mount) / remote_dir if remote_dir else Path(mount)
        off_dumps = (
            sorted(
                off_base.glob("daily/*.dump.gz"),
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )
            if off_base.is_dir()
            else []
        )
        if off_dumps:
            report["last_offsite_verify"] = {
                "path": str(off_dumps[0]),
                "mtime": datetime.fromtimestamp(off_dumps[0].stat().st_mtime, tz=UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "size_bytes": off_dumps[0].stat().st_size,
                "method": "nfs_or_mounted_offsite",
            }

    if not configured:
        report["status"] = "blocked_credential"
        report["blockers"].append(
            "No off-site destination — set BACKUP_NFS_EXPORT or "
            "BACKUP_STORAGE_BOX_SSH (do not commit secrets). "
            "Local dumps alone are not off-site."
        )

    if not Path("/var/lib/extra-consultoria/backups").exists():
        try:
            r = subprocess.run(  # noqa: S603
                [
                    "/usr/bin/ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=8",
                    "ec-prod",
                    f"python3 -c {json.dumps(_VPS_PROBE)}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if r.returncode == 0 and r.stdout.strip():
                remote_rep = json.loads(r.stdout.strip().splitlines()[-1])
                report["vps_probe"] = remote_rep
                report["status"] = remote_rep.get("status", report["status"])
                if report["status"] == "blocked_credential":
                    report["blockers"] = [
                        "VPS off-site not configured "
                        "(BACKUP_NFS_EXPORT / BACKUP_STORAGE_BOX_SSH empty)"
                    ]
                elif report["status"] == "configured_unverified":
                    report["blockers"] = [
                        "Off-site configured but no verified dump under mount yet"
                    ]
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass
    elif report["status"] == "unknown" and configured:
        if mount and not os.path.ismount(mount):
            report["status"] = "fail"
            report["blockers"].append(f"configured mount {mount} not active")
        elif report.get("last_offsite_verify"):
            report["status"] = "ok"
            report["blockers"] = []
        else:
            report["status"] = "configured_unverified"
            report["blockers"].append(
                "Off-site destination configured but transfer integrity not yet "
                "verified — run backup + restore drill + hash verify"
            )

    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=None)
    args = p.parse_args(argv)
    report = probe()
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
