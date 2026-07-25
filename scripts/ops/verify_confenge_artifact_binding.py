#!/usr/bin/env python3
"""Fail-closed SHA binding for CONFENGE commercial RC artifacts.

Any of artifact_git_sha / run_git_sha / gate_git_sha / review_git_sha that
differs from PR HEAD produces FAIL (objective §4).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"

SHA_KEYS = ("artifact_git_sha", "run_git_sha", "gate_git_sha", "review_git_sha", "git_sha")


def git_head(root: Path | None = None) -> str:
    r = root or _ROOT
    return subprocess.check_output(  # noqa: S603,S607
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=str(r),
        text=True,
        stderr=subprocess.DEVNULL,
        timeout=5,
    ).strip()


def check_artifact_binding(
    *,
    head_sha: str,
    result_path: Path | None = None,
    extra_paths: list[Path] | None = None,
) -> dict[str, Any]:
    """Return binding report; ok is True only when all present SHAs match HEAD."""
    paths = [result_path or (_ART / "result.json")]
    if extra_paths:
        paths.extend(extra_paths)
    issues: list[str] = []
    details: dict[str, Any] = {"head_sha": head_sha, "files": {}}

    for path in paths:
        p = Path(path)
        if not p.is_file():
            issues.append(f"missing:{p}")
            details["files"][str(p)] = {"present": False}
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"invalid_json:{p}:{exc}")
            details["files"][str(p)] = {"present": True, "error": str(exc)}
            continue
        file_issues: list[str] = []
        found: dict[str, str | None] = {}
        for key in SHA_KEYS:
            val = data.get(key)
            if val is None:
                continue
            sval = str(val)
            found[key] = sval
            if sval != head_sha and sval != "unknown":
                file_issues.append(f"{key}={sval}!={head_sha}")
        # nested sha_binding.match_run_to_head must not paper over mismatch
        bind = data.get("sha_binding") or {}
        if bind.get("match_run_to_head") is False:
            file_issues.append("sha_binding.match_run_to_head=false")
        if file_issues:
            issues.extend(f"{p.name}:{x}" for x in file_issues)
        details["files"][str(p)] = {"present": True, "shas": found, "issues": file_issues}

    ok = len(issues) == 0
    return {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "head_sha": head_sha,
        "issues": issues,
        "details": details,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="CONFENGE commercial artifact SHA binding gate")
    p.add_argument("--result", default=str(_ART / "result.json"))
    p.add_argument("--queue-summary", default=str(_ART / "queue-summary.json"))
    p.add_argument("--head", default=None, help="Override HEAD SHA (tests)")
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)
    head = args.head or git_head()
    report = check_artifact_binding(
        head_sha=head,
        result_path=Path(args.result),
        extra_paths=[Path(args.queue_summary)] if Path(args.queue_summary).is_file() else None,
    )
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
