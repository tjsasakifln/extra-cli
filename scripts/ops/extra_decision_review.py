#!/usr/bin/env python3
"""Human decision registration for Extra weekly decision loop.

CLI:

  python3 -m scripts.ops.extra_decision_review list --run-dir PATH
  python3 -m scripts.ops.extra_decision_review decide OPP_ID --run-dir PATH \\
      --decision ACCEPT|REJECT|DEFER --reason "..." --actor tiago
  python3 -m scripts.ops.extra_decision_review finalize --run-dir PATH --actor tiago
  python3 -m scripts.ops.extra_decision_review accept-empty --run-dir PATH \\
      --reason "..." --actor tiago

Never auto-accepts. PASS_EXTRA_DECISION_LOOP_ACCEPTED only after explicit human finalize.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "extra-decision-review/1.0"
DECISIONS = frozenset({"ACCEPT", "REJECT", "DEFER"})
PACKAGE_DECISIONS = frozenset({"ACCEPTED", "ACCEPTED_WITH_LIMITATIONS", "REJECTED"})
LEDGER_NAME = "human-decisions.jsonl"
STATE_NAME = "decision-loop-state.json"

READY_FOR_HUMAN = "READY_FOR_HUMAN_ACCEPTANCE"
PASS_ACCEPTED = "PASS_EXTRA_DECISION_LOOP_ACCEPTED"  # noqa: S105


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_run_dir(run_dir: Path) -> Path:
    p = Path(run_dir)
    if not p.is_dir():
        raise FileNotFoundError(f"run-dir not found: {p}")
    return p


def load_shortlist_bundle(run_dir: Path) -> dict[str, Any]:
    """Load actionable summary or first-client shortlist artifacts."""
    candidates = [
        run_dir / "actionable-summary.json",
        run_dir / "shortlist.json",
        run_dir / "03-shortlist.json",
    ]
    for c in candidates:
        if c.is_file():
            data = _load_json(c)
            data["_path"] = str(c)
            data["_hash"] = sha256_file(c)
            return data
    # synthetic empty
    return {
        "result": "NO_ACTIONABLE_TENDER",
        "shortlist": [],
        "shortlist_count": 0,
        "candidates_evaluated": 0,
        "_path": None,
        "_hash": None,
    }


def list_items(run_dir: Path) -> dict[str, Any]:
    bundle = load_shortlist_bundle(run_dir)
    shortlist = list(bundle.get("shortlist") or [])
    # normalize id field
    items = []
    for s in shortlist:
        if isinstance(s, dict) and "evidence" in s and "state" in s:
            # actionable format
            items.append(
                {
                    "opportunity_id": s.get("opportunity_id"),
                    "state": s.get("state"),
                    "actionable": s.get("actionable"),
                    "orgao": (s.get("evidence") or {}).get("orgao"),
                    "objeto": (s.get("evidence") or {}).get("objeto"),
                }
            )
        else:
            items.append(
                {
                    "opportunity_id": s.get("opportunity_id") or s.get("numero_controle"),
                    "state": s.get("recommendation") or s.get("state"),
                    "actionable": s.get("recommendation") == "REVIEW",
                    "orgao": s.get("orgao"),
                    "objeto": s.get("objeto"),
                }
            )
    ledger = read_ledger(run_dir)
    return {
        "run_dir": str(run_dir),
        "result": bundle.get("result"),
        "items": items,
        "n_items": len(items),
        "decisions_recorded": len(ledger),
        "bundle_hash": bundle.get("_hash"),
        "profile_stamp": bundle.get("profile_stamp"),
    }


def read_ledger(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / LEDGER_NAME
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def append_decision(run_dir: Path, record: dict[str, Any]) -> Path:
    path = run_dir / LEDGER_NAME
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def decide(
    run_dir: Path,
    *,
    opportunity_id: str,
    decision: str,
    reason: str,
    actor: str,
    next_action: str | None = None,
    next_action_due: str | None = None,
) -> dict[str, Any]:
    decision_u = decision.strip().upper()
    if decision_u not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}")
    if not reason.strip():
        raise ValueError("reason is required")
    if not actor.strip():
        raise ValueError("actor is required")

    bundle = load_shortlist_bundle(run_dir)
    shortlist = list(bundle.get("shortlist") or [])
    known_ids = set()
    for s in shortlist:
        known_ids.add(str(s.get("opportunity_id") or s.get("numero_controle") or ""))
    # allow NO_ACTIONABLE marker
    if opportunity_id == "NO_ACTIONABLE_TENDER":
        if bundle.get("result") != "NO_ACTIONABLE_TENDER" and shortlist:
            raise ValueError("NO_ACTIONABLE_TENDER only valid when shortlist empty / result says so")
    elif known_ids and opportunity_id not in known_ids:
        raise ValueError(f"opportunity_id not in shortlist: {opportunity_id}")

    profile_stamp = bundle.get("profile_stamp") or {}
    record = {
        "schema": SCHEMA,
        "recorded_at": utc_now(),
        "actor": actor.strip(),
        "opportunity_id": opportunity_id,
        "decision": decision_u,
        "reason": reason.strip(),
        "next_action": next_action,
        "next_action_due": next_action_due,
        "report_version": bundle.get("schema") or bundle.get("result"),
        "profile_version": profile_stamp.get("version"),
        "profile_hash": profile_stamp.get("profile_hash"),
        "evidence_hash": bundle.get("_hash"),
        "run_dir": str(run_dir),
    }
    append_decision(run_dir, record)
    return record


def accept_empty(
    run_dir: Path,
    *,
    reason: str,
    actor: str,
) -> dict[str, Any]:
    """Accept that there is no actionable tender — not a fake tender decision."""
    bundle = load_shortlist_bundle(run_dir)
    if bundle.get("shortlist"):
        raise ValueError("Cannot accept-empty while shortlist is non-empty")
    return decide(
        run_dir,
        opportunity_id="NO_ACTIONABLE_TENDER",
        decision="ACCEPT",
        reason=reason,
        actor=actor,
        next_action="Aumentar cobertura / completar perfil e reexecutar weekly",
    )


def finalize(
    run_dir: Path,
    *,
    actor: str,
    package_decision: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Finalize human review for the run.

    Emits PASS_EXTRA_DECISION_LOOP_ACCEPTED only when package_decision is ACCEPTED*
    and at least one decision was recorded (including accept-empty).
    """
    if not actor.strip():
        raise ValueError("actor is required for finalize")
    ledger = read_ledger(run_dir)
    bundle = load_shortlist_bundle(run_dir)
    shortlist = list(bundle.get("shortlist") or [])

    # Require decision coverage
    decided_ids = {r["opportunity_id"] for r in ledger}
    if shortlist:
        missing = []
        for s in shortlist:
            oid = str(s.get("opportunity_id") or s.get("numero_controle") or "")
            if oid and oid not in decided_ids:
                missing.append(oid)
        if missing:
            raise ValueError(f"Missing decisions for: {missing}")
    else:
        if "NO_ACTIONABLE_TENDER" not in decided_ids:
            raise ValueError(
                "Empty shortlist requires accept-empty (decision on NO_ACTIONABLE_TENDER)"
            )

    pkg = (package_decision or "").strip().upper() or None
    if pkg is not None and pkg not in PACKAGE_DECISIONS:
        raise ValueError(f"package_decision must be one of {sorted(PACKAGE_DECISIONS)}")

    if pkg in {"ACCEPTED", "ACCEPTED_WITH_LIMITATIONS"}:
        terminal = PASS_ACCEPTED
    else:
        terminal = READY_FOR_HUMAN

    state = {
        "schema": SCHEMA,
        "terminal_state": terminal,
        "finalized_at": utc_now() if pkg else None,
        "finalized_by": actor if pkg else None,
        "package_decision": pkg,
        "notes": notes,
        "decisions": ledger,
        "n_decisions": len(ledger),
        "shortlist_count": len(shortlist),
        "result": bundle.get("result"),
        "bundle_hash": bundle.get("_hash"),
        "profile_stamp": bundle.get("profile_stamp"),
        "ready_reason": None
        if pkg
        else "Aguardando package_decision humana (ACCEPTED|ACCEPTED_WITH_LIMITATIONS|REJECTED)",
    }
    _write_json(run_dir / STATE_NAME, state)
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extra decision human review CLI")
    parser.add_argument("--run-dir", required=True, help="Directory of decision-loop run artifacts")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List shortlist / empty result")

    p_dec = sub.add_parser("decide", help="Record ACCEPT|REJECT|DEFER")
    p_dec.add_argument("opportunity_id")
    p_dec.add_argument("--decision", required=True)
    p_dec.add_argument("--reason", required=True)
    p_dec.add_argument("--actor", required=True)
    p_dec.add_argument("--next-action")
    p_dec.add_argument("--next-action-due")

    p_empty = sub.add_parser("accept-empty", help="Accept NO_ACTIONABLE_TENDER honestly")
    p_empty.add_argument("--reason", required=True)
    p_empty.add_argument("--actor", required=True)

    p_fin = sub.add_parser("finalize", help="Finalize package (or emit READY_FOR_HUMAN_ACCEPTANCE)")
    p_fin.add_argument("--actor", required=True)
    p_fin.add_argument(
        "--package-decision",
        choices=sorted(PACKAGE_DECISIONS),
        help="Omit to leave READY_FOR_HUMAN_ACCEPTANCE",
    )
    p_fin.add_argument("--notes")

    args = parser.parse_args(argv)
    run_dir = resolve_run_dir(Path(args.run_dir))
    try:
        if args.cmd == "list":
            print(json.dumps(list_items(run_dir), indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "decide":
            rec = decide(
                run_dir,
                opportunity_id=args.opportunity_id,
                decision=args.decision,
                reason=args.reason,
                actor=args.actor,
                next_action=args.next_action,
                next_action_due=args.next_action_due,
            )
            print(json.dumps(rec, indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "accept-empty":
            rec = accept_empty(run_dir, reason=args.reason, actor=args.actor)
            print(json.dumps(rec, indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "finalize":
            st = finalize(
                run_dir,
                actor=args.actor,
                package_decision=args.package_decision,
                notes=args.notes,
            )
            print(json.dumps(st, indent=2, ensure_ascii=False))
            return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
