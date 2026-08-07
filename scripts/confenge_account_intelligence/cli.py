"""CLI: single CNPJ or batch JSONL → confenge-account-intelligence-v1 JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from scripts.confenge_account_intelligence.catalog import default_catalog_path, load_catalog
from scripts.confenge_account_intelligence.pipeline import (
    build_dossier,
    process_batch,
    resolve_cnpj_from_records,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
        if not isinstance(obj, dict):
            raise SystemExit(f"JSONL row must be object at {path}:{line_no}")
        rows.append(obj)
    return rows


def _load_input(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return _load_jsonl(path)
    data = _load_json(path)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        # Allow wrapper {"records": [...]} or single company
        if isinstance(data.get("records"), list):
            return [x for x in data["records"] if isinstance(x, dict)]
        return [data]
    raise SystemExit(f"Unsupported input shape in {path}")


def _write_jsonl(rows: list[dict[str, Any]], stream: TextIO) -> None:
    for row in rows:
        stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.confenge_account_intelligence",
        description=(
            "CONFENGE account-intelligence service router. "
            "Reads company JSON/JSONL and emits confenge-account-intelligence-v1 JSONL."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Process one company JSON or a batch JSONL")
    run.add_argument(
        "--input",
        "-i",
        type=Path,
        required=True,
        help="Path to company JSON, list JSON, or JSONL",
    )
    run.add_argument(
        "--cnpj",
        type=str,
        default=None,
        help="Optional: select a single CNPJ from the input file",
    )
    run.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output JSONL path (default: stdout)",
    )
    run.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Reference date YYYY-MM-DD (default: record.as_of or today)",
    )
    run.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help=f"Catalog YAML (default: {default_catalog_path()})",
    )
    run.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Enable FS cache under this directory (cnpj_root+source_hash+as_of)",
    )
    run.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Batch concurrency limit (default: 4)",
    )
    run.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print single JSON object instead of JSONL (only for one record)",
    )

    cat = sub.add_parser("catalog", help="Print catalog version and service ids")
    cat.add_argument("--catalog", type=Path, default=None)

    return p


def cmd_catalog(args: argparse.Namespace) -> int:
    path = str(args.catalog) if args.catalog else None
    catalog = load_catalog(path)
    payload = {
        "catalog_id": catalog.get("catalog_id"),
        "catalog_version": catalog.get("catalog_version") or catalog.get("version"),
        "version_date": catalog.get("version_date"),
        "service_ids": [s.get("service_id") for s in catalog.get("services") or []],
        "service_count": len(catalog.get("services") or []),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    records = _load_input(args.input)
    if args.cnpj:
        match = resolve_cnpj_from_records(records, args.cnpj)
        if match is None:
            print(f"CNPJ not found in input: {args.cnpj}", file=sys.stderr)
            return 2
        records = [match]

    catalog_path = str(args.catalog) if args.catalog else None
    catalog = load_catalog(catalog_path)
    use_cache = args.cache_dir is not None
    kwargs: dict[str, Any] = {
        "catalog": catalog,
        "as_of": args.as_of,
        "use_cache": use_cache,
        "cache_dir": args.cache_dir,
    }

    if len(records) == 1:
        dossiers = [build_dossier(records[0], **kwargs)]
    else:
        dossiers = process_batch(records, max_workers=args.max_workers, **kwargs)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as fh:
            if args.pretty and len(dossiers) == 1:
                fh.write(json.dumps(dossiers[0], ensure_ascii=False, indent=2, default=str) + "\n")
            else:
                _write_jsonl(dossiers, fh)
    else:
        if args.pretty and len(dossiers) == 1:
            print(json.dumps(dossiers[0], ensure_ascii=False, indent=2, default=str))
        else:
            _write_jsonl(dossiers, sys.stdout)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "catalog":
        return cmd_catalog(args)
    if args.command == "run":
        return cmd_run(args)
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
