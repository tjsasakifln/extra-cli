"""Run evidence / provenance chain helpers (file-level, no DB).

Provides stable run_id generation, soft git metadata, content hashes, and a
canonical evidence dict for pilot/crawl terminal artifacts.

Never embeds secrets (DSN, passwords, tokens) in env snapshots.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Env keys safe to record in evidence (CONTRACTS_* operational knobs only).
_ENV_ALLOWLIST_PREFIXES = ("CONTRACTS_",)
_ENV_ALLOWLIST_EXACT = frozenset(
    {
        "CONTRACTS_FULL_DAYS",
        "CONTRACTS_WINDOW_DAYS",
        "CONTRACTS_MAX_PAGES",
        "CONTRACTS_PAGE_SIZE",
        "CONTRACTS_REQUEST_DELAY",
        "CONTRACTS_JANELA_DELAY",
        "CONTRACTS_READ_TIMEOUT",
        "CONTRACTS_MAX_RETRIES",
        "CONTRACTS_UPSERT_BATCH",
        "CONTRACTS_CHECKPOINT_DIR",
        "CONTRACTS_REQUIRE_SAME_RUN_ID",
        "CONTRACTS_INCREMENTAL_DAYS",
        "CONTRACTS_BACKFILL_YEARS",
        "CONTRACTS_BASE",
    }
)
_ENV_SECRET_MARKERS = (
    "PASSWORD",
    "PASSWD",
    "SECRET",
    "TOKEN",
    "DSN",
    "DATABASE_URL",
    "API_KEY",
    "CREDENTIAL",
    "PRIVATE",
    "AUTH",
)


def new_run_id(prefix: str = "run") -> str:
    """Generate a unique run id: ``{prefix}-{utcstamp}-{shortuuid}``."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:10]
    safe_prefix = (prefix or "run").strip() or "run"
    return f"{safe_prefix}-{stamp}-{short}"


def get_git_meta() -> dict[str, str | None]:
    """Return git_sha and git_branch; soft-fail to None on any error."""
    git_sha: str | None = None
    git_branch: str | None = None
    try:
        git_sha = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],  # noqa: S607
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            .decode("utf-8", errors="replace")
            .strip()
            or None
        )
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        git_sha = None
    try:
        git_branch = (
            subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],  # noqa: S607
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            .decode("utf-8", errors="replace")
            .strip()
            or None
        )
        if git_branch == "HEAD":
            git_branch = "detached"
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        git_branch = None
    return {"git_sha": git_sha, "git_branch": git_branch}


def sha256_bytes(data: bytes) -> str:
    """SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str | None:
    """SHA-256 hex digest of a file, or None if unreadable/missing."""
    try:
        p = Path(path)
        if not p.is_file():
            return None
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def sha256_json(obj: Any) -> str:
    """Stable SHA-256 of a JSON-serializable object (sorted keys)."""
    payload = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def host_id() -> str:
    """Short non-reversible host identifier (hashed hostname)."""
    name = socket.gethostname() or "unknown"
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]


def env_non_secret(extra: dict[str, Any] | None = None) -> dict[str, str]:
    """Snapshot of allowlisted CONTRACTS_* env vars (never DSN/password)."""
    out: dict[str, str] = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if any(m in upper for m in _ENV_SECRET_MARKERS):
            continue
        if upper in _ENV_ALLOWLIST_EXACT or any(
            upper.startswith(p) for p in _ENV_ALLOWLIST_PREFIXES
        ):
            # Double-check nested secrets in value-looking keys
            if any(m in upper for m in ("DSN", "PASSWORD", "SECRET", "TOKEN")):
                continue
            out[key] = str(value)
    if extra:
        for k, v in extra.items():
            uk = str(k).upper()
            if any(m in uk for m in _ENV_SECRET_MARKERS):
                continue
            out[str(k)] = str(v)
    return out


def build_run_evidence(**kwargs: Any) -> dict[str, Any]:
    """Build a canonical run-evidence dict.

    Required semantic fields (filled with defaults when omitted):
      run_id, git_sha, git_branch, started_at, completed_at, host_id,
      command, args, env_non_secret, checkpoint_path, checkpoint_hash,
      output_path, output_hash, log_path, log_hash, migration_head,
      counts_before, counts_after, status, errors, criteria,
      claims_allowed, claims_forbidden
    """
    git = get_git_meta()
    now = datetime.now(UTC).isoformat()

    run_id = kwargs.get("run_id") or new_run_id()
    checkpoint_path = kwargs.get("checkpoint_path")
    output_path = kwargs.get("output_path")
    log_path = kwargs.get("log_path")

    checkpoint_hash = kwargs.get("checkpoint_hash")
    if checkpoint_hash is None and checkpoint_path:
        checkpoint_hash = sha256_file(checkpoint_path)

    output_hash = kwargs.get("output_hash")
    if output_hash is None and output_path:
        output_hash = sha256_file(output_path)

    log_hash = kwargs.get("log_hash")
    if log_hash is None and log_path:
        log_hash = sha256_file(log_path)

    env_snap = kwargs.get("env_non_secret")
    if env_snap is None:
        env_snap = env_non_secret()

    evidence: dict[str, Any] = {
        "run_id": run_id,
        "git_sha": kwargs.get("git_sha", git.get("git_sha")),
        "git_branch": kwargs.get("git_branch", git.get("git_branch")),
        "started_at": kwargs.get("started_at") or now,
        "completed_at": kwargs.get("completed_at"),
        "host_id": kwargs.get("host_id") or host_id(),
        "command": kwargs.get("command"),
        "args": kwargs.get("args") or {},
        "env_non_secret": env_snap,
        "checkpoint_path": str(checkpoint_path) if checkpoint_path else None,
        "checkpoint_hash": checkpoint_hash,
        "output_path": str(output_path) if output_path else None,
        "output_hash": output_hash,
        "log_path": str(log_path) if log_path else None,
        "log_hash": log_hash,
        "migration_head": kwargs.get("migration_head"),
        "counts_before": kwargs.get("counts_before") or {},
        "counts_after": kwargs.get("counts_after") or {},
        "status": kwargs.get("status"),
        "errors": list(kwargs.get("errors") or []),
        "criteria": kwargs.get("criteria") or {},
        "claims_allowed": list(kwargs.get("claims_allowed") or []),
        "claims_forbidden": list(kwargs.get("claims_forbidden") or []),
    }
    # Preserve any extra non-colliding keys for callers
    reserved = set(evidence.keys())
    for k, v in kwargs.items():
        if k not in reserved and k not in {
            "checkpoint_hash",
            "output_hash",
            "log_hash",
        }:
            evidence[k] = v
    return evidence


def assert_checkpoint_run_id(checkpoint_dict: dict[str, Any], run_id: str) -> None:
    """Raise ValueError if checkpoint is bound to a different run_id."""
    if not isinstance(checkpoint_dict, dict):
        raise ValueError("checkpoint_dict must be a dict")
    meta = checkpoint_dict.get("meta") or {}
    existing = meta.get("run_id")
    if existing is not None and existing != run_id:
        raise ValueError(
            f"checkpoint run_id mismatch: existing={existing!r} current={run_id!r}"
        )


def verify_checkpoint_hash(path: str | Path, expected_hash: str | None) -> None:
    """Raise ValueError if file hash does not match expected (tamper detection)."""
    if not expected_hash:
        raise ValueError("expected checkpoint_hash is required for proof validation")
    actual = sha256_file(path)
    if actual is None:
        raise ValueError(f"checkpoint missing or unreadable: {path}")
    if actual != expected_hash:
        raise ValueError(
            f"checkpoint hash mismatch (tampered or stale): "
            f"expected={expected_hash[:16]}… actual={actual[:16]}…"
        )


def assert_proof_run_coherence(report: dict[str, Any]) -> None:
    """Fail-closed: path/success proof must share run_id across report/evidence/checkpoint.

    Rules:
    - report.run_id required
    - evidence.run_id must equal report.run_id
    - evidence must include checkpoint_hash and git_sha (or explicit null git soft-fail only if documented)
    - path_proof, if present with status=success, must carry same run_id
    - skipped_resume alone cannot be path_proof for a foreign checkpoint without
      windows completed in this run
    """
    if not isinstance(report, dict):
        raise ValueError("report must be a dict")
    run_id = report.get("run_id")
    if not run_id:
        raise ValueError("report missing run_id — cannot claim path/pilot proof")
    evidence = report.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError("report missing evidence block — cannot claim proof")
    if evidence.get("run_id") != run_id:
        raise ValueError(
            f"evidence.run_id {evidence.get('run_id')!r} != report.run_id {run_id!r}"
        )
    if not evidence.get("checkpoint_hash") and not evidence.get(
        "checkpoint_content_sha256"
    ):
        raise ValueError(
            "evidence.checkpoint_hash or checkpoint_content_sha256 required for proof"
        )
    # Embedded checkpoint content must match declared content hash when both present
    embedded = report.get("checkpoint")
    content_hash = evidence.get("checkpoint_content_sha256")
    if embedded is not None and content_hash:
        actual = sha256_json(embedded)
        if actual != content_hash:
            raise ValueError(
                "embedded checkpoint content hash mismatch (artifact tampered)"
            )
    if report.get("status") == "running":
        raise ValueError("status=running is not a terminal proof artifact")
    path = report.get("path_proof")
    if isinstance(path, dict) and path.get("status") == "success":
        path_rid = path.get("run_id")
        if path_rid is not None and path_rid != run_id:
            raise ValueError(
                f"path_proof.run_id {path_rid!r} != report.run_id {run_id!r}"
            )
        # Foreign resume: only skipped windows, no completed in this run → invalid path proof
        totals = report.get("totals") or {}
        windows_ok = int(totals.get("windows_ok") or 0)
        if windows_ok < 1 and int(totals.get("windows_skipped_resume") or 0) >= 1:
            raise ValueError(
                "path_proof success cannot rest only on skipped_resume "
                "(foreign or prior run windows) — need a clean window in this run_id"
            )


def bind_checkpoint_run_id(
    checkpoint_dict: dict[str, Any], run_id: str
) -> dict[str, Any]:
    """Stamp run_id on checkpoint meta; record prior run_ids for resume history.

    Allows resume of completed_windows across runs. Updates:
      meta.run_id          — current run
      meta.run_ids         — ordered unique history including current
      meta.previous_run_ids — prior run ids (excluding current)
    """
    cp = dict(checkpoint_dict)
    meta = dict(cp.get("meta") or {})
    prev = meta.get("run_id")
    run_ids = list(meta.get("run_ids") or [])
    previous = list(meta.get("previous_run_ids") or [])

    if prev and prev != run_id:
        if prev not in previous:
            previous.append(prev)
        if prev not in run_ids:
            run_ids.append(prev)

    if run_id not in run_ids:
        run_ids.append(run_id)

    meta["run_id"] = run_id
    meta["run_ids"] = run_ids
    meta["previous_run_ids"] = previous
    cp["meta"] = meta
    return cp
