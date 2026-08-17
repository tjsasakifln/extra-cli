"""CLI: list, validate, export, compare, verify. Refuses export when the gate fails."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from scripts.public_read_consumers.export import (
    ExportRefusedError,
    compare_dirs,
    export_consumer,
    load_json,
    verify_dir,
)
from scripts.public_read_consumers.live_refresh import RefreshRefusedError, refresh, replay_dir
from scripts.public_read_consumers.registry import (
    get_consumer,
    list_consumer_ids,
    load_consumer_contract,
    validate_registry,
)


def _print(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _cmd_list(_: argparse.Namespace) -> int:
    records = []
    for consumer_id in list_consumer_ids():
        item = get_consumer(consumer_id)
        records.append(
            {
                "consumer_id": item["consumer_id"],
                "schema": item["schema"],
                "schema_version": item["schema_version"],
                "decision": item["decision"],
                "grain": item["grain"],
            }
        )
    _print({"ok": True, "consumers": records, "consumer_ids": list_consumer_ids()})
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    if args.consumer:
        record = get_consumer(args.consumer)
        contract = load_consumer_contract(args.consumer)
        errors = []
        if contract.get("schema") != record.get("schema"):
            errors.append("schema_mismatch")
        if args.payload:
            raw = load_json(args.payload)
            if raw.get("claimed_live") and (
                raw.get("catalog_mode") == "fixture"
                or raw.get("official_live") is True
                and raw.get("producer_status") == "CONTRACT_FIXTURE"
            ):
                errors.append("fixture_as_live")
        _print({"ok": not errors, "consumer_id": record["consumer_id"], "schema": record["schema"], "errors": errors})
        return 0 if not errors else 2
    report = validate_registry()
    _print(report)
    return 0 if report["ok"] else 2


def _cmd_export(args: argparse.Namespace) -> int:
    sources = {"fixture": args.fixture, "payload": args.payload}
    present = [name for name, value in sources.items() if value]
    if len(present) != 1:
        raise SystemExit("export requires exactly one of --fixture or --payload")
    raw = load_json(args.fixture or args.payload)
    live = bool(args.live)
    fixture = bool(args.fixture) or not live
    try:
        result = export_consumer(
            args.consumer,
            raw,
            args.out,
            fixture=fixture,
            live=live,
            now=str(raw.get("generated_at") or raw.get("as_of") or ""),
        )
    except ExportRefusedError as exc:
        _print({"ok": False, "reason_code": exc.reason_code, "error": str(exc)})
        return 2
    _print(result)
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    _print({"ok": True, **compare_dirs(args.left, args.right)})
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    try:
        _print(verify_dir(args.path))
    except ValueError as exc:
        _print({"ok": False, "reason_code": str(exc)})
        return 2
    return 0


def _cmd_refresh(args: argparse.Namespace) -> int:
    snapshot = load_json(args.snapshot) if args.snapshot else None
    if args.replay_snapshot:
        snapshot = load_json(args.replay_snapshot)
    try:
        result = refresh(
            consumer=args.consumer,
            out=args.out,
            dsn=args.dsn,
            snapshot=snapshot,
            fixture=bool(args.fixture or (snapshot and not args.live and args.snapshot)),
            live=bool(args.live),
            fail_before_rename=bool(getattr(args, "fail_before_rename", False)),
        )
    except RefreshRefusedError as exc:
        _print({"ok": False, "reason_code": exc.reason_code, "error": str(exc)})
        return 2
    _print(result)
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    try:
        result = replay_dir(args.path)
    except RefreshRefusedError as exc:
        _print({"ok": False, "reason_code": exc.reason_code, "error": str(exc)})
        return 2
    _print(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m scripts.public_read_consumers")
    sub = parser.add_subparsers(dest="command", required=True)

    listed = sub.add_parser("list", help="List named consumers")
    listed.set_defaults(func=_cmd_list)

    validate = sub.add_parser("validate", help="Validate registry or a named consumer contract")
    validate.add_argument("--consumer", help="Named consumer id or alias")
    validate.add_argument("--payload", help="Optional payload to check live/fixture labels")
    validate.set_defaults(func=_cmd_validate)

    export_cmd = sub.add_parser("export", help="Export a named consumer payload + manifest")
    export_cmd.add_argument("--consumer", required=True)
    export_cmd.add_argument("--fixture", help="Labeled fixture JSON; never live")
    export_cmd.add_argument("--payload", help="Payload JSON")
    export_cmd.add_argument("--out", required=True)
    export_cmd.add_argument("--live", action="store_true", help="Refuse unless official_live producers are present")
    export_cmd.set_defaults(func=_cmd_export)

    compare = sub.add_parser("compare", help="Diff two export directories")
    compare.add_argument("--left", required=True)
    compare.add_argument("--right", required=True)
    compare.set_defaults(func=_cmd_compare)

    verify = sub.add_parser("verify", help="Verify content hashes in an export directory")
    verify.add_argument("--path", required=True)
    verify.set_defaults(func=_cmd_verify)

    refresh_cmd = sub.add_parser("refresh", help="Official-live or fixture contract-analysis refresh")
    refresh_cmd.add_argument("--consumer", required=True)
    refresh_cmd.add_argument("--out", required=True)
    refresh_cmd.add_argument("--dsn", help="Optional live DSN for official SELECT")
    refresh_cmd.add_argument("--snapshot", help="Snapshot JSON (fixture or previously exported)")
    refresh_cmd.add_argument("--replay-snapshot", dest="replay_snapshot", help="Replay a stored snapshot.json")
    refresh_cmd.add_argument("--fixture", action="store_true", help="Label the input as fixture; official_live=false")
    refresh_cmd.add_argument("--live", action="store_true", help="Require official_select snapshot")
    refresh_cmd.add_argument("--fail-before-rename", action="store_true", help=argparse.SUPPRESS)
    refresh_cmd.set_defaults(func=_cmd_refresh)

    replay_cmd = sub.add_parser("replay", help="Replay snapshot.json inside an export directory")
    replay_cmd.add_argument("--path", required=True)
    replay_cmd.set_defaults(func=_cmd_replay)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
