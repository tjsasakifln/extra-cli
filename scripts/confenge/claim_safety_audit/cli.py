"""Claim-safety audit over the published CONFENGE outbound feed.

Usage:
  python -m scripts.confenge claim_safety_audit [--dry-run]
  python -m scripts.confenge claim_safety_audit --apply
  python -m scripts.confenge claim_safety_audit rollback

Exit codes (same convention as ``scripts/check-alerts.py`` / ``scripts/intel_pipeline.py``):
  0  corpus is clean, or the apply corrected it / was an observable no-op
  1  unsafe or unreadable claims found in dry-run
  2  error, or a refusal (fail-closed)

``--dry-run`` is the default and writes nothing under the feed directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_activation.publish import (
    DEFAULT_ALERT_LEDGER,
    DEFAULT_STATE_PATH,
    _assert_membership_deactivation_delta,
    _read_json,
    _read_state,
    atomic_publish_directory,
)
from scripts.confenge_claim_safety.classify import (
    ClaimSafetyResult,
    active_proven_reason_codes,
    class_distribution,
    classify_lead,
    link_contract,
)
from scripts.confenge_claim_safety.policy import (
    CLAIM_SAFETY_CORPUS_HASH_ALGORITHM,
    CLAIM_SAFETY_POLICY_VERSION,
    PUBLISHABLE_CLASSES,
    UNSAFE_PRESENT_CLAIM,
)
from scripts.confenge_claim_safety.rewrite import ClaimRewriteError, rewrite_lead

EXIT_OK = 0
EXIT_UNSAFE_FOUND = 1
EXIT_REFUSED = 2

DEFAULT_PUBLISH_DIR = Path("/opt/confenge-plane/feed-www")
DEFAULT_FEED_DIR = DEFAULT_PUBLISH_DIR / "current"
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BUILD_DIR = REPO_ROOT / "artifacts" / "confenge" / "claim-safety" / "build"

ROLLBACK_ANCHOR_KEY = "claim_safety_rollback_anchor"

STATUS_CLEAN = "clean"
STATUS_UNSAFE_FOUND = "unsafe_found"
STATUS_PUBLISHED = "published"
STATUS_SKIPPED_NO_CHANGE = "skipped_no_change"
STATUS_SKIPPED_SAME = "skipped_same_publication_semantics"
STATUS_REFUSED = "refused"


# --------------------------------------------------------------------------- #
# feed IO
# --------------------------------------------------------------------------- #
def load_feed(feed_dir: Path) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    """Read ``manifest.json`` and every chunk it declares, in manifest order."""
    manifest = _read_json(feed_dir / "manifest.json")
    chunks: list[tuple[str, dict[str, Any]]] = []
    for entry in manifest.get("chunks") or []:
        if not isinstance(entry, dict):
            raise ValueError("manifest chunk entry is not an object")
        name = str(entry.get("file") or "").strip()
        if not name or Path(name).name != name:
            raise ValueError(f"unsafe chunk file name: {name!r}")
        chunks.append((name, _read_json(feed_dir / name)))
    return manifest, chunks


def _lead_id(lead: dict[str, Any]) -> str:
    value = lead.get("source_lead_id")
    if value:
        return str(value)
    company = lead.get("company") if isinstance(lead.get("company"), dict) else {}
    return str(company.get("cnpj14") or "")


def corpus_hash(results: list[tuple[str, ClaimSafetyResult]]) -> str:
    """Deterministic digest of the audited corpus: (lead id, class, surface)."""
    digest = hashlib.sha256()
    for lead_id, result in sorted(results, key=lambda row: row[0]):
        surface_sha = hashlib.sha256(result.surface.encode("utf-8")).hexdigest()
        digest.update(f"{lead_id}\t{result.safety_class}\t{surface_sha}\n".encode())
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# audit
# --------------------------------------------------------------------------- #
def audit_corpus(
    chunks: list[tuple[str, dict[str, Any]]],
    *,
    today: date | None = None,
) -> tuple[list[tuple[str, ClaimSafetyResult]], list[ClaimSafetyResult]]:
    pairs: list[tuple[str, ClaimSafetyResult]] = []
    for _name, payload in chunks:
        for lead in payload.get("leads") or []:
            if not isinstance(lead, dict):
                continue
            pairs.append((_lead_id(lead), classify_lead(lead, today=today)))
    return pairs, [result for _lead_id_, result in pairs]


def build_report(
    *,
    feed_dir: Path,
    manifest: dict[str, Any],
    pairs: list[tuple[str, ClaimSafetyResult]],
    mode: str,
    status: str,
) -> dict[str, Any]:
    results = [result for _lead_id_, result in pairs]
    matrix: dict[str, Counter[str]] = defaultdict(Counter)
    for result in results:
        matrix[result.why_now_code or "MISSING"][result.safety_class] += 1
    unsafe = [
        {
            "source_lead_id": lead_id,
            "why_now_code": result.why_now_code,
            "contract_id": result.contract_id,
            "activity_state": result.activity_state,
            "reason_codes": list(result.reason_codes),
        }
        for lead_id, result in pairs
        if result.safety_class not in PUBLISHABLE_CLASSES
    ]
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    return {
        "schema_id": "confenge.claim_safety_audit_report.v1",
        "policy_version": CLAIM_SAFETY_POLICY_VERSION,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "mode": mode,
        "status": status,
        "feed_dir": str(feed_dir),
        "run_id": source.get("run_id"),
        "publication_semantic_hash": manifest.get("publication_semantic_hash"),
        "lead_count": len(results),
        "manifest_lead_count": manifest.get("lead_count"),
        "class_distribution": class_distribution(results),
        "class_by_why_now_code": {code: dict(counts) for code, counts in sorted(matrix.items())},
        "reason_codes": active_proven_reason_codes(results),
        "corpus_hash": corpus_hash(pairs),
        "corpus_hash_algorithm": CLAIM_SAFETY_CORPUS_HASH_ALGORITHM,
        "non_publishable_count": len(unsafe),
        "unsafe_present_claim_count": sum(1 for r in results if r.safety_class == UNSAFE_PRESENT_CLAIM),
        "non_publishable_sample": unsafe[:50],
    }


# --------------------------------------------------------------------------- #
# apply
# --------------------------------------------------------------------------- #
def rewrite_corpus(
    chunks: list[tuple[str, dict[str, Any]]],
    *,
    today: date | None = None,
) -> tuple[list[tuple[str, dict[str, Any]]], set[str], int]:
    """Rewrite every non-publishable lead. Returns (chunks, changed_files, count)."""
    changed_files: set[str] = set()
    rewritten = 0
    output: list[tuple[str, dict[str, Any]]] = []
    for name, payload in chunks:
        leads = payload.get("leads") or []
        new_leads: list[Any] = []
        touched = False
        for lead in leads:
            if not isinstance(lead, dict):
                new_leads.append(lead)
                continue
            result = classify_lead(lead, today=today)
            if result.safety_class in PUBLISHABLE_CLASSES:
                new_leads.append(lead)
                continue
            updated, _changed = rewrite_lead(
                lead,
                contract=link_contract(lead),
                today=today,
                reason_codes=result.reason_codes,
            )
            new_leads.append(updated)
            touched = True
            rewritten += 1
        if touched:
            payload = {**payload, "leads": new_leads}
            changed_files.add(name)
        output.append((name, payload))
    return output, changed_files, rewritten


def _serialize_chunk(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def stage_build_dir(
    *,
    feed_dir: Path,
    build_dir: Path,
    manifest: dict[str, Any],
    chunks: list[tuple[str, dict[str, Any]]],
    changed_files: set[str],
    claim_safety_block: dict[str, Any],
) -> dict[str, Any]:
    """Copy the release, overwrite rewritten chunks and close the manifest hashes."""
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(feed_dir, build_dir, symlinks=False)

    by_name = dict(chunks)
    ceiling = int(manifest.get("max_bytes_per_chunk") or 0)
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    for entry in manifest.get("chunks") or []:
        name = str(entry.get("file"))
        path = build_dir / name
        if name in changed_files:
            raw = _serialize_chunk(by_name[name])
            if ceiling and len(raw) > ceiling:
                raise ValueError(f"rewritten chunk {name} exceeds the declared byte ceiling: {len(raw)} > {ceiling}")
            path.write_bytes(raw)
        raw_bytes = path.read_bytes()
        total_bytes += len(raw_bytes)
        entries.append(
            {
                **entry,
                "content_hash": hashlib.sha256(raw_bytes).hexdigest(),
                "byte_count": len(raw_bytes),
            }
        )

    updated = {
        **manifest,
        "chunks": entries,
        "total_chunk_bytes": total_bytes,
        "claim_safety": claim_safety_block,
    }
    updated.pop("manifest_content_hash", None)
    manifest_path = build_dir / "manifest.json"
    raw = (json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    manifest_path.write_bytes(raw)
    updated["manifest_content_hash"] = hashlib.sha256(raw).hexdigest()
    raw = (json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    manifest_path.write_bytes(raw)
    return updated


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def _emit(report: dict[str, Any], report_json: Path | None) -> None:
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if report_json is not None:
        report_json.parent.mkdir(parents=True, exist_ok=True)
        report_json.write_text(text + "\n", encoding="utf-8")
    print(text)


def run_audit(args: argparse.Namespace) -> int:
    feed_dir = Path(args.feed_dir)
    today = date.fromisoformat(args.today) if args.today else None
    try:
        manifest, chunks = load_feed(feed_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"claim-safety-audit: cannot read feed at {feed_dir}: {exc}", file=sys.stderr)
        return EXIT_REFUSED

    pairs, results = audit_corpus(chunks, today=today)
    non_publishable = [r for r in results if r.safety_class not in PUBLISHABLE_CLASSES]

    if not args.apply:
        status = STATUS_CLEAN if not non_publishable else STATUS_UNSAFE_FOUND
        report = build_report(feed_dir=feed_dir, manifest=manifest, pairs=pairs, mode="dry-run", status=status)
        _emit(report, Path(args.report_json) if args.report_json else None)
        return EXIT_OK if not non_publishable else EXIT_UNSAFE_FOUND

    if not non_publishable:
        report = build_report(
            feed_dir=feed_dir, manifest=manifest, pairs=pairs, mode="apply", status=STATUS_SKIPPED_NO_CHANGE
        )
        report["rewritten_lead_count"] = 0
        report["published"] = False
        _emit(report, Path(args.report_json) if args.report_json else None)
        return EXIT_OK

    try:
        rewritten_chunks, changed_files, rewritten_count = rewrite_corpus(chunks, today=today)
    except ClaimRewriteError as exc:
        print(f"claim-safety-audit: refusing to publish — {exc}", file=sys.stderr)
        return EXIT_REFUSED

    # Corpus invariant (AC 6, 7, 10, 20): after the rewrite every single lead must
    # land in a publishable class. Anything else fails closed, including a
    # template this audit never anticipated.
    post_pairs, post_results = audit_corpus(rewritten_chunks, today=today)
    residual = [r for r in post_results if r.safety_class not in PUBLISHABLE_CLASSES]
    if residual:
        report = build_report(
            feed_dir=feed_dir, manifest=manifest, pairs=post_pairs, mode="apply", status=STATUS_REFUSED
        )
        report["refusal_reason"] = "post_rewrite_corpus_still_carries_non_publishable_leads"
        _emit(report, Path(args.report_json) if args.report_json else None)
        return EXIT_REFUSED

    post_report = build_report(
        feed_dir=feed_dir, manifest=manifest, pairs=post_pairs, mode="apply", status=STATUS_PUBLISHED
    )
    claim_safety_block = {
        "policy_version": CLAIM_SAFETY_POLICY_VERSION,
        "corpus_hash": post_report["corpus_hash"],
        "corpus_hash_algorithm": CLAIM_SAFETY_CORPUS_HASH_ALGORITHM,
        "class_distribution": post_report["class_distribution"],
        "rewritten_lead_count": rewritten_count,
        "unsafe_present_claim_count": post_report["unsafe_present_claim_count"],
        "reason_codes": post_report["reason_codes"],
    }

    build_dir = Path(args.build_dir)
    try:
        stage_build_dir(
            feed_dir=feed_dir,
            build_dir=build_dir,
            manifest=manifest,
            chunks=rewritten_chunks,
            changed_files=changed_files,
            claim_safety_block=claim_safety_block,
        )
        outcome = atomic_publish_directory(
            build_dir,
            Path(args.publish_dir),
            state_path=Path(args.state_path),
            alert_ledger=Path(args.alert_ledger),
        )
    except Exception as exc:  # noqa: BLE001 — publication refusal must be reported, not raised
        print(f"claim-safety-audit: publication refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED

    published = bool(outcome.get("ok"))
    post_report["status"] = STATUS_PUBLISHED if published else STATUS_SKIPPED_SAME
    post_report["published"] = published
    post_report["rewritten_lead_count"] = rewritten_count
    post_report["release_dir"] = outcome.get("release_dir")
    post_report["skipped_same"] = bool(outcome.get("skipped_same"))
    post_report["build_dir"] = str(build_dir)
    state = _read_state(Path(args.state_path))
    post_report["rollback_plan"] = {
        "anchor_key": ROLLBACK_ANCHOR_KEY,
        "anchor": state.get(ROLLBACK_ANCHOR_KEY),
        "command": "python3 -m scripts.confenge claim_safety_audit rollback",
    }
    _emit(post_report, Path(args.report_json) if args.report_json else None)
    return EXIT_OK


def run_rollback(args: argparse.Namespace) -> int:
    publish_dir = Path(args.publish_dir)
    state_path = Path(args.state_path)
    state = _read_state(state_path)
    anchor = str(state.get(ROLLBACK_ANCHOR_KEY) or "").strip()
    if not anchor:
        print(
            f"claim-safety-audit rollback: no {ROLLBACK_ANCHOR_KEY} in {state_path}; refusing",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    if Path(anchor).name != anchor:
        print(f"claim-safety-audit rollback: unsafe anchor {anchor!r}", file=sys.stderr)
        return EXIT_REFUSED
    target = publish_dir / "releases" / anchor
    if not (target / "manifest.json").is_file():
        print(f"claim-safety-audit rollback: anchored release is not readable: {target}", file=sys.stderr)
        return EXIT_REFUSED

    current = publish_dir / args.current_name
    try:
        from_manifest = _read_json(current / "manifest.json")
        to_manifest = _read_json(target / "manifest.json")
        _assert_membership_deactivation_delta(current, from_manifest, target, to_manifest)
    except Exception as exc:  # noqa: BLE001 — a membership delta is a refusal, not a crash
        print(f"claim-safety-audit rollback: membership delta guard refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED

    link_tmp = publish_dir / f".{args.current_name}.rollback-tmp"
    if link_tmp.exists() or link_tmp.is_symlink():
        link_tmp.unlink()
    link_tmp.symlink_to(Path("releases") / anchor, target_is_directory=True)
    try:
        os.replace(str(link_tmp), str(current))
    except Exception:
        link_tmp.unlink(missing_ok=True)
        raise

    report = {
        "schema_id": "confenge.claim_safety_rollback_report.v1",
        "policy_version": CLAIM_SAFETY_POLICY_VERSION,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "rolled_back",
        "anchor": anchor,
        "restored_release": str(target),
        "membership_delta_guard": "revalidated_no_additional_drops",
    }
    _emit(report, Path(args.report_json) if args.report_json else None)
    return EXIT_OK


# --------------------------------------------------------------------------- #
# argv
# --------------------------------------------------------------------------- #
def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--publish-dir", default=str(DEFAULT_PUBLISH_DIR))
    parser.add_argument("--current-name", default="current")
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--alert-ledger", default=str(DEFAULT_ALERT_LEDGER))
    parser.add_argument("--report-json", default=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claim_safety_audit", description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    audit = subparsers.add_parser("audit", help="classify the published corpus (default)")
    mode = audit.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="classify only; writes nothing (default)")
    mode.add_argument("--apply", action="store_true", help="rewrite unsafe claims and publish a new release")
    audit.add_argument("--feed-dir", default=str(DEFAULT_FEED_DIR))
    audit.add_argument("--build-dir", default=str(DEFAULT_BUILD_DIR))
    audit.add_argument("--today", default=None, help="ISO date used as the activity reference (tests)")
    _add_common(audit)

    rollback = subparsers.add_parser("rollback", help="restore the release anchored before the last apply")
    _add_common(rollback)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        argv = ["audit", *argv]
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "rollback":
        return run_rollback(args)
    return run_audit(args)


if __name__ == "__main__":
    raise SystemExit(main())
