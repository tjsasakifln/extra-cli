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
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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

    remote = conf.get("BACKUP_STORAGE_BOX_SSH") or os.environ.get("BACKUP_STORAGE_BOX_SSH") or ""
    mount = conf.get("BACKUP_MOUNT_POINT") or os.environ.get("BACKUP_MOUNT_POINT") or ""
    report: dict[str, Any] = {
        "as_of": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "offsite_configured": bool(remote),
        "mount_point": mount or None,
        "mount_active": bool(mount and os.path.ismount(mount)),
        "last_local_dump": None,
        "last_offsite_verify": None,
        "status": "unknown",
        "blockers": [],
    }

    local_dir = Path("/var/lib/extra-consultoria/backups/postgresql")
    if local_dir.is_dir():
        dumps = sorted(local_dir.glob("*.dump"), key=lambda x: x.stat().st_mtime, reverse=True)
        if dumps:
            report["last_local_dump"] = {
                "path": str(dumps[0]),
                "mtime": datetime.fromtimestamp(dumps[0].stat().st_mtime, tz=UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "size_bytes": dumps[0].stat().st_size,
            }

    if not remote:
        report["status"] = "blocked_credential"
        report["blockers"].append(
            "BACKUP_STORAGE_BOX_SSH empty — configure off-site destination "
            "(do not commit secrets). Local dumps alone are not off-site."
        )
        return report

    # If configured, require mount or successful rsync probe without printing secrets
    if mount and not os.path.ismount(mount):
        report["status"] = "fail"
        report["blockers"].append(f"configured mount {mount} not active")
        return report

    report["status"] = "configured_unverified"
    report["blockers"].append(
        "Off-site destination configured but transfer integrity not yet verified "
        "in this campaign run — run restore drill + hash verify"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=None)
    args = p.parse_args(argv)
    report = probe()
    # Prefer probing VPS via ssh when local is laptop
    if not Path("/var/lib/extra-consultoria/backups").exists():
        try:
            r = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=8",
                    "ec-prod",
                    "python3 - <<'PY'\n"
                    "import json,os\n"
                    "from pathlib import Path\n"
                    "from datetime import datetime, timezone\n"
                    "remote=open('/etc/backup-database.conf').read() if Path('/etc/backup-database.conf').is_file() else ''\n"
                    "has_ssh='BACKUP_STORAGE_BOX_SSH=' in remote and not any(line.strip().endswith('BACKUP_STORAGE_BOX_SSH=') or line.strip()=='BACKUP_STORAGE_BOX_SSH=' for line in remote.splitlines() if 'BACKUP_STORAGE_BOX_SSH' in line)\n"
                    # simpler parse
                    "vals={}\n"
                    "[vals.update({l.split('=',1)[0].strip(): l.split('=',1)[1].strip()}) for l in remote.splitlines() if '=' in l and not l.strip().startswith('#')]\n"
                    "sshv=vals.get('BACKUP_STORAGE_BOX_SSH','')\n"
                    "d=Path('/var/lib/extra-consultoria/backups/postgresql')\n"
                    "dumps=sorted(d.glob('*.dump'), key=lambda x: x.stat().st_mtime, reverse=True) if d.is_dir() else []\n"
                    "out={'offsite_configured': bool(sshv), 'local_dumps': len(dumps), "
                    "'last_local': str(dumps[0]) if dumps else None, "
                    "'status': 'blocked_credential' if not sshv else 'configured_unverified'}\n"
                    "print(json.dumps(out))\n"
                    "PY",
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
                        "VPS BACKUP_STORAGE_BOX_SSH empty — off-site not configured"
                    ]
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass

    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
