"""CLI: python3 -m scripts.public_integrity replay --fixture FILE --cnpj DIGITS --out PAYLOAD"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.public_integrity.cache import cache_from_fixture
from scripts.public_integrity.clock import parse_clock
from scripts.public_integrity.cnpj import digits_only
from scripts.public_integrity.export import write_consumer_export
from scripts.public_integrity.models import DEFAULT_TTL_SECONDS, SCHEMA_VERSION
from scripts.public_integrity.producer import produce
from scripts.public_integrity.schema import validate_payload
from scripts.public_integrity.transport import FixtureTransport, HttpTransport, load_fixture


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is None:
        sys.stdout.write(text)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _print(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def replay_fixture(
    fixture_path: str | Path,
    *,
    cnpj: str,
    ttl_seconds: int | None = None,
) -> dict[str, Any]:
    fixture = load_fixture(fixture_path)
    clock = parse_clock(fixture.get("clock"))
    ttl = int(fixture.get("ttl_seconds") or ttl_seconds or DEFAULT_TTL_SECONDS)
    transport = FixtureTransport(fixture)
    cache, lookup = cache_from_fixture(fixture, now=clock)
    queried = digits_only(cnpj) or cnpj
    if lookup is not None and lookup.hit:
        # Bind the fixture cache to the private CNPJ without storing it in the fixture file.
        cache.put(
            queried,
            lookup.payload or {},
            stored_at=lookup.stored_at or clock,
            expires_at=lookup.expires_at or clock,
        )
        lookup = cache.get(queried, now=clock)
    return produce(
        queried,
        transport=transport,
        clock=clock,
        ttl_seconds=ttl,
        cache=cache,
        cache_lookup=lookup,
    )


def _cmd_replay(args: argparse.Namespace) -> int:
    payload = replay_fixture(args.fixture, cnpj=args.cnpj, ttl_seconds=args.ttl_seconds)
    if args.out:
        _write_json(Path(args.out), payload)
    _print(
        {
            "schema": payload["schema"],
            "schema_version": payload["schema_version"],
            "aggregate_state": payload["aggregate_state"],
            "query_id": payload["query_id"],
            "content_hash": payload["content_hash"],
            "not_legal_conclusion": payload["not_legal_conclusion"],
            "as_of": payload["as_of"],
            "expires_at": payload["expires_at"],
            "freshness": payload["freshness"],
            "sources": {
                source_id: {
                    "status": source["status"],
                    "coverage_complete": source["coverage_complete"],
                    "pages_fetched": source["pages_fetched"],
                    "pages_expected": source["pages_expected"],
                    "as_of": source["as_of"],
                }
                for source_id, source in payload["sources"].items()
            },
            "record_count": len(payload["records"]),
        }
    )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    errors = validate_payload(payload)
    ok = not errors and payload.get("schema_version") == SCHEMA_VERSION
    _print({"ok": ok, "errors": errors, "schema": payload.get("schema")})
    return 0 if ok else 2


def _cmd_export_consumer(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    manifest = write_consumer_export(payload, args.out)
    _print({"ok": True, **manifest})
    return 0


def _cmd_live(args: argparse.Namespace) -> int:
    transport = HttpTransport()
    payload = produce(digits_only(args.cnpj) or args.cnpj, transport=transport)
    if args.out:
        _write_json(Path(args.out), payload)
    _print(
        {
            "schema": payload["schema"],
            "aggregate_state": payload["aggregate_state"],
            "content_hash": payload["content_hash"],
            "live": True,
        }
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed CEIS/CNEP public-read-integrity producer.")
    sub = parser.add_subparsers(dest="command", required=True)

    replay = sub.add_parser("replay", help="Replay a captured fixture (default CI path).")
    replay.add_argument("--fixture", required=True)
    replay.add_argument("--cnpj", required=True, help="Private CNPJ digits. Never written to public fixtures.")
    replay.add_argument("--out", default=None)
    replay.add_argument("--ttl-seconds", type=int, default=None)
    replay.set_defaults(func=_cmd_replay)

    validate = sub.add_parser("validate", help="Validate a private payload against the contract.")
    validate.add_argument("--payload", required=True)
    validate.set_defaults(func=_cmd_validate)

    export = sub.add_parser("export-consumer", help="Write SELECT-only web-cfg#156 fixture. Not live.")
    export.add_argument("--payload", required=True)
    export.add_argument("--out", required=True)
    export.set_defaults(func=_cmd_export_consumer)

    live = sub.add_parser("live", help="Live Portal da Transparência (not the CI bar).")
    live.add_argument("--cnpj", required=True)
    live.add_argument("--out", default=None)
    live.set_defaults(func=_cmd_live)

    args = parser.parse_args(argv)
    return int(args.func(args))
