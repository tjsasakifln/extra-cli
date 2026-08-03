"""CLI: python -m scripts.decision_memory <command>

Exit codes:
  0  success
  1  operational failure / not ok
  2  validation / usage error
  3  database unavailable / persistence failure
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from scripts.decision_memory.db import connect, require_client_id
from scripts.decision_memory.import_legacy import import_run
from scripts.decision_memory.metrics import compute_metrics
from scripts.decision_memory.models import (
    ActionCompleteInput,
    ActionCriticality,
    ActionRecordInput,
    ActionStatus,
    ConfirmationDegree,
    DecisionRecordInput,
    EventOrigin,
    HumanDecision,
    LegacyDecision,
    OutcomeRecordInput,
    OutcomeType,
    SystemRecommendation,
    TemporalIntegrity,
)
from scripts.decision_memory.repository import DecisionMemoryRepository
from scripts.decision_memory.weekly_board import build_weekly_board

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_DB = 3


def _print(data: dict[str, Any], as_json: bool = True) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n"
    sys.stdout.write(text)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _repo(dsn: str | None) -> tuple[Any, DecisionMemoryRepository]:
    try:
        conn = connect(dsn)
    except Exception as exc:  # noqa: BLE001 — surface as DB exit
        raise ConnectionError(str(exc)) from exc
    return conn, DecisionMemoryRepository(conn)


def cmd_decision_record(args: argparse.Namespace) -> int:
    client_id = require_client_id(args.client_id)
    human: HumanDecision
    legacy: LegacyDecision | None
    try:
        human = HumanDecision(args.decision.upper())
    except ValueError:
        # allow legacy
        from scripts.decision_memory.mapping import map_legacy_decision

        try:
            human, legacy = map_legacy_decision(args.decision)
        except Exception as exc:
            _print({"ok": False, "error": str(exc)})
            return EXIT_USAGE
    else:
        if args.legacy_decision:
            legacy = LegacyDecision(args.legacy_decision.upper())
        else:
            from scripts.decision_memory.mapping import HUMAN_TO_LEGACY

            legacy = HUMAN_TO_LEGACY.get(human)

    try:
        inp = DecisionRecordInput(
            client_id=client_id,
            opportunity_key=args.opportunity_key,
            actor=args.actor,
            justification=args.justification,
            human_decision=human,
            legacy_decision=legacy,
            system_recommendation=SystemRecommendation((args.system_recommendation or "NOT_PROVIDED").upper()),
            cycle_id=args.cycle_id,
            run_id=args.run_id,
            decided_at=_parse_dt(args.decided_at),
            profile_id=args.profile_id,
            profile_version=args.profile_version,
            profile_hash=args.profile_hash,
            evidence_hash=args.evidence_hash,
            evidence_locators=args.evidence_locator or [],
            temporal_integrity=TemporalIntegrity((args.temporal_integrity or "PROSPECTIVE").upper()),
            origin=EventOrigin((args.origin or "cli").lower()),
            idempotency_key=args.idempotency_key,
            premises=args.premise or [],
            constraints_known=args.constraint or [],
            data_limitations=args.limitation or [],
        )
    except Exception as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_USAGE

    try:
        conn, repo = _repo(args.dsn)
    except ConnectionError as exc:
        _print({"ok": False, "status": "DB_UNAVAILABLE", "error": str(exc)})
        return EXIT_DB
    try:
        result = repo.record_decision(inp)
        _print({"ok": True, "status": result["status"], "client_id": client_id, "data": result})
        return EXIT_OK
    except Exception as exc:
        conn.rollback()
        _print({"ok": False, "status": "PERSISTENCE_FAILED", "error": str(exc)})
        return EXIT_DB
    finally:
        conn.close()


def cmd_decision_list(args: argparse.Namespace) -> int:
    client_id = require_client_id(args.client_id)
    try:
        conn, repo = _repo(args.dsn)
    except ConnectionError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_DB
    try:
        rows = repo.list_decisions(
            client_id,
            opportunity_key=args.opportunity_key,
            limit=args.limit,
            current_only=not args.all_events,
        )
        _print({"ok": True, "status": "PASS", "client_id": client_id, "data": {"items": rows, "n": len(rows)}})
        return EXIT_OK
    finally:
        conn.close()


def cmd_decision_show(args: argparse.Namespace) -> int:
    client_id = require_client_id(args.client_id)
    try:
        conn, repo = _repo(args.dsn)
    except ConnectionError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_DB
    try:
        row = repo.get_decision(client_id, args.event_id)
        if not row:
            _print({"ok": False, "status": "NOT_FOUND", "error": "decision not found for client"})
            return EXIT_FAIL
        _print({"ok": True, "status": "PASS", "client_id": client_id, "data": row})
        return EXIT_OK
    finally:
        conn.close()


def cmd_decision_history(args: argparse.Namespace) -> int:
    client_id = require_client_id(args.client_id)
    try:
        conn, repo = _repo(args.dsn)
    except ConnectionError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_DB
    try:
        rows = repo.decision_history(client_id, args.opportunity_key)
        _print(
            {
                "ok": True,
                "status": "PASS",
                "client_id": client_id,
                "data": {"opportunity_key": args.opportunity_key, "events": rows, "n": len(rows)},
            }
        )
        return EXIT_OK
    finally:
        conn.close()


def cmd_action_record(args: argparse.Namespace) -> int:
    client_id = require_client_id(args.client_id)
    try:
        inp = ActionRecordInput(
            client_id=client_id,
            decision_event_id=UUID(args.decision_event_id),
            opportunity_key=args.opportunity_key,
            description=args.description,
            actor=args.actor,
            owner=args.owner,
            owner_absent_reason=args.owner_absent_reason,
            due_at=_parse_dt(args.due_at),
            due_absent_reason=args.due_absent_reason,
            criticality=ActionCriticality((args.criticality or "NORMAL").upper()),
            status=ActionStatus((args.status or "OPEN").upper()),
            idempotency_key=args.idempotency_key,
        )
    except Exception as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_USAGE
    try:
        conn, repo = _repo(args.dsn)
    except ConnectionError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_DB
    try:
        result = repo.record_action(inp)
        _print({"ok": True, "status": result["status"], "client_id": client_id, "data": result})
        return EXIT_OK
    except Exception as exc:
        conn.rollback()
        _print({"ok": False, "error": str(exc)})
        return EXIT_FAIL
    finally:
        conn.close()


def cmd_action_complete(args: argparse.Namespace) -> int:
    client_id = require_client_id(args.client_id)
    try:
        inp = ActionCompleteInput(
            client_id=client_id,
            action_event_id=UUID(args.action_event_id),
            actor=args.actor,
            evidence_hash=args.evidence_hash,
            evidence_locators=args.evidence_locator or [],
            completed_at=_parse_dt(args.completed_at),
            notes=args.notes,
            idempotency_key=args.idempotency_key,
        )
    except Exception as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_USAGE
    try:
        conn, repo = _repo(args.dsn)
    except ConnectionError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_DB
    try:
        result = repo.complete_action(inp)
        _print({"ok": True, "status": result["status"], "client_id": client_id, "data": result})
        return EXIT_OK
    except Exception as exc:
        conn.rollback()
        _print({"ok": False, "error": str(exc)})
        return EXIT_FAIL
    finally:
        conn.close()


def cmd_action_list(args: argparse.Namespace) -> int:
    client_id = require_client_id(args.client_id)
    try:
        conn, repo = _repo(args.dsn)
    except ConnectionError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_DB
    try:
        rows = repo.list_actions(client_id, status=args.status, limit=args.limit)
        _print({"ok": True, "status": "PASS", "client_id": client_id, "data": {"items": rows, "n": len(rows)}})
        return EXIT_OK
    finally:
        conn.close()


def cmd_outcome_record(args: argparse.Namespace) -> int:
    client_id = require_client_id(args.client_id)
    try:
        inp = OutcomeRecordInput(
            client_id=client_id,
            opportunity_key=args.opportunity_key,
            outcome_type=OutcomeType(args.outcome_type.upper()),
            observed_at=_parse_dt(args.observed_at) or datetime.now().astimezone(),
            source=args.source,
            evidence_hash=args.evidence_hash,
            actor=args.actor,
            decision_event_id=UUID(args.decision_event_id) if args.decision_event_id else None,
            locator=args.locator,
            confirmation_degree=ConfirmationDegree((args.confirmation_degree or "DECLARED").upper()),
            observations=args.observations,
            expected_margin=args.expected_margin,
            realized_margin=args.realized_margin,
            idempotency_key=args.idempotency_key,
        )
    except Exception as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_USAGE
    try:
        conn, repo = _repo(args.dsn)
    except ConnectionError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_DB
    try:
        result = repo.record_outcome(inp)
        _print({"ok": True, "status": result["status"], "client_id": client_id, "data": result})
        return EXIT_OK
    except Exception as exc:
        conn.rollback()
        _print({"ok": False, "error": str(exc)})
        return EXIT_FAIL
    finally:
        conn.close()


def cmd_outcome_list(args: argparse.Namespace) -> int:
    client_id = require_client_id(args.client_id)
    try:
        conn, repo = _repo(args.dsn)
    except ConnectionError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_DB
    try:
        rows = repo.list_outcomes(client_id, opportunity_key=args.opportunity_key, limit=args.limit)
        _print({"ok": True, "status": "PASS", "client_id": client_id, "data": {"items": rows, "n": len(rows)}})
        return EXIT_OK
    finally:
        conn.close()


def cmd_import_run(args: argparse.Namespace) -> int:
    client_id = require_client_id(args.client_id)
    apply = bool(args.apply)
    # dry-run is default; --apply required for writes
    paths = [Path(p) for p in (args.path or [])]
    try:
        conn, repo = _repo(args.dsn)
    except ConnectionError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_DB
    try:
        report = import_run(
            repo,
            client_id=client_id,
            actor=args.actor,
            paths=paths,
            apply=apply,
            cycle_id=args.cycle_id,
            run_id=args.run_id,
        )
        _print(report)
        return EXIT_OK if report.get("ok") else EXIT_FAIL
    except Exception as exc:
        conn.rollback()
        _print({"ok": False, "error": str(exc)})
        return EXIT_USAGE
    finally:
        conn.close()


def cmd_weekly_board(args: argparse.Namespace) -> int:
    client_id = require_client_id(args.client_id)
    try:
        conn, repo = _repo(args.dsn)
    except ConnectionError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_DB
    try:
        board = build_weekly_board(
            repo,
            client_id=client_id,
            cycle_id=args.cycle_id,
            lookback_days=args.lookback_days,
        )
        if args.output:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(board, indent=2, ensure_ascii=False, default=str) + "\n")
        _print({"ok": True, "status": "PASS", "client_id": client_id, "data": board})
        return EXIT_OK
    finally:
        conn.close()


def cmd_metrics(args: argparse.Namespace) -> int:
    client_id = require_client_id(args.client_id)
    try:
        conn, repo = _repo(args.dsn)
    except ConnectionError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_DB
    try:
        m = compute_metrics(
            repo,
            client_id=client_id,
            period_start=_parse_dt(args.period_start),
            period_end=_parse_dt(args.period_end),
        )
        _print(m)
        return EXIT_OK
    finally:
        conn.close()


def cmd_integrity_verify(args: argparse.Namespace) -> int:
    client_id = require_client_id(args.client_id)
    try:
        conn, repo = _repo(args.dsn)
    except ConnectionError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_DB
    try:
        report = repo.verify_integrity(client_id)
        _print(report)
        return EXIT_OK if report.get("ok") else EXIT_FAIL
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.decision_memory",
        description="Decision & Outcome Memory v1 (canonical PostgreSQL)",
    )
    p.add_argument(
        "--dsn",
        default=None,
        help="PostgreSQL DSN (default LOCAL_DATALAKE_DSN)",
    )
    p.add_argument(
        "--client-id",
        required=False,
        help="Client scope (required for all write/read commands; no silent default)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # decision
    d = sub.add_parser("decision", help="Decision commands")
    dsub = d.add_subparsers(dest="decision_cmd", required=True)

    dr = dsub.add_parser("record", help="Record a human decision")
    dr.add_argument("--opportunity-key", required=True)
    dr.add_argument("--decision", required=True, help="GO|REVIEW|NO_GO or ACCEPT|REJECT|DEFER")
    dr.add_argument("--actor", required=True)
    dr.add_argument("--justification", required=True)
    dr.add_argument("--legacy-decision")
    dr.add_argument("--system-recommendation")
    dr.add_argument("--cycle-id")
    dr.add_argument("--run-id")
    dr.add_argument("--decided-at")
    dr.add_argument("--profile-id")
    dr.add_argument("--profile-version")
    dr.add_argument("--profile-hash")
    dr.add_argument("--evidence-hash")
    dr.add_argument("--evidence-locator", action="append")
    dr.add_argument("--temporal-integrity")
    dr.add_argument("--origin")
    dr.add_argument("--idempotency-key")
    dr.add_argument("--premise", action="append")
    dr.add_argument("--constraint", action="append")
    dr.add_argument("--limitation", action="append")

    dl = dsub.add_parser("list")
    dl.add_argument("--opportunity-key")
    dl.add_argument("--limit", type=int, default=100)
    dl.add_argument("--all-events", action="store_true")

    ds = dsub.add_parser("show")
    ds.add_argument("event_id")

    dh = dsub.add_parser("history")
    dh.add_argument("opportunity_key")

    # action
    a = sub.add_parser("action")
    asub = a.add_subparsers(dest="action_cmd", required=True)
    ar = asub.add_parser("record")
    ar.add_argument("--decision-event-id", required=True)
    ar.add_argument("--opportunity-key", required=True)
    ar.add_argument("--description", required=True)
    ar.add_argument("--actor", required=True)
    ar.add_argument("--owner")
    ar.add_argument("--owner-absent-reason")
    ar.add_argument("--due-at")
    ar.add_argument("--due-absent-reason")
    ar.add_argument("--criticality")
    ar.add_argument("--status")
    ar.add_argument("--idempotency-key")

    ac = asub.add_parser("complete")
    ac.add_argument("action_event_id")
    ac.add_argument("--actor", required=True)
    ac.add_argument("--evidence-hash", required=True)
    ac.add_argument("--evidence-locator", action="append")
    ac.add_argument("--completed-at")
    ac.add_argument("--notes")
    ac.add_argument("--idempotency-key")

    al = asub.add_parser("list")
    al.add_argument("--status")
    al.add_argument("--limit", type=int, default=100)

    # outcome
    o = sub.add_parser("outcome")
    osub = o.add_subparsers(dest="outcome_cmd", required=True)
    or_ = osub.add_parser("record")
    or_.add_argument("--opportunity-key", required=True)
    or_.add_argument("--outcome-type", required=True)
    or_.add_argument("--source", required=True)
    or_.add_argument("--evidence-hash", required=True)
    or_.add_argument("--actor", required=True)
    or_.add_argument("--observed-at")
    or_.add_argument("--decision-event-id")
    or_.add_argument("--locator")
    or_.add_argument("--confirmation-degree")
    or_.add_argument("--observations")
    or_.add_argument("--expected-margin", type=float)
    or_.add_argument("--realized-margin", type=float)
    or_.add_argument("--idempotency-key")

    ol = osub.add_parser("list")
    ol.add_argument("--opportunity-key")
    ol.add_argument("--limit", type=int, default=100)

    # import-run
    imp = sub.add_parser("import-run")
    imp.add_argument("--path", action="append", required=True, help="Explicit file path (repeatable)")
    imp.add_argument("--actor", required=True)
    imp.add_argument("--apply", action="store_true", help="Persist (default is dry-run)")
    imp.add_argument("--dry-run", action="store_true", help="Explicit dry-run (default)")
    imp.add_argument("--cycle-id")
    imp.add_argument("--run-id")

    wb = sub.add_parser("weekly-board")
    wb.add_argument("--cycle-id")
    wb.add_argument("--lookback-days", type=int, default=14)
    wb.add_argument("--output")

    met = sub.add_parser("metrics")
    met.add_argument("--period-start")
    met.add_argument("--period-end")

    integ = sub.add_parser("integrity")
    isub = integ.add_subparsers(dest="integrity_cmd", required=True)
    isub.add_parser("verify")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # client_id required for all commands
    if not getattr(args, "client_id", None):
        _print({"ok": False, "error": "client_id is required (no silent default to extra)"})
        return EXIT_USAGE

    try:
        if args.cmd == "decision":
            if args.decision_cmd == "record":
                return cmd_decision_record(args)
            if args.decision_cmd == "list":
                return cmd_decision_list(args)
            if args.decision_cmd == "show":
                return cmd_decision_show(args)
            if args.decision_cmd == "history":
                return cmd_decision_history(args)
        if args.cmd == "action":
            if args.action_cmd == "record":
                return cmd_action_record(args)
            if args.action_cmd == "complete":
                return cmd_action_complete(args)
            if args.action_cmd == "list":
                return cmd_action_list(args)
        if args.cmd == "outcome":
            if args.outcome_cmd == "record":
                return cmd_outcome_record(args)
            if args.outcome_cmd == "list":
                return cmd_outcome_list(args)
        if args.cmd == "import-run":
            return cmd_import_run(args)
        if args.cmd == "weekly-board":
            return cmd_weekly_board(args)
        if args.cmd == "metrics":
            return cmd_metrics(args)
        if args.cmd == "integrity" and args.integrity_cmd == "verify":
            return cmd_integrity_verify(args)
    except ValueError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_USAGE
    _print({"ok": False, "error": "unknown command"})
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
