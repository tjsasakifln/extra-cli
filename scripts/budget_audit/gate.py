"""Campaign quality gates."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.budget_audit.constants import CAMPAIGN_ID
from scripts.budget_audit.isolation import IsolationError, check_diff_against_base, guard


def _repo_root() -> Path:
    out = subprocess.check_output(  # noqa: S603
        ["git", "rev-parse", "--show-toplevel"],  # noqa: S607
        text=True,
    )
    return Path(out.strip())


def gate_parallel_isolation() -> dict[str, Any]:
    result = guard(skip_diff=False)
    payload = {
        "gate": "parallel-isolation",
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
        "context": result.context,
    }
    if not result.ok:
        return payload
    # extra: confirm no denylist dirty
    return payload


def gate_campaign() -> dict[str, Any]:
    root = _repo_root()
    iso = gate_parallel_isolation()
    if not iso["ok"]:
        return {"gate": "campaign", "ok": False, "isolation": iso}

    steps: list[dict[str, Any]] = [{"name": "isolation", "ok": True}]

    # imports
    try:
        import scripts.budget_audit  # noqa: F401
        import scripts.budget_audit.cli  # noqa: F401
        import scripts.budget_audit.workbook_reader  # noqa: F401

        steps.append({"name": "imports", "ok": True})
    except Exception as exc:  # noqa: BLE001
        steps.append({"name": "imports", "ok": False, "error": str(exc)})
        return {"gate": "campaign", "ok": False, "steps": steps}

    # ruff if available
    ruff = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "scripts/budget_audit", "tests/budget_audit"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    steps.append(
        {
            "name": "ruff",
            "ok": ruff.returncode == 0,
            "stdout": ruff.stdout[-2000:],
            "stderr": ruff.stderr[-2000:],
        }
    )

    # unit tests (no-cov: project pytest.ini may write coverage outside allowlist)
    pytest = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/budget_audit",
            "-q",
            "--tb=line",
            "--no-cov",
            "--junitxml=artifacts/campaigns/ENGINEERING-BUDGET-COMPOSITION-BDI-AUDIT-01/tests.xml",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    steps.append(
        {
            "name": "pytest",
            "ok": pytest.returncode == 0,
            "stdout": pytest.stdout[-3000:],
            "stderr": pytest.stderr[-3000:],
        }
    )

    ok = all(s.get("ok") for s in steps)
    return {"gate": "campaign", "ok": ok, "steps": steps, "campaign_id": CAMPAIGN_ID}


def gate_release_candidate() -> dict[str, Any]:
    camp = gate_campaign()
    if not camp.get("ok"):
        return {"gate": "release-candidate", "ok": False, "campaign": camp}

    root = _repo_root()
    # require evidence files
    evidence = root / "artifacts/campaigns/ENGINEERING-BUDGET-COMPOSITION-BDI-AUDIT-01"
    required = [
        "baseline.json",
        "worktree-lock.json",
        "isolation.json",
        "manifest.json",
        "legacy-economic-risk-assessment.json",
    ]
    missing = [r for r in required if not (evidence / r).is_file()]
    ok = not missing
    return {
        "gate": "release-candidate",
        "ok": ok,
        "missing": missing,
        "campaign": {"ok": camp.get("ok")},
    }


def gate_verify() -> dict[str, Any]:
    iso = gate_parallel_isolation()
    root = _repo_root()
    lock = json.loads(
        (root / "artifacts/campaigns/ENGINEERING-BUDGET-COMPOSITION-BDI-AUDIT-01/worktree-lock.json").read_text()
    )
    bad = check_diff_against_base(lock["base_sha"], root)
    return {
        "gate": "verify",
        "ok": iso["ok"] and not bad,
        "isolation": iso,
        "disallowed_paths": bad,
        "production_touched": lock.get("production_touched"),
        "soak_touched": lock.get("soak_touched"),
        "database_used": lock.get("database_used"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m scripts.budget_audit.gate")
    parser.add_argument(
        "name",
        choices=["parallel-isolation", "campaign", "release-candidate", "verify"],
    )
    args = parser.parse_args(argv)
    try:
        if args.name == "parallel-isolation":
            result = gate_parallel_isolation()
        elif args.name == "campaign":
            result = gate_campaign()
        elif args.name == "release-candidate":
            result = gate_release_candidate()
        else:
            result = gate_verify()
    except IsolationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        print("FAIL")
        return 2

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    status = "PASS" if result.get("ok") else "FAIL"
    print(status)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
