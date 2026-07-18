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


# DoD §29 — fields every audited execution must carry (presence; may be null
# only when explicitly justified in ``limitations``).
EXECUTION_AUDIT_REQUIRED_FIELDS: tuple[str, ...] = (
    "run_id",
    "code_version",  # git_sha alias
    "schema_version",
    "spreadsheet_hash",
    "source",
    "capability",
    "parameters",
    "period",
)

# DoD §29 continuation — operational outcome fields on every audited run.
EXECUTION_OUTCOME_REQUIRED_FIELDS: tuple[str, ...] = (
    "started_at",
    "completed_at",
    "status",
    "counts_before",
    "counts_after",
    "errors",
    "checkpoint_path",
    "provenance",
)


def resolve_spreadsheet_hash(path: str | Path | None = None) -> str | None:
    """Hash of the canonical Extra targets spreadsheet when present."""
    if path is not None:
        return sha256_file(path)
    root = Path(__file__).resolve().parents[2]
    candidates = [
        root / "Extra - alvos de licitação. R-0.xlsx",
        root / "data" / "Extra - alvos de licitação. R-0.xlsx",
    ]
    for c in candidates:
        h = sha256_file(c)
        if h:
            return h
    return None


def resolve_schema_version(migration_head: str | None = None) -> str:
    """Best-effort schema version from migration head or migrations dir."""
    if migration_head:
        return str(migration_head)
    root = Path(__file__).resolve().parents[2]
    mig = root / "db" / "migrations"
    if not mig.is_dir():
        return "unknown"
    files = sorted(p.name for p in mig.glob("*.sql"))
    if not files:
        return "unknown"
    return files[-1]


def build_execution_audit_record(
    *,
    source: str,
    capability: str,
    parameters: dict[str, Any] | None = None,
    period: dict[str, Any] | str | None = None,
    run_id: str | None = None,
    schema_version: str | None = None,
    spreadsheet_hash: str | None = None,
    code_version: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build an execution record satisfying DoD §29 audit field requirements.

    Always includes: run_id, code_version (git SHA), schema_version,
    spreadsheet_hash, source, capability, parameters, period.
    """
    git = get_git_meta()
    evidence = build_run_evidence(
        run_id=run_id,
        git_sha=code_version or kwargs.get("git_sha") or git.get("git_sha"),
        **{k: v for k, v in kwargs.items() if k != "git_sha"},
    )
    record = dict(evidence)
    record["code_version"] = (
        code_version or evidence.get("git_sha") or git.get("git_sha") or "unknown"
    )
    record["schema_version"] = schema_version or resolve_schema_version(
        kwargs.get("migration_head") if isinstance(kwargs.get("migration_head"), str) else None
    )
    record["spreadsheet_hash"] = spreadsheet_hash or resolve_spreadsheet_hash()
    record["source"] = source
    record["capability"] = capability
    record["parameters"] = parameters if parameters is not None else (evidence.get("args") or {})
    record["period"] = period if period is not None else {"label": "unspecified"}
    # Outcome / audit trail defaults
    if not record.get("started_at"):
        record["started_at"] = datetime.now(UTC).isoformat()
    if not record.get("completed_at"):
        record["completed_at"] = datetime.now(UTC).isoformat()
    if not record.get("status") or record.get("status") is None:
        record["status"] = kwargs.get("status") or "unknown"
    record.setdefault("counts_before", kwargs.get("counts_before") or {})
    record.setdefault("counts_after", kwargs.get("counts_after") or {})
    record.setdefault("errors", list(kwargs.get("errors") or []))
    record.setdefault(
        "checkpoint_path",
        kwargs.get("checkpoint_path") or record.get("checkpoint_path"),
    )
    record["provenance"] = kwargs.get("provenance") or {
        "run_id": record["run_id"],
        "code_version": record["code_version"],
        "schema_version": record["schema_version"],
        "source": source,
        "capability": capability,
        "spreadsheet_hash": record.get("spreadsheet_hash"),
    }
    # Self-check required fields
    missing = [f for f in EXECUTION_AUDIT_REQUIRED_FIELDS if f not in record]
    if missing:
        raise ValueError(f"execution audit record missing fields: {missing}")
    return record


def attach_report_source_runs(
    report: dict[str, Any],
    source_runs: list[str],
) -> dict[str, Any]:
    """Stamp a report artifact with originating run_ids (DoD: report refs runs)."""
    out = dict(report)
    out["source_run_ids"] = list(source_runs)
    if not source_runs:
        raise ValueError("report must reference at least one source run_id")
    return out


def validate_execution_audit_record(
    record: dict[str, Any],
    *,
    require_outcome: bool = False,
) -> dict[str, Any]:
    """Return ok/issues for a record against DoD §29 required fields."""
    issues: list[str] = []
    fields = list(EXECUTION_AUDIT_REQUIRED_FIELDS)
    if require_outcome:
        fields.extend(EXECUTION_OUTCOME_REQUIRED_FIELDS)
    for field in fields:
        if field not in record:
            issues.append(f"missing:{field}")
        elif record[field] in (None, "", {}, []) and field not in {
            "spreadsheet_hash",
            "checkpoint_path",
            "errors",
            "counts_before",
            "counts_after",
        }:
            if field == "period" and record[field] in ({}, None):
                issues.append(f"empty:{field}")
            elif field not in {"spreadsheet_hash", "checkpoint_path"}:
                issues.append(f"empty:{field}")
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "required_fields": fields,
    }


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


def assert_proof_run_coherence(
    report: dict[str, Any],
    *,
    verify_live_checkpoint_file: bool = True,
) -> None:
    """Fail-closed: path/success proof must share run_id and checkpoint window set.

    Rules:
    - report.run_id required; evidence.run_id must match
    - checkpoint_hash and/or checkpoint_content_sha256 required
    - embedded checkpoint content hash must match when both present
    - path_proof success requires:
        * same run_id (when set)
        * path_proof.window ∈ checkpoint.completed_windows
        * every windows[].status==completed key ⊆ checkpoint.completed_windows
        * not only skipped_resume
    - when checkpoint.meta.run_id == report.run_id and verify_live_checkpoint_file,
      re-hash live checkpoint file against evidence.checkpoint_hash
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

    ckpt_completed: set[str] = set()
    if isinstance(embedded, dict):
        ckpt_completed = {str(x) for x in (embedded.get("completed_windows") or [])}

    report_completed = {
        str(w.get("window_key"))
        for w in (report.get("windows") or [])
        if isinstance(w, dict) and w.get("status") == "completed" and w.get("window_key")
    }
    if report_completed and not report_completed.issubset(ckpt_completed):
        missing = sorted(report_completed - ckpt_completed)
        raise ValueError(
            "windows marked completed not present in checkpoint.completed_windows: "
            + ", ".join(missing)
        )

    path = report.get("path_proof")
    if isinstance(path, dict) and path.get("status") == "success":
        path_rid = path.get("run_id")
        if path_rid is not None and path_rid != run_id:
            raise ValueError(
                f"path_proof.run_id {path_rid!r} != report.run_id {run_id!r}"
            )
        totals = report.get("totals") or {}
        windows_ok = int(totals.get("windows_ok") or 0)
        if windows_ok < 1 and int(totals.get("windows_skipped_resume") or 0) >= 1:
            raise ValueError(
                "path_proof success cannot rest only on skipped_resume "
                "(foreign or prior run windows) — need a clean window in this run_id"
            )
        window_key = path.get("window")
        if window_key:
            if str(window_key) not in ckpt_completed:
                raise ValueError(
                    f"path_proof.window {window_key!r} not in "
                    f"checkpoint.completed_windows={sorted(ckpt_completed)}"
                )

    # Live file re-hash when this run owns the checkpoint file
    if verify_live_checkpoint_file and isinstance(embedded, dict):
        meta = embedded.get("meta") or {}
        if meta.get("run_id") == run_id and evidence.get("checkpoint_hash"):
            cp_path = evidence.get("checkpoint_path") or report.get("checkpoint_path")
            if cp_path:
                verify_checkpoint_hash(cp_path, evidence["checkpoint_hash"])


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
