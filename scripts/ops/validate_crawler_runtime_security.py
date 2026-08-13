"""Fail-closed preflight and static systemd hardening score for crawler units."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

REQUIRED_DIRECTIVES = (
    "User=extra-consultoria",
    "NoNewPrivileges=true",
    "PrivateTmp=true",
    "PrivateDevices=true",
    "ProtectSystem=strict",
    "ProtectHome=true",
    "ProtectKernelTunables=true",
    "ProtectKernelModules=true",
    "ProtectControlGroups=true",
    "RestrictSUIDSGID=true",
)
MINIMUM_SCORE = 0.9


def unit_hardening_score(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    present = [directive for directive in REQUIRED_DIRECTIVES if directive in text]
    missing = [directive for directive in REQUIRED_DIRECTIVES if directive not in text]
    score = len(present) / len(REQUIRED_DIRECTIVES)
    return {
        "unit": str(path),
        "score": score,
        "minimum": MINIMUM_SCORE,
        "passed": score >= MINIMUM_SCORE,
        "missing": missing,
    }


def validate_environment_file(path: Path, *, expected_uid: int | None = None) -> dict[str, Any]:
    info = path.stat()
    mode = stat.S_IMODE(info.st_mode)
    owner_ok = expected_uid is None or info.st_uid == expected_uid
    return {
        "path": str(path),
        "mode": f"{mode:04o}",
        "owner_uid": info.st_uid,
        "expected_uid": expected_uid,
        "passed": mode == 0o600 and owner_ok,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate crawler runtime security")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--unit", type=Path)
    parser.add_argument("--allow-root-check", action="store_true")
    args = parser.parse_args(argv)
    checks: dict[str, Any] = {
        "non_root": args.allow_root_check or os.geteuid() != 0,
        "environment_file": validate_environment_file(
            args.env_file,
            expected_uid=None if args.allow_root_check else os.geteuid(),
        ),
    }
    if args.unit:
        checks["unit_hardening"] = unit_hardening_score(args.unit)
    passed = bool(checks["non_root"] and checks["environment_file"]["passed"])
    if "unit_hardening" in checks:
        passed = passed and bool(checks["unit_hardening"]["passed"])
    print(json.dumps({"status": "pass" if passed else "fail", "checks": checks}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
