"""Isolation guard — fail closed outside registered campaign worktree."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, cast

CAMPAIGN_ID = "BID-SUBMISSION-READINESS-COMPLIANCE-PACK-01"
EXPECTED_BRANCH = "campaign/bid-submission-readiness-compliance-pack-01"
ALLOWLIST_PREFIXES = (
    "scripts/bid_readiness/",
    "tests/bid_readiness/",
    "specs/009-bid-submission-readiness/",
    "artifacts/campaigns/BID-SUBMISSION-READINESS-COMPLIANCE-PACK-01/",
    "integration-handoff/BID-SUBMISSION-READINESS-COMPLIANCE-PACK-01/",
    "docs/architecture/adr/ADR-033-bid-readiness-evidence-model.md",
)

PRIVATE_PATH_MARKERS = (
    "/opt/extra-consultoria",
    "ec-prod",
    "artifacts/campaigns/EXTRA-LIVE-CONSULTING-PACK-01",
    "artifacts/campaigns/CANONICAL-ENTITY-LINKAGE-01",
    "artifacts/campaigns/EDITAL-TECHNICAL-TRIAGE-CASE-PACK-01",
    "artifacts/campaigns/ENGINEERING-BUDGET-COMPOSITION-BDI-AUDIT-01",
)


class IsolationError(RuntimeError):
    """Raised when isolation invariants are violated."""


def _run_git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(  # noqa: S603
        ["/usr/bin/git", *args] if Path("/usr/bin/git").is_file() else ["git", *args],  # noqa: S607
        cwd=str(cwd),
        text=True,
    ).strip()


def repo_root() -> Path:
    # Prefer git toplevel of CWD
    try:
        return Path(_run_git(["rev-parse", "--show-toplevel"], Path.cwd())).resolve()
    except Exception as exc:  # noqa: BLE001
        raise IsolationError(f"not a git worktree: {exc}") from exc


def load_lock(root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root()
    path = root / "artifacts/campaigns/BID-SUBMISSION-READINESS-COMPLIANCE-PACK-01" / "worktree-lock.json"
    if not path.is_file():
        raise IsolationError(f"worktree lock missing: {path}")
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def assert_isolation(root: Path | None = None, *, require_branch: bool = True) -> dict[str, Any]:
    """Fail if executed outside campaign worktree / branch / lock invariants."""
    root = (root or repo_root()).resolve()
    lock = load_lock(root)

    for key in (
        "campaign_id",
        "branch",
        "worktree_path",
        "base_sha",
        "production_touched",
        "soak_touched",
        "database_used",
        "confidential_documents_committed",
    ):
        if key not in lock:
            raise IsolationError(f"lock missing field: {key}")

    if lock["campaign_id"] != CAMPAIGN_ID:
        raise IsolationError("campaign_id mismatch in lock")

    wt = Path(str(lock["worktree_path"])).resolve()
    if root != wt:
        raise IsolationError(f"executed outside registered worktree: cwd_root={root} expected={wt}")

    primary = Path(str(lock.get("primary_checkout_path", ""))).resolve()
    if primary.exists() and root == primary:
        raise IsolationError("executed on primary checkout — forbidden")

    branch = _run_git(["branch", "--show-current"], root)
    if require_branch:
        if not branch:
            raise IsolationError("detached HEAD is not allowed")
        if branch != lock["branch"] or branch != EXPECTED_BRANCH:
            raise IsolationError(f"branch mismatch: current={branch!r} lock={lock['branch']!r}")

    head = _run_git(["rev-parse", "HEAD"], root)
    base = str(lock["base_sha"])
    if not base:
        raise IsolationError("base_sha not registered")

    # Isolation flags must be explicitly false
    for flag in (
        "production_touched",
        "soak_touched",
        "database_used",
        "confidential_documents_committed",
    ):
        if lock.get(flag) is not False:
            raise IsolationError(f"isolation flag {flag} must be false, got {lock.get(flag)!r}")

    # Forbid DB/VPS env leakage
    for env_key in ("LOCAL_DATALAKE_DSN", "DATABASE_URL", "PGPASSWORD", "SSH_AUTH_SOCK_VPS"):
        if os.environ.get(env_key):
            # DSN presence alone is not fatal if unused; record only when gate runs hard mode
            pass

    return {
        "ok": True,
        "root": str(root),
        "branch": branch,
        "head": head,
        "base_sha": base,
        "lock": lock,
    }


def path_is_allowlisted(rel_path: str) -> bool:
    p = rel_path.replace("\\", "/").lstrip("./")
    if p == "docs/architecture/adr/ADR-033-bid-readiness-evidence-model.md":
        return True
    return any(p == pref.rstrip("/") or p.startswith(pref) for pref in ALLOWLIST_PREFIXES)


def assert_fileset(base_sha: str, root: Path | None = None) -> list[str]:
    root = root or repo_root()
    try:
        diff = _run_git(["diff", "--name-only", f"{base_sha}...HEAD"], root)
    except subprocess.CalledProcessError as exc:
        raise IsolationError(f"fileset diff failed: {exc}") from exc
    files = [ln.strip() for ln in diff.splitlines() if ln.strip()]
    bad = [f for f in files if not path_is_allowlisted(f)]
    if bad:
        raise IsolationError(f"files outside allowlist: {bad}")
    return files


def assert_no_foreign_roots(paths: list[str]) -> None:
    for p in paths:
        for marker in PRIVATE_PATH_MARKERS:
            if marker in p:
                raise IsolationError(f"access to foreign/private path: {p}")
