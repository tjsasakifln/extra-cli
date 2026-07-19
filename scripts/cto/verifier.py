"""Independent deterministic verifier — executor cannot self-approve."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.cto.paths import cycles_dir, repo_root
from scripts.cto.policies import forbidden_claims, path_allowed
from scripts.cto.redaction import redact_obj, redact_text

# Safe caps for captured diffs (bytes / chars)
DIFF_CHAR_CAP = 200_000
UNTRACKED_CONTENT_CAP = 40_000
FILE_HASH_CAP_BYTES = 2_000_000


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    r"(api[_-]?key|secret|token|password|ghp_|github_pat_|sk-[A-Za-z0-9]{10,})\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{8,}",
    re.I,
)

CLAIM_HINTS = re.compile(
    r"\b(LOCAL_READY|PRE_VPS_FINAL_READY|VPS_OPERATIONAL|PROJECT_DONE|95%\s*coverage)\b",
    re.I,
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _sha256_file(path: Path) -> str | None:
    try:
        if not path.is_file() or path.is_symlink():
            return None
        size = path.stat().st_size
        if size > FILE_HASH_CAP_BYTES:
            h = hashlib.sha256()
            with path.open("rb") as fh:
                remaining = FILE_HASH_CAP_BYTES
                while remaining > 0:
                    chunk = fh.read(min(65536, remaining))
                    if not chunk:
                        break
                    h.update(chunk)
                    remaining -= len(chunk)
            return h.hexdigest() + f":partial:{size}"
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _classify_status_line(line: str) -> tuple[str, str] | None:
    if not line.strip():
        return None
    # porcelain v1: XY path
    code = line[:2]
    path = line[3:].strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    if code == "??":
        return "untracked", path
    if code[0] != " " and code[0] != "?":
        return "staged", path
    return "unstaged", path


def _branch_committed_changes(cwd: Path) -> dict[str, Any]:
    """Files/diff committed on this branch since merge-base with main.

    Live Grok often commits inside the worktree before verify runs. Working
    tree porcelain alone would then look empty and false-fail EXECUTE work.
    """
    committed: list[str] = []
    raw_diff = ""
    base_used: str | None = None
    for ref in ("main", "master", "origin/main", "origin/master"):
        mb = _run(["git", "merge-base", "HEAD", ref], cwd)
        if mb.get("exit_code") != 0:
            continue
        base = (mb.get("stdout") or "").strip()
        if not base:
            continue
        names = _run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd)
        if names.get("exit_code") == 0:
            committed = [
                ln.strip() for ln in (names.get("stdout") or "").splitlines() if ln.strip()
            ]
        diff = _run(["git", "diff", f"{base}...HEAD"], cwd)
        if diff.get("exit_code") == 0:
            raw_diff = diff.get("stdout") or ""
        base_used = base
        break
    return {
        "committed": committed,
        "diff_text": raw_diff,
        "merge_base": base_used,
    }


def capture_working_tree(cwd: Path) -> dict[str, Any]:
    """Capture staged/unstaged/untracked inventory, full diff (capped) + hashes.

    Includes committed branch delta vs main so post-commit Grok work is visible.
    """
    status = _run(["git", "status", "--porcelain"], cwd)
    staged: list[str] = []
    unstaged: list[str] = []
    untracked: list[str] = []
    for ln in (status.get("stdout") or "").splitlines():
        classified = _classify_status_line(ln)
        if not classified:
            continue
        kind, path = classified
        if kind == "staged":
            staged.append(path)
        elif kind == "unstaged":
            unstaged.append(path)
        else:
            untracked.append(path)

    # Full diff vs HEAD (includes staged via HEAD comparison for modified tracked)
    diff_head = _run(["git", "diff", "HEAD"], cwd)
    # Also staged-only and unstaged-only for inventory completeness
    diff_staged = _run(["git", "diff", "--cached"], cwd)
    diff_unstaged = _run(["git", "diff"], cwd)
    branch_delta = _branch_committed_changes(cwd)
    raw_diff = (
        (diff_head.get("stdout") or "")
        + "\n"
        + (diff_staged.get("stdout") or "")
        + "\n"
        + (branch_delta.get("diff_text") or "")
    )
    truncated = False
    if len(raw_diff) > DIFF_CHAR_CAP:
        raw_diff = raw_diff[:DIFF_CHAR_CAP]
        truncated = True
    diff_hash = _sha256_text(raw_diff)

    untracked_details: list[dict[str, Any]] = []
    for rel in untracked[:80]:
        p = cwd / rel
        entry: dict[str, Any] = {
            "path": rel,
            "is_symlink": p.is_symlink() if p.exists() or p.is_symlink() else False,
            "exists": p.exists(),
            "sha256": None,
            "secret_hit": False,
            "claim_hit": False,
            "content_sample": None,
        }
        if p.is_symlink():
            try:
                entry["symlink_target"] = os.readlink(p)
            except OSError:
                entry["symlink_target"] = None
        elif p.is_file():
            entry["sha256"] = _sha256_file(p)
            try:
                sample = p.read_text(encoding="utf-8", errors="replace")[:UNTRACKED_CONTENT_CAP]
            except OSError:
                sample = ""
            entry["content_sample"] = redact_text(sample[:500])
            entry["secret_hit"] = bool(SECRET_FILE_HINTS.search(sample))
            entry["claim_hit"] = bool(CLAIM_HINTS.search(sample))
        untracked_details.append(entry)

    modified_all = sorted(
        set(staged + unstaged + untracked + list(branch_delta.get("committed") or []))
    )

    return {
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "committed_since_main": list(branch_delta.get("committed") or []),
        "merge_base": branch_delta.get("merge_base"),
        "modified_all": modified_all,
        "diff": {
            "text": redact_text(raw_diff),
            "sha256": diff_hash,
            "truncated": truncated,
            "char_len": len(raw_diff),
            "char_cap": DIFF_CHAR_CAP,
            "unstaged_exit": diff_unstaged.get("exit_code"),
            "staged_exit": diff_staged.get("exit_code"),
            "head_exit": diff_head.get("exit_code"),
            "includes_branch_commits": bool(branch_delta.get("committed")),
        },
        "untracked_details": untracked_details,
        "status_exit": status.get("exit_code"),
    }


def _criterion(
    name: str,
    status: str,
    *,
    evidence: str,
    detail: str = "",
) -> dict[str, Any]:
    if status not in {"PASS", "FAIL", "UNPROVEN"}:
        raise ValueError(f"invalid criterion status: {status}")
    return {
        "criterion": name,
        "status": status,
        "evidence": evidence,
        "detail": detail,
    }


def _resolve_under_worktree(cwd: Path, rel: str) -> tuple[Path | None, str | None]:
    """Resolve path under worktree; reject escapes and symlinks outside."""
    try:
        base = cwd.resolve()
        candidate = (cwd / rel).resolve()
        candidate.relative_to(base)
    except (OSError, ValueError):
        return None, "path escapes worktree or is invalid"
    if candidate.is_symlink():
        try:
            target = Path(os.readlink(candidate))
            if not target.is_absolute():
                target = (candidate.parent / target).resolve()
            else:
                target = target.resolve()
            target.relative_to(base)
        except (OSError, ValueError):
            return None, "symlink target escapes worktree"
    return candidate, None


def verify(
    *,
    decision: dict[str, Any],
    worktree: Path | None = None,
    baseline_dod_sha: str | None = None,
    root: Path | None = None,
    skip_tests: bool = False,
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run verification suite with criterion-by-criterion matrix.

    Returns result PASS|FAIL|INCOMPLETE|UNSAFE.
    Any UNPROVEN criterion or executor failure blocks PASS.
    """
    root = root or repo_root()
    cwd = worktree or root
    cycle_id = decision.get("cycle_id") or "unknown"
    failed: list[str] = []
    repair_hints: list[str] = []
    unsafe = False
    matrix: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    # --- 0) worktree boundary / symlink escape ---
    try:
        cwd_resolved = cwd.resolve()
        if not cwd_resolved.is_dir():
            matrix.append(
                _criterion(
                    "worktree_exists",
                    "FAIL",
                    evidence=str(cwd),
                    detail="worktree path is not a directory",
                )
            )
            failed.append("worktree missing")
            unsafe = True
        else:
            matrix.append(
                _criterion("worktree_exists", "PASS", evidence=str(cwd_resolved))
            )
    except OSError as exc:
        matrix.append(
            _criterion("worktree_exists", "FAIL", evidence=str(cwd), detail=str(exc))
        )
        failed.append("worktree resolve failed")
        unsafe = True

    # --- 1) git diff --check ---
    diff_check = _run(["git", "diff", "--check"], cwd)
    checks.append({"name": "git_diff_check", **diff_check})
    if "conflict" in (diff_check.get("stdout") or "").lower():
        matrix.append(
            _criterion(
                "conflict_markers",
                "FAIL",
                evidence="git diff --check",
                detail="conflict markers present",
            )
        )
        failed.append("git diff --check reported conflict markers")
        repair_hints.append("Remove conflict markers")
    else:
        matrix.append(
            _criterion(
                "conflict_markers",
                "PASS",
                evidence="git diff --check",
                detail=f"exit={diff_check.get('exit_code')}",
            )
        )

    # --- 2) full working tree capture ---
    tree = capture_working_tree(cwd)
    modified = list(tree["modified_all"])
    checks.append(
        {
            "name": "working_tree",
            "staged": tree["staged"][:100],
            "unstaged": tree["unstaged"][:100],
            "untracked": tree["untracked"][:100],
            "diff_sha256": tree["diff"]["sha256"],
            "diff_truncated": tree["diff"]["truncated"],
        }
    )
    matrix.append(
        _criterion(
            "diff_capture",
            "PASS",
            evidence=f"diff.sha256={tree['diff']['sha256']}",
            detail=(
                f"staged={len(tree['staged'])} unstaged={len(tree['unstaged'])} "
                f"untracked={len(tree['untracked'])} truncated={tree['diff']['truncated']}"
            ),
        )
    )

    # symlink / escape among modified paths
    escape_hits: list[str] = []
    for path in modified:
        resolved, err = _resolve_under_worktree(cwd, path)
        if err:
            escape_hits.append(f"{path}: {err}")
    if escape_hits:
        unsafe = True
        failed.append(f"worktree escape/symlink: {escape_hits[:10]}")
        matrix.append(
            _criterion(
                "worktree_escape_guard",
                "FAIL",
                evidence="path resolve",
                detail="; ".join(escape_hits[:10]),
            )
        )
    else:
        matrix.append(
            _criterion(
                "worktree_escape_guard",
                "PASS",
                evidence="path resolve under worktree",
            )
        )

    # --- 3) path allowlist ---
    allowed = list(decision.get("allowed_paths") or [])
    forbidden = list(decision.get("forbidden_paths") or []) + [".env", ".env.local"]
    scope_violations: list[str] = []
    if decision.get("decision") in {"EXECUTE", "REPAIR"} and allowed:
        for path in modified:
            if path.startswith("output/"):
                continue
            if not path_allowed(path, allowed, forbidden):
                scope_violations.append(path)
    if scope_violations:
        failed.append(f"paths outside allowed scope: {scope_violations[:20]}")
        repair_hints.append("Revert files outside allowed_paths")
        unsafe = True
        matrix.append(
            _criterion(
                "path_scope",
                "FAIL",
                evidence="git status + allowed_paths",
                detail=str(scope_violations[:20]),
            )
        )
    else:
        matrix.append(
            _criterion(
                "path_scope",
                "PASS",
                evidence="git status + allowed_paths",
                detail=f"modified={len(modified)}",
            )
        )
    checks.append(
        {
            "name": "path_scope",
            "modified": modified[:100],
            "violations": scope_violations,
        }
    )

    # --- 4) secrets in diff + untracked content ---
    blob = tree["diff"]["text"] or ""
    secret_in_diff = bool(SECRET_FILE_HINTS.search(blob))
    secret_untracked = [
        u["path"] for u in tree["untracked_details"] if u.get("secret_hit")
    ]
    if secret_in_diff or secret_untracked:
        failed.append("possible secret in diff/untracked")
        unsafe = True
        repair_hints.append("Remove secrets from diff; use env vars")
        matrix.append(
            _criterion(
                "secret_scan",
                "FAIL",
                evidence="regex SECRET_FILE_HINTS on diff+untracked",
                detail=f"diff={secret_in_diff} untracked={secret_untracked[:10]}",
            )
        )
    else:
        matrix.append(
            _criterion(
                "secret_scan",
                "PASS",
                evidence="regex SECRET_FILE_HINTS on diff+untracked",
            )
        )
    checks.append(
        {
            "name": "secret_scan",
            "hit_diff": secret_in_diff,
            "hit_untracked": secret_untracked,
        }
    )

    # --- 5) DoD mutation audit ---
    dod_changed = any(p == "DOD.md" or p.endswith("/DOD.md") for p in modified)
    dod_audit: dict[str, Any] = {"changed": dod_changed, "unauthorized_checks": False}
    if dod_changed:
        allow_dod = "DOD.md" in allowed or any(a in {"DOD.md", "**/DOD.md"} for a in allowed)
        if not allow_dod:
            failed.append("DOD.md modified without allowlist")
            unsafe = True
            dod_audit["unauthorized_checks"] = True
            repair_hints.append("Revert DOD.md changes or obtain human authorization")
            matrix.append(
                _criterion(
                    "dod_mutation",
                    "FAIL",
                    evidence="DOD.md in modified paths",
                    detail="not in allowed_paths",
                )
            )
        else:
            matrix.append(
                _criterion(
                    "dod_mutation",
                    "PASS",
                    evidence="DOD.md allowed by decision",
                )
            )
        if baseline_dod_sha:
            current = (cwd / "DOD.md").read_bytes() if (cwd / "DOD.md").is_file() else b""
            cur_sha = hashlib.sha256(current).hexdigest()
            dod_audit["baseline_sha"] = baseline_dod_sha
            dod_audit["current_sha"] = cur_sha
    else:
        matrix.append(
            _criterion("dod_mutation", "PASS", evidence="DOD.md not modified")
        )
    checks.append({"name": "dod_audit", **dod_audit})

    # --- 6) forbidden claims ---
    claim_hits: list[str] = []
    for claim in forbidden_claims():
        if claim in blob:
            claim_hits.append(claim)
    claim_untracked = [u["path"] for u in tree["untracked_details"] if u.get("claim_hit")]
    if claim_hits or claim_untracked:
        failed.append(f"forbidden claims present: {claim_hits or claim_untracked}")
        repair_hints.append("Remove forbidden readiness claims")
        matrix.append(
            _criterion(
                "claims_audit",
                "FAIL",
                evidence="forbidden_claims scan",
                detail=str(claim_hits or claim_untracked),
            )
        )
    else:
        matrix.append(
            _criterion("claims_audit", "PASS", evidence="forbidden_claims scan")
        )
    checks.append({"name": "claims_audit", "hits": claim_hits, "untracked": claim_untracked})

    # --- 7) branch guard ---
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    branch_name = (branch.get("stdout") or "").strip()
    if branch_name in {"main", "master"} and decision.get("decision") in {"EXECUTE", "REPAIR"}:
        failed.append("execution on main/master forbidden")
        unsafe = True
        matrix.append(
            _criterion(
                "branch_guard",
                "FAIL",
                evidence=f"git rev-parse → {branch_name}",
            )
        )
    else:
        matrix.append(
            _criterion(
                "branch_guard",
                "PASS",
                evidence=f"branch={branch_name}",
            )
        )
    checks.append({"name": "branch_guard", "branch": branch_name})

    # --- 8) executor status (if provided) ---
    if execution is not None:
        exec_status = str(execution.get("status") or "")
        exit_code = execution.get("exit_code")
        bad_statuses = {
            "failed",
            "unsafe",
            "escalated",
            "error",
        }
        ok_statuses = {
            "completed",
            "mock_completed",
            "dry_run",
            "skipped",
        }
        if exec_status in bad_statuses or (
            exit_code is not None and exit_code not in (0, None) and exec_status not in ok_statuses
        ):
            failed.append(f"executor failed: status={exec_status} exit={exit_code}")
            matrix.append(
                _criterion(
                    "executor_status",
                    "FAIL",
                    evidence=f"execution.status={exec_status} exit_code={exit_code}",
                )
            )
        elif exec_status in ok_statuses:
            matrix.append(
                _criterion(
                    "executor_status",
                    "PASS",
                    evidence=f"execution.status={exec_status}",
                )
            )
        elif exec_status in {"", "planned"}:
            matrix.append(
                _criterion(
                    "executor_status",
                    "UNPROVEN",
                    evidence="execution payload incomplete",
                    detail=f"status={exec_status!r}",
                )
            )
        else:
            matrix.append(
                _criterion(
                    "executor_status",
                    "PASS",
                    evidence=f"execution.status={exec_status}",
                )
            )
    else:
        # Without execution context we cannot claim executor success for EXECUTE
        if decision.get("decision") in {"EXECUTE", "REPAIR"} and not skip_tests:
            matrix.append(
                _criterion(
                    "executor_status",
                    "UNPROVEN",
                    evidence="execution not provided to verify()",
                )
            )
        else:
            matrix.append(
                _criterion(
                    "executor_status",
                    "PASS",
                    evidence="execution not required (skip/non-execute)",
                )
            )

    # --- 9) tests ---
    test_results: list[dict[str, Any]] = []
    if not skip_tests:
        cmds = list(decision.get("test_commands") or [])
        if not cmds and decision.get("decision") in {"EXECUTE", "REPAIR"}:
            matrix.append(
                _criterion(
                    "tests",
                    "UNPROVEN",
                    evidence="no test_commands on EXECUTE/REPAIR",
                )
            )
        for cmd_str in cmds:
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
            res = _run(parts, cwd, timeout=600)
            test_results.append(res)
            if res["exit_code"] != 0:
                failed.append(f"test failed: {cmd_str}")
                repair_hints.append(f"Fix failures in: {cmd_str}")
        if cmds:
            if any(r.get("exit_code") not in (0,) for r in test_results):
                matrix.append(
                    _criterion(
                        "tests",
                        "FAIL",
                        evidence="test_commands execution",
                        detail=str(
                            [
                                (r.get("cmd"), r.get("exit_code"))
                                for r in test_results
                            ][:10]
                        ),
                    )
                )
            else:
                matrix.append(
                    _criterion(
                        "tests",
                        "PASS",
                        evidence="test_commands execution",
                        detail=f"ran={len(test_results)}",
                    )
                )
    else:
        matrix.append(
            _criterion("tests", "PASS", evidence="skip_tests=True")
        )
    checks.append({"name": "tests", "results": test_results})

    # --- 10) acceptance criteria matrix ---
    ac = list(decision.get("acceptance_criteria") or [])
    if decision.get("decision") in {"EXECUTE", "REPAIR"} and not ac:
        failed.append("missing acceptance_criteria")
        matrix.append(
            _criterion(
                "acceptance_criteria_present",
                "FAIL",
                evidence="decision.acceptance_criteria",
            )
        )
    else:
        matrix.append(
            _criterion(
                "acceptance_criteria_present",
                "PASS",
                evidence=f"count={len(ac)}",
            )
        )
    for i, criterion in enumerate(ac):
        # Heuristic proof: tests pass + files changed, else UNPROVEN
        evidence_bits: list[str] = []
        status = "UNPROVEN"
        if skip_tests:
            # Explicit skip: deferred proof — treated as PASS only for dry-run paths
            # (caller sets skip_tests). Real live runs must not pass skip_tests.
            status = "PASS"
            evidence_bits.append("skip_tests=True (acceptance proof deferred by operator)")
        elif test_results and all(r.get("exit_code") == 0 for r in test_results) and modified:
            status = "PASS"
            evidence_bits.append("tests exit 0 + modified files")
        elif test_results and any(r.get("exit_code") != 0 for r in test_results):
            status = "FAIL"
            evidence_bits.append("tests failed")
        else:
            evidence_bits.append("no concrete proof binding this AC to test/file")
        # Soft: if criterion mentions a path that exists in modified → partial proof
        for path in modified:
            if path in str(criterion) or Path(path).name in str(criterion):
                if status == "UNPROVEN":
                    status = "PASS"
                    evidence_bits.append(f"path match: {path}")
                break
        matrix.append(
            _criterion(
                f"ac[{i}]",
                status,
                evidence="; ".join(evidence_bits) or "none",
                detail=str(criterion)[:240],
            )
        )
    checks.append({"name": "acceptance_criteria", "count": len(ac)})

    # --- 11) required evidence existence ---
    required_ev = list(decision.get("required_evidence") or [])
    missing_ev: list[str] = []
    for ev in required_ev:
        # evidence may be a relative path under worktree/root/cycle dir
        candidates = [
            cwd / str(ev),
            root / str(ev),
            cycles_dir(root) / str(cycle_id) / str(ev),
            cwd / "output" / "cto" / "cycles" / str(cycle_id) / str(ev),
        ]
        # also allow bare names found in cycle dir
        cdir = cycles_dir(root) / str(cycle_id)
        if cdir.is_dir():
            candidates.append(cdir / Path(str(ev)).name)
        found = False
        for cand in candidates:
            if cand.is_file():
                found = True
                break
        # name-like evidence that is not a path (e.g. "pytest log") → UNPROVEN unless tests ran
        if not found:
            if "pytest" in str(ev).lower() and test_results and all(
                r.get("exit_code") == 0 for r in test_results
            ):
                found = True
            elif "decision.json" in str(ev) and (cycles_dir(root) / str(cycle_id) / "decision.json").is_file():
                found = True
            elif "observation.json" in str(ev):
                from scripts.cto.paths import observation_path

                if observation_path(root).is_file():
                    found = True
            elif skip_tests:
                # still unproven — do not invent
                pass
        if not found:
            missing_ev.append(str(ev))
    if required_ev and missing_ev:
        if skip_tests:
            matrix.append(
                _criterion(
                    "required_evidence",
                    "PASS",
                    evidence="skip_tests=True defers evidence existence check",
                    detail=f"missing_deferred={missing_ev[:10]}",
                )
            )
        else:
            matrix.append(
                _criterion(
                    "required_evidence",
                    "UNPROVEN",
                    evidence="filesystem lookup",
                    detail=f"missing={missing_ev[:10]}",
                )
            )
    elif required_ev:
        matrix.append(
            _criterion(
                "required_evidence",
                "PASS",
                evidence="filesystem lookup",
                detail=f"count={len(required_ev)}",
            )
        )
    else:
        # Empty required_evidence is OK for NOOP; for EXECUTE live runs, UNPROVEN
        if decision.get("decision") in {"EXECUTE", "REPAIR"} and not skip_tests:
            matrix.append(
                _criterion(
                    "required_evidence",
                    "UNPROVEN",
                    evidence="decision.required_evidence empty",
                )
            )
        else:
            matrix.append(
                _criterion(
                    "required_evidence",
                    "PASS",
                    evidence="decision.required_evidence",
                    detail="empty list or skip_tests",
                )
            )
    checks.append({"name": "required_evidence", "required": required_ev, "missing": missing_ev})

    # --- Aggregate matrix ---
    unproven = [m for m in matrix if m["status"] == "UNPROVEN"]
    fail_matrix = [m for m in matrix if m["status"] == "FAIL"]
    for m in unproven:
        if m["criterion"] not in {x.split(":")[0] for x in failed}:
            failed.append(f"UNPROVEN: {m['criterion']} — {m.get('detail') or m.get('evidence')}")

    # Determine result
    if unsafe or any(
        m["status"] == "FAIL"
        and m["criterion"]
        in {
            "secret_scan",
            "path_scope",
            "branch_guard",
            "dod_mutation",
            "worktree_escape_guard",
            "worktree_exists",
        }
        for m in matrix
    ):
        result = "UNSAFE" if unsafe else "FAIL"
        if unsafe:
            result = "UNSAFE"
        elif fail_matrix:
            result = "FAIL"
    elif fail_matrix:
        result = "FAIL"
    elif unproven:
        # any UNPROVEN blocks PASS
        result = "FAIL"
        repair_hints.append("Provide concrete evidence for UNPROVEN criteria")
    elif decision.get("decision") in {"EXECUTE", "REPAIR"} and not modified and not skip_tests:
        result = "INCOMPLETE"
        failed.append("no file changes detected after EXECUTE/REPAIR")
        repair_hints.append("Implement required changes or mark NOOP")
        matrix.append(
            _criterion(
                "file_changes",
                "FAIL",
                evidence="git status empty after EXECUTE",
            )
        )
    else:
        result = "PASS"
        # skip_tests dry-run/mock: no modified files is incomplete only for live runs
        if modified or decision.get("decision") not in {"EXECUTE", "REPAIR"}:
            fc_status = "PASS"
            fc_ev = f"modified_count={len(modified)}"
        elif skip_tests and execution and str(execution.get("status") or "") in {
            "mock_completed",
            "dry_run",
        }:
            fc_status = "PASS"
            fc_ev = f"skip_tests + execution.status={execution.get('status')}"
        elif skip_tests:
            fc_status = "PASS"
            fc_ev = "skip_tests=True (file change proof deferred)"
        else:
            fc_status = "UNPROVEN"
            fc_ev = f"modified_count={len(modified)}"
        matrix.append(
            _criterion(
                "file_changes",
                fc_status,
                evidence=fc_ev,
            )
        )
        if any(m["status"] == "UNPROVEN" for m in matrix):
            result = "FAIL"
            for m in matrix:
                if m["status"] == "UNPROVEN":
                    failed.append(f"UNPROVEN: {m['criterion']}")

    # Final hard rules
    if any(m["status"] == "UNPROVEN" for m in matrix):
        if result == "PASS":
            result = "FAIL"
        for m in matrix:
            if m["status"] == "UNPROVEN" and f"UNPROVEN: {m['criterion']}" not in failed:
                failed.append(f"UNPROVEN: {m['criterion']} — {m.get('evidence')}")
    if execution is not None:
        if str(execution.get("status") or "") in {"failed", "unsafe", "escalated"}:
            if result == "PASS":
                result = "FAIL"
            if not any("executor failed" in f for f in failed):
                failed.append(f"executor failed: {execution.get('status')}")

    out = {
        "schema_version": "1.1",
        "timestamp_utc": _utc_now(),
        "cycle_id": cycle_id,
        "decision_id": decision.get("decision_id"),
        "result": result,
        "failed_criteria": failed,
        "repair_hints": repair_hints,
        "checks": checks,
        "criterion_matrix": matrix,
        "diff": {
            "sha256": tree["diff"]["sha256"],
            "truncated": tree["diff"]["truncated"],
            "char_len": tree["diff"]["char_len"],
            "text": tree["diff"]["text"],
        },
        "files": {
            "staged": tree["staged"],
            "unstaged": tree["unstaged"],
            "untracked": tree["untracked"],
            "modified": modified,
        },
        "worktree": str(cwd),
    }
    out = redact_obj(out)

    cdir = cycles_dir(root) / str(cycle_id)
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "verification.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out
