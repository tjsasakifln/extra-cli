"""LI-8 (minimo) — CLI ``build`` e ``verify``.

Fora de escopo desta story (ficam para a story 2): ``replay`` e ``explain-fit``.

    python3 -m scripts.confenge_live_intelligence.cli build --effective-date 2026-09-02
    python3 -m scripts.confenge_live_intelligence.cli verify --snapshot-id LI-...

Nao ha kill switch: a forma de pausar o motor e nao invocar este CLI. A decisao
de NAO reusar ``truth_plane_kill_switch`` do outbound e deliberada e esta
registrada no ADR-040 (acoplaria os dois motores, violando o isolamento que e a
razao de ser deste pacote).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime

from scripts.confenge_live_intelligence.producer import build_snapshot
from scripts.confenge_live_intelligence.verifier import (
    LiveIntelligenceVerificationError,
    verify_snapshot,
)

DEFAULT_DSN = "postgresql://test:test@127.0.0.1:5433/extra_test"


def _dsn(explicit: str | None) -> str:
    return explicit or os.environ.get("LOCAL_DATALAKE_DSN") or DEFAULT_DSN


def _connect(dsn: str):  # pragma: no cover - fina camada de IO
    import psycopg2
    import psycopg2.extras

    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="confenge-live-intelligence")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="constroi e sela um snapshot as-of")
    build.add_argument("--effective-date", required=True, type=_parse_date)
    build.add_argument("--dsn", default=None)
    build.add_argument("--created-by", default="cli")

    verify = sub.add_parser("verify", help="re-deriva todos os hashes de um snapshot")
    verify.add_argument("--snapshot-id", required=True)
    verify.add_argument("--dsn", default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = _connect(_dsn(args.dsn))
    try:
        if args.command == "build":
            result = build_snapshot(
                conn,
                as_of=args.effective_date,
                created_by=args.created_by,
            )
            print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
            return 0 if result.state != "BLOCKED" else 2
        report = verify_snapshot(conn, args.snapshot_id)
        print(
            json.dumps(
                {
                    "snapshot_id": report.snapshot_id,
                    "state": report.state,
                    "checks": list(report.checks),
                    "verified_opportunities": report.verified_opportunities,
                    "verified_companies": report.verified_companies,
                    "verified_fits": report.verified_fits,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except LiveIntelligenceVerificationError as exc:
        print(f"VERIFY_FAILED: {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
