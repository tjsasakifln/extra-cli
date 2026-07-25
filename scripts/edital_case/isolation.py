"""Worktree isolation guard for EDITAL-TECHNICAL-TRIAGE-CASE-PACK-01.

All campaign commands must call `enforce_isolation()` before mutating state.
Fails closed when identity cannot be proven.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.edital_case import CAMPAIGN_BRANCH, CAMPAIGN_ID, DEFAULT_CAMPAIGN_DIR

PRODUCTION_PATH_MARKERS = (
    "/opt/extra-consultoria",
    "ec-prod",
)

FORBIDDEN_CAMPAIGN_MARKERS = (
    "EXTRA-LIVE-CONSULTING-PACK-01",
    "CANONICAL-ENTITY-LINKAGE-01",
    "OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01",
    "HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01",
    "CLIENT-READY-RECURRING-CONSULTING-CYCLE-01",
    "NATIONAL-CONTRACTS-INTELLIGENCE",
)

ALLOWED_PATH_PREFIXES = (
    "scripts/edital_case/",
    "tests/edital_case/",
    "specs/007-edital-technical-triage/",
    "artifacts/campaigns/EDITAL-TECHNICAL-TRIAGE-CASE-PACK-01/",
    "docs/architecture/adr/ADR-031-edital-case-evidence-model.md",
    "integration-handoff/EDITAL-TECHNICAL-TRIAGE-CASE-PACK-01/",
    "integration-handoff/",
    # PDF/DOCX extractors required by edital_case (CI full suite)
    "requirements.txt",
)

DENIED_PATH_EXACT = frozenset(
    {
        "DOD.md",
        "README.md",
        "CLAUDE.md",
        "AGENTS.md",
        "Makefile",
        ".github/workflows/ci.yml",
        "docs/DEVELOPMENT.md",
        "docs/canonical-entry-points.yaml",
        "docs/architecture/adr/INDEX.md",
        "config/client_profiles/extra.yaml",
        "scripts/workspace/cli.py",
        "scripts/workspace/actions.py",
        "scripts/ops/weekly_cycle.py",
        "scripts/ops/live_consulting_pack.py",
        "scripts/ops/strategic_monthly_monitor.py",
    }
)

DENIED_PATH_PREFIXES = (
    "scripts/workspace/",
    "scripts/linkage/",
    "scripts/national_intel/",
    "db/migrations/",
    "deploy/",
    "artifacts/campaigns/EXTRA-LIVE-CONSULTING-PACK-01/",
    "artifacts/campaigns/CANONICAL-ENTITY-LINKAGE-01/",
    "artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/",
    "artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/",
)


class IsolationError(RuntimeError):
    """Raised when campaign isolation invariants are violated."""


@dataclass(frozen=True)
class IsolationContext:
    campaign_id: str
    branch: str
    worktree_path: str
    git_common_dir: str
    base_sha: str
    origin_main_sha_at_start: str
    primary_checkout_path: str
    head_sha: str
    campaign_root: str
    production_touched: bool
    soak_touched: bool
    database_used: bool
    vps_accessed: bool


def _run_git(*args: str, cwd: Path | None = None) -> str:
    try:
        out = subprocess.check_output(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=str(cwd) if cwd else None,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise IsolationError(f"git identity unavailable: {exc}") from exc


def _load_lock(repo_root: Path) -> dict[str, Any]:
    lock_path = repo_root / DEFAULT_CAMPAIGN_DIR / "worktree-lock.json"
    if not lock_path.is_file():
        raise IsolationError(f"missing worktree-lock.json at {lock_path}")
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IsolationError(f"invalid worktree-lock.json: {exc}") from exc
    if not isinstance(data, dict):
        raise IsolationError("worktree-lock.json must be an object")
    return data


def _load_isolation_meta(repo_root: Path) -> dict[str, Any]:
    path = repo_root / DEFAULT_CAMPAIGN_DIR / "isolation.json"
    if not path.is_file():
        raise IsolationError(f"missing isolation.json at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IsolationError(f"invalid isolation.json: {exc}") from exc
    if not isinstance(data, dict):
        raise IsolationError("isolation.json must be an object")
    return data


def _require_bool_false(meta: dict[str, Any], key: str) -> bool:
    if key not in meta:
        raise IsolationError(f"manifest missing required key: {key}")
    val = meta[key]
    if val is None:
        raise IsolationError(f"{key} must be false, got null")
    if val is not False:
        raise IsolationError(f"{key} must be false, got {val!r}")
    return False


def resolve_repo_root(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    try:
        top = _run_git("rev-parse", "--show-toplevel", cwd=start)
    except IsolationError:
        # fallback: walk parents
        cur = start
        for _ in range(12):
            if (cur / ".git").exists() or (cur / "scripts" / "edital_case").is_dir():
                return cur
            if cur.parent == cur:
                break
            cur = cur.parent
        raise IsolationError("cannot determine git repository root")
    return Path(top).resolve()


def enforce_isolation(
    *,
    allow_primary: bool = False,
    require_campaign_root_env: bool = False,
) -> IsolationContext:
    """Validate process is running inside the campaign worktree.

    Raises IsolationError on any failure.
    """
    repo_root = resolve_repo_root()
    lock = _load_lock(repo_root)
    iso = _load_isolation_meta(repo_root)

    branch = _run_git("branch", "--show-current", cwd=repo_root)
    if not branch:
        raise IsolationError("detached HEAD is not allowed for this campaign")
    expected_branch = lock.get("branch") or CAMPAIGN_BRANCH
    if branch != expected_branch:
        raise IsolationError(
            f"branch mismatch: running on {branch!r}, expected {expected_branch!r}"
        )

    head = _run_git("rev-parse", "HEAD", cwd=repo_root)
    common = Path(_run_git("rev-parse", "--git-common-dir", cwd=repo_root)).resolve()
    worktree_path = str(repo_root)
    lock_wt = str(Path(str(lock.get("worktree_path", ""))).resolve())
    if lock_wt and worktree_path != lock_wt:
        raise IsolationError(
            f"worktree path mismatch: cwd root {worktree_path!r} != lock {lock_wt!r}"
        )

    primary = str(Path(str(lock.get("primary_checkout_path", ""))).resolve())
    if not allow_primary and primary and worktree_path == primary:
        raise IsolationError(
            "refusing to run campaign commands on the primary checkout"
        )

    lock_common = lock.get("git_common_dir")
    if lock_common:
        if str(common) != str(Path(str(lock_common)).resolve()):
            raise IsolationError(
                f"git common dir mismatch: {common} != {lock_common}"
            )

    base_sha = str(lock.get("base_sha") or "")
    if not base_sha or len(base_sha) < 7:
        raise IsolationError("base_sha missing from worktree-lock.json")

    # Ensure HEAD is descendant of base (same line of work from origin/main)
    try:
        merge_base = _run_git("merge-base", base_sha, head, cwd=repo_root)
        if merge_base != base_sha and not head.startswith(base_sha[:12]):
            # still ok if head == base at start
            if head != base_sha:
                # verify base is ancestor
                _run_git("merge-base", "--is-ancestor", base_sha, head, cwd=repo_root)
    except IsolationError as exc:
        raise IsolationError(
            f"worktree not created from registered base_sha {base_sha}: {exc}"
        ) from exc

    if lock.get("campaign_id") != CAMPAIGN_ID:
        raise IsolationError(f"campaign_id mismatch in lock: {lock.get('campaign_id')}")

    production_touched = _require_bool_false(lock, "production_touched")
    soak_touched = _require_bool_false(lock, "soak_touched")
    database_used = _require_bool_false(iso, "database_used")
    vps_accessed = _require_bool_false(iso, "vps_accessed")
    _require_bool_false(iso, "production_touched")
    _require_bool_false(iso, "soak_touched")

    campaign_root = os.environ.get("EDITAL_CAMPAIGN_ROOT") or str(
        iso.get("campaign_root") or ""
    )
    if require_campaign_root_env and not os.environ.get("EDITAL_CAMPAIGN_ROOT"):
        raise IsolationError("EDITAL_CAMPAIGN_ROOT is required")

    # Path safety: reject production markers in env
    for key, val in os.environ.items():
        low = f"{key}={val}".lower()
        if any(m in low for m in ("ec-prod", "/opt/extra-consultoria")):
            if key.startswith("EDITAL_") or "SSH" in key or "PG" in key:
                raise IsolationError(f"production-related env detected: {key}")

    cwd_s = str(Path.cwd().resolve())
    if any(m in cwd_s for m in PRODUCTION_PATH_MARKERS):
        raise IsolationError(f"cwd looks like production path: {cwd_s}")

    return IsolationContext(
        campaign_id=CAMPAIGN_ID,
        branch=branch,
        worktree_path=worktree_path,
        git_common_dir=str(common),
        base_sha=base_sha,
        origin_main_sha_at_start=str(lock.get("origin_main_sha_at_start") or base_sha),
        primary_checkout_path=primary,
        head_sha=head,
        campaign_root=campaign_root,
        production_touched=production_touched,
        soak_touched=soak_touched,
        database_used=database_used,
        vps_accessed=vps_accessed,
    )


def path_is_allowed(rel_path: str) -> bool:
    """Return True if rel_path is inside the campaign allowlist."""
    norm = rel_path.replace("\\", "/").lstrip("./")
    if norm in DENIED_PATH_EXACT:
        return False
    for pref in DENIED_PATH_PREFIXES:
        if norm == pref.rstrip("/") or norm.startswith(pref):
            return False
    for pref in ALLOWED_PATH_PREFIXES:
        if norm == pref.rstrip("/") or norm.startswith(pref):
            return True
    return False


def check_allowlist_diff(base_sha: str, repo_root: Path | None = None) -> list[str]:
    """Return list of changed paths outside allowlist (empty = ok)."""
    root = repo_root or resolve_repo_root()
    try:
        out = _run_git("diff", "--name-only", f"{base_sha}...HEAD", cwd=root)
    except IsolationError:
        out = _run_git("diff", "--name-only", base_sha, "HEAD", cwd=root)
    violations: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if not path_is_allowed(line):
            violations.append(line)
    return violations


def assert_no_foreign_paths(path: Path) -> None:
    """Fail if path points into another campaign or production tree."""
    s = str(path.resolve())
    for marker in PRODUCTION_PATH_MARKERS:
        if marker in s:
            raise IsolationError(f"path touches production marker {marker}: {s}")
    for marker in FORBIDDEN_CAMPAIGN_MARKERS:
        if marker in s:
            raise IsolationError(f"path touches foreign campaign {marker}: {s}")


def safety_flags() -> dict[str, bool]:
    return {
        "production_touched": False,
        "soak_touched": False,
        "vps_accessed": False,
        "database_used": False,
    }
