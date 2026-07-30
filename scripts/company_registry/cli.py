"""CLI for official company registry lifecycle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.company_registry.activate import activate_release, rollback_release, validate_load
from scripts.company_registry.commercial_bridge import (
    fail_closed_commercial_precheck,
    publish_matches_to_supplier_registry,
)
from scripts.company_registry.coverage import compute_coverage
from scripts.company_registry.diff import diff_releases
from scripts.company_registry.downloader import download_file
from scripts.company_registry.health import health_report
from scripts.company_registry.loader import load_jsonl_selective, load_zip_into_db
from scripts.company_registry.lookup import lookup_cnpj, read_active_pointer
from scripts.company_registry.manifest import load_manifest, save_manifest, set_status
from scripts.company_registry.models import ReleaseStatus
from scripts.company_registry.outcome_ledger import feedback_metrics, record_transition
from scripts.company_registry.paths import db_path_for_release, ensure_layout, raw_dir
from scripts.company_registry.refresh import refresh
from scripts.company_registry.release_discovery import discover_release
from scripts.company_registry.selective_fetch import fetch_interest_jsonl


def _print(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def cmd_discover(_args: argparse.Namespace) -> int:
    m = discover_release()
    save_manifest(m)
    _print(m)
    return 0 if m.get("status") == "DISCOVERED" else 2


def cmd_download(args: argparse.Namespace) -> int:
    ensure_layout()
    m = discover_release() if not args.release_id else load_manifest(args.release_id)
    if not m:
        _print({"ok": False, "error": "manifest_missing"})
        return 2
    release_id = m["release_id"]
    set_status(m, ReleaseStatus.DOWNLOADING.value)
    save_manifest(m)
    files = (m.get("discovery") or {}).get("files") or []
    raw = raw_dir(release_id)
    raw.mkdir(parents=True, exist_ok=True)
    results = []
    for f in files:
        dest = raw / f["file_name"]
        if not f.get("url"):
            continue
        res = download_file(f["url"], dest)
        results.append(res)
        if res.get("ok"):
            m.setdefault("sha256", {})[f["file_name"]] = res.get("sha256")
            m.setdefault("content_lengths", {})[f["file_name"]] = res.get("size_bytes")
            m.setdefault("files_downloaded", []).append(f["file_name"])
    ok = any(r.get("ok") for r in results) if results else False
    set_status(m, ReleaseStatus.DOWNLOADED.value if ok else ReleaseStatus.FAILED.value)
    save_manifest(m)
    _print({"ok": ok, "results": results, "manifest": m})
    return 0 if ok else 2


def cmd_validate_raw(args: argparse.Namespace) -> int:
    from scripts.company_registry.integrity import validate_downloaded_file

    release_id = args.release_id
    raw = raw_dir(release_id)
    reports = []
    for z in sorted(raw.glob("*.zip")):
        reports.append({"file": z.name, **validate_downloaded_file(z)})
    ok = bool(reports) and all(r["ok"] for r in reports)
    _print({"ok": ok, "reports": reports})
    return 0 if ok else 2


def cmd_load(args: argparse.Namespace) -> int:
    release_id = args.release_id
    db = db_path_for_release(release_id, staging=True)
    if db.exists() and args.clean:
        db.unlink()
    interest = None
    if args.interest_file:
        interest = {
            line.strip()
            for line in Path(args.interest_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    if args.jsonl:
        res = load_jsonl_selective(args.jsonl, db, source_label=args.source_label)
        _print(res)
        return 0 if res.get("ok") else 2
    raw = Path(args.raw_dir) if args.raw_dir else raw_dir(release_id)
    reports = []
    for z in sorted(raw.glob("*.zip")):
        reports.append(
            load_zip_into_db(
                z,
                db,
                interest_cnpjs=interest,
                interest_roots={c[:8] for c in interest} if interest else None,
            )
        )
    ok = any(r.get("ok") for r in reports)
    m = load_manifest(release_id) or {"release_id": release_id}
    m["row_counts"] = {"loads": reports}
    set_status(m, ReleaseStatus.LOADING.value if ok else ReleaseStatus.FAILED.value)
    save_manifest(m)
    _print({"ok": ok, "loads": reports})
    return 0 if ok else 2


def cmd_validate_load(args: argparse.Namespace) -> int:
    res = validate_load(args.release_id, min_establishments=args.min_rows)
    _print(res)
    return 0 if res.get("ok") else 2


def cmd_activate(args: argparse.Namespace) -> int:
    res = activate_release(args.release_id, min_establishments=args.min_rows, force=args.force)
    _print(res)
    return 0 if res.get("ok") else 2


def cmd_rollback(args: argparse.Namespace) -> int:
    res = rollback_release(args.release_id)
    _print(res)
    return 0 if res.get("ok") else 2


def cmd_refresh(args: argparse.Namespace) -> int:
    interest = None
    if args.interest_file:
        interest = [
            line.strip()
            for line in Path(args.interest_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    res = refresh(
        force=args.force,
        interest_cnpjs=interest,
        jsonl_path=args.jsonl,
        local_raw_dir=args.raw_dir,
        source_label=args.source_label,
    )
    _print(res)
    return 0 if res.get("ok") else 2


def cmd_coverage(args: argparse.Namespace) -> int:
    cnpjs = []
    if args.cnpj_file:
        cnpjs = [
            line.strip()
            for line in Path(args.cnpj_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    top20 = []
    if args.top20_file:
        top20 = [
            line.strip()
            for line in Path(args.top20_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    res = compute_coverage(cnpjs, top20=top20, release_id=args.release_id)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _print(res)
    return 0 if res.get("gates", {}).get("registry_available") else 2


def cmd_diff(args: argparse.Namespace) -> int:
    res = diff_releases(args.old, args.new)
    _print(res)
    return 0 if res.get("ok") else 2


def cmd_health(args: argparse.Namespace) -> int:
    res = health_report(smoke_cnpj=args.cnpj)
    _print(res)
    return 0 if res.get("ok") else 2


def cmd_lookup(args: argparse.Namespace) -> int:
    rec = lookup_cnpj(args.cnpj, release_id=args.release_id)
    _print(rec.as_dict())
    return 0 if rec.official_match_status == "MATCHED" else 1


def cmd_publish(args: argparse.Namespace) -> int:
    from scripts.commercial_leads.dbutil import connect

    cnpjs = [
        line.strip()
        for line in Path(args.cnpj_file).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    conn = connect(args.dsn)
    try:
        res = publish_matches_to_supplier_registry(
            conn, cnpjs, source=args.source_label
        )
    finally:
        conn.close()
    _print(res)
    return 0 if res.get("ok") else 2


def cmd_precheck(_args: argparse.Namespace) -> int:
    res = fail_closed_commercial_precheck()
    _print(res)
    return 0 if res.get("ok") else 2


def cmd_selective_fetch(args: argparse.Namespace) -> int:
    cnpjs = [
        line.strip()
        for line in Path(args.cnpj_file).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    res = fetch_interest_jsonl(
        cnpjs,
        args.out,
        max_workers=args.workers,
        limit=args.limit,
    )
    _print(res)
    return 0 if res.get("ok") else 2


def cmd_outcome(args: argparse.Namespace) -> int:
    if args.action == "record":
        res = record_transition(
            cnpj14=args.cnpj,
            to_state=args.state,
            actor=args.actor,
            human_confirmed=args.human_confirmed,
            channel=args.channel,
            campaign=args.campaign,
            observation=args.observation,
            rejection_or_loss_reason=args.reason,
            registry_release_id=(read_active_pointer() or {}).get("release_id"),
        )
        _print(res)
        return 0
    if args.action == "metrics":
        _print(feedback_metrics())
        return 0
    _print({"error": "unknown_action"})
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m scripts.company_registry")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("discover-release").set_defaults(func=cmd_discover)
    d = sub.add_parser("download")
    d.add_argument("--release-id")
    d.set_defaults(func=cmd_download)

    vr = sub.add_parser("validate-raw")
    vr.add_argument("--release-id", required=True)
    vr.set_defaults(func=cmd_validate_raw)

    ld = sub.add_parser("load")
    ld.add_argument("--release-id", required=True)
    ld.add_argument("--raw-dir")
    ld.add_argument("--jsonl")
    ld.add_argument("--interest-file")
    ld.add_argument("--source-label", default="rfb_public_cadastral")
    ld.add_argument("--clean", action="store_true")
    ld.set_defaults(func=cmd_load)

    vl = sub.add_parser("validate-load")
    vl.add_argument("--release-id", required=True)
    vl.add_argument("--min-rows", type=int, default=1)
    vl.set_defaults(func=cmd_validate_load)

    ac = sub.add_parser("activate")
    ac.add_argument("--release-id", required=True)
    ac.add_argument("--min-rows", type=int, default=1)
    ac.add_argument("--force", action="store_true")
    ac.set_defaults(func=cmd_activate)

    rb = sub.add_parser("rollback")
    rb.add_argument("--release-id")
    rb.set_defaults(func=cmd_rollback)

    rf = sub.add_parser("refresh")
    rf.add_argument("--force", action="store_true")
    rf.add_argument("--jsonl")
    rf.add_argument("--raw-dir")
    rf.add_argument("--interest-file")
    rf.add_argument("--source-label", default="rfb_public_cadastral")
    rf.set_defaults(func=cmd_refresh)

    cv = sub.add_parser("coverage")
    cv.add_argument("--cnpj-file", required=True)
    cv.add_argument("--top20-file")
    cv.add_argument("--release-id")
    cv.add_argument("--out")
    cv.set_defaults(func=cmd_coverage)

    df = sub.add_parser("diff")
    df.add_argument("--old", required=True)
    df.add_argument("--new", required=True)
    df.set_defaults(func=cmd_diff)

    h = sub.add_parser("health")
    h.add_argument("--cnpj")
    h.set_defaults(func=cmd_health)

    lk = sub.add_parser("lookup")
    lk.add_argument("--cnpj", required=True)
    lk.add_argument("--release-id")
    lk.set_defaults(func=cmd_lookup)

    pub = sub.add_parser("publish-supplier-registry")
    pub.add_argument("--dsn", required=True)
    pub.add_argument("--cnpj-file", required=True)
    pub.add_argument("--source-label", default="rfb_public_cadastral")
    pub.set_defaults(func=cmd_publish)

    sub.add_parser("commercial-precheck").set_defaults(func=cmd_precheck)

    sf = sub.add_parser("selective-fetch")
    sf.add_argument("--cnpj-file", required=True)
    sf.add_argument("--out", required=True)
    sf.add_argument("--workers", type=int, default=4)
    sf.add_argument("--limit", type=int)
    sf.set_defaults(func=cmd_selective_fetch)

    oc = sub.add_parser("outcome")
    oc.add_argument("action", choices=["record", "metrics"])
    oc.add_argument("--cnpj")
    oc.add_argument("--state")
    oc.add_argument("--actor")
    oc.add_argument("--human-confirmed", action="store_true")
    oc.add_argument("--channel")
    oc.add_argument("--campaign")
    oc.add_argument("--observation")
    oc.add_argument("--reason")
    oc.set_defaults(func=cmd_outcome)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
