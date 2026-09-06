"""CLI for CONFENGE target-fit continuous refresh.

Commands:
  refresh / worker / reconcile / status / explain / requeue /
  set-mode / metrics / shadow-export
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from scripts.confenge_target_fit import MODULE_VERSION, TARGET_FIT_VERSION
from scripts.confenge_target_fit.cdc import company_from_any_cnpj
from scripts.confenge_target_fit.config import TargetFitRefreshConfig
from scripts.confenge_target_fit.db import connect
from scripts.confenge_target_fit.explain import explain_cnpj, format_explain
from scripts.confenge_target_fit.reconcile import run_reconcile
from scripts.confenge_target_fit.refresh import run_refresh
from scripts.confenge_target_fit.status import build_health, exit_code_for, metrics_snapshot
from scripts.confenge_target_fit.store import ensure_control_defaults, requeue_company, set_control
from scripts.confenge_target_fit.worker import run_worker_cycle, run_worker_loop


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.confenge_target_fit",
        description=(
            "CONFENGE target-fit continuous refresh — "
            f"{MODULE_VERSION} / classifier {TARGET_FIT_VERSION}"
        ),
    )
    p.add_argument("--dsn", default=None, help="State/source Postgres DSN")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--commercial-operation-id")
    p.add_argument("--commercial-operation-scope", choices=("stage", "cycle"))
    p.add_argument("--commercial-owner-id")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("refresh", help="CDC enqueue + optional worker drain")
    r.add_argument("--no-drain", action="store_true")
    r.add_argument("--max-batches", type=int, default=5)

    w = sub.add_parser("worker", help="Process dirty queue")
    w.add_argument("--loop", action="store_true", help="Long-running loop")
    w.add_argument("--max-batches", type=int, default=1)
    w.add_argument("--max-cycles", type=int, default=None)
    w.add_argument("--idle-sleep", type=float, default=15.0)

    rec = sub.add_parser("reconcile", help="National consistency sweep")
    rec.add_argument(
        "--max-enqueue",
        type=int,
        default=None,
        help=(
            "Diagnostic/smoke bound only — never commercial capacity. "
            "Omit for full national enqueue of all missing roots."
        ),
    )
    rec.add_argument(
        "--drain-worker",
        action="store_true",
        help="After enqueue, run worker batches (use with --max-worker-batches).",
    )
    rec.add_argument(
        "--max-worker-batches",
        type=int,
        default=0,
        help="Worker batches to drain after reconcile when --drain-worker is set.",
    )

    sub.add_parser("status", help="Healthcheck (nonzero exit if alert)")
    sub.add_parser("metrics", help="JSON metrics snapshot")

    ex = sub.add_parser("explain", help="Explain target-fit for a CNPJ")
    ex.add_argument("--cnpj", required=True)
    ex.add_argument("--json", action="store_true")

    rq = sub.add_parser("requeue", help="Force requeue a CNPJ")
    rq.add_argument("--cnpj", required=True)
    rq.add_argument("--priority", type=int, default=90)

    sm = sub.add_parser("set-mode", help="Set TARGET_FIT async mode")
    sm.add_argument(
        "mode",
        choices=["SHADOW", "ACTIVE", "CANARY", "AUTO_PAUSE"],
    )
    sm.add_argument("--clear-auto-pause", action="store_true")

    se = sub.add_parser("shadow-export", help="Export shadow-vs-current CSV")
    se.add_argument(
        "--out",
        default="artifacts/confenge/target-fit/shadow-vs-current.csv",
    )

    sub.add_parser("version", help="Print module / classifier versions")

    rc = sub.add_parser(
        "reclassify-insufficient",
        help=(
            "Downgrade SHADOW PROBABLE without positive ICP evidence to "
            "TARGET_INSUFFICIENT_EVIDENCE (idempotent)"
        ),
    )
    rc.add_argument("--dry-run", action="store_true")
    rc.add_argument("--limit", type=int, default=None, help="Optional candidate cap")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    cfg = TargetFitRefreshConfig.from_env()

    if args.cmd == "version":
        print(f"module={MODULE_VERSION}")
        print(f"classifier={TARGET_FIT_VERSION}")
        print(f"default_mode={cfg.async_mode}")
        return 0

    try:
        dsn = cfg.resolve_state_dsn(args.dsn)
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    if args.cmd == "refresh":
        from scripts.ops.confenge_commercial_mutex import (
            EXIT_AUTHORITY_BUSY,
            AuthorityError,
            acquire_stage_from_env,
        )

        try:
            with acquire_stage_from_env(
                "refresh",
                operation_id=args.commercial_operation_id,
                scope=args.commercial_operation_scope,
                owner_id=args.commercial_owner_id,
            ) as claim:
                stats = run_refresh(
                    dsn,
                    cfg=cfg,
                    drain_worker=not args.no_drain,
                    max_worker_batches=args.max_batches,
                )
                if not stats.error:
                    claim.complete(stats.as_dict())
        except AuthorityError as exc:
            print(f"AUTHORITY_REFUSED: {exc}", file=sys.stderr)
            return EXIT_AUTHORITY_BUSY
        print(json.dumps(stats.as_dict(), indent=2, default=str))
        return 1 if stats.error else 0

    if args.cmd == "worker":
        if args.loop:
            run_worker_loop(
                dsn,
                cfg=cfg,
                idle_sleep_seconds=args.idle_sleep,
                max_cycles=args.max_cycles,
            )
            return 0
        stats = run_worker_cycle(dsn, cfg=cfg, max_batches=args.max_batches)
        print(json.dumps(stats.as_dict(), indent=2, default=str))
        return 1 if stats.error else 0

    if args.cmd == "reconcile":
        from scripts.ops.confenge_commercial_mutex import (
            EXIT_AUTHORITY_BUSY,
            AuthorityError,
            acquire_stage_from_env,
        )

        try:
            with acquire_stage_from_env(
                "reconcile",
                operation_id=args.commercial_operation_id,
                scope=args.commercial_operation_scope,
                owner_id=args.commercial_owner_id,
            ) as claim:
                stats = run_reconcile(
                    dsn,
                    cfg=cfg,
                    max_enqueue=args.max_enqueue,
                    drain_worker=bool(getattr(args, "drain_worker", False)),
                    max_worker_batches=int(getattr(args, "max_worker_batches", 0) or 0),
                )
                if not stats.error:
                    claim.complete(stats.as_dict())
        except AuthorityError as exc:
            print(f"AUTHORITY_REFUSED: {exc}", file=sys.stderr)
            return EXIT_AUTHORITY_BUSY
        print(json.dumps(stats.as_dict(), indent=2, default=str))
        return 1 if stats.error else 0

    if args.cmd == "reclassify-insufficient":
        from scripts.confenge_target_fit.reclassify_insufficient import (
            reclassify_shadow_probable_without_evidence,
        )

        conn = connect(dsn, readonly=False)
        try:
            result = reclassify_shadow_probable_without_evidence(
                conn,
                dry_run=bool(args.dry_run),
                limit=args.limit,
            )
        finally:
            conn.close()
        print(json.dumps(result, indent=2, default=str))
        return 0

    if args.cmd == "status":
        report = build_health(dsn, cfg=cfg)
        print(report.format_human())
        return exit_code_for(report)

    if args.cmd == "metrics":
        print(json.dumps(metrics_snapshot(dsn), indent=2, default=str))
        return 0

    if args.cmd == "explain":
        data = explain_cnpj(dsn, args.cnpj)
        if args.json:
            print(json.dumps(data, indent=2, default=str))
        else:
            print(format_explain(data))
        return 0

    if args.cmd == "requeue":
        ck, raiz = company_from_any_cnpj(args.cnpj)
        conn = connect(dsn, readonly=False)
        try:
            ensure_control_defaults(conn)
            key = requeue_company(
                conn,
                company_key=ck,
                cnpj_raiz=raiz,
                priority=args.priority,
            )
            conn.commit()
        finally:
            conn.close()
        print(json.dumps({"company_key": ck, "idempotency_key": key}))
        return 0

    if args.cmd == "set-mode":
        conn = connect(dsn, readonly=False)
        try:
            ensure_control_defaults(conn)
            set_control(conn, "async_mode", {"mode": args.mode})
            if args.clear_auto_pause or args.mode != "AUTO_PAUSE":
                if args.clear_auto_pause:
                    set_control(
                        conn,
                        "auto_pause",
                        {"paused": False, "reason": None},
                    )
            if args.mode == "AUTO_PAUSE":
                set_control(
                    conn,
                    "auto_pause",
                    {"paused": True, "reason": "manual"},
                )
            conn.commit()
        finally:
            conn.close()
        print(json.dumps({"mode": args.mode}))
        return 0

    if args.cmd == "shadow-export":
        return _shadow_export(dsn, Path(args.out))

    parser.error(f"unknown command {args.cmd}")
    return 2


def _shadow_export(dsn: str, out: Path) -> int:
    import csv

    conn = connect(dsn, readonly=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT company_key, cnpj_raiz, shadow_class, shadow_confidence,
                       current_class, current_confidence, transition,
                       target_fit_version, source_watermark, computed_at
                FROM confenge_target_fit_shadow
                ORDER BY computed_at DESC
                """
            )
            rows = cur.fetchall() or []
    finally:
        conn.close()

    out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "company",
        "old",
        "new",
        "old_confidence",
        "new_confidence",
        "transition",
        "version",
        "watermark",
        "computed_at",
        "expected?",
    ]
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            old = r.get("current_class")
            new = r.get("shadow_class")
            expected = "yes" if old == new else "review"
            w.writerow(
                {
                    "company": r.get("company_key"),
                    "old": old,
                    "new": new,
                    "old_confidence": r.get("current_confidence"),
                    "new_confidence": r.get("shadow_confidence"),
                    "transition": r.get("transition"),
                    "version": r.get("target_fit_version"),
                    "watermark": r.get("source_watermark"),
                    "computed_at": r.get("computed_at"),
                    "expected?": expected,
                }
            )
    print(f"wrote {out} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
