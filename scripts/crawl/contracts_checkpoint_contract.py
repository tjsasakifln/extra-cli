"""Safe checkpoint contract for PNCP contracts incremental jobs.

Distinguishes:

* ``logical_job_id`` — stable identity of the recurring job
* ``attempt_run_id`` — per-execution id (also mirrored as ``meta.run_id`` for
  backward compatibility with evidence tooling)

Rules (FAIL_CLOSED):

1. Same logical_job_id + compatible params → legitimate attempt rebind
2. Different campaign_id → refuse silent reuse (migrate/archive required)
3. Completed windows preserved across attempts
4. Never delete checkpoint without backup
5. Corrupt checkpoint → archive + fresh start only with ``--force-reset``

CLI::

    python -m scripts.crawl.contracts_checkpoint_contract diagnose \\
        --checkpoint-dir data/contracts_checkpoints/incremental
    python -m scripts.crawl.contracts_checkpoint_contract migrate \\
        --checkpoint-dir data/contracts_checkpoints/incremental \\
        --logical-job-id pncp-contracts-incremental
    python -m scripts.crawl.contracts_checkpoint_contract repair \\
        --checkpoint-dir data/contracts_checkpoints/incremental \\
        --rebind-attempt
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CHECKPOINT_VERSION = 2
LOGICAL_JOB_INCREMENTAL = "pncp-contracts-incremental"
SOURCE_PNCP_CONTRACTS = "pncp_contracts"
CAPABILITY_HISTORICAL = "historical_contracts"
DEFAULT_MODE = "full"


class CheckpointContractError(ValueError):
    """Incompatible or corrupt checkpoint."""


@dataclass
class CheckpointIdentity:
    logical_job_id: str
    attempt_run_id: str | None
    campaign_id: str | None
    checkpoint_version: int
    source: str
    capability: str
    incremental_days: int | None
    code_sha: str | None = None
    schema_version: str | None = None


@dataclass
class DiagnoseResult:
    path: str
    exists: bool
    ok: bool
    identity: CheckpointIdentity | None = None
    completed_windows: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    raw_meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "exists": self.exists,
            "ok": self.ok,
            "identity": None
            if self.identity is None
            else {
                "logical_job_id": self.identity.logical_job_id,
                "attempt_run_id": self.identity.attempt_run_id,
                "campaign_id": self.identity.campaign_id,
                "checkpoint_version": self.identity.checkpoint_version,
                "source": self.identity.source,
                "capability": self.identity.capability,
                "incremental_days": self.identity.incremental_days,
                "code_sha": self.identity.code_sha,
                "schema_version": self.identity.schema_version,
            },
            "completed_windows": self.completed_windows,
            "issues": self.issues,
            "raw_meta": self.raw_meta,
        }


def checkpoint_file(checkpoint_dir: str | Path, mode: str = DEFAULT_MODE) -> Path:
    return Path(checkpoint_dir) / f"contracts_{mode}.json"


def _now_z() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def archive_checkpoint(path: Path, *, reason: str) -> Path | None:
    """Copy checkpoint to sibling backup; never delete source here."""
    if not path.is_file():
        return None
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    bak = path.with_suffix(path.suffix + f".bak.{ts}")
    shutil.copy2(path, bak)
    sidecar = bak.with_suffix(bak.suffix + ".reason.txt")
    sidecar.write_text(f"{_now_z()} reason={reason}\n", encoding="utf-8")
    logger.info("archived checkpoint %s -> %s (%s)", path, bak, reason)
    return bak


def load_raw(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointContractError(f"corrupt checkpoint {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CheckpointContractError(f"checkpoint root must be object: {path}")
    return data


def extract_identity(data: dict[str, Any]) -> CheckpointIdentity:
    meta = dict(data.get("meta") or {})
    attempt = meta.get("attempt_run_id") or meta.get("run_id")
    logical = meta.get("logical_job_id") or ""
    # Legacy: infer incremental job when campaign_role says so
    if not logical:
        role = str(meta.get("campaign_role") or "")
        if role == "historical_contracts_incremental" or meta.get("incremental_days"):
            logical = LOGICAL_JOB_INCREMENTAL
        elif attempt or data.get("completed_windows"):
            # Unknown legacy — leave empty so migrate must set explicitly
            logical = ""
    days = meta.get("incremental_days")
    try:
        days_i = int(days) if days is not None else None
    except (TypeError, ValueError):
        days_i = None
    try:
        ver = int(meta.get("checkpoint_version") or 1)
    except (TypeError, ValueError):
        ver = 1
    return CheckpointIdentity(
        logical_job_id=str(logical or ""),
        attempt_run_id=str(attempt) if attempt else None,
        campaign_id=(
            str(meta["campaign_id"])
            if meta.get("campaign_id") is not None
            else (str(meta["campaign"]) if meta.get("campaign") is not None else None)
        ),
        checkpoint_version=ver,
        source=str(data.get("source") or meta.get("source") or SOURCE_PNCP_CONTRACTS),
        capability=str(meta.get("capability") or CAPABILITY_HISTORICAL),
        incremental_days=days_i,
        code_sha=meta.get("code_sha"),
        schema_version=meta.get("schema_version"),
    )


def diagnose(checkpoint_dir: str | Path, *, mode: str = DEFAULT_MODE) -> DiagnoseResult:
    path = checkpoint_file(checkpoint_dir, mode)
    if not path.is_file():
        return DiagnoseResult(path=str(path), exists=False, ok=True, issues=["missing_ok_fresh"])
    try:
        data = load_raw(path)
    except CheckpointContractError as exc:
        return DiagnoseResult(
            path=str(path),
            exists=True,
            ok=False,
            issues=[f"corrupt:{exc}"],
        )
    ident = extract_identity(data)
    issues: list[str] = []
    if not ident.logical_job_id:
        issues.append("missing_logical_job_id_legacy")
    if ident.checkpoint_version < CHECKPOINT_VERSION:
        issues.append(f"schema_old:v{ident.checkpoint_version}")
    windows = [str(w) for w in (data.get("completed_windows") or [])]
    ok = "corrupt" not in " ".join(issues)
    return DiagnoseResult(
        path=str(path),
        exists=True,
        ok=ok and "corrupt" not in issues,
        identity=ident,
        completed_windows=windows,
        issues=issues,
        raw_meta=dict(data.get("meta") or {}),
    )


def migrate_meta(
    data: dict[str, Any],
    *,
    logical_job_id: str,
    campaign_id: str | None = None,
    incremental_days: int | None = None,
    code_sha: str | None = None,
    schema_version: str | None = None,
    force_campaign: bool = False,
) -> dict[str, Any]:
    """Return updated checkpoint dict with v2 identity fields (in-memory)."""
    out = dict(data)
    meta = dict(out.get("meta") or {})
    existing = extract_identity(out)

    if (
        existing.campaign_id
        and campaign_id
        and existing.campaign_id != campaign_id
        and not force_campaign
    ):
        raise CheckpointContractError(
            f"campaign mismatch existing={existing.campaign_id!r} "
            f"requested={campaign_id!r}; use force_campaign after archive"
        )

    if (
        existing.logical_job_id
        and existing.logical_job_id != logical_job_id
        and not force_campaign
    ):
        raise CheckpointContractError(
            f"logical_job_id mismatch existing={existing.logical_job_id!r} "
            f"requested={logical_job_id!r}"
        )

    if incremental_days is not None and existing.incremental_days is not None:
        if int(existing.incremental_days) != int(incremental_days) and not force_campaign:
            raise CheckpointContractError(
                f"incremental_days mismatch existing={existing.incremental_days} "
                f"requested={incremental_days}"
            )

    meta["logical_job_id"] = logical_job_id
    meta["checkpoint_version"] = CHECKPOINT_VERSION
    meta["source"] = out.get("source") or SOURCE_PNCP_CONTRACTS
    meta["capability"] = meta.get("capability") or CAPABILITY_HISTORICAL
    if campaign_id is not None:
        meta["campaign_id"] = campaign_id
    if incremental_days is not None:
        meta["incremental_days"] = int(incremental_days)
    if code_sha:
        meta["code_sha"] = code_sha
    if schema_version:
        meta["schema_version"] = schema_version
    # Mirror attempt fields
    if meta.get("run_id") and not meta.get("attempt_run_id"):
        meta["attempt_run_id"] = meta["run_id"]
    meta["migrated_at"] = _now_z()
    meta["campaign_role"] = meta.get("campaign_role") or "historical_contracts_incremental"
    out["meta"] = meta
    out["updated_at"] = _now_z()
    return out


def rebind_attempt(
    data: dict[str, Any],
    *,
    attempt_run_id: str,
    logical_job_id: str,
    campaign_id: str | None = None,
    incremental_days: int | None = None,
) -> dict[str, Any]:
    """Rebind attempt_run_id for same logical job; preserve completed_windows."""
    migrated = migrate_meta(
        data,
        logical_job_id=logical_job_id,
        campaign_id=campaign_id,
        incremental_days=incremental_days,
    )
    meta = dict(migrated.get("meta") or {})
    prev = meta.get("attempt_run_id") or meta.get("run_id")
    run_ids = list(meta.get("run_ids") or [])
    previous = list(meta.get("previous_run_ids") or [])
    if prev and prev != attempt_run_id:
        if prev not in previous:
            previous.append(prev)
        if prev not in run_ids:
            run_ids.append(prev)
    if attempt_run_id not in run_ids:
        run_ids.append(attempt_run_id)
    meta["attempt_run_id"] = attempt_run_id
    meta["run_id"] = attempt_run_id  # backward compat for evidence
    meta["run_ids"] = run_ids
    meta["previous_run_ids"] = previous
    meta["attempt_rebind"] = True
    meta["foreign_resume"] = False  # same logical job is not foreign
    meta["last_attempt_at"] = _now_z()
    migrated["meta"] = meta
    migrated["updated_at"] = _now_z()
    return migrated


def can_legitimately_rebind(
    data: dict[str, Any],
    *,
    logical_job_id: str,
    campaign_id: str | None,
    incremental_days: int | None,
) -> tuple[bool, str]:
    """Whether a new attempt_run_id may rebind without env override."""
    if not data:
        return True, "empty_fresh"
    ident = extract_identity(data)
    if not ident.logical_job_id:
        # Legacy without logical id: allow rebind only when role/days match incremental
        if incremental_days is not None and ident.incremental_days is not None:
            if int(ident.incremental_days) != int(incremental_days):
                return False, "legacy_days_mismatch"
        # Treat as migratable same job if we are claiming incremental
        if logical_job_id == LOGICAL_JOB_INCREMENTAL:
            return True, "legacy_migrate_to_logical"
        return False, "legacy_unknown_job"
    if ident.logical_job_id != logical_job_id:
        return False, f"logical_job_mismatch:{ident.logical_job_id}"
    if (
        campaign_id
        and ident.campaign_id
        and ident.campaign_id != campaign_id
    ):
        return False, f"campaign_mismatch:{ident.campaign_id}"
    if (
        incremental_days is not None
        and ident.incremental_days is not None
        and int(ident.incremental_days) != int(incremental_days)
    ):
        return False, f"days_mismatch:{ident.incremental_days}"
    return True, "same_logical_job"


def apply_attempt_to_checkpoint_dict(
    checkpoint_dict: dict[str, Any],
    attempt_run_id: str,
    *,
    logical_job_id: str = LOGICAL_JOB_INCREMENTAL,
    campaign_id: str | None = None,
    incremental_days: int | None = None,
    allow_foreign: bool = False,
) -> dict[str, Any]:
    """Core binder used by pilot / incremental paths.

    Same logical job → rebind attempt (no ValueError).
    Different job/campaign → ValueError unless allow_foreign.
    """
    if not checkpoint_dict:
        checkpoint_dict = {
            "source": SOURCE_PNCP_CONTRACTS,
            "mode": DEFAULT_MODE,
            "completed_windows": [],
            "meta": {},
        }
    ok, reason = can_legitimately_rebind(
        checkpoint_dict,
        logical_job_id=logical_job_id,
        campaign_id=campaign_id,
        incremental_days=incremental_days,
    )
    if ok:
        return rebind_attempt(
            checkpoint_dict,
            attempt_run_id=attempt_run_id,
            logical_job_id=logical_job_id,
            campaign_id=campaign_id,
            incremental_days=incremental_days,
        )
    if allow_foreign:
        # Explicit foreign: archive semantics left to caller; rebind with force
        forced = migrate_meta(
            checkpoint_dict,
            logical_job_id=logical_job_id,
            campaign_id=campaign_id,
            incremental_days=incremental_days,
            force_campaign=True,
        )
        rebound = rebind_attempt(
            forced,
            attempt_run_id=attempt_run_id,
            logical_job_id=logical_job_id,
            campaign_id=campaign_id,
            incremental_days=incremental_days,
        )
        meta = dict(rebound.get("meta") or {})
        meta["foreign_resume"] = True
        meta["foreign_reason"] = reason
        rebound["meta"] = meta
        return rebound
    existing = (checkpoint_dict.get("meta") or {}).get("run_id")
    raise CheckpointContractError(
        f"checkpoint rebind refused reason={reason} "
        f"existing_run_id={existing!r} attempt={attempt_run_id!r}"
    )


def save_raw(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def cmd_diagnose(args: argparse.Namespace) -> int:
    result = diagnose(args.checkpoint_dir, mode=args.mode)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.ok else 1


def cmd_migrate(args: argparse.Namespace) -> int:
    path = checkpoint_file(args.checkpoint_dir, args.mode)
    if not path.is_file():
        data: dict[str, Any] = {
            "source": SOURCE_PNCP_CONTRACTS,
            "mode": args.mode,
            "completed_windows": [],
            "meta": {},
        }
    else:
        archive_checkpoint(path, reason="migrate")
        data = load_raw(path)
    try:
        out = migrate_meta(
            data,
            logical_job_id=args.logical_job_id,
            campaign_id=args.campaign_id,
            incremental_days=args.days,
            force_campaign=bool(args.force),
        )
    except CheckpointContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    save_raw(path, out)
    print(json.dumps({"status": "migrated", "path": str(path), "meta": out.get("meta")}, indent=2))
    return 0


def cmd_repair(args: argparse.Namespace) -> int:
    path = checkpoint_file(args.checkpoint_dir, args.mode)
    if not path.is_file():
        print(json.dumps({"status": "missing", "path": str(path)}))
        return 0
    archive_checkpoint(path, reason="repair")
    try:
        data = load_raw(path)
    except CheckpointContractError as exc:
        if args.force_reset:
            empty = {
                "source": SOURCE_PNCP_CONTRACTS,
                "mode": args.mode,
                "completed_windows": [],
                "meta": {
                    "logical_job_id": args.logical_job_id,
                    "checkpoint_version": CHECKPOINT_VERSION,
                    "capability": CAPABILITY_HISTORICAL,
                    "reset_reason": f"corrupt:{exc}",
                    "reset_at": _now_z(),
                },
                "updated_at": _now_z(),
            }
            save_raw(path, empty)
            print(json.dumps({"status": "reset_after_corrupt", "path": str(path)}, indent=2))
            return 0
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.clear_windows:
        data["completed_windows"] = []
        data["total_windows_completed"] = 0
        data["current_window_start"] = None
        data["last_error"] = None

    if args.rebind_attempt:
        from scripts.crawl.run_evidence import new_run_id

        attempt = args.attempt_run_id or new_run_id(prefix="contracts-90d")
        try:
            data = apply_attempt_to_checkpoint_dict(
                data,
                attempt,
                logical_job_id=args.logical_job_id,
                campaign_id=args.campaign_id,
                incremental_days=args.days,
                allow_foreign=bool(args.force),
            )
        except CheckpointContractError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    else:
        data = migrate_meta(
            data,
            logical_job_id=args.logical_job_id,
            campaign_id=args.campaign_id,
            incremental_days=args.days,
            force_campaign=bool(args.force),
        )

    save_raw(path, data)
    print(json.dumps({"status": "repaired", "path": str(path), "meta": data.get("meta")}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diagnose", help="Diagnose checkpoint contract")
    d.add_argument("--checkpoint-dir", required=True)
    d.add_argument("--mode", default=DEFAULT_MODE)
    d.set_defaults(func=cmd_diagnose)

    m = sub.add_parser("migrate", help="Migrate checkpoint to v2 identity")
    m.add_argument("--checkpoint-dir", required=True)
    m.add_argument("--mode", default=DEFAULT_MODE)
    m.add_argument("--logical-job-id", default=LOGICAL_JOB_INCREMENTAL)
    m.add_argument("--campaign-id", default=None)
    m.add_argument("--days", type=int, default=None)
    m.add_argument("--force", action="store_true")
    m.set_defaults(func=cmd_migrate)

    r = sub.add_parser("repair", help="Archive + repair / rebind attempt")
    r.add_argument("--checkpoint-dir", required=True)
    r.add_argument("--mode", default=DEFAULT_MODE)
    r.add_argument("--logical-job-id", default=LOGICAL_JOB_INCREMENTAL)
    r.add_argument("--campaign-id", default=None)
    r.add_argument("--days", type=int, default=None)
    r.add_argument("--rebind-attempt", action="store_true")
    r.add_argument("--attempt-run-id", default=None)
    r.add_argument("--clear-windows", action="store_true")
    r.add_argument("--force", action="store_true")
    r.add_argument("--force-reset", action="store_true")
    r.set_defaults(func=cmd_repair)
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
