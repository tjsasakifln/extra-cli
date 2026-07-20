"""Run execution ledger — material DoD advance for §29 rastreabilidade (cycle-1).

Before: executions could finish without a durable error list or report→run link.
After: every recorded run has run_id, status, errors[], and optional report paths
referencing the originating run_id. Manual mutations append an audit entry.

Does NOT claim full §29 complete — PARTIAL with automated tests + reproducible API.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_LEDGER_DIR = Path("output") / "run-execution-ledger"


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_path(root: Path | None = None, *, name: str = "ledger.jsonl") -> Path:
    base = (root or Path.cwd()) / DEFAULT_LEDGER_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base / name


def new_run_id(prefix: str = "run") -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{ts}-{uuid.uuid4().hex[:8]}"


def record_execution(
    *,
    command: str | list[str],
    status: str,
    errors: list[str] | None = None,
    exit_code: int | None = None,
    report_paths: list[str] | None = None,
    run_id: str | None = None,
    meta: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Append one execution record. Always stores errors list (possibly empty)."""
    rid = run_id or new_run_id()
    cmd_list = command if isinstance(command, list) else [str(command)]
    record = {
        "schema_version": "1.0",
        "run_id": rid,
        "timestamp_utc": _utc_now(),
        "command": cmd_list,
        "status": status,  # ok | failed | partial | cancelled
        "exit_code": exit_code,
        "errors": list(errors or []),
        "report_paths": list(report_paths or []),
        "meta": meta or {},
    }
    # Link: each report path is associated to this run_id
    record["report_run_links"] = [
        {"report": p, "run_id": rid} for p in (report_paths or [])
    ]
    path = ledger_path(root)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def record_manual_mutation(
    *,
    actor: str,
    path: str,
    reason: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Audit entry for manual file mutations (rastreabilidade)."""
    entry = {
        "schema_version": "1.0",
        "kind": "manual_mutation",
        "mutation_id": f"mut-{uuid.uuid4().hex[:12]}",
        "timestamp_utc": _utc_now(),
        "actor": actor,
        "path": path,
        "reason": reason,
        "errors": [],
    }
    path_l = ledger_path(root, name="manual-mutations.jsonl")
    with path_l.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load_ledger(root: Path | None = None) -> list[dict[str, Any]]:
    path = ledger_path(root)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"errors": ["corrupt_ledger_line"], "raw": line[:200]})
    return rows


def reports_for_run(run_id: str, root: Path | None = None) -> list[str]:
    out: list[str] = []
    for row in load_ledger(root):
        if row.get("run_id") == run_id:
            out.extend(row.get("report_paths") or [])
    return out


def runs_with_errors(root: Path | None = None) -> list[dict[str, Any]]:
    return [r for r in load_ledger(root) if r.get("errors")]


def ledger_checksum(root: Path | None = None) -> str:
    path = ledger_path(root)
    if not path.is_file():
        return hashlib.sha256(b"").hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_invariants(root: Path | None = None) -> dict[str, Any]:
    """Deterministic checks used by tests / CTO verifier test_ids."""
    rows = load_ledger(root)
    missing_errors_field = [r.get("run_id") for r in rows if "errors" not in r]
    unlinked = []
    for r in rows:
        for p in r.get("report_paths") or []:
            links = r.get("report_run_links") or []
            if not any(L.get("report") == p and L.get("run_id") == r.get("run_id") for L in links):
                unlinked.append({"run_id": r.get("run_id"), "report": p})
    ok = not missing_errors_field and not unlinked
    return {
        "ok": ok,
        "n_runs": len(rows),
        "n_with_errors": len(runs_with_errors(root)),
        "missing_errors_field": missing_errors_field,
        "unlinked_reports": unlinked,
        "checksum": ledger_checksum(root),
    }


def record_execution_safe(
    *,
    command: str | list[str],
    status: str,
    errors: list[str] | None = None,
    exit_code: int | None = None,
    report_paths: list[str] | None = None,
    run_id: str | None = None,
    meta: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any] | None:
    """Best-effort ledger write — never raises into operational entrypoints."""
    try:
        return record_execution(
            command=command,
            status=status,
            errors=errors,
            exit_code=exit_code,
            report_paths=report_paths,
            run_id=run_id,
            meta=meta,
            root=root,
        )
    except Exception as exc:  # noqa: BLE001 — ledger must not break ops
        return {"ok": False, "error": str(exc), "errors": [str(exc)]}
