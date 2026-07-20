"""Seal verified commit SHA + tree hash so publisher cannot drift after review.

Flow:
  executor finishes → candidate commit → clean worktree →
  verifier seals SHA/tree → review binds to seal → publisher pushes exact seal.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.cto.paths import cycles_dir, repo_root
from scripts.cto.redaction import redact_obj


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(cmd: list[str], cwd: Path, timeout: int = 60) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
        return {
            "cmd": cmd,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
        }
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "exit_code": -1, "stdout": "", "stderr": "timeout"}
    except FileNotFoundError:
        return {"cmd": cmd, "exit_code": -2, "stdout": "", "stderr": "not_found"}


def git_head(worktree: Path) -> str | None:
    res = _run(["git", "rev-parse", "HEAD"], worktree)
    return res["stdout"] if res["exit_code"] == 0 and res["stdout"] else None


def git_tree(worktree: Path, commit: str | None = None) -> str | None:
    ref = commit or "HEAD"
    res = _run(["git", "rev-parse", f"{ref}^{{tree}}"], worktree)
    return res["stdout"] if res["exit_code"] == 0 and res["stdout"] else None


def worktree_is_clean(worktree: Path) -> bool:
    res = _run(["git", "status", "--porcelain"], worktree)
    return res["exit_code"] == 0 and not res["stdout"]


def is_descendant(worktree: Path, commit: str, base: str) -> bool:
    """True if commit is base or a descendant of base."""
    if not commit or not base:
        return False
    if commit == base:
        return True
    res = _run(["git", "merge-base", "--is-ancestor", base, commit], worktree)
    return res["exit_code"] == 0


def build_seal(
    *,
    worktree: Path,
    cycle_id: str,
    decision_id: str | None,
    verification_result: str,
    base_commit: str | None = None,
    allowed_paths: list[str] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Create a seal document bound to the current HEAD/tree of the worktree."""
    root = root or repo_root()
    head = git_head(worktree)
    tree = git_tree(worktree, head) if head else None
    clean = worktree_is_clean(worktree)
    descendant_ok = True
    if base_commit and head:
        descendant_ok = is_descendant(worktree, head, base_commit)
    seal: dict[str, Any] = {
        "schema_version": "1.0",
        "cycle_id": cycle_id,
        "decision_id": decision_id,
        "timestamp_utc": _utc_now(),
        "worktree": str(worktree),
        "commit_sha": head,
        "tree_hash": tree,
        "base_commit": base_commit,
        "worktree_clean": clean,
        "is_descendant_of_base": descendant_ok,
        "verification_result": verification_result,
        "allowed_paths": list(allowed_paths or []),
        "publishable": bool(
            head
            and tree
            and clean
            and descendant_ok
            and verification_result == "PASS"
        ),
    }
    payload = json.dumps(
        {
            "cycle_id": cycle_id,
            "commit_sha": head,
            "tree_hash": tree,
            "verification_result": verification_result,
        },
        sort_keys=True,
    )
    seal["seal_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    seal = redact_obj(seal)
    cdir = cycles_dir(root) / str(cycle_id)
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "seal.json").write_text(
        json.dumps(seal, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return seal


def load_seal(cycle_id: str, root: Path | None = None) -> dict[str, Any] | None:
    path = cycles_dir(root) / str(cycle_id) / "seal.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def assert_publishable_seal(
    *,
    worktree: Path,
    seal: dict[str, Any],
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail-closed checks before publisher push. Never runs git add -A."""
    errors: list[str] = []
    if not seal:
        return {"ok": False, "errors": ["missing seal"]}
    if seal.get("verification_result") != "PASS":
        errors.append(
            f"seal verification_result={seal.get('verification_result')!r} != PASS"
        )
    if verification is not None and verification.get("result") != "PASS":
        errors.append(f"live verification.result={verification.get('result')!r} != PASS")
    if not worktree_is_clean(worktree):
        errors.append("worktree dirty — publish forbidden after review")
    head = git_head(worktree)
    tree = git_tree(worktree, head) if head else None
    if head != seal.get("commit_sha"):
        errors.append(
            f"HEAD {head!r} diverges from sealed commit_sha {seal.get('commit_sha')!r}"
        )
    if tree != seal.get("tree_hash"):
        errors.append(
            f"tree {tree!r} diverges from sealed tree_hash {seal.get('tree_hash')!r}"
        )
    if seal.get("base_commit") and head:
        if not is_descendant(worktree, head, str(seal["base_commit"])):
            errors.append("commit is not a descendant of expected base")
    if not seal.get("publishable") and not errors:
        errors.append("seal.publishable is false")
    return {
        "ok": not errors,
        "errors": errors,
        "commit_sha": head,
        "tree_hash": tree,
        "seal_sha256": seal.get("seal_sha256"),
    }
