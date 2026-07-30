#!/usr/bin/env python3
"""CLI for procurement process public documents capability."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


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
    )
    _print({"count": summary["count"], "by_status": summary["by_status"]})
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
        )
        _print(run.to_dict() if hasattr(run, "to_dict") else run)
        status = getattr(run, "status", None)
        ok = status is not None and status.value in ("SUCCESS_NONZERO", "SUCCESS_ZERO")
        return 0 if ok else 1
    summary = collect_many(
        only_active=not args.all,
        limit=args.limit,
        since=args.since,
        until=args.until,
        max_processes=args.max_processes,
        download=not args.no_download,
    )
    _print({"count": summary["count"], "by_status": summary["by_status"]})
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    from scripts.process_documents.collect import backfill

    summary = backfill(since=args.since, until=args.until, limit=args.limit, download=not args.no_download)
    _print({"count": summary.get("count"), "by_status": summary.get("by_status"), "checkpoint": summary.get("checkpoint_uri")})
    return 0


def cmd_incremental(args: argparse.Namespace) -> int:
    from scripts.process_documents.collect import incremental

    summary = incremental(download=not args.no_download, limit=args.limit)
    _print({"count": summary.get("count"), "by_status": summary.get("by_status")})
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
    return 0 if summary.get("status") in ("SUCCESS_NONZERO", "SUCCESS_ZERO") else 1


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
    )
    _print(summary)
    return 0 if summary.get("documents", 0) >= 0 else 1


def cmd_show(args: argparse.Namespace) -> int:
    """Lookup documents by process/edital/contract id from run artifacts."""
    from scripts.process_documents.storage import DEFAULT_META_ROOT, ensure_roots

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
    pr.set_defaults(func=cmd_probe)

    c = sub.add_parser("collect", help="Live document collection")
    c.add_argument("--entity", default=None)
    c.add_argument("--all", action="store_true")
    c.add_argument("--limit", type=int, default=10)
    c.add_argument("--since", default=None)
    c.add_argument("--until", default=None)
    c.add_argument("--max-processes", type=int, default=8)
    c.add_argument("--no-download", action="store_true")
    c.set_defaults(func=cmd_collect)

    b = sub.add_parser("backfill", help="Resumable historical backfill")
    b.add_argument("--all", action="store_true")
    b.add_argument("--since", default=None)
    b.add_argument("--until", default=None)
    b.add_argument("--limit", type=int, default=20)
    b.add_argument("--no-download", action="store_true")
    b.set_defaults(func=cmd_backfill)

    inc = sub.add_parser("incremental", help="Incremental document refresh")
    inc.add_argument("--all", action="store_true")
    inc.add_argument("--limit", type=int, default=50)
    inc.add_argument("--no-download", action="store_true")
    inc.set_defaults(func=cmd_incremental)

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
    ms.set_defaults(func=cmd_multi_source_session)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
