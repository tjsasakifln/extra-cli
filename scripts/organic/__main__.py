"""CLI: python -m scripts.organic --pseo-dir DIR --out FILE [--gsc-dir DIR]"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def _load_gsc_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Organic Opportunity Engine (extra-cli)")
    p.add_argument(
        "--pseo-dir",
        required=True,
        help="Directory with pSEO export JSON (markets.json, problem_service.json, …)",
    )
    p.add_argument(
        "--out",
        default="-",
        help="Output SEO_OPPORTUNITIES.json path, or - for stdout",
    )
    p.add_argument(
        "--gsc-dir",
        default=None,
        help="Optional GSC export dir with Consultas.csv and Paginas.csv",
    )
    p.add_argument("--as-of", default=None, help="ISO date cut for provenance")
    args = p.parse_args(argv)

    gsc_q: list[dict] = []
    gsc_p: list[dict] = []
    if args.gsc_dir:
        gdir = Path(args.gsc_dir)
        gsc_q = _load_gsc_csv(gdir / "Consultas.csv")
        gsc_p = _load_gsc_csv(gdir / "Paginas.csv")

    # Late import so --help works without heavy deps
    from scripts.organic.engine import run_engine

    out_path = None if args.out == "-" else args.out
    doc = run_engine(
        pseo_dir=args.pseo_dir,
        out_path=out_path,
        gsc_queries=gsc_q or None,
        gsc_pages=gsc_p or None,
        as_of=args.as_of,
    )
    # Strip non-serializable / internal
    public = {k: v for k, v in doc.items() if not k.startswith("_")}
    if args.out == "-":
        json.dump(public, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(
            json.dumps(
                {
                    "ok": True,
                    "out": args.out,
                    "total": public.get("counts", {}).get("total"),
                    "bofu": public.get("counts", {}).get("bofu"),
                    "data_driven": public.get("counts", {}).get("data_driven"),
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
