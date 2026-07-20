"""Run execution ledger — material DoD advance for §29 rastreabilidade (cycle-1).

Before: executions could finish without a durable error list or report→run link.
After: every recorded run has run_id, status, errors[], and optional report paths
referencing the originating run_id. Manual mutations/overrides append audit entries
with motivo/data/autor (fail-closed).

Operator CLI:
  python3 -m scripts.ops.run_execution_ledger record --command X --status ok
  python3 -m scripts.ops.run_execution_ledger verify
  python3 -m scripts.ops.run_execution_ledger override --target T --action A \\
      --motivo M --autor U
  python3 -m scripts.ops.run_execution_ledger mutation --actor U --path P --reason R

Does NOT claim full §29 complete — PARTIAL with automated tests + reproducible API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_LEDGER_DIR = Path("output") / "run-execution-ledger"
DEFAULT_OVERRIDE_NAME = "manual-overrides.jsonl"


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_path(root: Path | None = None, *, name: str = "ledger.jsonl") -> Path:
    base = (root or Path.cwd()) / DEFAULT_LEDGER_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base / name


def override_ledger_path(root: Path | None = None) -> Path:
    return ledger_path(root, name=DEFAULT_OVERRIDE_NAME)


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
    """Append one execution record. Always stores errors list (possibly empty).

    Invariant (DoD §29): key ``errors`` is ALWAYS present as a list.
    When report_paths is non-empty, each path is linked via report_run_links
    with the same run_id.
    """
    rid = run_id or new_run_id()
    cmd_list = command if isinstance(command, list) else [str(command)]
    # Normalize: never store None for errors — always a list (empty on success).
    err_list: list[str] = list(errors) if errors is not None else []
    paths = list(report_paths or [])
    record: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": rid,
        "timestamp_utc": _utc_now(),
        "command": cmd_list,
        "status": status,  # ok | failed | partial | cancelled
        "exit_code": exit_code,
        "errors": err_list,
        "report_paths": paths,
        "meta": meta or {},
    }
    # Link: each report path is associated to this run_id
    record["report_run_links"] = [{"report": p, "run_id": rid} for p in paths]
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
    """Audit entry for manual file mutations (rastreabilidade). Fail-closed."""
    if not actor or not str(actor).strip():
        raise ValueError("manual_mutation requires actor")
    if not path or not str(path).strip():
        raise ValueError("manual_mutation requires path")
    if not reason or not str(reason).strip():
        raise ValueError("manual_mutation requires reason")
    entry = {
        "schema_version": "1.0",
        "kind": "manual_mutation",
        "mutation_id": f"mut-{uuid.uuid4().hex[:12]}",
        "timestamp_utc": _utc_now(),
        "actor": str(actor).strip(),
        "path": str(path).strip(),
        "reason": str(reason).strip(),
        "errors": [],
    }
    path_l = ledger_path(root, name="manual-mutations.jsonl")
    with path_l.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def record_manual_override(
    *,
    target: str,
    action: str,
    motivo: str,
    autor: str,
    before: Any = None,
    after: Any = None,
    run_id: str | None = None,
    data: str | None = None,
    root: Path | None = None,
    ledger_file: Path | None = None,
) -> dict[str, Any]:
    """Record a manual override via manual_override_ledger (motivo/data/autor required).

    Fail-closed: missing motivo/data/autor raises ValueError (never silent).
    """
    from scripts.lib.manual_override_ledger import append_override, new_override

    ov = new_override(
        target=target,
        action=action,
        motivo=motivo,
        autor=autor,
        before=before,
        after=after,
        run_id=run_id,
        data=data,
    )
    out = ledger_file or override_ledger_path(root)
    append_override(out, ov)
    row = {
        "schema_version": "1.0",
        "kind": "manual_override",
        "target": ov.target,
        "action": ov.action,
        "motivo": ov.motivo,
        "autor": ov.autor,
        "data": ov.data,
        "before": ov.before,
        "after": ov.after,
        "run_id": ov.run_id,
        "ledger_path": str(out),
        "errors": [],
    }
    return row


def record_override_safe(
    *,
    target: str,
    action: str,
    motivo: str,
    autor: str,
    before: Any = None,
    after: Any = None,
    run_id: str | None = None,
    data: str | None = None,
    root: Path | None = None,
) -> dict[str, Any] | None:
    """Best-effort override write for ops paths that must not raise on I/O.

    Still fail-closed on validation (missing motivo/autor/data returns error dict
    with ok=False rather than writing incomplete rows).
    """
    try:
        return record_manual_override(
            target=target,
            action=action,
            motivo=motivo,
            autor=autor,
            before=before,
            after=after,
            run_id=run_id,
            data=data,
            root=root,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "errors": [str(exc)]}
    except Exception as exc:  # noqa: BLE001 — ledger must not break ops
        return {"ok": False, "error": str(exc), "errors": [str(exc)]}


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
    # Manual mutations: actor + reason required if file exists
    mut_path = ledger_path(root, name="manual-mutations.jsonl")
    mut_issues: list[str] = []
    if mut_path.is_file():
        for line in mut_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                mut_issues.append("corrupt_mutation_line")
                continue
            if not m.get("actor"):
                mut_issues.append(f"missing_actor:{m.get('mutation_id')}")
            if not m.get("reason"):
                mut_issues.append(f"missing_reason:{m.get('mutation_id')}")
    # Overrides: motivo/data/autor
    ov_path = override_ledger_path(root)
    ov_issues: list[str] = []
    if ov_path.is_file():
        from scripts.lib.manual_override_ledger import load_overrides, validate_override_row

        for row in load_overrides(ov_path):
            v = validate_override_row(row)
            if not v["ok"]:
                ov_issues.append(f"{row.get('target')}:{v['issues']}")
    ok = not missing_errors_field and not unlinked and not mut_issues and not ov_issues
    return {
        "ok": ok,
        "n_runs": len(rows),
        "n_with_errors": len(runs_with_errors(root)),
        "missing_errors_field": missing_errors_field,
        "unlinked_reports": unlinked,
        "manual_mutation_issues": mut_issues,
        "override_issues": ov_issues,
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


def _cmd_record(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else None
    errs = list(args.error or [])
    reports = list(args.report or [])
    rec = record_execution(
        command=args.command,
        status=args.status,
        errors=errs,
        exit_code=args.exit_code,
        report_paths=reports,
        run_id=args.run_id,
        meta={"entrypoint": "cli", "source": "run_execution_ledger"},
        root=root,
    )
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else None
    inv = verify_invariants(root)
    text = json.dumps(inv, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if inv.get("ok") else 1


def _cmd_override(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else None
    try:
        row = record_manual_override(
            target=args.target,
            action=args.action,
            motivo=args.motivo,
            autor=args.autor,
            before=args.before,
            after=args.after,
            run_id=args.run_id,
            data=args.data,
            root=root,
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "errors": [str(exc)]}, ensure_ascii=False))
        return 2
    print(json.dumps(row, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_mutation(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else None
    try:
        row = record_manual_mutation(
            actor=args.actor,
            path=args.path,
            reason=args.reason,
            root=root,
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "errors": [str(exc)]}, ensure_ascii=False))
        return 2
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python3 -m scripts.ops.run_execution_ledger",
        description="DoD §29 execution/override ledger (record · verify · override · mutation)",
    )
    p.add_argument(
        "--root",
        default=None,
        help="Workspace root for ledger files (default: cwd)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="Append one execution record with errors[] + report→run")
    rec.add_argument("--command", required=True, help="Command string recorded")
    rec.add_argument(
        "--status",
        default="ok",
        choices=("ok", "failed", "partial", "cancelled"),
    )
    rec.add_argument("--exit-code", type=int, default=None)
    rec.add_argument("--error", action="append", default=[], help="Error string (repeatable)")
    rec.add_argument("--report", action="append", default=[], help="Report path (repeatable)")
    rec.add_argument("--run-id", default=None)
    rec.set_defaults(func=_cmd_record)

    ver = sub.add_parser("verify", help="Verify ledger invariants (errors field, report→run)")
    ver.add_argument("--out", default=None, help="Write JSON result to path")
    ver.set_defaults(func=_cmd_verify)

    ov = sub.add_parser("override", help="Append manual override (motivo/data/autor required)")
    ov.add_argument("--target", required=True)
    ov.add_argument("--action", required=True)
    ov.add_argument("--motivo", required=True)
    ov.add_argument("--autor", required=True)
    ov.add_argument("--data", default=None, help="ISO timestamp (default: now UTC)")
    ov.add_argument("--before", default=None)
    ov.add_argument("--after", default=None)
    ov.add_argument("--run-id", default=None)
    ov.set_defaults(func=_cmd_override)

    mut = sub.add_parser("mutation", help="Append manual mutation audit entry")
    mut.add_argument("--actor", required=True)
    mut.add_argument("--path", required=True)
    mut.add_argument("--reason", required=True)
    mut.set_defaults(func=_cmd_mutation)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
