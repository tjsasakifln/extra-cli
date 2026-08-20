"""CLI: python3 -m scripts.bid_readiness_public run --edital FILE --out ENVELOPE"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.bid_readiness_public.compose import load_authorized_manifest, produce
from scripts.bid_readiness_public.export import write_consumer_export
from scripts.bid_readiness_public.models import SCHEMA_VERSION, default_policy
from scripts.bid_readiness_public.redaction import public_envelope
from scripts.bid_readiness_public.schema import validate_payload


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is None:
        sys.stdout.write(text)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _print(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _optional_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value)


def run_from_args(args: argparse.Namespace) -> dict[str, Any]:
    edital = _optional_path(args.edital)
    planilha = _optional_path(args.planilha)
    documents = _optional_path(args.documents)
    acervo = _optional_path(args.acervo)
    requirements = _optional_path(args.requirements)
    if args.manifest:
        roles = load_authorized_manifest(Path(args.manifest))
        edital = roles.get("edital") or edital
        planilha = roles.get("planilha") or planilha
        documents = roles.get("documents") or documents
        acervo = roles.get("acervo") or acervo
        requirements = roles.get("requirements") or requirements
    entity = None
    if args.entity:
        entity = json.loads(Path(args.entity).read_text(encoding="utf-8"))
    policy = default_policy()
    if args.policy_version:
        policy["policy_version"] = args.policy_version
    work_dir = Path(args.work_dir)
    return produce(
        edital=edital,
        planilha=planilha,
        documents=documents,
        acervo=acervo,
        requirements=requirements,
        work_dir=work_dir,
        clock=args.as_of,
        policy=policy,
        source_access=args.source_access,
        entity=entity,
    )


def _cmd_run(args: argparse.Namespace) -> int:
    payload = run_from_args(args)
    if args.out:
        _write_json(Path(args.out), payload)
    if args.public_out:
        _write_json(Path(args.public_out), public_envelope(payload))
    _print(
        {
            "schema_version": payload["schema_version"],
            "overall_state": payload["overall_state"],
            "query_id": payload["query_id"],
            "content_hash": payload["content_hash"],
            "human_review_required": payload["human_review_required"],
            "publication_authorization": payload["publication_authorization"],
            "index_authorization": payload["index_authorization"],
            "not_legal_conclusion": payload["not_legal_conclusion"],
            "finding_count": len(payload.get("findings") or []),
            "source_access": payload["source_access"],
        }
    )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    errors = validate_payload(payload)
    ok = not errors and payload.get("schema_version") == SCHEMA_VERSION
    _print({"ok": ok, "errors": errors, "schema_version": payload.get("schema_version")})
    return 0 if ok else 2


def _cmd_export_consumer(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    manifest = write_consumer_export(payload, args.out)
    _print({"ok": True, **manifest})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.bid_readiness_public",
        description="Private public-read-bid-readiness/1.0 producer (manual-first, no upload).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Compose engines from explicit local paths or an authorized manifest")
    run.add_argument("--edital", default=None)
    run.add_argument("--planilha", default=None)
    run.add_argument("--documents", default=None)
    run.add_argument("--acervo", default=None)
    run.add_argument("--requirements", default=None)
    run.add_argument("--manifest", default=None, help="Authorized manifest with relative paths")
    run.add_argument("--entity", default=None)
    run.add_argument("--as-of", default=None)
    run.add_argument("--policy-version", default=None)
    run.add_argument("--source-access", default="private_local", choices=("private_local", "redacted_fixture"))
    run.add_argument("--work-dir", required=True)
    run.add_argument("--out", default=None)
    run.add_argument("--public-out", default=None)
    run.set_defaults(func=_cmd_run)

    validate = sub.add_parser("validate", help="Validate a produced envelope")
    validate.add_argument("--payload", required=True)
    validate.set_defaults(func=_cmd_validate)

    export = sub.add_parser("export-consumer", help="Write SELECT-only web-cfg#155 fixture")
    export.add_argument("--payload", required=True)
    export.add_argument("--out", required=True)
    export.set_defaults(func=_cmd_export_consumer)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
