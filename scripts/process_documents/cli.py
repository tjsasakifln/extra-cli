#!/usr/bin/env python3
"""CLI for procurement process public documents capability."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.ops.multi_source_open_pack.pilot_gate import PilotScaleBlockedError


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def cmd_discover(args: argparse.Namespace) -> int:
    from scripts.process_documents.discovery import discover_all

    _, report = discover_all(persist=not args.no_persist, output_dir=args.output)
    slim = {k: v for k, v in report.items() if k != "entities"}
    slim["entity_sample"] = (report.get("entities") or [])[:3]
    _print(slim)
    return 0 if report.get("meets_100_percent") else 1


def cmd_classify_activity(args: argparse.Namespace) -> int:
    from scripts.process_documents.activity import classify_all_activity

    _, report = classify_all_activity(persist=not args.no_persist, output_dir=args.output, dsn=args.dsn)
    slim = {k: v for k, v in report.items() if k != "entities"}
    _print(slim)
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    from scripts.process_documents.collect import collect_many

    summary = collect_many(
        only_active=not args.all,
        limit=args.limit,
        download=False,
        max_processes=args.max_processes,
        multi_source=not args.single_source,
        rotation=not args.no_rotation,
        pilot_approval_path=args.pilot_approval,
    )
    _print(
        {
            "count": summary["count"],
            "by_status": summary["by_status"],
            "selection_policy": summary.get("selection_policy"),
            "multi_source": summary.get("multi_source"),
            "selected_canonical_ids": (summary.get("selected_canonical_ids") or [])[:20],
        }
    )
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    from scripts.process_documents.collect import collect_entity, collect_many

    if args.entity:
        run = collect_entity(
            args.entity,
            since=args.since,
            until=args.until,
            max_processes=args.max_processes,
            download=not args.no_download,
            multi_source=not args.single_source,
        )
        payload = run.to_dict() if hasattr(run, "to_dict") else run
        _print(payload)
        if isinstance(payload, dict):
            status = payload.get("status")
        else:
            st = getattr(run, "status", None)
            status = st.value if hasattr(st, "value") else st
        ok = status in ("SUCCESS_NONZERO", "SUCCESS_ZERO", "partial")
        return 0 if ok else 1
    summary = collect_many(
        only_active=not args.all,
        limit=args.limit,
        since=args.since,
        until=args.until,
        max_processes=args.max_processes,
        download=not args.no_download,
        multi_source=not args.single_source,
        rotation=not args.no_rotation,
        pilot_approval_path=args.pilot_approval,
    )
    _print(
        {
            "count": summary["count"],
            "by_status": summary["by_status"],
            "selection_policy": summary.get("selection_policy"),
            "multi_source": summary.get("multi_source"),
        }
    )
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    from scripts.process_documents.collect import backfill

    summary = backfill(
        since=args.since,
        until=args.until,
        limit=args.limit,
        download=not args.no_download,
        pilot_approval_path=args.pilot_approval,
    )
    _print({"count": summary.get("count"), "by_status": summary.get("by_status"), "checkpoint": summary.get("checkpoint_uri")})
    return 0


def cmd_incremental(args: argparse.Namespace) -> int:
    from scripts.process_documents.collect import incremental

    summary = incremental(
        download=not args.no_download,
        limit=args.limit,
        multi_source=not args.single_source,
        rotation=not args.no_rotation,
        drain=not args.no_drain,
        max_batches=args.max_batches,
        max_entities=args.max_entities,
        max_wall_seconds=args.max_wall_seconds,
        pilot_approval_path=args.pilot_approval,
    )
    _print(
        {
            "count": summary.get("count"),
            "by_status": summary.get("by_status"),
            "selection_policy": summary.get("selection_policy"),
            "multi_source": summary.get("multi_source"),
            "eligible_count": summary.get("eligible_count"),
            "overdue_count": summary.get("overdue_count"),
            "lag_cleared": summary.get("lag_cleared"),
            "drain_stop_reason": summary.get("drain_stop_reason"),
            "capacity_insufficient": summary.get("capacity_insufficient"),
            "batches": summary.get("batches"),
            "sla_alert_count": summary.get("sla_alert_count"),
            "selected_canonical_ids": (summary.get("selected_canonical_ids") or [])[:20],
        }
    )
    return 0


def cmd_queue_status(args: argparse.Namespace) -> int:
    from scripts.process_documents.discovery import load_discovery
    from scripts.process_documents.entity_queue import (
        build_sla_alerts,
        load_entity_queue,
        queue_summary,
    )
    from scripts.process_documents.statuses import ActivityStatus

    discoveries = load_discovery()
    targets = [d for d in discoveries if d.activity_status == ActivityStatus.ACTIVE.value]
    if not targets:
        targets = list(discoveries)
    queue = load_entity_queue()
    summary = queue_summary(targets, queue)
    alerts = build_sla_alerts(targets, queue)
    sample = []
    for d in targets[: args.limit]:
        e = queue.get(d.canonical_id)
        sample.append(
            {
                "canonical_id": d.canonical_id,
                "next_run_at": e.next_run_at if e else None,
                "last_attempt_at": e.last_attempt_at if e else None,
                "last_success_at": e.last_success_at if e else None,
                "consecutive_failures": e.consecutive_failures if e else 0,
                "attempt_count": e.attempt_count if e else 0,
                "last_status": e.last_status if e else None,
            }
        )
    _print(
        {
            "queue": summary,
            "sla_alert_count": len(alerts),
            "sla_alerts_sample": alerts[:20],
            "entity_sample": sample,
        }
    )
    return 0 if summary.get("lag_cleared") else 1


def cmd_ops_health(args: argparse.Namespace) -> int:
    from scripts.process_documents.discovery import load_discovery
    from scripts.process_documents.ops_health import collect_ops_health, emit_alerts_to_pipeline
    from scripts.process_documents.statuses import ActivityStatus

    discoveries = load_discovery()
    targets = [d for d in discoveries if d.activity_status == ActivityStatus.ACTIVE.value]
    report = collect_ops_health(discoveries=targets or discoveries, persist=not args.no_persist)
    if args.dispatch_alerts:
        report["dispatch"] = emit_alerts_to_pipeline(report.get("alerts") or [], dry_run=not args.live_alerts)
    slim = {k: v for k, v in report.items() if k not in {"sla_alerts_sample"}}
    slim["alerts_sample"] = (report.get("alerts") or [])[:15]
    _print(slim)
    return 0 if report.get("healthy") else 1


def cmd_daily_report(args: argparse.Namespace) -> int:
    from scripts.process_documents.daily_ops_report import build_daily_ops_report, list_daily_report_streak
    from scripts.process_documents.discovery import load_discovery
    from scripts.process_documents.statuses import ActivityStatus

    discoveries = load_discovery()
    targets = [d for d in discoveries if d.activity_status == ActivityStatus.ACTIVE.value]
    report = build_daily_ops_report(discoveries=targets or discoveries, day=args.day, persist=True)
    streak = list_daily_report_streak()
    _print({"report": report, "streak": streak})
    return 0


def cmd_backup_proof(args: argparse.Namespace) -> int:
    from scripts.process_documents.backup_restore_proof import run_backup_restore_proof

    report = run_backup_restore_proof(remote=args.remote)
    _print(report)
    return 0 if report.get("local_restore_proven") else 1


def cmd_process_cards(args: argparse.Namespace) -> int:
    import json
    from pathlib import Path

    from scripts.process_documents.process_card import build_cards_from_collect_summary
    from scripts.process_documents.storage import ensure_roots

    _, meta = ensure_roots()
    src = Path(args.from_manifest) if args.from_manifest else meta / "collect-batch-latest.json"
    if not src.is_file():
        _print({"error": f"missing manifest: {src}"})
        return 1
    summary = json.loads(src.read_text(encoding="utf-8"))
    report = build_cards_from_collect_summary(summary, persist=True)
    _print(report)
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    from scripts.process_documents.coverage import compute_operational_coverage, full_coverage_bundle

    if args.full:
        bundle, code = full_coverage_bundle(persist=True)
        _print(
            {
                "exit_code": code,
                "discovery_percent": bundle["discovery"].get("entity_source_discovery_coverage_percent"),
                "operational_percent": bundle["operational"].get("percent"),
                "recall_percent": bundle["recall"].get("percent"),
                "financial_percent": bundle["financial"].get("percent"),
                "completeness": {
                    k: v.get("percent") for k, v in (bundle["completeness"].get("metrics") or {}).items()
                },
            }
        )
        return code
    report = compute_operational_coverage(persist=True)
    _print(report)
    return 0 if report.get("meets_threshold") else 1


def cmd_process_recall(args: argparse.Namespace) -> int:
    from scripts.process_documents.coverage import compute_process_recall

    report = compute_process_recall(benchmark_path=args.benchmark, persist=True)
    _print(report)
    return 0 if report.get("meets_threshold") else 1


def cmd_financial(args: argparse.Namespace) -> int:
    from scripts.process_documents.coverage import compute_financial_coverage

    report = compute_financial_coverage(persist=True)
    _print(report)
    return 0 if report.get("meets_threshold") else 1


def cmd_completeness(args: argparse.Namespace) -> int:
    from scripts.process_documents.coverage import compute_completeness

    report = compute_completeness(persist=True)
    _print(report)
    metrics = report.get("metrics") or {}
    ok = all(m.get("meets_threshold") for m in metrics.values()) if metrics else False
    return 0 if ok else 1


def cmd_gaps(args: argparse.Namespace) -> int:
    from scripts.process_documents.coverage import compute_gaps

    report = compute_gaps(persist=True)
    _print({"active_gap_count": report.get("active_gap_count"), "sample": (report.get("active_gaps") or [])[:20]})
    return 0


def cmd_build_corpus(args: argparse.Namespace) -> int:
    from scripts.process_documents.corpus import build_corpus_from_runs

    manifest = build_corpus_from_runs(output_dir=args.output)
    _print(
        {
            "process_count": manifest.get("process_count"),
            "engineering_process_count": manifest.get("engineering_process_count"),
            "complete_envelope_count": manifest.get("complete_envelope_count"),
            "portal_family_count": manifest.get("portal_family_count"),
            "annotated_requirements_count": manifest.get("annotated_requirements_count"),
            "issue_137_unblock_allowed": manifest.get("issue_137_unblock_allowed"),
            "ready_to_submit_language_allowed": False,
        }
    )
    return 0 if manifest.get("issue_137_unblock_allowed") else 1


def cmd_sanitize(args: argparse.Namespace) -> int:
    from scripts.process_documents.sanitize import sanitize_corpus_dir

    report = sanitize_corpus_dir(Path(args.corpus))
    _print(report)
    return 0


def cmd_validate_corpus(args: argparse.Namespace) -> int:
    from scripts.process_documents.corpus import (
        MIN_ANNOTATED_REQUIREMENTS,
        MIN_COMPLETE_ENVELOPES,
        MIN_ENGINEERING,
        MIN_PORTAL_FAMILIES,
        MIN_PROCESSES,
    )

    path = Path(args.corpus)
    if path.is_dir():
        path = path / "corpus-manifest.json"
    if not path.is_file():
        print(json.dumps({"error": f"missing manifest: {path}"}))
        return 1
    manifest = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "processes": manifest.get("process_count", 0) >= MIN_PROCESSES,
        "engineering": manifest.get("engineering_process_count", 0) >= MIN_ENGINEERING,
        "envelopes": manifest.get("complete_envelope_count", 0) >= MIN_COMPLETE_ENVELOPES,
        "families": manifest.get("portal_family_count", 0) >= MIN_PORTAL_FAMILIES,
        "annotations": manifest.get("annotated_requirements_count", 0) >= MIN_ANNOTATED_REQUIREMENTS,
        "no_ready_to_submit": not manifest.get("ready_to_submit_language_allowed", False),
    }
    _print({"checks": checks, "manifest_summary": {k: manifest.get(k) for k in (
        "process_count",
        "engineering_process_count",
        "complete_envelope_count",
        "portal_family_count",
        "annotated_requirements_count",
    )}})
    return 0 if all(checks.values()) else 1


def cmd_harvest(args: argparse.Namespace) -> int:
    from scripts.process_documents.harvest_pncp import harvest_sc_window

    summary = harvest_sc_window(
        since=args.since,
        until=args.until,
        max_processes=args.max_processes,
        max_pages_per_modalidade=args.max_pages,
        download=not args.no_download,
    )
    _print({k: v for k, v in summary.items() if k != "documents"})
    return 0 if summary.get("status") in ("SUCCESS_NONZERO", "SUCCESS_ZERO") and summary.get("status") != "PARTIAL_CAPACITY_EXHAUSTED" else 1


def cmd_expand_zips(args: argparse.Namespace) -> int:
    from scripts.process_documents.expand_zips import expand_zip_documents

    summary = expand_zip_documents(
        max_zips=int(args.max_zips),
        max_members_per_zip=int(args.max_members),
    )
    _print(summary)
    return 0 if summary.get("expanded_documents", 0) >= 0 else 1


def cmd_multi_source_session(args: argparse.Namespace) -> int:
    from scripts.process_documents.multi_source_session import run_multi_source_session_campaign

    summary = run_multi_source_session_campaign(
        max_processes=int(args.max_processes),
        include_ciga_dom=not args.no_ciga_dom,
        include_origin_html=not args.no_html,
        include_sc_compras=not args.no_sc_compras,
    )
    _print(summary)
    return 0 if summary.get("documents", 0) >= 0 else 1


def cmd_show(args: argparse.Namespace) -> int:
    """Lookup documents by process/edital/contract id from run artifacts."""
    from scripts.process_documents.storage import ensure_roots

    _, meta = ensure_roots()
    q = (args.query or "").strip()
    hits = []
    runs_dir = meta / "runs"
    if runs_dir.is_dir():
        for result_path in runs_dir.glob("*/result.json"):
            data = json.loads(result_path.read_text(encoding="utf-8"))
            for doc in data.get("documents") or []:
                blob = json.dumps(doc, ensure_ascii=False)
                if q in blob or q == data.get("canonical_entity_id"):
                    hits.append(
                        {
                            "run_id": data.get("run_id"),
                            "entity": data.get("canonical_entity_id"),
                            "source": doc.get("source_id"),
                            "title": doc.get("original_title"),
                            "sha256": doc.get("sha256"),
                            "version": doc.get("version"),
                            "raw_uri": doc.get("raw_uri"),
                            "url": doc.get("download_url"),
                            "category": doc.get("document_category"),
                            "procurement_id": doc.get("procurement_id"),
                        }
                    )
    _print({"query": q, "count": len(hits), "documents": hits[:50]})
    return 0 if hits else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m scripts.process_documents")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("discover", help="Cadastral discovery for 1093 entities")
    d.add_argument("--all", action="store_true")
    d.add_argument("--output", type=Path, default=None)
    d.add_argument("--no-persist", action="store_true")
    d.set_defaults(func=cmd_discover)

    a = sub.add_parser("classify-activity", help="Independent activity classification")
    a.add_argument("--all", action="store_true")
    a.add_argument("--dsn", default=None)
    a.add_argument("--output", type=Path, default=None)
    a.add_argument("--no-persist", action="store_true")
    a.set_defaults(func=cmd_classify_activity)

    pr = sub.add_parser("probe", help="Probe sources without download")
    pr.add_argument("--all", action="store_true")
    pr.add_argument("--limit", type=int, default=10)
    pr.add_argument("--max-processes", type=int, default=3)
    pr.add_argument("--pilot-approval", type=Path, default=None)
    pr.add_argument(
        "--single-source",
        action="store_true",
        help="Opt out of multi-source (legacy preferred family only)",
    )
    pr.add_argument(
        "--no-rotation",
        action="store_true",
        help="Opt out of staleness rotation (legacy static sort)",
    )
    pr.set_defaults(func=cmd_probe)

    c = sub.add_parser("collect", help="Live document collection")
    c.add_argument("--entity", default=None)
    c.add_argument("--all", action="store_true")
    c.add_argument("--limit", type=int, default=10)
    c.add_argument("--since", default=None)
    c.add_argument("--until", default=None)
    c.add_argument("--max-processes", type=int, default=8)
    c.add_argument("--pilot-approval", type=Path, default=None)
    c.add_argument("--no-download", action="store_true")
    c.add_argument(
        "--single-source",
        action="store_true",
        help="Opt out of multi-source (legacy preferred family only)",
    )
    c.add_argument(
        "--no-rotation",
        action="store_true",
        help="Opt out of staleness rotation (legacy static sort)",
    )
    c.set_defaults(func=cmd_collect)

    b = sub.add_parser("backfill", help="Resumable historical backfill")
    b.add_argument("--all", action="store_true")
    b.add_argument("--since", default=None)
    b.add_argument("--until", default=None)
    b.add_argument("--limit", type=int, default=20)
    b.add_argument("--pilot-approval", type=Path, default=None)
    b.add_argument("--no-download", action="store_true")
    b.set_defaults(func=cmd_backfill)

    inc = sub.add_parser(
        "incremental",
        help="Incremental document refresh (daily: success-lag queue + multi-source + drain)",
    )
    inc.add_argument("--all", action="store_true")
    inc.add_argument("--limit", type=int, default=50, help="Entities per drain batch")
    inc.add_argument("--pilot-approval", type=Path, default=None)
    inc.add_argument("--no-download", action="store_true")
    inc.add_argument(
        "--single-source",
        action="store_true",
        help="Opt out of multi-source (legacy preferred family only)",
    )
    inc.add_argument(
        "--no-rotation",
        action="store_true",
        help="Opt out of success-lag rotation (legacy static sort)",
    )
    inc.add_argument(
        "--no-drain",
        action="store_true",
        help="Run a single batch only (do not continue until lag cleared / capacity exhausted)",
    )
    inc.add_argument("--max-batches", type=int, default=None)
    inc.add_argument("--max-entities", type=int, default=None)
    inc.add_argument("--max-wall-seconds", type=float, default=None)
    inc.set_defaults(func=cmd_incremental)

    qs = sub.add_parser("queue-status", help="Entity queue + SLA lag status")
    qs.add_argument("--limit", type=int, default=20)
    qs.set_defaults(func=cmd_queue_status)

    oh = sub.add_parser("ops-health", help="Audit dirs/env/disk/DB/SLA (timer ≠ healthy)")
    oh.add_argument("--no-persist", action="store_true")
    oh.add_argument("--dispatch-alerts", action="store_true")
    oh.add_argument("--live-alerts", action="store_true", help="Actually send (not dry-run)")
    oh.set_defaults(func=cmd_ops_health)

    dr = sub.add_parser("daily-report", help="Daily coverage/update report (7-day streak evidence)")
    dr.add_argument("--day", default=None)
    dr.set_defaults(func=cmd_daily_report)

    bp = sub.add_parser("backup-proof", help="Pack meta snapshot + local restore verify (+ optional remote)")
    bp.add_argument("--remote", default=None, help="rsync/scp target or set PROCESS_DOCUMENTS_BACKUP_REMOTE")
    bp.set_defaults(func=cmd_backup_proof)

    pc = sub.add_parser("process-cards", help="Build multi-source process cards from latest collect manifest")
    pc.add_argument("--from-manifest", default=None)
    pc.set_defaults(func=cmd_process_cards)

    cov = sub.add_parser("coverage", help="Operational coverage report")
    cov.add_argument("--full", action="store_true", help="Full multi-metric bundle + gate exit")
    cov.set_defaults(func=cmd_coverage)

    rec = sub.add_parser("process-recall", help="Process recall vs independent benchmark")
    rec.add_argument("--benchmark", default=None)
    rec.set_defaults(func=cmd_process_recall)

    fin = sub.add_parser("financial-coverage", help="Financial coverage ratio")
    fin.set_defaults(func=cmd_financial)

    comp = sub.add_parser("completeness", help="Document completeness metrics")
    comp.set_defaults(func=cmd_completeness)

    g = sub.add_parser("gaps", help="Nominal gaps for active entities")
    g.set_defaults(func=cmd_gaps)

    bc = sub.add_parser("build-corpus", help="Build bid_readiness public corpus manifest")
    bc.add_argument("--process", default=None, help="optional filter (reserved)")
    bc.add_argument("--output", default=None)
    bc.set_defaults(func=cmd_build_corpus)

    s = sub.add_parser("sanitize", help="Sanitize corpus text extracts")
    s.add_argument("--corpus", required=True)
    s.set_defaults(func=cmd_sanitize)

    v = sub.add_parser("validate-corpus", help="Validate corpus against minima")
    v.add_argument("--corpus", required=True)
    v.set_defaults(func=cmd_validate_corpus)

    sh = sub.add_parser("show", help="Show documents by process/edital/entity")
    sh.add_argument("query")
    sh.set_defaults(func=cmd_show)

    hv = sub.add_parser("harvest-pncp", help="Bulk live PNCP harvest (SC window) for corpus/proof")
    hv.add_argument("--since", default=None)
    hv.add_argument("--until", default=None)
    hv.add_argument("--max-processes", type=int, default=40)
    hv.add_argument("--max-pages", type=int, default=3)
    hv.add_argument("--no-download", action="store_true")
    hv.set_defaults(func=cmd_harvest)

    ez = sub.add_parser("expand-zips", help="Expand CAS ZIP packs into member documents")
    ez.add_argument("--max-zips", type=int, default=200)
    ez.add_argument("--max-members", type=int, default=40)
    ez.set_defaults(func=cmd_expand_zips)

    ms = sub.add_parser(
        "multi-source-session",
        help="Live multi-source collect for session/proposal/qualification packs",
    )
    ms.add_argument("--max-processes", type=int, default=150)
    ms.add_argument("--no-ciga-dom", action="store_true")
    ms.add_argument("--no-html", action="store_true")
    ms.add_argument("--no-sc-compras", action="store_true")
    ms.set_defaults(func=cmd_multi_source_session)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except PilotScaleBlockedError as exc:
        _print(
            {
                "terminal_state": "BLOCKED",
                "queue_mutated": False,
                "pilot_gate": exc.decision.to_dict(),
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
