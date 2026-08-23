#!/usr/bin/env python3
"""Run coverage diagnostics and snapshot/export without failure suppression.

The diagnostic intentionally returns non-zero while coverage gaps exist. It
must not be an ``ExecStartPre`` because that would prevent the canonical
snapshot (including its denominator and ``as_of``) from being written.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime


def _default_runner(command: Sequence[str]) -> int:
    # Commands are fixed below; no operator/user input reaches argv.
    return subprocess.run(list(command), check=False).returncode  # noqa: S603


def _run(
    name: str,
    command: list[str],
    runner: Callable[[Sequence[str]], int],
) -> dict[str, object]:
    try:
        code = int(runner(command))
        return {"name": name, "exit_code": code, "status": "pass" if code == 0 else "fail"}
    except Exception as exc:  # noqa: BLE001 - sibling evidence must still run
        return {
            "name": name,
            "exit_code": 2,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }


def run_bundle(
    *, runner: Callable[[Sequence[str]], int] = _default_runner
) -> dict[str, object]:
    python = sys.executable
    checks = [
        _run(
            "coverage_diagnostic",
            [python, "-m", "scripts.crawl.monitor", "--report-coverage"],
            runner,
        ),
        _run(
            "coverage_snapshot_export",
            [python, "-m", "scripts.local_datalake", "coverage", "--snapshot", "--export"],
            runner,
        ),
    ]
    exit_code = max(int(item["exit_code"]) for item in checks)
    return {
        "event": "coverage_bundle",
        "as_of": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "HEALTHY" if exit_code == 0 else "UNHEALTHY",
        "exit_code": exit_code,
        "checks": checks,
    }


def main() -> int:
    report = run_bundle()
    print(json.dumps(report, ensure_ascii=False, default=str))
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
