"""CLI: python -m scripts.linkage run|investigate|guard"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m scripts.linkage")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Execute linkage pipeline on isolated DSN")
    p_run.add_argument("--dsn", default=os.environ.get("LINKAGE_TEST_DSN") or os.environ.get("LOCAL_DATALAKE_DSN"))
    p_run.add_argument("--run-id")
    p_run.add_argument("--snapshot-id")
    p_run.add_argument("--snapshot-hash")
    p_run.add_argument("--contract-limit", type=int, default=50)
    p_run.add_argument("--max-opportunities", type=int, default=None)
    p_run.add_argument("--out", type=Path, help="Write result JSON")

    p_inv = sub.add_parser("investigate", help="Investigate opportunity from last/ given run")
    p_inv.add_argument("--dsn", default=os.environ.get("LINKAGE_TEST_DSN") or os.environ.get("LOCAL_DATALAKE_DSN"))
    p_inv.add_argument("--run-id", required=True)
    p_inv.add_argument("--opportunity-id", type=int, required=True)
    p_inv.add_argument("--dossier-dir", type=Path)

    p_g = sub.add_parser("guard", help="Isolation guard check")
    p_g.add_argument("--dsn", default=os.environ.get("LINKAGE_TEST_DSN") or os.environ.get("LOCAL_DATALAKE_DSN"))

    args = p.parse_args(argv)

    if args.cmd == "guard":
        from scripts.linkage.isolation import check_dsn

        chk = check_dsn(args.dsn)
        print(json.dumps(chk.as_dict(), indent=2))
        return 0 if chk.ok and not chk.production_touched else 2

    if args.cmd == "run":
        from scripts.linkage.pipeline import run_linkage

        if not args.dsn:
            print(json.dumps({"error": "missing_dsn"}), file=sys.stderr)
            return 2
        try:
            res = run_linkage(
                args.dsn,
                run_id=args.run_id,
                snapshot_id=args.snapshot_id,
                snapshot_hash=args.snapshot_hash,
                contract_limit_per_opp=args.contract_limit,
                max_opportunities=args.max_opportunities,
            )
        except RuntimeError as exc:
            print(json.dumps({"error": str(exc), "status": "ISOLATION_BLOCK"}), file=sys.stderr)
            return 3
        payload = res.as_dict()
        text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        print(text)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
        return 0 if res.status == "completed" else 1

    if args.cmd == "investigate":
        from scripts.linkage.dossier import build_dossier, write_dossier
        from scripts.linkage.isolation import assert_isolated
        from scripts.linkage.pipeline import connect, investigate_opportunity

        assert_isolated(args.dsn)
        conn = connect(args.dsn)
        try:
            inv = investigate_opportunity(conn, args.run_id, args.opportunity_id)
        finally:
            conn.close()
        dos = build_dossier(inv)
        print(json.dumps(dos, indent=2, ensure_ascii=False, default=str))
        if args.dossier_dir:
            paths = write_dossier(dos, args.dossier_dir)
            print(json.dumps({"written": paths}, indent=2), file=sys.stderr)
        return 0 if inv.get("status") == "OK" else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
