"""Deterministic CLI for ranking publication candidates and evidence packs."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from scripts.contract_publication.engine import (
    build_packs,
    build_run_document,
    input_payload_hash,
    load_policy_file,
    load_snapshot,
    rank_candidates,
)
from scripts.contract_publication.export_400 import export_bundle
from scripts.contract_publication.facts import catalog_mode_of, project_record
from scripts.contract_publication.pack import build_evidence_pack
from scripts.contract_publication.report import build_status_report, render_status_markdown
from scripts.contract_publication.schema import (
    EXPORT_CANDIDATES,
    EXPORT_MANIFEST,
    EXPORT_STATUS_JSON,
    EXPORT_STATUS_MD,
    OFFICIAL_DATA_UNAVAILABLE,
    canonical_dumps,
    content_hash,
    manifest_contains_forbidden_token,
    producer_sha,
)


def _print(payload: Any) -> None:
    sys.stdout.write(canonical_dumps(payload) + "\n")


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload if payload.endswith("\n") else payload + "\n", encoding="utf-8")
    else:
        path.write_text(canonical_dumps(payload) + "\n", encoding="utf-8")


def _unavailable_document(*, as_of: str | None = None) -> dict[str, Any]:
    document = {
        "schema": "contract-publication-candidate/1.0",
        "score_formula_version": "publication-value-score/1.0",
        "status": OFFICIAL_DATA_UNAVAILABLE,
        "catalog_mode": "official_unavailable",
        "as_of": as_of,
        "candidates": [],
        "packs": {},
        "coverage": {
            "candidate_count": 0,
            "by_state": {"REJECT": 0, "HOLD_FOR_DATA": 0, "EDITORIAL_REVIEW": 0},
            "review_count": 0,
            "shortlist_count": 0,
        },
        "reason_codes": ["no_versioned_official_projection"],
        "producer_sha": producer_sha(),
    }
    hits = manifest_contains_forbidden_token(document)
    if hits:
        raise ValueError(f"forbidden_manifest_token:{hits}")
    document["content_hash"] = content_hash({key: value for key, value in document.items() if key != "content_hash"})
    return document


def _run_rank(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any], list[Any]]:
    policy = load_policy_file(args.policy)
    as_of, records, catalog_mode, snapshot_id = load_snapshot(args.snapshot)
    started = time.perf_counter()
    ranked = rank_candidates(
        records,
        as_of=as_of,
        window_start=args.window_start,
        window_end=args.window_end,
        catalog_mode=catalog_mode,
        policy=policy,
    )
    packs = build_packs(records, ranked, as_of=as_of, catalog_mode=catalog_mode, policy=policy)
    digest = input_payload_hash(
        records,
        as_of=as_of,
        policy=policy,
        window_start=args.window_start,
        window_end=args.window_end,
    )
    previous = None
    if args.previous:
        prior = json.loads(Path(args.previous).read_text(encoding="utf-8"))
        previous = prior.get("candidates") or prior
    document = build_run_document(
        ranked,
        packs,
        as_of=as_of,
        input_hash=digest,
        catalog_mode=catalog_mode,
        policy=policy,
        snapshot_id=snapshot_id,
        window_start=args.window_start,
        window_end=args.window_end,
        previous_candidates=previous,
    )
    elapsed = (time.perf_counter() - started) * 1000.0
    report = build_status_report(
        ranked,
        as_of=as_of,
        snapshot_id=snapshot_id,
        input_hash=digest,
        policy_hash=content_hash(policy),
        catalog_mode=catalog_mode,
        elapsed_ms=elapsed,
        previous=document.get("invalidation"),
    )
    return document, packs, report, ranked


def cmd_rank(args: argparse.Namespace) -> int:
    document, packs, report, ranked = _run_rank(args)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        _write(out / EXPORT_CANDIDATES, document)
        _write(
            out / EXPORT_MANIFEST,
            {
                "schema": document["schema"],
                "catalog_mode": document["catalog_mode"],
                "status": document["status"],
                "as_of": document["as_of"],
                "content_hash": document["content_hash"],
                "input_hash": document["input_hash"],
                "producer_sha": document["producer_sha"],
                "policy_version": document["policy_version"],
                "candidate_count": document["coverage"]["candidate_count"],
            },
        )
        packs_dir = out / "packs"
        packs_dir.mkdir(parents=True, exist_ok=True)
        for candidate_id, pack in packs.items():
            _write(packs_dir / f"{candidate_id}.json", pack)
        export_dir = out / "export-400"
        bundle = export_bundle(ranked, packs)
        _write(
            export_dir / "manifest.json",
            {
                "schema": bundle["schema"],
                "catalog_mode": "fixture",
                "count": bundle["count"],
                "content_hash": bundle["content_hash"],
            },
        )
        analyses_dir = export_dir / "analyses"
        analyses_dir.mkdir(parents=True, exist_ok=True)
        for analysis in bundle["analyses"]:
            _write(analyses_dir / f"{analysis['analysis_candidate_id']}.json", analysis)
        _write(out / EXPORT_STATUS_JSON, report)
        _write(out / EXPORT_STATUS_MD, render_status_markdown(report))
        hits = manifest_contains_forbidden_token(json.loads((out / EXPORT_MANIFEST).read_text(encoding="utf-8")))
        if hits:
            raise SystemExit(f"forbidden_manifest_token:{hits}")
        _print(
            {
                "ok": True,
                "path": str(out / EXPORT_CANDIDATES),
                "content_hash": document["content_hash"],
                "input_hash": document["input_hash"],
                "by_state": document["coverage"]["by_state"],
                "shortlist": document["shortlist_ids"],
            }
        )
        return 0
    _print(document)
    return 0


def cmd_rebuild_pack(args: argparse.Namespace) -> int:
    policy = load_policy_file(args.policy)
    as_of, records, catalog_mode, _snapshot_id = load_snapshot(args.snapshot)
    ranked = rank_candidates(records, as_of=as_of, catalog_mode=catalog_mode, policy=policy)
    match = next(
        (
            item
            for item in ranked
            if item.analysis_candidate_id == args.candidate_id or item.canonical_contract_id == args.candidate_id
        ),
        None,
    )
    if match is None:
        raise SystemExit(f"candidate_not_found:{args.candidate_id}")
    record = next(
        (
            item
            for item in records
            if item.get("canonical_contract_id") == match.canonical_contract_id
            or item.get("source_record_id") == match.source_record_id
        ),
        records[0],
    )
    projected = project_record(record, as_of=as_of, catalog_mode=catalog_mode_of(record, catalog_mode))
    pack = build_evidence_pack(projected, match)
    if args.out:
        _write(Path(args.out), pack)
    else:
        _print(pack)
    return 0


def cmd_export_400(args: argparse.Namespace) -> int:
    _document, packs, _report, ranked = _run_rank(args)
    bundle = export_bundle(ranked, packs, claimed_live=bool(args.claimed_live))
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        _write(out / "bundle.json", bundle)
        analyses = out / "analyses"
        for analysis in bundle["analyses"]:
            _write(analyses / f"{analysis['analysis_candidate_id']}.json", analysis)
        _print({"ok": True, "path": str(out), "content_hash": bundle["content_hash"], "count": bundle["count"]})
        return 0
    _print(bundle)
    return 0


def cmd_live(args: argparse.Namespace) -> int:
    document = _unavailable_document(as_of=args.as_of)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        _write(out / EXPORT_CANDIDATES, document)
        _write(
            out / EXPORT_MANIFEST,
            {
                "schema": document["schema"],
                "catalog_mode": document["catalog_mode"],
                "status": document["status"],
                "as_of": document["as_of"],
                "content_hash": document["content_hash"],
                "producer_sha": document["producer_sha"],
            },
        )
        report = {
            "corpus": "unavailable",
            "snapshot_hash": None,
            "policy": "publication-value-score/1.0",
            "policy_hash": None,
            "producer_sha": producer_sha(),
            "as_of": args.as_of,
            "catalog_mode": "official_unavailable",
            "status": OFFICIAL_DATA_UNAVAILABLE,
            "by_state": {"REJECT": 0, "HOLD_FOR_DATA": 0, "EDITORIAL_REVIEW": 0},
            "score_distribution": {"known_count": 0, "min": None, "max": None, "mean": None},
            "score_decomposition": {},
            "rejection_reasons": [],
            "hold_reasons": [],
            "freshness": {"fresh": 0, "stale": 0, "unknown": 0},
            "coverage": {"candidate_count": 0, "evidence_ref_count": 0, "shortlist_ids": []},
            "defects": ["no_versioned_official_projection"],
            "corrections": [],
            "cost_latency": {"elapsed_ms": 0, "candidates": 0},
            "diff_vs_previous": {"note": "no_previous_run"},
            "recommendation": "NEEDS_DATA",
        }
        _write(out / EXPORT_STATUS_JSON, report)
        _write(out / EXPORT_STATUS_MD, render_status_markdown(report))
    _print({"ok": False, "status": OFFICIAL_DATA_UNAVAILABLE, "content_hash": document["content_hash"]})
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m scripts.contract_publication")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_shared(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument("--snapshot", required=False, help="Versioned snapshot JSON")
        cmd.add_argument("--policy", help="Versioned policy JSON (defaults to publication-value-score/1.0)")
        cmd.add_argument("--window-start", dest="window_start")
        cmd.add_argument("--window-end", dest="window_end")
        cmd.add_argument("--previous", help="Previous candidates.json for directed invalidation")
        cmd.add_argument("--out", help="Output directory")

    rank_cmd = sub.add_parser("rank", help="Rank snapshot, write packs, export and report")
    add_shared(rank_cmd)
    rank_cmd.set_defaults(func=cmd_rank)

    pack_cmd = sub.add_parser("rebuild-pack", help="Rebuild one evidence pack")
    add_shared(pack_cmd)
    pack_cmd.add_argument("--candidate-id", dest="candidate_id", required=True)
    pack_cmd.set_defaults(func=cmd_rebuild_pack)

    export_cmd = sub.add_parser("export-400", help="Export public-read-contract-analysis/1.0 bundle")
    add_shared(export_cmd)
    export_cmd.add_argument("--claimed-live", dest="claimed_live", action="store_true")
    export_cmd.set_defaults(func=cmd_export_400)

    live_cmd = sub.add_parser("live", help="Official path; fail-closed when unavailable")
    live_cmd.add_argument("--dsn", help="Ignored unless a versioned official projection exists")
    live_cmd.add_argument("--as-of", dest="as_of")
    live_cmd.add_argument("--out")
    live_cmd.set_defaults(func=cmd_live)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command in {"rank", "rebuild-pack", "export-400"} and not args.snapshot:
        raise SystemExit("informe --snapshot")
    return int(args.func(args))
