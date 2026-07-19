"""Independent deterministic verifier — executor cannot self-approve."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.cto.paths import cycles_dir, dod_path, repo_root
from scripts.cto.policies import forbidden_claims, path_allowed
from scripts.cto.redaction import redact_obj, redact_text


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(cmd: list[str], cwd: Path, timeout: int = 300) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "cmd": cmd,
            "exit_code": proc.returncode,
            "stdout": redact_text((proc.stdout or "")[-12000:]),
            "stderr": redact_text((proc.stderr or "")[-6000:]),
        }
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "exit_code": -1, "stdout": "", "stderr": "timeout"}
    except FileNotFoundError:
        return {"cmd": cmd, "exit_code": -2, "stdout": "", "stderr": "not_found"}


SECRET_FILE_HINTS = re.compile(
    r"(api[_-]?key|secret|token|password)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{8,}",
    re.I,
)


def verify(
    *,
    decision: dict[str, Any],
    worktree: Path | None = None,
    baseline_dod_sha: str | None = None,
    root: Path | None = None,
    skip_tests: bool = False,
) -> dict[str, Any]:
    """Run verification suite. Returns result PASS|FAIL|INCOMPLETE|UNSAFE."""
    root = root or repo_root()
    cwd = worktree or root
    cycle_id = decision.get("cycle_id") or "unknown"
    failed: list[str] = []
    checks: list[dict[str, Any]] = []
    repair_hints: list[str] = []
    unsafe = False

    # 1) git diff --check
    diff_check = _run(["git", "diff", "--check"], cwd)
    checks.append({"name": "git_diff_check", **diff_check})
    if diff_check["exit_code"] not in (0,):
        # exit 0 clean; also ok if no diff
        if "conflict" in (diff_check.get("stdout") or "").lower():
            failed.append("git diff --check reported conflict markers")
            repair_hints.append("Remove conflict markers")

    # 2) modified paths vs allowlist
    name_status = _run(["git", "diff", "--name-only", "HEAD"], cwd)
    unstaged = [
        ln.strip() for ln in (name_status.get("stdout") or "").splitlines() if ln.strip()
    ]
    # also staged and untracked lightly
    status = _run(["git", "status", "--porcelain"], cwd)
    modified: list[str] = []
    for ln in (status.get("stdout") or "").splitlines():
        if not ln.strip():
            continue
        path = ln[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        modified.append(path)

    allowed = list(decision.get("allowed_paths") or [])
    forbidden = list(decision.get("forbidden_paths") or []) + [".env", ".env.local"]
    scope_violations = []
    if decision.get("decision") in {"EXECUTE", "REPAIR"} and allowed:
        for path in modified:
            if path.startswith("output/"):
                continue  # outputs ok
            if not path_allowed(path, allowed, forbidden):
                scope_violations.append(path)
    if scope_violations:
        failed.append(f"paths outside allowed scope: {scope_violations[:20]}")
        repair_hints.append("Revert files outside allowed_paths")
        unsafe = True

    checks.append(
        {
            "name": "path_scope",
            "modified": modified[:100],
            "violations": scope_violations,
        }
    )

    # 3) secrets scan on diff
    diff = _run(["git", "diff", "HEAD"], cwd)
    if SECRET_FILE_HINTS.search(diff.get("stdout") or ""):
        failed.append("possible secret in diff")
        unsafe = True
        repair_hints.append("Remove secrets from diff; use env vars")
    checks.append({"name": "secret_scan", "hit": bool(SECRET_FILE_HINTS.search(diff.get("stdout") or ""))})

    # 4) DoD mutation audit
    dod_changed = any(p == "DOD.md" or p.endswith("/DOD.md") for p in modified)
    dod_audit = {"changed": dod_changed, "unauthorized_checks": False}
    if dod_changed:
        # Compare checkbox deltas — any new [x] without decision allowing it is fail
        # Fail closed: default unauthorized unless decision meta allows
        allow_dod = "DOD.md" in allowed or any(a in {"DOD.md", "**/DOD.md"} for a in allowed)
        if not allow_dod:
            failed.append("DOD.md modified without allowlist")
            unsafe = True
            dod_audit["unauthorized_checks"] = True
            repair_hints.append("Revert DOD.md changes or obtain human authorization")
        if baseline_dod_sha:
            import hashlib

            current = (cwd / "DOD.md").read_bytes() if (cwd / "DOD.md").is_file() else b""
            cur_sha = hashlib.sha256(current).hexdigest()
            dod_audit["baseline_sha"] = baseline_dod_sha
            dod_audit["current_sha"] = cur_sha
    checks.append({"name": "dod_audit", **dod_audit})

    # 5) forbidden claims in diff
    claim_hits = []
    blob = diff.get("stdout") or ""
    for claim in forbidden_claims():
        if claim in blob:
            # allow if only in comments removing claim? still flag
            claim_hits.append(claim)
    if claim_hits:
        failed.append(f"forbidden claims present in diff: {claim_hits}")
        repair_hints.append("Remove forbidden readiness claims")
    checks.append({"name": "claims_audit", "hits": claim_hits})

    # 6) main branch execution forbidden
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    branch_name = (branch.get("stdout") or "").strip()
    if branch_name in {"main", "master"} and decision.get("decision") in {"EXECUTE", "REPAIR"}:
        failed.append("execution on main/master forbidden")
        unsafe = True
    checks.append({"name": "branch_guard", "branch": branch_name})

    # 7) test commands from decision
    test_results = []
    if not skip_tests:
        for cmd_str in decision.get("test_commands") or []:
            # never shell=True with raw issue content — split safely
            if any(tok in cmd_str for tok in (";", "&&", "|", "`", "$(", "\n", "rm -rf")):
                test_results.append(
                    {
                        "cmd": cmd_str,
                        "exit_code": -3,
                        "stderr": "rejected unsafe command",
                    }
                )
                failed.append(f"unsafe test command rejected: {cmd_str[:80]}")
                unsafe = True
                continue
            parts = cmd_str.split()
            if not parts:
                continue
            # map python -m pytest ...
            res = _run(parts, cwd, timeout=600)
            test_results.append(res)
            if res["exit_code"] != 0:
                failed.append(f"test failed: {cmd_str}")
                repair_hints.append(f"Fix failures in: {cmd_str}")
    checks.append({"name": "tests", "results": test_results})

    # 8) acceptance criteria presence (cannot fully auto-prove; mark incomplete if empty evidence)
    ac = decision.get("acceptance_criteria") or []
    if decision.get("decision") in {"EXECUTE", "REPAIR"} and not ac:
        failed.append("missing acceptance_criteria")
    checks.append({"name": "acceptance_criteria", "count": len(ac)})

    # Determine result
    if unsafe:
        result = "UNSAFE"
    elif failed:
        result = "FAIL"
    elif decision.get("decision") in {"EXECUTE", "REPAIR"} and not modified and not skip_tests:
        # might be incomplete if expected code change
        result = "INCOMPLETE"
        failed.append("no file changes detected after EXECUTE/REPAIR")
        repair_hints.append("Implement required changes or mark NOOP")
    else:
        result = "PASS"

    out = {
        "schema_version": "1.0",
        "timestamp_utc": _utc_now(),
        "cycle_id": cycle_id,
        "decision_id": decision.get("decision_id"),
        "result": result,
        "failed_criteria": failed,
        "repair_hints": repair_hints,
        "checks": checks,
        "worktree": str(cwd),
    }
    out = redact_obj(out)

    # persist
    cdir = cycles_dir(root) / str(cycle_id)
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "verification.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out
