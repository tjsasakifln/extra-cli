#!/usr/bin/env python3
"""Fail-closed readback for PNCP and target-fit maintenance.

The source freshness contract proves whether PNCP produced a newly closed
window.  This module proves the independent maintenance plane is still alive:
timers remain loaded/enabled/active, the long-running worker remains enabled
and active, and worker/refresh/reconcile cycles keep recording successful
progress inside their operational windows.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "SOURCE_MAINTENANCE_HEALTH/1.0"

PNCP_TIMER = "pncp-contracts.timer"
PNCP_SERVICE = "pncp-contracts.service"
SOURCE_FRESHNESS_SERVICE = "extra-confenge-source-freshness-gate.service"
TARGET_FIT_WORKER = "extra-confenge-target-fit-worker.service"
TARGET_FIT_REFRESH_TIMER = "extra-confenge-target-fit-refresh.timer"
TARGET_FIT_REFRESH_SERVICE = "extra-confenge-target-fit-refresh.service"
TARGET_FIT_RECONCILE_TIMER = "extra-confenge-target-fit-reconcile.timer"
TARGET_FIT_RECONCILE_SERVICE = "extra-confenge-target-fit-reconcile.service"
HEALTH_TIMER = "extra-health-check.timer"

TIMER_TO_SERVICE = {
    PNCP_TIMER: PNCP_SERVICE,
    TARGET_FIT_REFRESH_TIMER: TARGET_FIT_REFRESH_SERVICE,
    TARGET_FIT_RECONCILE_TIMER: TARGET_FIT_RECONCILE_SERVICE,
    HEALTH_TIMER: "extra-health-check.service",
}
READBACK_UNITS = tuple(
    dict.fromkeys(
        [
            *TIMER_TO_SERVICE,
            *TIMER_TO_SERVICE.values(),
            SOURCE_FRESHNESS_SERVICE,
            TARGET_FIT_WORKER,
        ]
    )
)

# The limits include each timer's RandomizedDelaySec and the service runtime
# budget.  They are liveness contracts, not business/freshness thresholds.
def progress_max_age_seconds() -> dict[str, int]:
    """Resolve liveness windows from the shipped operational contracts."""
    from scripts.confenge_target_fit.config import TargetFitRefreshConfig

    cfg = TargetFitRefreshConfig.from_env()
    return {
        "worker": int(cfg.reclass_slo_minutes) * 60,
        "refresh": 90 * 60,
        "reconcile": 31 * 60 * 60,
    }

# Ingestion and source-health observation must not advance any commercial or
# target-fit stage.  `pncp_contract_freshness --health` exits non-zero for every
# non-FRESH contract, so an OnSuccess on either unit turns a source incident
# into a silent downstream kill switch.  Each stage owns an independent timer.
DECOUPLED_ON_SUCCESS = (PNCP_SERVICE, SOURCE_FRESHNESS_SERVICE)

SYSTEMD_PROPERTIES = (
    "LoadState",
    "UnitFileState",
    "ActiveState",
    "SubState",
    "Result",
    "ExecMainStatus",
    "ExecMainStartTimestamp",
    "ExecMainExitTimestamp",
    "LastTriggerUSec",
    "NextElapseUSecRealtime",
    "Persistent",
    "OnSuccess",
    "Requires",
    "Requisite",
    "BindsTo",
    "PartOf",
    "Conflicts",
    "PropagatesStopTo",
    "StopWhenUnneeded",
    "FragmentPath",
)

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+"
)
_DSN_USERINFO = re.compile(r"(?i)\b(postgres(?:ql)?://)[^@\s]+@")


def sanitize_error(value: object, *, limit: int = 500) -> str:
    """Keep the factual cause while removing common secret-bearing forms."""
    text = " ".join(str(value or "").split())
    text = _DSN_USERINFO.sub(r"\1[REDACTED]@", text)
    text = _SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    return text[:limit]


def parse_timestamp(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw or raw.lower() in {"n/a", "never", "0"}:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(raw, "%a %Y-%m-%d %H:%M:%S %z")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _systemctl_show(
    unit: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, str]:
    command = [
        "systemctl",
        "show",
        unit,
        "--no-pager",
        f"--property={','.join(SYSTEMD_PROPERTIES)}",
    ]
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - readback must preserve sibling checks
        return {"LoadState": "error", "Error": sanitize_error(f"{type(exc).__name__}: {exc}")}
    payload: dict[str, str] = {}
    for line in (completed.stdout or "").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            payload[key] = value
    if completed.returncode != 0:
        payload.setdefault("LoadState", "error")
        payload["Error"] = sanitize_error(completed.stderr or f"systemctl exit {completed.returncode}")
    return payload


def collect_unit_readback(
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, dict[str, str]]:
    return {unit: _systemctl_show(unit, runner=runner) for unit in READBACK_UNITS}


def _connect(dsn: str) -> Any:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    return psycopg2.connect(dsn, cursor_factory=RealDictCursor)


def collect_progress(
    *,
    dsn: str | None = None,
    connect: Callable[[str], Any] | None = None,
) -> dict[str, dict[str, Any]]:
    effective = (dsn or os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL") or "").strip()
    if not effective:
        return {"_error": {"code": "NO_DSN", "message": "state DSN is not configured"}}
    conn = None
    try:
        conn = (connect or _connect)(effective)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT kinds.cycle_kind,
                       latest.started_at AS latest_started_at,
                       latest.finished_at AS latest_finished_at,
                       latest.status AS latest_status,
                       latest.error_message AS latest_error_message,
                       latest.cycle_id AS latest_cycle_id,
                       successful.last_success_at
                FROM (VALUES ('worker'), ('refresh'), ('reconcile')) AS kinds(cycle_kind)
                LEFT JOIN LATERAL (
                    SELECT started_at, finished_at, status, error_message, cycle_id
                    FROM confenge_target_fit_cycle_meta
                    WHERE cycle_kind = kinds.cycle_kind
                    ORDER BY started_at DESC
                    LIMIT 1
                ) AS latest ON TRUE
                LEFT JOIN LATERAL (
                    SELECT finished_at AS last_success_at
                    FROM confenge_target_fit_cycle_meta
                    WHERE cycle_kind = kinds.cycle_kind
                      AND status = 'success'
                      AND finished_at IS NOT NULL
                    ORDER BY started_at DESC
                    LIMIT 1
                ) AS successful ON TRUE
                """
            )
            rows = list(cur.fetchall() or [])
        return {
            str(row["cycle_kind"]): {
                "last_success_at": (
                    row["last_success_at"].isoformat()
                    if hasattr(row.get("last_success_at"), "isoformat")
                    else row.get("last_success_at")
                ),
                "latest_attempt": {
                    "started_at": (
                        row["latest_started_at"].isoformat()
                        if hasattr(row.get("latest_started_at"), "isoformat")
                        else row.get("latest_started_at")
                    ),
                    "finished_at": (
                        row["latest_finished_at"].isoformat()
                        if hasattr(row.get("latest_finished_at"), "isoformat")
                        else row.get("latest_finished_at")
                    ),
                    "status": row.get("latest_status"),
                    "cycle_id": row.get("latest_cycle_id"),
                    "error": sanitize_error(row.get("latest_error_message")),
                },
            }
            for row in rows
        }
    except Exception as exc:  # noqa: BLE001 - structured diagnostic, never blank exit
        return {
            "_error": {
                "code": type(exc).__name__.upper(),
                "message": sanitize_error(f"{type(exc).__name__}: {exc}"),
            }
        }
    finally:
        if conn is not None:
            conn.close()


def _git_sha(repo_root: Path) -> str | None:
    root = repo_root or Path(__file__).resolve().parents[2]
    try:
        completed = subprocess.run(  # noqa: S603 - shell is not used
            ["git", "rev-parse", "HEAD"],  # noqa: S607 - canonical local executable
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def collect_release_identity(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[2]
    env_sha = (os.getenv("EXTRA_DEPLOYED_SHA") or os.getenv("GIT_SHA") or "").strip()
    marker = root / ".deployed_sha"
    marker_sha = marker.read_text(encoding="utf-8").strip() if marker.is_file() else ""
    checkout_sha = _git_sha(root) or ""
    effective = env_sha or marker_sha or checkout_sha
    observed = {value for value in (env_sha, marker_sha, checkout_sha) if value}
    return {
        "effective_sha": effective or None,
        "env_sha": env_sha or None,
        "marker_sha": marker_sha or None,
        "checkout_sha": checkout_sha or None,
        "consistent": len(observed) <= 1,
    }


def deployed_sha(repo_root: Path | None = None) -> str | None:
    """Compatibility helper for callers that only need the effective SHA."""
    return collect_release_identity(repo_root).get("effective_sha")


def collect_snapshot(
    *,
    now: datetime | None = None,
    dsn: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    connect: Callable[[str], Any] | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    release = collect_release_identity(repo_root)
    return {
        "as_of": observed_at.isoformat().replace("+00:00", "Z"),
        "release_sha": release.get("effective_sha"),
        "release_identity": release,
        "units": collect_unit_readback(runner=runner),
        "progress": collect_progress(dsn=dsn, connect=connect),
        "progress_max_age_seconds": progress_max_age_seconds(),
    }


def _words(value: object) -> set[str]:
    return {part for part in str(value or "").split() if part}


def build_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    as_of = parse_timestamp(snapshot.get("as_of")) or datetime.now(UTC)
    units = {str(k): dict(v) for k, v in dict(snapshot.get("units") or {}).items()}
    progress = {str(k): dict(v) for k, v in dict(snapshot.get("progress") or {}).items()}
    reasons: list[str] = []

    for service in set(TIMER_TO_SERVICE.values()) | {
        SOURCE_FRESHNESS_SERVICE,
        TARGET_FIT_WORKER,
    }:
        if units.get(service, {}).get("LoadState") != "loaded":
            reasons.append(
                f"{service.upper().replace('-', '_').replace('.', '_')}_NOT_LOADED"
            )

    for timer, triggered_service in TIMER_TO_SERVICE.items():
        state = units.get(timer, {})
        prefix = timer.upper().replace("-", "_").replace(".", "_")
        if state.get("LoadState") != "loaded":
            reasons.append(f"{prefix}_NOT_LOADED")
        if state.get("UnitFileState") != "enabled":
            reasons.append(f"{prefix}_NOT_ENABLED")
        if state.get("ActiveState") != "active":
            reasons.append(f"{prefix}_NOT_ACTIVE")
        triggered = units.get(triggered_service, {})
        timer_is_running_job = (
            state.get("SubState") == "running"
            and triggered.get("ActiveState") in {"active", "activating"}
        )
        if not state.get("NextElapseUSecRealtime") and not timer_is_running_job:
            reasons.append(f"{prefix}_NO_NEXT_TRIGGER")
        if str(state.get("Persistent") or "").lower() not in {"yes", "true", "1"}:
            reasons.append(f"{prefix}_NOT_PERSISTENT")
        for relationship in (
            "Requires",
            "Requisite",
            "BindsTo",
            "PartOf",
            "Conflicts",
            "PropagatesStopTo",
        ):
            if triggered_service in _words(state.get(relationship)):
                reasons.append(f"{prefix}_LIFECYCLE_COUPLED_{relationship.upper()}")
        if str(state.get("StopWhenUnneeded") or "").lower() in {"yes", "true", "1"}:
            reasons.append(f"{prefix}_STOP_WHEN_UNNEEDED")

    worker = units.get(TARGET_FIT_WORKER, {})
    if worker.get("LoadState") != "loaded":
        reasons.append("TARGET_FIT_WORKER_NOT_LOADED")
    if worker.get("UnitFileState") != "enabled":
        reasons.append("TARGET_FIT_WORKER_NOT_ENABLED")
    if worker.get("ActiveState") != "active":
        reasons.append("TARGET_FIT_WORKER_NOT_ACTIVE")

    for source in DECOUPLED_ON_SUCCESS:
        if _words(units.get(source, {}).get("OnSuccess")):
            reasons.append(f"{source.upper().replace('-', '_').replace('.', '_')}_ONSUCCESS_COUPLED")

    progress_error = progress.get("_error")
    if progress_error:
        reasons.append(f"PROGRESS_READ_FAILED_{progress_error.get('code') or 'UNKNOWN'}")
    progress_readback: dict[str, Any] = {}
    resolved_limits = {
        str(key): int(value)
        for key, value in dict(
            snapshot.get("progress_max_age_seconds") or progress_max_age_seconds()
        ).items()
    }
    for cycle_kind, max_age in resolved_limits.items():
        item = progress.get(cycle_kind, {})
        finished = parse_timestamp(item.get("last_success_at"))
        age = (as_of - finished).total_seconds() if finished else None
        latest_attempt = dict(item.get("latest_attempt") or {})
        progress_readback[cycle_kind] = {
            **item,
            "age_seconds": age,
            "max_age_seconds": max_age,
        }
        if finished is None:
            reasons.append(f"TARGET_FIT_{cycle_kind.upper()}_NO_PROGRESS")
        elif age is not None and (age < -300 or age > max_age):
            reasons.append(f"TARGET_FIT_{cycle_kind.upper()}_PROGRESS_STALE")
        latest_status = str(latest_attempt.get("status") or "").lower()
        if latest_status and latest_status not in {"success", "running"}:
            reasons.append(
                f"TARGET_FIT_{cycle_kind.upper()}_LAST_CYCLE_{latest_status.upper()}"
            )

    release_identity = dict(snapshot.get("release_identity") or {})
    release_sha = str(
        release_identity.get("effective_sha") or snapshot.get("release_sha") or ""
    ).strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", release_sha):
        reasons.append("RELEASE_SHA_UNPROVEN")
    observed_shas = {
        str(release_identity.get(field) or "").strip()
        for field in ("env_sha", "marker_sha", "checkout_sha")
        if release_identity.get(field)
    }
    if len(observed_shas) > 1 or release_identity.get("consistent") is False:
        reasons.append("RELEASE_SHA_DRIFT")

    deduped_reasons = list(dict.fromkeys(reasons))
    status = "HEALTHY" if not deduped_reasons else "UNHEALTHY"
    return {
        "contract_version": CONTRACT_VERSION,
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "status": status,
        "health_exit": 0 if status == "HEALTHY" else 2,
        "reason_codes": deduped_reasons,
        "release_sha": release_sha or None,
        "release_identity": release_identity or {"effective_sha": release_sha or None},
        "units": units,
        "progress": progress_readback,
        "progress_error": progress_error,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--health", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.from_snapshot:
        snapshot = json.loads(args.from_snapshot.read_text(encoding="utf-8"))
    else:
        snapshot = collect_snapshot()
    contract = build_contract(snapshot)
    rendered = json.dumps(contract, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return int(contract["health_exit"]) if args.health else 0


if __name__ == "__main__":
    raise SystemExit(main())
