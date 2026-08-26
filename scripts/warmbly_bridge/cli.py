"""CLI: python -m scripts.warmbly_bridge <command>

Commands:
  export-outreach   Produce chunked confenge.outreach.v1 feed
  serve-outcomes    Local HMAC receptor for confenge.outcome.v1
  verify-outcome    Verify one signed outcome payload (dry, no server)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from scripts.warmbly_bridge import (
    DEFAULT_HMAC_SKEW_SECONDS,
    DEFAULT_MAX_BODY_BYTES,
    DEFAULT_MAX_BYTES_PER_CHUNK,
    DEFAULT_MAX_LEADS_PER_CHUNK,
    DEFAULT_PROFILE_ID,
    DEFAULT_PROFILE_VERSION,
)
from scripts.warmbly_bridge.export import ExportConfig, export_outreach
from scripts.warmbly_bridge.hmac_sig import sign_outcome_hmac, verify_outcome_hmac
from scripts.warmbly_bridge.io_jsonl import InputError
from scripts.warmbly_bridge.outcome_mapping import OutcomeValidationError
from scripts.warmbly_bridge.persist import (
    DecisionMemoryOutcomeStore,
    InMemoryOutcomeStore,
    persist_outcome,
)
from scripts.warmbly_bridge.receptor import ReceptorConfig, process_outcome_request, serve_forever

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


def _print(data: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n")


def cmd_export(args: argparse.Namespace) -> int:
    cfg = ExportConfig(
        universe=Path(args.universe),
        account_intelligence=Path(args.account_intelligence),
        contacts=Path(args.contacts),
        target_fit_snapshot=(Path(args.target_fit_snapshot) if args.target_fit_snapshot else None),
        contact_projection_report=(Path(args.contact_projection_report) if args.contact_projection_report else None),
        expected_universe_count=args.expected_universe_count,
        out_dir=Path(args.out),
        limit=args.limit,
        max_leads_per_chunk=args.max_leads_per_chunk,
        max_bytes_per_chunk=args.max_bytes_per_chunk,
        profile_id=args.profile_id,
        profile_version=args.profile_version,
        system=args.system,
        generated_at=args.generated_at,
        datalake_watermark=args.datalake_watermark,
        repo_sha=args.repo_sha,
    )
    try:
        result = export_outreach(cfg)
    except InputError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_USAGE
    except Exception as exc:  # noqa: BLE001
        _print({"ok": False, "error": str(exc)})
        return EXIT_FAIL
    _print(result)
    return EXIT_OK


def _build_store(args: argparse.Namespace) -> Any:
    if getattr(args, "memory_store", False):
        return InMemoryOutcomeStore()
    dsn = getattr(args, "dsn", None) or os.environ.get("LOCAL_DATALAKE_DSN")
    if not dsn:
        raise ValueError("no outcome store DSN: pass --dsn, set LOCAL_DATALAKE_DSN, or explicitly pass --memory-store")
    from scripts.decision_memory.db import connect
    from scripts.decision_memory.repository import DecisionMemoryRepository

    conn = connect(dsn)
    return DecisionMemoryOutcomeStore(DecisionMemoryRepository(conn))


def cmd_serve(args: argparse.Namespace) -> int:
    secret = args.secret or os.environ.get("CONFENGE_OUTCOME_WEBHOOK_SECRET") or ""
    if not secret:
        _print(
            {
                "ok": False,
                "error": "missing secret: pass --secret or set CONFENGE_OUTCOME_WEBHOOK_SECRET",
            }
        )
        return EXIT_USAGE
    try:
        store = _build_store(args)
    except ValueError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_USAGE
    config = ReceptorConfig(
        secret=secret,
        store=store,
        client_id=args.client_id,
        max_skew_seconds=args.max_skew_seconds,
        max_body_bytes=args.max_body_bytes,
        path=args.path,
    )
    server = serve_forever(config, host=args.host, port=args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return EXIT_OK


def cmd_verify_outcome(args: argparse.Namespace) -> int:
    secret = args.secret or os.environ.get("CONFENGE_OUTCOME_WEBHOOK_SECRET") or ""
    body_path = Path(args.body)
    if not body_path.is_file():
        _print({"ok": False, "error": f"body file not found: {body_path}"})
        return EXIT_USAGE
    body = body_path.read_bytes()
    if args.sign:
        if not secret:
            _print({"ok": False, "error": "secret required to --sign"})
            return EXIT_USAGE
        ts = int(args.timestamp) if args.timestamp else int(time.time())
        header = sign_outcome_hmac(secret, ts, body)
        _print({"ok": True, "signature": header, "timestamp": ts})
        return EXIT_OK

    header = args.signature or ""
    ok, reason = verify_outcome_hmac(
        secret,
        header,
        body,
        max_skew_seconds=args.max_skew_seconds,
    )
    if not ok:
        _print({"ok": False, "error": reason})
        return EXIT_FAIL

    store = InMemoryOutcomeStore()
    config = ReceptorConfig(
        secret=secret,
        store=store,
        client_id=args.client_id,
        max_skew_seconds=args.max_skew_seconds,
        max_body_bytes=args.max_body_bytes,
    )
    status, payload = process_outcome_request(body=body, signature_header=header, config=config)
    payload["http_status"] = status
    _print(payload)
    return EXIT_OK if status < 300 else EXIT_FAIL


def cmd_ingest_outcome(args: argparse.Namespace) -> int:
    """Ingest an unsigned local outcome file into store (dev only; no HMAC)."""
    body = Path(args.body).read_text(encoding="utf-8")
    envelope = json.loads(body)
    store = _build_store(args)
    try:
        result = persist_outcome(envelope, store=store, client_id=args.client_id)
    except OutcomeValidationError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_USAGE
    _print(result)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m scripts.warmbly_bridge")
    sub = p.add_subparsers(dest="command", required=True)

    e = sub.add_parser("export-outreach", help="Export confenge.outreach.v1 chunks")
    e.add_argument("--universe", required=True, help="Universe JSONL path")
    e.add_argument("--account-intelligence", required=True, help="Account intelligence JSONL path")
    e.add_argument("--contacts", required=True, help="Contacts JSONL path")
    e.add_argument(
        "--target-fit-snapshot",
        default=None,
        help="Authoritative full target-fit snapshot JSONL; defaults to embedded universe decisions",
    )
    e.add_argument(
        "--contact-projection-report",
        default=None,
        help="Terminal full-population contact projection report paired with --contacts",
    )
    e.add_argument(
        "--expected-universe-count",
        type=int,
        default=None,
        help="Declared authoritative universe cardinality; required for coverage_complete=true",
    )
    e.add_argument("--out", required=True, help="Output directory for chunks + manifest")
    e.add_argument("--limit", type=int, default=None, help="Smoke limit (Top N); omit in production")
    e.add_argument("--max-leads-per-chunk", type=int, default=DEFAULT_MAX_LEADS_PER_CHUNK)
    e.add_argument("--max-bytes-per-chunk", type=int, default=DEFAULT_MAX_BYTES_PER_CHUNK)
    e.add_argument("--profile-id", default=DEFAULT_PROFILE_ID)
    e.add_argument("--profile-version", default=DEFAULT_PROFILE_VERSION)
    e.add_argument("--system", default="extra-cli")
    e.add_argument("--generated-at", default=None, help="Override generated_at (tests)")
    e.add_argument(
        "--datalake-watermark",
        default=None,
        help="Canonical CDC watermark used to evaluate target-fit freshness",
    )
    e.add_argument("--repo-sha", default=None, help="Override repo_sha (tests)")
    e.set_defaults(func=cmd_export)

    s = sub.add_parser("serve-outcomes", help="Local HMAC outcome receptor")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8787)
    s.add_argument("--path", default="/webhooks/warmbly/outcome")
    s.add_argument("--secret", default=None)
    s.add_argument("--client-id", default="confenge")
    s.add_argument("--dsn", default=None, help="Postgres DSN for Decision Memory (optional)")
    s.add_argument("--memory-store", action="store_true", help="Force in-memory store")
    s.add_argument("--max-skew-seconds", type=int, default=DEFAULT_HMAC_SKEW_SECONDS)
    s.add_argument("--max-body-bytes", type=int, default=DEFAULT_MAX_BODY_BYTES)
    s.set_defaults(func=cmd_serve)

    v = sub.add_parser("verify-outcome", help="Sign or verify+persist one outcome body")
    v.add_argument("--body", required=True)
    v.add_argument("--secret", default=None)
    v.add_argument("--signature", default=None, help="X-Warmbly-Signature header value")
    v.add_argument("--sign", action="store_true", help="Only print signature header")
    v.add_argument("--timestamp", default=None, help="Unix ts for --sign")
    v.add_argument("--client-id", default="confenge")
    v.add_argument("--max-skew-seconds", type=int, default=DEFAULT_HMAC_SKEW_SECONDS)
    v.add_argument("--max-body-bytes", type=int, default=DEFAULT_MAX_BODY_BYTES)
    v.set_defaults(func=cmd_verify_outcome)

    i = sub.add_parser("ingest-outcome", help="Ingest unsigned outcome JSON (dev)")
    i.add_argument("--body", required=True)
    i.add_argument("--client-id", default="confenge")
    i.add_argument("--dsn", default=None)
    i.add_argument("--memory-store", action="store_true")
    i.set_defaults(func=cmd_ingest_outcome)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
