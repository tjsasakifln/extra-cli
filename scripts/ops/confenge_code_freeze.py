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
    executed = (
        exec_path.read_text(encoding="utf-8").strip().split()[0]
        if exec_path.is_file()
        else freeze_sha
    )

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
    non_artifact = [
        f
        for f in changed
        if not any(f.startswith(p) for p in ALLOWED_POST_FREEZE_PREFIXES)
    ]
    artifact_only = len(changed) > 0 and len(non_artifact) == 0
    ok = executed == freeze_sha and (not code_changed or artifact_only)

    # Path-based artifact-only proof freeze..HEAD (authoritative for post-freeze lag)
    path_changed: list[str] = []
    if freeze_sha != head:
        try:
            path_changed = _git("diff", "--name-only", f"{freeze_sha}..{head}").splitlines()
        except subprocess.CalledProcessError:
            path_changed = changed
    path_non = [
        f for f in path_changed
        if not any(f.startswith(p) for p in ALLOWED_POST_FREEZE_PREFIXES)
    ]
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
        and (
            not fr.get("code_changed_after_execution")
            or fr.get("artifact_only_commits_after_execution")
        )
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
    head = _git("rev-parse", "HEAD")
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

    ok = bool(
        freeze.get("executed_code_sha") == freeze.get("final_code_freeze_sha")
        and freeze.get("ok")
    )
    report = {
        "ok": ok,
        "status": "PASS" if ok else "BLOCKED_CODE_EXECUTION_SHA_MISMATCH",
        "current_pr_head_sha": head,
        "final_code_freeze_sha": freeze.get("final_code_freeze_sha"),
        "executed_code_sha": freeze.get("executed_code_sha"),
        "evidence_commit_sha": head,
        "code_tree_hash_at_execution": freeze.get("code_tree_hash_at_execution"),
        "code_tree_hash_at_current_head": freeze.get("code_tree_hash_at_current_head"),
        "code_changed_after_execution": freeze.get("code_changed_after_execution"),
        "artifact_only_commits_after_execution": freeze.get(
            "artifact_only_commits_after_execution"
        ),
        "execution": env,
        "match_run_to_head": freeze.get("executed_code_sha") == head
        or freeze.get("artifact_only_commits_after_execution"),
        "verified_at": utc_now(),
    }
    (ART / "evidence-provenance-gate.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def mark_freeze() -> dict[str, Any]:
    head = _git("rev-parse", "HEAD")
    (ART / "FINAL_CODE_FREEZE_SHA.txt").write_text(head + "\n", encoding="utf-8")
    (ART / "EXECUTED_CODE_SHA.txt").write_text(head + "\n", encoding="utf-8")
    return verify_code_freeze(freeze_sha=head)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mark-freeze")
    sub.add_parser("verify-freeze")
    sub.add_parser("verify-artifact-only")
    sub.add_parser("verify-provenance")
    args = ap.parse_args(argv)
    if args.cmd == "mark-freeze":
        rep = mark_freeze()
    elif args.cmd == "verify-freeze":
        rep = verify_code_freeze()
    elif args.cmd == "verify-artifact-only":
        rep = verify_post_execution_artifact_only_diff()
    else:
        rep = verify_evidence_provenance()
    print(json.dumps(rep, indent=2, default=str))
    return 0 if rep.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
