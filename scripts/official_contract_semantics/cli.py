"""CLI for official contract semantic observations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.official_contract_semantics.constants import DEFAULT_LIVE_LIMIT, SCHEMA_VERSION
from scripts.official_contract_semantics.coverage import coverage_matrix
from scripts.official_contract_semantics.export_comparables import export_comparables_corpus
from scripts.official_contract_semantics.export_publication import export_publication_evidence
from scripts.official_contract_semantics.extract import extract_many_paths, extract_path
from scripts.official_contract_semantics.live import run_live_readonly
from scripts.official_contract_semantics.models import OfficialContractObservation, observation_from_mapping
from scripts.official_contract_semantics.persist import append_observations
from scripts.official_contract_semantics.reconcile import reconcile
from scripts.official_contract_semantics.serialize import load_json, load_jsonl, write_json, write_jsonl
from scripts.official_contract_semantics.validate import validate_many


def _print(payload: Any) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return 0


def _load_observations(path: Path) -> tuple[OfficialContractObservation, ...]:
    if path.suffix == ".jsonl":
        return tuple(observation_from_mapping(row) for row in load_jsonl(path))
    payload = load_json(path)
    if isinstance(payload, dict) and "observations" in payload:
        rows = payload["observations"]
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = [payload]
    return tuple(observation_from_mapping(row) for row in rows)


def _extract_inputs(paths: list[str]) -> Any:
    if len(paths) == 1:
        return extract_path(paths[0])
    return extract_many_paths(paths)


def cmd_extract(args: argparse.Namespace) -> int:
    result = _extract_inputs(args.input)
    payload = result.as_dict()
    if args.out:
        write_json(args.out, payload)
    return _print(payload)


def cmd_validate(args: argparse.Namespace) -> int:
    result = _extract_inputs(args.input)
    rows = [item.as_dict() for item in result.observations]
    if args.raw:
        payload = load_json(args.input[0]) if len(args.input) == 1 else None
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict) and "observations" in payload:
            rows = payload["observations"]
        elif isinstance(payload, dict):
            rows = [payload]
    accepted, rejected = validate_many(rows)
    document = {
        "schema": SCHEMA_VERSION,
        "accepted": [item.as_dict() for item in accepted],
        "rejected": list(rejected),
        "document_errors": [item.as_dict() for item in result.document_errors],
        "unavailabilities": [item.as_dict() for item in result.unavailabilities],
    }
    if args.out:
        write_json(args.out, document)
    return _print(document)


def cmd_reconcile(args: argparse.Namespace) -> int:
    observations = _load_observations(Path(args.input))
    reconciled = reconcile(observations)
    if args.store:
        reconciled, _digest = append_observations(args.store, reconciled)
    payload = {
        "schema": SCHEMA_VERSION,
        "observations": [item.as_dict() for item in reconciled],
        "coverage": coverage_matrix(reconciled),
    }
    if args.out:
        if str(args.out).endswith(".jsonl"):
            write_jsonl(args.out, [item.as_dict() for item in reconciled])
        else:
            write_json(args.out, payload)
    return _print(payload)


def cmd_export_comparables(args: argparse.Namespace) -> int:
    observations = reconcile(_load_observations(Path(args.input)))
    document = export_comparables_corpus(
        observations,
        as_of=args.as_of,
        case_id=args.case,
        focal_id=args.focal,
    )
    if args.out:
        write_json(args.out, document)
    return _print(document)


def cmd_export_publication(args: argparse.Namespace) -> int:
    observations = reconcile(_load_observations(Path(args.input)))
    document = export_publication_evidence(observations, as_of=args.as_of)
    if args.out:
        write_json(args.out, document)
    return _print(document)


def cmd_live(args: argparse.Namespace) -> int:
    manifest = run_live_readonly(
        dsn=args.dsn,
        limit=args.limit,
        out_dir=args.out,
        cache_dir=args.cache_dir,
        fetch_pages=not args.skip_pages,
        as_of=args.as_of,
    )
    printable = {key: value for key, value in manifest.items() if key != "observations"}
    printable["observation_ids"] = [item["observation_id"] for item in manifest.get("observations") or []]
    return _print(printable)


def cmd_pipeline(args: argparse.Namespace) -> int:
    extracted = _extract_inputs(args.input)
    accepted, rejected = validate_many([item.as_dict() for item in extracted.observations])
    reconciled = reconcile(accepted)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    extract_hash = write_json(out / "extract.json", extracted.as_dict())
    obs_hash = write_jsonl(out / "observations.jsonl", [item.as_dict() for item in reconciled])
    comparables = export_comparables_corpus(reconciled, as_of=args.as_of, case_id=args.case, focal_id=args.focal)
    publication = export_publication_evidence(reconciled, as_of=args.as_of)
    comp_hash = write_json(out / "export-comparables.json", comparables)
    pub_hash = write_json(out / "export-publication-evidence.json", publication)
    summary = {
        "schema": SCHEMA_VERSION,
        "accepted": len(accepted),
        "rejected": len(rejected),
        "rejections": list(rejected),
        "document_errors": [item.as_dict() for item in extracted.document_errors],
        "unavailabilities": [item.as_dict() for item in extracted.unavailabilities],
        "reconciled": len(reconciled),
        "coverage": coverage_matrix(reconciled),
        "artifact_sha256": {
            "extract.json": extract_hash,
            "observations.jsonl": obs_hash,
            "export-comparables.json": comp_hash,
            "export-publication-evidence.json": pub_hash,
        },
    }
    write_json(out / "pipeline-summary.json", summary)
    return _print(summary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m scripts.official_contract_semantics")
    sub = parser.add_subparsers(dest="command", required=True)

    extract = sub.add_parser("extract")
    extract.add_argument("--input", nargs="+", required=True)
    extract.add_argument("--out")
    extract.set_defaults(func=cmd_extract)

    validate = sub.add_parser("validate")
    validate.add_argument("--input", nargs="+", required=True)
    validate.add_argument("--out")
    validate.add_argument("--raw", action="store_true")
    validate.set_defaults(func=cmd_validate)

    recon = sub.add_parser("reconcile")
    recon.add_argument("--input", required=True)
    recon.add_argument("--out")
    recon.add_argument("--store")
    recon.set_defaults(func=cmd_reconcile)

    comparables = sub.add_parser("export-comparables")
    comparables.add_argument("--input", required=True)
    comparables.add_argument("--out")
    comparables.add_argument("--as-of", dest="as_of", default="2026-08-01")
    comparables.add_argument("--case", default="official_semantics_export")
    comparables.add_argument("--focal")
    comparables.set_defaults(func=cmd_export_comparables)

    publication = sub.add_parser("export-publication-evidence")
    publication.add_argument("--input", required=True)
    publication.add_argument("--out")
    publication.add_argument("--as-of", dest="as_of", default="2026-08-15T00:00:00+00:00")
    publication.set_defaults(func=cmd_export_publication)

    live = sub.add_parser("live-readonly")
    live.add_argument("--dsn")
    live.add_argument("--limit", type=int, default=DEFAULT_LIVE_LIMIT)
    live.add_argument("--out")
    live.add_argument("--cache-dir", dest="cache_dir")
    live.add_argument("--as-of", dest="as_of")
    live.add_argument("--skip-pages", action="store_true")
    live.set_defaults(func=cmd_live)

    pipeline = sub.add_parser("pipeline")
    pipeline.add_argument("--input", nargs="+", required=True)
    pipeline.add_argument("--out", required=True)
    pipeline.add_argument("--as-of", dest="as_of", default="2026-08-01")
    pipeline.add_argument("--case", default="official_semantics_export")
    pipeline.add_argument("--focal")
    pipeline.set_defaults(func=cmd_pipeline)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
