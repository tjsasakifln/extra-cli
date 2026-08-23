#!/usr/bin/env python3
"""Run independent infrastructure and PNCP freshness health checks.

Both checks always execute. A failing first check cannot suppress freshness
evidence, and a partial/failed freshness result can never become HEALTHY.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path


def _run_check(name: str, fn: Callable[[], int]) -> dict[str, object]:
    try:
        code = int(fn())
        return {"name": name, "exit_code": code, "status": "pass" if code == 0 else "fail"}
    except Exception as exc:  # noqa: BLE001 - health must record sibling failures
        return {"name": name, "exit_code": 2, "status": "error", "error": f"{type(exc).__name__}: {exc}"}


def run_bundle(*, freshness_output: Path) -> dict[str, object]:
    from scripts import health_check
    from scripts.ops import pncp_contract_freshness

    checks = [
        _run_check("infrastructure", health_check.main),
        _run_check(
            "pncp_contract_freshness",
            lambda: pncp_contract_freshness.main(
                ["--live", "--health", "--output", str(freshness_output)]
            ),
        ),
    ]
    exit_code = max(int(item["exit_code"]) for item in checks)
    return {
        "event": "health_bundle",
        "as_of": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "HEALTHY" if exit_code == 0 else "UNHEALTHY",
        "exit_code": exit_code,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--freshness-output",
        type=Path,
        default=Path("output/ops/pncp-contract-freshness.json"),
    )
    args = parser.parse_args(argv)
    report = run_bundle(freshness_output=args.freshness_output)
    print(json.dumps(report, ensure_ascii=False, default=str))
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
