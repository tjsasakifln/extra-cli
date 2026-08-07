"""CLI: national B2G construction universe for CONFENGE.

Examples
--------
# Full national scale (production — requires datalake DSN):
python3 -m scripts.confenge_universe build \\
  --out output/confenge_universe \\
  --dsn \"$LOCAL_DATALAKE_DSN\"

# Fixture / offline:
python3 -m scripts.confenge_universe build \\
  --out /tmp/universe_out \\
  --csv tests/fixtures/confenge_universe/contracts_sample.csv \\
  --dnc tests/fixtures/confenge_universe/dnc.txt \\
  --as-of 2026-08-01

# Diagnostic sample (NOT full-scale proof):
python3 -m scripts.confenge_universe build \\
  --out output/confenge_universe_sample \\
  --dsn \"$LOCAL_DATALAKE_DSN\" \\
  --max-rows 50000

Outputs
-------
- confenge-universe-v1.jsonl
- confenge-universe-manifest-v1.json

Priority score orders the queue only; it never removes a legitimate
construction firm from the universe. DNC is dominant for outreach.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from scripts.confenge_universe import DEFAULT_JSONL_NAME, DEFAULT_MANIFEST_NAME, MODULE_VERSION
from scripts.confenge_universe.pipeline import run_universe_build
from scripts.confenge_universe.source import mask_dsn


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m scripts.confenge_universe",
        description=(
            "Build the canonical national universe of private construction/"
            "engineering companies active in public contracts (CONFENGE)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--version", action="version", version=f"confenge_universe {MODULE_VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser(
        "build",
        help="Stream contracts → root dedupe → construction evidence → JSONL+manifest",
    )
    b.add_argument(
        "--out",
        required=True,
        help="Output directory for confenge-universe-v1.jsonl + manifest",
    )
    b.add_argument(
        "--dsn",
        default=None,
        help="Postgres DSN for pncp_supplier_contracts (or set LOCAL_DATALAKE_DSN)",
    )
    b.add_argument(
        "--csv",
        default=None,
        help="Offline CSV of contracts (fixture / diagnostic)",
    )
    b.add_argument(
        "--as-of",
        default=None,
        help="Reference date YYYY-MM-DD (default: today)",
    )
    b.add_argument(
        "--batch-size",
        type=int,
        default=2000,
        help="Keyset batch size (bounded memory)",
    )
    b.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help=(
            "Diagnostic row cap. Omit for full-scale national production. "
            "When set, manifest records sampling and does NOT claim full population."
        ),
    )
    b.add_argument(
        "--min-contract-value",
        type=float,
        default=0.0,
        help="Optional soft floor on valor_total (default 0 = all contracts)",
    )
    b.add_argument("--uf", default=None, help="Optional UF filter (diagnostic)")
    b.add_argument(
        "--dnc",
        default=None,
        help="Path to DNC list (txt/json/jsonl of CNPJ14 or roots)",
    )
    b.add_argument(
        "--no-independent-brand",
        action="store_true",
        help="Disable independent decision-brand split; always collapse by CNPJ root",
    )
    b.add_argument(
        "--result-json",
        default=None,
        help="Optional path to write full run result JSON (counts + paths)",
    )
    return p


def cmd_build(args: argparse.Namespace) -> int:
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    if not args.dsn and not args.csv:
        # resolve_source will try env; if missing, fail with clear message
        pass
    try:
        result = run_universe_build(
            as_of=as_of,
            dsn=args.dsn,
            csv_path=args.csv,
            out_dir=args.out,
            batch_size=args.batch_size,
            max_rows=args.max_rows,
            min_contract_value=args.min_contract_value,
            uf=args.uf,
            dnc_path=args.dnc,
            enable_independent_brand=not args.no_independent_brand,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    counts = result.get("counts") or {}
    print(
        f"[confenge_universe] status={result.get('status')} "
        f"eligibles={counts.get('eligibles')} exclusions={counts.get('exclusions')} "
        f"input_roots={counts.get('input_supplier_roots')} "
        f"contracts={counts.get('input_contract_rows')} "
        f"recon_ok={result.get('reconciliation_ok')} "
        f"jsonl={result.get('jsonl_path')} "
        f"manifest={result.get('manifest_path')}"
    )
    if args.dsn:
        print(f"  dsn={mask_dsn(args.dsn)}")
    if args.max_rows is not None:
        print(
            "  NOTE: --max-rows set — this run is a diagnostic sample, "
            "not full-scale population proof. Full-scale: omit --max-rows."
        )
    else:
        print(
            f"  outputs: {DEFAULT_JSONL_NAME} + {DEFAULT_MANIFEST_NAME} "
            f"under {args.out}"
        )

    if args.result_json:
        path = Path(args.result_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        slim: dict[str, Any] = {
            k: result[k]
            for k in (
                "status",
                "as_of",
                "repo_sha",
                "jsonl_path",
                "manifest_path",
                "counts",
                "reconciliation_ok",
            )
            if k in result
        }
        path.write_text(
            json.dumps(slim, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )

    return 0 if result.get("status") == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "build":
        return cmd_build(args)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
