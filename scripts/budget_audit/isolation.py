"""Isolation guard — every campaign command must pass this before work."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.budget_audit.constants import (
    ALLOWED_EXACT,
    ALLOWED_PATH_PREFIXES,
    CAMPAIGN_ID,
    DENYLIST_PREFIXES,
    EXPECTED_BRANCH,
    FORBIDDEN_ENV_KEYS,
    FORBIDDEN_PATH_MARKERS,
    ISOLATION_RELPATH,
    LOCK_RELPATH,
)


class IsolationError(RuntimeError):
    """Raised when isolation guard fails."""


@dataclass
class IsolationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise IsolationError("; ".join(self.errors))


def _git(args: list[str], cwd: Path | None = None) -> str:
    try:
        return subprocess.check_output(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=str(cwd) if cwd else None,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise IsolationError(f"git command failed: git {' '.join(args)}: {exc}") from exc


def _repo_root() -> Path:
    return Path(_git(["rev-parse", "--show-toplevel"])).resolve()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise IsolationError(f"required file missing: {path}")
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise IsolationError(f"expected object JSON in {path}")
    return data


def is_path_allowed(rel_path: str) -> bool:
    """Return True if relative path is inside the campaign allowlist."""
    normalized = rel_path.replace("\\", "/").lstrip("./")
    if normalized in ALLOWED_EXACT:
        return True
    # git status --porcelain may report only the untracked directory root
    untracked_dir_roots = {
        "scripts/budget_audit",
        "tests/budget_audit",
        "specs/008-engineering-budget-composition-bdi-audit",
        "artifacts/campaigns/ENGINEERING-BUDGET-COMPOSITION-BDI-AUDIT-01",
        "integration-handoff",
        "integration-handoff/ENGINEERING-BUDGET-COMPOSITION-BDI-AUDIT-01",
    }
    if normalized.rstrip("/") in untracked_dir_roots:
        return True
    for prefix in ALLOWED_PATH_PREFIXES:
        p = prefix.rstrip("/")
        if normalized == p or normalized.startswith(prefix) or normalized.startswith(p + "/"):
            return True
    return False


def is_path_denied(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/").lstrip("./")
    for denied in DENYLIST_PREFIXES:
        if normalized == denied.rstrip("/") or normalized.startswith(denied):
            return True
    return False


def check_diff_against_base(base_sha: str, repo_root: Path | None = None) -> list[str]:
    """Return list of paths outside allowlist in base...HEAD diff."""
    root = repo_root or _repo_root()
    try:
        out = subprocess.check_output(  # noqa: S603
            ["git", "diff", "--name-only", f"{base_sha}...HEAD"],  # noqa: S607
            cwd=str(root),
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        # empty branch or identical
        return []
    bad: list[str] = []
    for line in out.splitlines():
        path = line.strip()
        if not path:
            continue
        if is_path_denied(path) or not is_path_allowed(path):
            bad.append(path)
    return bad


def guard(
    *,
    skip_diff: bool = False,
    require_env_roots: bool = False,
) -> IsolationResult:
    """Run full isolation guard. Fail closed."""
    errors: list[str] = []
    warnings: list[str] = []
    context: dict[str, Any] = {}

    try:
        repo_root = _repo_root()
    except IsolationError as exc:
        return IsolationResult(ok=False, errors=[str(exc)])

    context["repo_root"] = str(repo_root)
    lock_path = repo_root / LOCK_RELPATH
    isolation_path = repo_root / ISOLATION_RELPATH

    try:
        lock = _load_json(lock_path)
    except IsolationError as exc:
        return IsolationResult(ok=False, errors=[str(exc)], context=context)

    try:
        isolation = _load_json(isolation_path)
    except IsolationError as exc:
        return IsolationResult(ok=False, errors=[str(exc)], context=context)

    # Flags must be explicitly false
    for key in ("production_touched", "soak_touched", "database_used"):
        if lock.get(key) is not False:
            errors.append(f"lock.{key} must be false, got {lock.get(key)!r}")
        if isolation.get(key) is not False:
            errors.append(f"isolation.{key} must be false, got {isolation.get(key)!r}")

    if lock.get("campaign_id") != CAMPAIGN_ID:
        errors.append(f"lock.campaign_id mismatch: {lock.get('campaign_id')!r}")

    branch = _git(["branch", "--show-current"], cwd=repo_root)
    context["branch"] = branch
    if not branch:
        errors.append("detached HEAD is not allowed")
    elif branch != EXPECTED_BRANCH and not branch.startswith(EXPECTED_BRANCH):
        errors.append(
            f"branch must be {EXPECTED_BRANCH} (or suffix), got {branch!r}"
        )

    worktree_path = Path(str(lock["worktree_path"])).resolve()
    primary = Path(str(lock["primary_checkout_path"])).resolve()
    context["worktree_path"] = str(worktree_path)
    context["primary_checkout_path"] = str(primary)

    if repo_root == primary:
        errors.append("process is running in primary checkout — use dedicated worktree")

    if repo_root != worktree_path:
        errors.append(
            f"repo root {repo_root} does not match lock.worktree_path {worktree_path}"
        )

    try:
        if worktree_path.samefile(primary):
            errors.append("worktree_path is the same as primary_checkout_path")
    except OSError:
        pass

    # Forbidden environment
    for key in FORBIDDEN_ENV_KEYS:
        val = os.environ.get(key)
        if val:
            errors.append(f"forbidden env var set: {key}")

    for marker in FORBIDDEN_PATH_MARKERS:
        for env_key, env_val in os.environ.items():
            if marker in str(env_val):
                errors.append(f"env {env_key} points to forbidden path marker {marker}")

    # Optional exclusive roots
    if require_env_roots:
        for var in (
            "BUDGET_AUDIT_ROOT",
            "BUDGET_CASE_ROOT",
            "BUDGET_TMP_ROOT",
        ):
            if not os.environ.get(var):
                warnings.append(f"{var} not set (recommended for exclusive runtime roots)")

    # Diff allowlist
    base_sha = str(lock.get("base_sha") or lock.get("origin_main_sha_at_start") or "")
    context["base_sha"] = base_sha
    if not skip_diff and base_sha:
        bad = check_diff_against_base(base_sha, repo_root)
        if bad:
            errors.append(
                "paths outside allowlist in base...HEAD: " + ", ".join(bad[:20])
            )
            context["disallowed_paths"] = bad

    # Working tree dirty outside allowlist (ignore local tool noise)
    ignore_prefixes = (
        ".venv",
        ".venv-budget-audit",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".git/",
        "node_modules/",
    )
    try:
        status = subprocess.check_output(  # noqa: S603
            ["git", "status", "--porcelain"],  # noqa: S607
            cwd=str(repo_root),
            text=True,
        )
        dirty_bad: list[str] = []
        for line in status.splitlines():
            if len(line) < 4:
                continue
            path = line[3:].strip().split(" -> ")[-1].strip('"')
            if not path:
                continue
            if any(path.startswith(p) or f"/{p}" in path for p in ignore_prefixes):
                continue
            # untracked noise under campaign runtime tmp roots
            if path.startswith("/tmp/") or path.startswith("tmp/"):  # noqa: S108
                continue
            if not is_path_allowed(path):
                dirty_bad.append(path)
        if dirty_bad:
            errors.append(
                "dirty paths outside allowlist: " + ", ".join(dirty_bad[:20])
            )
            context["dirty_disallowed"] = dirty_bad
    except subprocess.CalledProcessError as exc:
        warnings.append(f"could not check working tree status: {exc}")

    ok = len(errors) == 0
    return IsolationResult(ok=ok, errors=errors, warnings=warnings, context=context)


def ensure_isolated(*, skip_diff: bool = False) -> IsolationResult:
    """Guard + raise on failure. Call at CLI entry."""
    result = guard(skip_diff=skip_diff)
    if not result.ok:
        for err in result.errors:
            print(f"ISOLATION ERROR: {err}", file=sys.stderr)
        result.raise_if_failed()
    for w in result.warnings:
        print(f"ISOLATION WARNING: {w}", file=sys.stderr)
    return result
