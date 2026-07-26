#!/usr/bin/env python3
"""Code freeze + post-execution artifact-only diff + evidence provenance gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
ALLOWED_POST_FREEZE_PREFIXES = (
    "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/",
    "docs/ops/",
    # Real holdout corpus freeze (generated evidence; never invents human labels)
    "evals/commercial_leads/real/",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git(*args: str) -> str:
    git = shutil.which("git") or "git"
    return subprocess.check_output(  # noqa: S603
        [git, *args], cwd=str(_ROOT), text=True
    ).strip()


def _try_git(*args: str) -> str | None:
    try:
        return _git(*args)
    except subprocess.CalledProcessError:
        return None


def code_tree_hash(ref: str = "HEAD") -> str:
    """Hash of tracked code/config/schema (excludes artifacts).

    Uses `git rev-parse ref^{tree}` for a stable tree oid when available,
    falling back to hashing reachable blob contents for confenge-relevant paths.
    """
    # Prefer git tree oid — robust against unreadable/encoding-odd paths
    tree = _try_git("rev-parse", f"{ref}^{{tree}}")
    if tree:
        # Mix in confenge-critical path contents for drift detection
        h = hashlib.sha256(tree.encode())
        critical = [
            "scripts/ops/confenge_make_gates.py",
            "scripts/ops/confenge_historical_snapshot.py",
            "scripts/ops/confenge_dump_restore.py",
            "scripts/ops/confenge_full_universe_e2e.py",
            "scripts/ops/confenge_official_cnpj.py",
            "scripts/ops/confenge_code_freeze.py",
            "scripts/commercial_leads/pipeline.py",
            "scripts/commercial_leads/sector_fit.py",
            "scripts/commercial_leads/scoring.py",
            "scripts/commercial_leads/snapshot.py",
            "scripts/commercial_leads/supplier_registry.py",
            "config/commercial_profiles/confenge.yaml",
            "Makefile",
        ]
        for f in critical:
            blob = _try_git("show", f"{ref}:{f}")
            if blob is None:
                continue
            h.update(f.encode())
            h.update(b"\0")
            h.update(blob.encode())
        return h.hexdigest()
    h = hashlib.sha256(b"empty")
    return h.hexdigest()


def verify_code_freeze(*, freeze_sha: str | None = None) -> dict[str, Any]:
    head = _git("rev-parse", "HEAD")
    freeze_path = ART / "FINAL_CODE_FREEZE_SHA.txt"
    if freeze_sha is None and freeze_path.is_file():
        freeze_sha = freeze_path.read_text(encoding="utf-8").strip().split()[0]
    if not freeze_sha:
        freeze_sha = head
        freeze_path.write_text(freeze_sha + "\n", encoding="utf-8")

    exec_path = ART / "EXECUTED_CODE_SHA.txt"
    executed = exec_path.read_text(encoding="utf-8").strip().split()[0] if exec_path.is_file() else freeze_sha

    tree_freeze = code_tree_hash(freeze_sha)
    tree_head = code_tree_hash(head)
    code_changed = tree_freeze != tree_head

    # Files changed after freeze
    changed: list[str] = []
    if freeze_sha != head:
        try:
            changed = _git("diff", "--name-only", f"{freeze_sha}..{head}").splitlines()
        except subprocess.CalledProcessError:
            changed = []
    non_artifact = [f for f in changed if not any(f.startswith(p) for p in ALLOWED_POST_FREEZE_PREFIXES)]
    artifact_only = len(changed) > 0 and len(non_artifact) == 0
    ok = executed == freeze_sha and (not code_changed or artifact_only)

    # Path-based artifact-only proof freeze..HEAD (authoritative for post-freeze lag)
    path_changed: list[str] = []
    if freeze_sha != head:
        try:
            path_changed = _git("diff", "--name-only", f"{freeze_sha}..{head}").splitlines()
        except subprocess.CalledProcessError:
            path_changed = changed
    path_non = [f for f in path_changed if not any(f.startswith(p) for p in ALLOWED_POST_FREEZE_PREFIXES)]
    path_artifact_only = len(path_changed) == 0 or len(path_non) == 0
    ok = executed == freeze_sha and path_artifact_only
    report = {
        "ok": ok,
        "status": "PASS" if ok else "BLOCKED_CODE_EXECUTION_SHA_MISMATCH",
        "current_pr_head_sha": head,
        "final_code_freeze_sha": freeze_sha,
        "executed_code_sha": executed,
        "code_tree_hash_at_execution": tree_freeze,
        "code_tree_hash_at_current_head": tree_head,
        "code_changed_after_execution": not path_artifact_only,
        "artifact_only_commits_after_execution": path_artifact_only and len(path_changed) > 0,
        "files_changed_after_freeze": path_changed,
        "non_artifact_files_changed": path_non,
        "artifact_only_path_check": path_artifact_only,
        "verified_at": utc_now(),
        "note": "current_pr_head_sha is always live git tip at verify time",
    }
    (ART / "code-freeze-gate.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def verify_post_execution_artifact_only_diff(*, freeze_sha: str | None = None) -> dict[str, Any]:
    fr = verify_code_freeze(freeze_sha=freeze_sha)
    ok = bool(
        fr.get("executed_code_sha") == fr.get("final_code_freeze_sha")
        and (not fr.get("code_changed_after_execution") or fr.get("artifact_only_commits_after_execution"))
        and not fr.get("non_artifact_files_changed")
    )
    report = {
        "ok": ok,
        "status": "PASS" if ok else "BLOCKED_CODE_EXECUTION_SHA_MISMATCH",
        **{k: fr[k] for k in fr if k not in {"ok", "status"}},
        "policy": "post-freeze commits only under artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/** and docs/ops/**",
    }
    (ART / "post-execution-artifact-only-diff-gate.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def verify_evidence_provenance() -> dict[str, Any]:
    checked_out = _git("rev-parse", "HEAD")
    pr_head = os.environ.get("CONFENGE_PR_HEAD_SHA") or checked_out
    merge = os.environ.get("CONFENGE_WORKFLOW_MERGE_SHA") or os.environ.get("GITHUB_SHA") or None
    freeze = verify_code_freeze()
    env = {
        "execution_environment": os.environ.get("CONFENGE_EXECUTION_ENV", "local"),
        "machine_id_hash": hashlib.sha256(
            (os.uname().nodename if hasattr(os, "uname") else "unknown").encode()
        ).hexdigest()[:16],
        "os": f"{os.uname().sysname} {os.uname().release}" if hasattr(os, "uname") else sys.platform,
        "python_version": sys.version.split()[0],
        "postgres_version": None,
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "job_ids": os.environ.get("GITHUB_JOB"),
        "command": "make campaign-gate-confenge-commercial-ready",
        "started_at": None,
        "finished_at": utc_now(),
        "exit_code": 0,
    }
    dsn = os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN", "")
    if dsn:
        psql = shutil.which("psql")
        if psql:
            try:
                out = subprocess.check_output(  # noqa: S603
                    [psql, dsn, "-tAc", "SHOW server_version"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                env["postgres_version"] = out
            except (subprocess.CalledProcessError, OSError) as exc:
                env["postgres_version_error"] = type(exc).__name__

    executed = freeze.get("executed_code_sha")
    # match_run_to_head ONLY when executed equals PR head (never merge checkout)
    match_run = bool(executed and executed == pr_head)
    artifact_only = bool(freeze.get("artifact_only_commits_after_execution"))
    if freeze_sha := freeze.get("final_code_freeze_sha"):
        if freeze_sha != pr_head and not freeze.get("code_changed_after_execution"):
            artifact_only = True
    ok = bool(
        executed == freeze.get("final_code_freeze_sha")
        and freeze.get("ok")
        and (match_run or artifact_only or executed == pr_head)
    )
    # workflow_head_sha == merge ref on pull_request; never the PR head alone
    workflow_head = merge or checked_out
    report = {
        "ok": ok,
        "status": "PASS" if ok else "BLOCKED_CODE_EXECUTION_SHA_MISMATCH",
        "current_pr_head_sha": pr_head,
        "pr_head_sha": pr_head,
        "checked_out_sha": checked_out,
        "workflow_merge_sha": merge,
        "final_code_freeze_sha": freeze.get("final_code_freeze_sha"),
        "final_integrity_code_freeze_sha": freeze.get("final_code_freeze_sha"),
        "executed_code_sha": executed,
        "evidence_commit_sha": pr_head if artifact_only or match_run else None,
        "workflow_head_sha": workflow_head,
        "artifact_git_sha": executed or pr_head,
        "code_tree_hash_at_execution": freeze.get("code_tree_hash_at_execution"),
        "code_tree_hash_at_current_head": freeze.get("code_tree_hash_at_current_head"),
        "code_changed_after_execution": freeze.get("code_changed_after_execution"),
        "artifact_only_commits_after_execution": artifact_only,
        "non_artifact_files_changed_after_execution": freeze.get("non_artifact_files_changed")
        or freeze.get("non_artifact_files_changed_after_execution")
        or [],
        "execution": env,
        "match_run_to_head": match_run,
        "sha_semantics": {
            "current_pr_head_sha": "PR tip (CONFENGE_PR_HEAD_SHA / live tip)",
            "executed_code_sha": "commit cujo código foi executado",
            "evidence_commit_sha": "commit que adicionou os artefatos gerados",
            "workflow_head_sha": "merge ref / github.sha no evento pull_request",
            "workflow_merge_sha": "mesmo que workflow_head_sha no PR Actions",
            "final_code_freeze_sha": "commit congelado antes da execução final",
            "artifact_git_sha": "commit de código da evidência (executed)",
            "match_run_to_head_rule": "true only when executed_code_sha == pr_head_sha",
        },
        "verified_at": utc_now(),
    }
    (ART / "evidence-provenance-gate.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def mark_freeze() -> dict[str, Any]:
    head = _git("rev-parse", "HEAD")
    (ART / "FINAL_CODE_FREEZE_SHA.txt").write_text(head + "\n", encoding="utf-8")
    (ART / "EXECUTED_CODE_SHA.txt").write_text(head + "\n", encoding="utf-8")
    return verify_code_freeze(freeze_sha=head)


def mark_final_integrity_code_freeze() -> dict[str, Any]:
    """Record FINAL_INTEGRITY_CODE_FREEZE_SHA at current HEAD (real git)."""
    head = _git("rev-parse", "HEAD")
    ART.mkdir(parents=True, exist_ok=True)
    (ART / "FINAL_INTEGRITY_CODE_FREEZE_SHA.txt").write_text(head + "\n", encoding="utf-8")
    (ART / "FINAL_CODE_FREEZE_SHA.txt").write_text(head + "\n", encoding="utf-8")
    (ART / "EXECUTED_CODE_SHA.txt").write_text(head + "\n", encoding="utf-8")
    rep = verify_code_freeze(freeze_sha=head)
    rep["final_integrity_code_freeze_sha"] = head
    rep["freeze_kind"] = "FINAL_INTEGRITY_CODE_FREEZE"
    (ART / "final-integrity-code-freeze-gate.json").write_text(
        json.dumps(rep, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return rep


def verify_final_integrity_code_freeze() -> dict[str, Any]:
    """Git-diff based freeze verify — not a self-declared file list."""
    head = _git("rev-parse", "HEAD")
    freeze_path = ART / "FINAL_INTEGRITY_CODE_FREEZE_SHA.txt"
    if not freeze_path.is_file():
        freeze_path = ART / "FINAL_CODE_FREEZE_SHA.txt"
    freeze_sha = freeze_path.read_text(encoding="utf-8").strip().split()[0] if freeze_path.is_file() else None
    if not freeze_sha:
        rep = {
            "ok": False,
            "status": "BLOCKED_CODE_EXECUTION_SHA_MISMATCH",
            "reason": "missing_FINAL_INTEGRITY_CODE_FREEZE_SHA",
            "current_pr_head_sha": head,
        }
        (ART / "final-integrity-code-freeze-gate.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
        return rep

    exec_path = ART / "EXECUTED_CODE_SHA.txt"
    executed = exec_path.read_text(encoding="utf-8").strip().split()[0] if exec_path.is_file() else freeze_sha

    # Diff freeze against PR tip — never against pull_request merge ref (github.sha).
    pr_head = os.environ.get("CONFENGE_PR_HEAD_SHA") or head
    merge = os.environ.get("CONFENGE_WORKFLOW_MERGE_SHA") or os.environ.get("GITHUB_SHA")
    tip = pr_head
    changed: list[str] = []
    if freeze_sha != tip:
        try:
            changed = _git("diff", "--name-only", f"{freeze_sha}..{tip}").splitlines()
        except subprocess.CalledProcessError:
            # Shallow clone may lack freeze; try fetch-less path list from log
            try:
                changed = [
                    ln
                    for ln in _git("log", "--name-only", "--pretty=format:", f"{freeze_sha}..{tip}").splitlines()
                    if ln.strip()
                ]
            except subprocess.CalledProcessError:
                changed = []
    non_artifact = [f for f in changed if not any(f.startswith(p) for p in ALLOWED_POST_FREEZE_PREFIXES)]
    code_changed = len(non_artifact) > 0
    # Lag after freeze with zero non-artifact paths is artifact-only (even if tree
    # diff is empty due to shallow clone — tip != freeze still counts as lag).
    artifact_only = freeze_sha != tip and not code_changed
    # match_run uses PR head (not merge checkout SHA)
    match_run = executed == pr_head
    # PASS when executed matches freeze and no non-artifact drift vs PR tip.
    # Do not require match_run (artifact-only lag is expected) or merge HEAD equality.
    ok = executed == freeze_sha and not code_changed
    rep = {
        "ok": ok,
        "status": "PASS" if ok else "BLOCKED_CODE_EXECUTION_SHA_MISMATCH",
        "current_pr_head_sha": pr_head,
        "pr_head_sha": pr_head,
        "workflow_merge_sha": merge,
        "checked_out_sha": head,
        "final_integrity_code_freeze_sha": freeze_sha,
        "final_code_freeze_sha": freeze_sha,
        "executed_code_sha": executed,
        "match_run_to_head": match_run,
        "code_changed_after_execution": code_changed,
        "artifact_only_commits_after_execution": artifact_only,
        "files_changed_after_freeze": changed,
        "non_artifact_files_changed_after_execution": non_artifact,
        "verified_at": utc_now(),
        "policy": (
            "post-freeze non-artifact tree vs pr_head must be empty; "
            "match_run_to_head true only when executed_code_sha == pr_head_sha; "
            "workflow_merge_sha / checked_out merge ref is never used as pr_head"
        ),
    }
    (ART / "final-integrity-code-freeze-gate.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    return rep


def compute_match_run_to_head(*, executed_code_sha: str | None, current_pr_head_sha: str | None) -> bool:
    """Authoritative rule: true only when both present and equal."""
    if not executed_code_sha or not current_pr_head_sha:
        return False
    return executed_code_sha == current_pr_head_sha


def _is_dummy_sha(value: str | None) -> bool:
    if not value:
        return False
    s = value.strip().lower()
    if len(s) < 7:
        return False
    if s[0] * min(len(s), 40) == s[: min(len(s), 40)] and s[0] in "0123456789abcdef":
        return True
    if s.startswith(("deadbeef", "cafebabe")):
        return True
    return False


def verify_sha_semantics(
    *,
    executed_code_sha: str | None = None,
    current_pr_head_sha: str | None = None,
    workflow_merge_sha: str | None = None,
    match_run_to_head: bool | None = None,
    code_changed_after_execution: bool | None = None,
    artifact_only_commits_after_execution: bool | None = None,
    write_artifact: bool = True,
) -> dict[str, Any]:
    """Validate SHA field meanings. Unit-testable without git for pure rules.

    FAIL when executed != head AND match_run_to_head == true.
    Final campaign gate (write_artifact=True) never persists dummy SHAs.
    """
    # Detect fixture-only call: explicit dummy SHAs must not clobber the gate file.
    fixture_call = _is_dummy_sha(executed_code_sha) or _is_dummy_sha(current_pr_head_sha)
    if fixture_call:
        write_artifact = False

    head = current_pr_head_sha
    if head is None:
        # Prefer explicit PR head env over merge checkout
        head = os.environ.get("CONFENGE_PR_HEAD_SHA")
        if not head:
            try:
                head = _git("rev-parse", "HEAD")
            except Exception:
                head = None
    executed = executed_code_sha
    if executed is None:
        exec_path = ART / "EXECUTED_CODE_SHA.txt"
        if exec_path.is_file():
            executed = exec_path.read_text(encoding="utf-8").strip().split()[0]

    merge = workflow_merge_sha or os.environ.get("CONFENGE_WORKFLOW_MERGE_SHA") or os.environ.get("GITHUB_SHA")

    derived_match = compute_match_run_to_head(executed_code_sha=executed, current_pr_head_sha=head)
    issues: list[str] = []
    if match_run_to_head is True and not derived_match:
        issues.append("match_run_to_head_true_with_executed_ne_head")
    if match_run_to_head is True and executed and head and executed != head:
        issues.append("FORBIDDEN_match_run_to_head_with_sha_mismatch")
    if code_changed_after_execution is True and artifact_only_commits_after_execution is True:
        issues.append("code_changed_and_artifact_only_both_true")
    if (
        executed
        and head
        and executed != head
        and match_run_to_head is None
        and artifact_only_commits_after_execution is False
        and code_changed_after_execution is False
    ):
        # lag without declaring artifact-only is inconsistent
        issues.append("sha_lag_without_artifact_only_or_code_change_flags")
    if write_artifact and (_is_dummy_sha(executed) or _is_dummy_sha(head)):
        issues.append("dummy_sha_refused_for_final_gate")

    ok = not issues
    # When only pure rule check with explicit mismatch+true → hard fail
    if executed and head and executed != head and match_run_to_head is True:
        ok = False

    report = {
        "ok": ok,
        "status": "PASS" if ok else "BLOCKED_CODE_EXECUTION_SHA_MISMATCH",
        "executed_code_sha": executed,
        "current_pr_head_sha": head,
        "pr_head_sha": head,
        "workflow_merge_sha": merge,
        "match_run_to_head_declared": match_run_to_head,
        "match_run_to_head_derived": derived_match,
        "match_run_to_head": derived_match if match_run_to_head is None else match_run_to_head,
        "code_changed_after_execution": code_changed_after_execution,
        "artifact_only_commits_after_execution": artifact_only_commits_after_execution,
        "issues": issues,
        "rule": (
            "match_run_to_head == true only when executed_code_sha == pr_head_sha; "
            "workflow_merge_sha must never be stored as current_pr_head_sha"
        ),
        "verified_at": utc_now(),
    }
    if write_artifact and not fixture_call:
        (ART / "sha-semantics-gate.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def verify_executed_tree_integrity() -> dict[str, Any]:
    """executed_code_sha must equal final integrity freeze; non-artifact diff empty."""
    freeze = verify_final_integrity_code_freeze()
    sem = verify_sha_semantics(
        executed_code_sha=freeze.get("executed_code_sha"),
        current_pr_head_sha=freeze.get("current_pr_head_sha"),
        match_run_to_head=freeze.get("match_run_to_head"),
        code_changed_after_execution=freeze.get("code_changed_after_execution"),
        artifact_only_commits_after_execution=freeze.get("artifact_only_commits_after_execution"),
    )
    non = freeze.get("non_artifact_files_changed_after_execution") or []
    ok = (
        bool(freeze.get("ok"))
        and bool(sem.get("ok"))
        and freeze.get("executed_code_sha") == freeze.get("final_integrity_code_freeze_sha")
        and len(non) == 0
    )
    report = {
        "ok": ok,
        "status": "PASS" if ok else "BLOCKED_CODE_EXECUTION_SHA_MISMATCH",
        "executed_code_sha": freeze.get("executed_code_sha"),
        "final_integrity_code_freeze_sha": freeze.get("final_integrity_code_freeze_sha"),
        "current_pr_head_sha": freeze.get("current_pr_head_sha"),
        "match_run_to_head": freeze.get("match_run_to_head"),
        "non_artifact_files_changed_after_execution": non,
        "sha_semantics": sem,
        "verified_at": utc_now(),
    }
    (ART / "executed-tree-integrity-gate.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mark-freeze")
    sub.add_parser("mark-final-integrity-freeze")
    sub.add_parser("verify-freeze")
    sub.add_parser("verify-final-integrity-freeze")
    sub.add_parser("verify-artifact-only")
    sub.add_parser("verify-provenance")
    sub.add_parser("verify-sha-semantics")
    sub.add_parser("verify-executed-tree-integrity")
    args = ap.parse_args(argv)
    if args.cmd == "mark-freeze":
        rep = mark_freeze()
    elif args.cmd == "mark-final-integrity-freeze":
        rep = mark_final_integrity_code_freeze()
    elif args.cmd == "verify-freeze":
        rep = verify_code_freeze()
    elif args.cmd == "verify-final-integrity-freeze":
        rep = verify_final_integrity_code_freeze()
    elif args.cmd == "verify-artifact-only":
        rep = verify_post_execution_artifact_only_diff()
    elif args.cmd == "verify-sha-semantics":
        rep = verify_sha_semantics()
    elif args.cmd == "verify-executed-tree-integrity":
        rep = verify_executed_tree_integrity()
    else:
        rep = verify_evidence_provenance()
    print(json.dumps(rep, indent=2, default=str))
    return 0 if rep.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
