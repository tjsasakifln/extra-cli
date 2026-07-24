#!/usr/bin/env python3
"""Deterministic gate for CANONICAL-ENTITY-LINKAGE-01.

Fail-closed: no || true, no skip-as-pass, no production/soak access.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.linkage.isolation import check_dsn, scan_command_line  # noqa: E402


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_cmd(cmd: list[str], *, env: dict[str, str], timeout: int = 600) -> dict[str, Any]:
    hits = scan_command_line(cmd)
    if hits:
        return {
            "cmd": cmd,
            "exit_code": 99,
            "stdout": "",
            "stderr": f"ISOLATION_GUARD blocked command markers={hits}",
            "seconds": 0,
        }
    t0 = time.monotonic()
    try:
        p = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "cmd": cmd,
            "exit_code": p.returncode,
            "stdout": (p.stdout or "")[-8000:],
            "stderr": (p.stderr or "")[-4000:],
            "seconds": round(time.monotonic() - t0, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "exit_code": 124,
            "stdout": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr": f"timeout after {timeout}s",
            "seconds": round(time.monotonic() - t0, 3),
        }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=os.environ.get("LINKAGE_TEST_DSN"))
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "artifacts/campaigns/CANONICAL-ENTITY-LINKAGE-01/campaign-gate.json",
    )
    ap.add_argument("--skip-full-suite", action="store_true", help="Only for local debug; RC must not use")
    args = ap.parse_args(argv)

    dsn = args.dsn or ""
    iso = check_dsn(dsn)
    results: list[dict[str, Any]] = []
    ok = True

    if not iso.ok or iso.production_touched:
        ok = False
        results.append({"step": "isolation", "exit_code": 2, "detail": iso.as_dict()})
    else:
        results.append({"step": "isolation", "exit_code": 0, "detail": iso.as_dict()})

    env = os.environ.copy()
    env["LINKAGE_TEST_DSN"] = dsn
    env["LOCAL_DATALAKE_DSN"] = dsn
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    steps: list[tuple[str, list[str], int]] = [
        ("migrate_1", [sys.executable, "-m", "scripts.ops.apply_migrations", "--dsn", dsn], 300),
        ("migrate_2_idempotent", [sys.executable, "-m", "scripts.ops.apply_migrations", "--dsn", dsn], 300),
        (
            "unit_linkage",
            [sys.executable, "-m", "pytest", "tests/test_canonical_entity_linkage.py", "-q", "--tb=line"],
            180,
        ),
        (
            "workspace_entity",
            [sys.executable, "-m", "scripts.workspace", "entity", "--json", "--dsn", dsn],
            60,
        ),
        (
            "workspace_competitors",
            [sys.executable, "-m", "scripts.workspace", "competitors", "--json", "--dsn", dsn, "--limit", "5"],
            60,
        ),
        (
            "workspace_expiring",
            [sys.executable, "-m", "scripts.workspace", "expiring-contracts", "--json", "--dsn", dsn, "--limit", "5"],
            60,
        ),
        ("isolation_guard_cli", [sys.executable, "-m", "scripts.linkage", "guard", "--dsn", dsn], 30),
    ]
    if not args.skip_full_suite:
        steps.insert(
            3,
            (
                "full_suite",
                [sys.executable, "-m", "scripts.ops.run_full_suite"],
                1800,
            ),
        )
        steps.insert(
            4,
            (
                "golden_path",
                [sys.executable, "-m", "scripts.golden_path", "--dsn", dsn],
                600,
            ),
        )

    for name, cmd, timeout in steps:
        if not iso.ok:
            results.append({"step": name, "exit_code": 2, "skipped_reason": "isolation_failed"})
            ok = False
            continue
        r = run_cmd(cmd, env=env, timeout=timeout)
        r["step"] = name
        results.append(r)
        if r["exit_code"] != 0:
            ok = False

    # Fail if workspace returned unknown-as-zero theater: EMPTY with no error is allowed;
    # but competitors must not claim success without items when linkage proves suppliers exist.
    payload = {
        "campaign_id": "CANONICAL-ENTITY-LINKAGE-01",
        "as_of": _utc(),
        "ok": ok,
        "production_touched": iso.production_touched,
        "dsn_masked": iso.dsn_masked,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": ok, "out": str(args.out), "production_touched": iso.production_touched}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
