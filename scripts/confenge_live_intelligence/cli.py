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

from scripts.confenge_live_intelligence import public_policy as policy
from scripts.confenge_live_intelligence.events import generate_events
from scripts.confenge_live_intelligence.export import LiveIntelligenceExportError, export_bundle
from scripts.confenge_live_intelligence.producer import build_snapshot
from scripts.confenge_live_intelligence.verifier import (
    LiveIntelligenceVerificationError,
    verify_bundle,
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

    # LI-W2 Task 9 — bundle publico e feed de eventos.
    export = sub.add_parser("export", help="gera o bundle publico a partir de um snapshot selado")
    export.add_argument("--snapshot-id", required=True)
    export.add_argument("--out-dir", required=True)
    export.add_argument("--dsn", default=None)
    # REQ-001 — proveniencia REIVINDICADA. Default fail-closed `fixture`: rodar o
    # export contra um banco de teste/seed sem declarar nada produz um bundle
    # rotulado fixture, que o consumidor recusa por
    # `producer_status_not_official_live`. `official_live` e uma afirmacao
    # deliberada do operador sobre a origem dos dados, nunca um default.
    export.add_argument(
        "--catalog-mode",
        choices=list(policy.CATALOG_MODES),
        default=policy.DEFAULT_CATALOG_MODE,
        help="proveniencia declarada do bundle (default: fixture, fail-closed)",
    )
    export.add_argument(
        "--verify-bundle",
        action="store_true",
        help="prova o bundle SERIALIZADO em disco depois de escrever (AC5/AC6)",
    )

    events = sub.add_parser("events", help="deriva e persiste eventos por diff entre snapshots selados")
    events.add_argument("--snapshot-id", required=True)
    events.add_argument("--prev-snapshot-id", default=None)
    events.add_argument("--dsn", default=None)
    events.add_argument("--dry-run", action="store_true", help="nao persiste; apenas lista os eventos derivados")

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
        if args.command == "export":
            manifest = export_bundle(
                conn,
                snapshot_id=args.snapshot_id,
                out_dir=args.out_dir,
                catalog_mode=args.catalog_mode,
            )
            payload = {
                "snapshot_id": args.snapshot_id,
                "out_dir": args.out_dir,
                "catalog_mode": manifest["catalog_mode"],
                "official_live": manifest["official_live"],
                "data_state": manifest["data_state"],
                "coverage": manifest["coverage"],
                "manifest_hash": manifest["manifest_hash"],
                "files": len(manifest["index"]["opportunities"]) + len(manifest["index"]["companies"]),
            }
            if args.verify_bundle:
                bundle_report = verify_bundle(args.out_dir)
                payload["bundle_checks"] = list(bundle_report.checks)
                payload["bundle_files_verified"] = bundle_report.files_verified
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        if args.command == "events":
            derived = generate_events(
                conn,
                snapshot_id=args.snapshot_id,
                prev_snapshot_id=args.prev_snapshot_id,
                persist=not args.dry_run,
            )
            print(
                json.dumps(
                    {
                        "snapshot_id": args.snapshot_id,
                        "prev_snapshot_id": args.prev_snapshot_id,
                        "persisted": not args.dry_run,
                        "events": [
                            {
                                "event_id": e.event_id,
                                "event_type": e.event_type,
                                "subject_key": e.subject_key,
                                "prev_semantic_hash": e.prev_semantic_hash,
                                "semantic_hash": e.semantic_hash,
                            }
                            for e in derived
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        snapshot_report = verify_snapshot(conn, args.snapshot_id)
        print(
            json.dumps(
                {
                    "snapshot_id": snapshot_report.snapshot_id,
                    "state": snapshot_report.state,
                    "checks": list(snapshot_report.checks),
                    "verified_opportunities": snapshot_report.verified_opportunities,
                    "verified_companies": snapshot_report.verified_companies,
                    "verified_fits": snapshot_report.verified_fits,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except LiveIntelligenceVerificationError as exc:
        print(f"VERIFY_FAILED: {exc}", file=sys.stderr)
        return 2
    except LiveIntelligenceExportError as exc:
        # Fail-closed: `export_bundle` monta o bundle inteiro antes do primeiro
        # write, entao nao existe bundle parcial em disco quando isto dispara.
        print(f"EXPORT_FAILED: {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
