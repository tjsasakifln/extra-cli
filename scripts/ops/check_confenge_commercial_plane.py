"""Read-only preflight for CONFENGE commercial-plane authority.

Usage:
  python3 -m scripts.ops.check_confenge_commercial_plane
  python3 -m scripts.ops.check_confenge_commercial_plane --host-readback
  python3 -m scripts.ops.check_confenge_commercial_plane --root /path --json-only

Exit 0 = PASS, 1 = FAIL, 2 = usage/error. Never starts commercial jobs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from scripts.ops.confenge_commercial_plane import (
    CHAIN_UNITS,
    Check,
    PlaneEvaluation,
    apply_host_readback,
    evaluate_repo,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _host_onsuccess(host: str, timeout: int) -> dict[str, str]:
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout}",
        host,
        "systemctl show "
        + " ".join(CHAIN_UNITS)
        + " -p Id -p OnSuccess --no-page",
    ]
    completed = subprocess.run(  # noqa: S603 — argv only; host is an explicit flag
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout + 10,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            (completed.stderr or completed.stdout or f"ssh exit {completed.returncode}").strip()
        )
    current = ""
    values: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if line.startswith("Id="):
            current = line.split("=", 1)[1].strip()
        elif line.startswith("OnSuccess=") and current:
            values[current] = line.split("=", 1)[1].strip()
    return values


def _emit(ev: PlaneEvaluation, *, json_only: bool) -> None:
    payload = {
        "ok": ev.ok,
        "tokens": ev.tokens,
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in ev.checks],
        "errors": ev.errors,
    }
    if json_only:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()
    for key in (
        "PNCP_LIVE_ROLE",
        "COMMERCIAL_OPERATIONAL_SOURCE",
        "PNCP_FRESH_IS_COMMERCIAL_GATE",
        "HOST_ONSUCCESS_COUPLING",
        "COMMERCIAL_STAGE_ORPHANS",
        "DATALAKE_FAIL_CLOSED_GATES",
        "CANONICAL_MUTEX",
        "ARCHITECTURE_AUTHORITY",
    ):
        print(f"{key}={ev.tokens.get(key, 'UNKNOWN')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--host-readback", action="store_true")
    parser.add_argument("--host", default="ec-prod")
    parser.add_argument("--ssh-timeout", type=int, default=20)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    try:
        ev = evaluate_repo(root)
    except Exception as exc:  # noqa: BLE001 — CLI must not traceback as success
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.host_readback:
        try:
            apply_host_readback(ev, _host_onsuccess(args.host, args.ssh_timeout))
        except Exception as exc:  # noqa: BLE001 — unreachable host stays gating
            ev.tokens["HOST_ONSUCCESS_COUPLING"] = "NOT_TESTED"
            ev.errors.append(f"host-readback launcher failed: {exc}")
            ev.checks.append(Check("host_readback_launcher", False, str(exc)))
            ev.tokens["ARCHITECTURE_AUTHORITY"] = "FAIL"

    _emit(ev, json_only=args.json_only)
    return 0 if ev.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
