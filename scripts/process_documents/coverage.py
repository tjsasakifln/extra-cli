"""Independent coverage metrics for process documents (never averaged)."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.process_documents.activity import active_entity_ids, classify_all_activity
from scripts.process_documents.discovery import EXPECTED_UNIVERSE, discover_all, load_discovery, ordered_id_hash
from scripts.process_documents.models import EntityDocumentDiscovery
from scripts.process_documents.statuses import (
    NOTICE_ANNEX_CATEGORIES,
    OPERATIONAL_SUCCESS,
    QUALIFICATION_CATEGORIES,
    SESSION_JUDGMENT_CATEGORIES,
    WINNING_PROPOSAL_CATEGORIES,
    ActivityStatus,
    DocumentRunStatus,
)
from scripts.process_documents.storage import DEFAULT_META_ROOT, ensure_roots, load_jsonl, write_json

THRESHOLDS = {
    "entity_source_discovery_coverage": 1.0,
    "active_entity_document_operational_coverage": 0.95,
    "relevant_process_recall": 0.98,
    "covered_financial_value_ratio": 0.99,
    "notice_and_annexes_completeness": 0.98,
    "session_judgment_homologation_completeness": 0.95,
    "winning_proposal_completeness": 0.85,
    "bidder_qualification_documents_completeness": 0.70,
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def load_run_index(meta_root: Path | None = None) -> list[dict[str, Any]]:
    _, meta = ensure_roots(meta_root=meta_root)
    return load_jsonl(meta / "run-index.jsonl")


def latest_runs_by_entity(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in runs:
        cid = row.get("canonical_entity_id")
        if not cid:
            continue
        prev = latest.get(cid)
        if prev is None or str(row.get("finished_at") or "") >= str(prev.get("finished_at") or ""):
            latest[cid] = row
    return latest


def compute_operational_coverage(
    discoveries: list[EntityDocumentDiscovery] | None = None,
    *,
    meta_root: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    discoveries = discoveries or load_discovery()
    active = [d for d in discoveries if d.activity_status == ActivityStatus.ACTIVE.value]
    # Active entities with pending activity evidence are NOT silently dropped;
    # only ACTIVE is in denominator. Pending remain in gaps.
    runs = latest_runs_by_entity(load_run_index(meta_root))
    covered: list[str] = []
    not_covered: list[dict[str, Any]] = []
    success_zero: list[dict[str, Any]] = []

    for d in active:
        run = runs.get(d.canonical_id)
        if not run:
            not_covered.append(
                {
                    "canonical_id": d.canonical_id,
                    "status": DocumentRunStatus.PENDING.value,
                    "reason": "no_live_run",
                }
            )
            continue
        status = run.get("status")
        try:
            st = DocumentRunStatus(status)
        except ValueError:
            st = DocumentRunStatus.UNKNOWN
        if st in OPERATIONAL_SUCCESS:
            covered.append(d.canonical_id)
            if st == DocumentRunStatus.SUCCESS_ZERO:
                success_zero.append(
                    {
                        "canonical_id": d.canonical_id,
                        "run_id": run.get("run_id"),
                        "status": st.value,
                    }
                )
        else:
            not_covered.append(
                {
                    "canonical_id": d.canonical_id,
                    "status": st.value,
                    "run_id": run.get("run_id"),
                    "reason": "non_operational_status",
                }
            )

    denom = len(active)
    numer = len(covered)
    ratio = (numer / denom) if denom else 0.0
    report = {
        "metric": "active_entity_document_operational_coverage",
        "threshold": THRESHOLDS["active_entity_document_operational_coverage"],
        "numerator": numer,
        "denominator": denom,
        "ratio": ratio,
        "percent": round(ratio * 100, 4),
        "meets_threshold": ratio >= THRESHOLDS["active_entity_document_operational_coverage"] and denom > 0,
        "active_ids_sha256": ordered_id_hash([d.canonical_id for d in active]),
        "covered_ids": sorted(covered),
        "not_covered": not_covered,
        "success_zero": success_zero,
        "pending_activity_count": sum(
            1 for d in discoveries if d.activity_status == ActivityStatus.UNKNOWN_PENDING_EVIDENCE.value
        ),
        "inactive_count": sum(1 for d in discoveries if d.activity_status == ActivityStatus.INACTIVE.value),
        "generated_at": _now(),
        "honesty_rules": [
            "timeout/403/429/5xx/partial never count as coverage",
            "active blocked entities remain in denominator",
            "SUCCESS_ZERO requires justification in run evidence",
        ],
    }
    if persist:
        _, meta = ensure_roots(meta_root=meta_root)
        write_json(meta / "document-coverage.json", report)
        (meta / "document-coverage.md").write_text(
            "# Active entity document operational coverage\n\n"
            f"- Ratio: **{report['percent']}%** ({numer}/{denom})\n"
            f"- Meets ≥95%: **{report['meets_threshold']}**\n"
            f"- Not covered: {len(not_covered)}\n"
            f"- SUCCESS_ZERO: {len(success_zero)}\n"
            f"- Generated: {report['generated_at']}\n",
            encoding="utf-8",
        )
    return report


def compute_process_recall(
    *,
    benchmark_path: Path | str | None = None,
    found_process_ids: set[str] | None = None,
    meta_root: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Recall against independent benchmark (not the crawler under test alone)."""
    _, meta = ensure_roots(meta_root=meta_root)
    bench_path = Path(benchmark_path or meta / "process-recall-benchmark.json")
    if bench_path.is_file():
        benchmark = json.loads(bench_path.read_text(encoding="utf-8"))
    else:
        benchmark = {
            "version": "process_recall_benchmark_v0_empty",
            "criteria": {
                "engineering_compatible": True,
                "geography": "Extra 200km SC universe",
                "window": "configurable",
                "modalities": "applicable",
            },
            "cutoff_date": datetime.now(UTC).date().isoformat(),
            "independent_sources": ["pncp", "entity_registry", "canonical_editais_contracts"],
            "expected_processes": [],
            "note": "Benchmark empty until independent inventory sealed — recall cannot claim 98%.",
        }
        write_json(bench_path, benchmark)

    expected = benchmark.get("expected_processes") or []
    expected_ids = []
    for p in expected:
        if isinstance(p, dict):
            expected_ids.append(str(p.get("process_id") or p.get("id")))
        else:
            expected_ids.append(str(p))
    expected_ids = [e for e in expected_ids if e and e != "None"]
    found = set(found_process_ids or set())
    # Always merge live operational evidence: run-index + run documents + corpus
    for row in load_run_index(meta):
        pid = row.get("process_id")
        if pid:
            found.add(str(pid))
    runs_dir = meta / "runs"
    if runs_dir.is_dir():
        for result_path in runs_dir.glob("*/result.json"):
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            qp = data.get("query_parameters") or {}
            if qp.get("process_id"):
                found.add(str(qp["process_id"]))
            for doc in data.get("documents") or []:
                pid = doc.get("procurement_id") or doc.get("notice_id")
                if pid:
                    found.add(str(pid))
    corpus_manifest = meta / "corpus-manifest.json"
    if corpus_manifest.is_file():
        cm = json.loads(corpus_manifest.read_text(encoding="utf-8"))
        for p in cm.get("processes") or []:
            pid = p.get("process_id") or p.get("procurement_id")
            if pid:
                found.add(str(pid))

    false_negatives = sorted(set(expected_ids) - set(found))
    true_positives = sorted(set(expected_ids) & set(found))
    denom = len(expected_ids)
    numer = len(true_positives)
    ratio = (numer / denom) if denom else 0.0
    report = {
        "metric": "relevant_process_recall",
        "threshold": THRESHOLDS["relevant_process_recall"],
        "numerator": numer,
        "denominator": denom,
        "ratio": ratio,
        "percent": round(ratio * 100, 4),
        "meets_threshold": denom > 0 and ratio >= THRESHOLDS["relevant_process_recall"],
        "benchmark_version": benchmark.get("version"),
        "benchmark_path": str(bench_path),
        "cutoff_date": benchmark.get("cutoff_date"),
        "independent_sources": benchmark.get("independent_sources"),
        "expected_ids_sha256": ordered_id_hash(expected_ids) if expected_ids else ordered_id_hash([]),
        "true_positives": true_positives,
        "false_negatives": [
            {"process_id": pid, "reason": "not_found_by_collectors"} for pid in false_negatives
        ],
        "limitations": [
            "Recall is undefined for gate pass when benchmark denominator is 0",
            "Crawler under evaluation must not be sole denominator source",
        ]
        + ([benchmark.get("note")] if benchmark.get("note") else []),
        "generated_at": _now(),
    }
    if persist:
        write_json(meta / "process-recall.json", report)
        (meta / "process-recall.md").write_text(
            "# Relevant process recall\n\n"
            f"- Ratio: **{report['percent']}%** ({numer}/{denom})\n"
            f"- Meets ≥98%: **{report['meets_threshold']}**\n"
            f"- Benchmark: `{report['benchmark_version']}`\n"
            f"- False negatives: {len(false_negatives)}\n",
            encoding="utf-8",
        )
    return report


def compute_financial_coverage(
    *,
    benchmark_path: Path | str | None = None,
    covered_process_ids: set[str] | None = None,
    meta_root: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    from scripts.process_documents.models import FINANCIAL_VALUE_HIERARCHY, resolve_financial_value

    _, meta = ensure_roots(meta_root=meta_root)
    bench_path = Path(benchmark_path or meta / "process-recall-benchmark.json")
    processes: list[dict[str, Any]] = []
    if bench_path.is_file():
        benchmark = json.loads(bench_path.read_text(encoding="utf-8"))
        processes = list(benchmark.get("expected_processes") or [])
    else:
        benchmark = {}

    covered = set(covered_process_ids or set())
    for row in load_run_index(meta):
        pid = row.get("process_id")
        if pid:
            covered.add(str(pid))
    runs_dir = meta / "runs"
    if runs_dir.is_dir():
        for result_path in runs_dir.glob("*/result.json"):
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for doc in data.get("documents") or []:
                pid = doc.get("procurement_id")
                if pid:
                    covered.add(str(pid))
    corpus_manifest = meta / "corpus-manifest.json"
    if corpus_manifest.is_file():
        cm = json.loads(corpus_manifest.read_text(encoding="utf-8"))
        for p in cm.get("processes") or []:
            pid = p.get("process_id") or p.get("procurement_id")
            if pid:
                covered.add(str(pid))

    total = 0.0
    covered_value = 0.0
    missing_value_ids: list[str] = []
    field_usage: dict[str, int] = defaultdict(int)
    for p in processes:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("process_id") or p.get("id") or "")
        val, field = resolve_financial_value(p)
        if val is None:
            missing_value_ids.append(pid)
            continue
        field_usage[field or "unknown"] += 1
        total += val
        if pid in covered:
            covered_value += val
    ratio = (covered_value / total) if total > 0 else 0.0
    report = {
        "metric": "covered_financial_value_ratio",
        "threshold": THRESHOLDS["covered_financial_value_ratio"],
        "value_hierarchy": list(FINANCIAL_VALUE_HIERARCHY),
        "total_value": total,
        "covered_value": covered_value,
        "uncovered_value": max(0.0, total - covered_value),
        "ratio": ratio,
        "percent": round(ratio * 100, 4),
        "meets_threshold": total > 0 and ratio >= THRESHOLDS["covered_financial_value_ratio"],
        "processes_without_value": missing_value_ids,
        "field_usage": dict(field_usage),
        "semantic_note": "Never sum estimated+homologated+contracted as equivalent",
        "generated_at": _now(),
    }
    if persist:
        write_json(meta / "financial-coverage.json", report)
        (meta / "financial-coverage.md").write_text(
            "# Financial coverage\n\n"
            f"- Ratio: **{report['percent']}%**\n"
            f"- Total: {total:.2f} | Covered: {covered_value:.2f}\n"
            f"- Hierarchy: {', '.join(FINANCIAL_VALUE_HIERARCHY)}\n"
            f"- Meets ≥99%: **{report['meets_threshold']}**\n",
            encoding="utf-8",
        )
    return report


def compute_completeness(
    *,
    meta_root: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Document completeness buckets from collected documents (per process).

    Methodology (process-level binary presence):
    - Reclassify weak categories (outro/unknown) from original_title/filename.
    - A process scores 1.0 for a bucket if it has ≥1 document in that family;
      0.0 otherwise. Metric = mean over processes with ≥1 collected document.
    - Category-fraction scoring is kept as diagnostic only (never used for gates).
    """
    from scripts.process_documents.classify_docs import classify_document_record

    _, meta = ensure_roots(meta_root=meta_root)
    runs_dir = meta / "runs"
    by_process: dict[str, set[str]] = defaultdict(set)
    titles_by_process: dict[str, list[str]] = defaultdict(list)
    if runs_dir.is_dir():
        for result_path in runs_dir.glob("*/result.json"):
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for doc in data.get("documents") or []:
                pid = str(doc.get("procurement_id") or doc.get("notice_id") or "unknown")
                cat = classify_document_record(doc)
                by_process[pid].add(cat)
                title = str(
                    doc.get("original_title")
                    or doc.get("original_filename")
                    or doc.get("title")
                    or ""
                )
                titles_by_process[pid].append(title)

    def _residual_blocker(pid: str, cats: set[str], bucket: str, required: set[str]) -> str | None:
        """Nominal residual reason when a process fails a completeness bucket."""
        if cats & required:
            return None
        titles = titles_by_process.get(pid) or []
        joined = " ".join(titles).lower()
        if "publicações de" in joined or "publicacoes de" in joined or "publicacoes_de" in joined:
            return "non_process_publication_dump"
        if titles and all((t.strip().isdigit() or not t.strip()) for t in titles):
            return "opaque_numeric_title_only"
        if bucket == "notice_and_annexes_completeness":
            return "notice_pack_not_published_or_unclassified"
        if bucket == "session_judgment_homologation_completeness":
            return "session_judgment_not_published_publicly"
        if bucket == "winning_proposal_completeness":
            return "winning_proposal_not_published_publicly"
        if bucket == "bidder_qualification_documents_completeness":
            return "bidder_qualification_not_published_publicly"
        return "missing_bucket_documents"

    notice_req = {c.value for c in NOTICE_ANNEX_CATEGORIES}
    session_req = {c.value for c in SESSION_JUDGMENT_CATEGORIES}
    win_req = {c.value for c in WINNING_PROPOSAL_CATEGORIES}
    qual_req = {c.value for c in QUALIFICATION_CATEGORIES}

    def binary_presence(categories: set[str], required: set[str]) -> float:
        if not required:
            return 0.0
        return 1.0 if categories & required else 0.0

    def category_fraction(categories: set[str], required: set[str]) -> float:
        if not required:
            return 0.0
        return len(categories & required) / len(required)

    # Full denominator: every process with ≥1 collected document (no shrinking).
    scorable = dict(by_process)
    n_procs = len(scorable)
    residual_nominal: dict[str, list[dict[str, Any]]] = {
        "notice_and_annexes_completeness": [],
        "session_judgment_homologation_completeness": [],
        "winning_proposal_completeness": [],
        "bidder_qualification_documents_completeness": [],
    }
    if n_procs == 0:
        notice = session = win = qual = 0.0
        notice_frac = session_frac = win_frac = qual_frac = 0.0
    else:
        notice = sum(binary_presence(cats, notice_req) for cats in scorable.values()) / n_procs
        session = sum(binary_presence(cats, session_req) for cats in scorable.values()) / n_procs
        win = sum(binary_presence(cats, win_req) for cats in scorable.values()) / n_procs
        qual = sum(binary_presence(cats, qual_req) for cats in scorable.values()) / n_procs
        notice_frac = sum(category_fraction(cats, notice_req) for cats in scorable.values()) / n_procs
        session_frac = sum(category_fraction(cats, session_req) for cats in scorable.values()) / n_procs
        win_frac = sum(category_fraction(cats, win_req) for cats in scorable.values()) / n_procs
        qual_frac = sum(category_fraction(cats, qual_req) for cats in scorable.values()) / n_procs
        for pid, cats in scorable.items():
            for key, req in (
                ("notice_and_annexes_completeness", notice_req),
                ("session_judgment_homologation_completeness", session_req),
                ("winning_proposal_completeness", win_req),
                ("bidder_qualification_documents_completeness", qual_req),
            ):
                blocker = _residual_blocker(pid, cats, key, req)
                if blocker:
                    residual_nominal[key].append(
                        {
                            "process_id": pid,
                            "blocker": blocker,
                            "categories_seen": sorted(cats)[:12],
                        }
                    )

    def _metric(ratio: float, key: str) -> dict[str, Any]:
        return {
            "ratio": ratio,
            "percent": round(ratio * 100, 4),
            "threshold": THRESHOLDS[key],
            "meets_threshold": ratio >= THRESHOLDS[key] and n_procs > 0,
            "methodology": "process_level_binary_presence",
            "residual_count": len(residual_nominal.get(key) or []),
        }

    report = {
        "metrics": {
            "notice_and_annexes_completeness": _metric(notice, "notice_and_annexes_completeness"),
            "session_judgment_homologation_completeness": _metric(
                session, "session_judgment_homologation_completeness"
            ),
            "winning_proposal_completeness": _metric(win, "winning_proposal_completeness"),
            "bidder_qualification_documents_completeness": _metric(
                qual, "bidder_qualification_documents_completeness"
            ),
        },
        "diagnostics_category_fraction": {
            "notice_and_annexes_completeness": round(notice_frac * 100, 4),
            "session_judgment_homologation_completeness": round(session_frac * 100, 4),
            "winning_proposal_completeness": round(win_frac * 100, 4),
            "bidder_qualification_documents_completeness": round(qual_frac * 100, 4),
            "note": "Diagnostic only — not used for gates (sparse public packs).",
        },
        "processes_scored": n_procs,
        "processes_raw": len(by_process),
        "denominator_policy": "full_no_shrink",
        "residual_nominal_sample": {
            k: v[:25] for k, v in residual_nominal.items()
        },
        "residual_nominal_counts": {k: len(v) for k, v in residual_nominal.items()},
        "generated_at": _now(),
        "note": (
            "Binary presence per process after title reclassification + ZIP expansion. "
            "Denominator is ALL processes with ≥1 document (no shrinking). "
            "Residuals listed nominally with blockers; publication limits remain for "
            "session/proposal/qualification packs on many public portals."
        ),
    }
    if persist:
        write_json(meta / "document-completeness.json", report)
        lines = ["# Document completeness\n"]
        for name, m in report["metrics"].items():
            lines.append(
                f"- `{name}`: **{m['percent']}%** (threshold {m['threshold']*100:.0f}%, meets={m['meets_threshold']})"
            )
        lines.append(f"\nProcesses scored: {n_procs}\n")
        lines.append(f"\nMethodology: process-level binary presence after title reclassification.\n")
        (meta / "document-completeness.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def compute_gaps(
    discoveries: list[EntityDocumentDiscovery] | None = None,
    *,
    meta_root: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    discoveries = discoveries or load_discovery()
    op = compute_operational_coverage(discoveries, meta_root=meta_root, persist=False)
    gaps = []
    for d in discoveries:
        if d.activity_status != ActivityStatus.ACTIVE.value:
            continue
        if d.canonical_id in op.get("covered_ids", []):
            continue
        gaps.append(
            {
                "canonical_id": d.canonical_id,
                "portal_family": d.portal_family,
                "blocker": d.blocker,
                "activity_status": d.activity_status,
                "access_status": d.access_status,
                "collection_strategy": d.collection_strategy,
                "fallback_strategy": d.fallback_strategy,
            }
        )
    report = {
        "active_gaps": gaps,
        "active_gap_count": len(gaps),
        "generated_at": _now(),
    }
    if persist:
        _, meta = ensure_roots(meta_root=meta_root)
        write_json(meta / "document-gaps.json", report)
        (meta / "document-gaps.md").write_text(
            "# Document gaps (active entities)\n\n"
            f"- Count: **{len(gaps)}**\n\n"
            + "\n".join(f"- `{g['canonical_id']}` family={g['portal_family']} blocker={g['blocker']}" for g in gaps[:100])
            + ("\n\n_(truncated)_" if len(gaps) > 100 else "\n"),
            encoding="utf-8",
        )
    return report


# Completeness keys that may be residual-waived by explicit product-owner decision
# when public publication limits prevent threshold attainment. Waiver never marks
# meets_threshold=true and never shrinks denominators.
_RESIDUAL_WAIVABLE_COMPLETENESS = frozenset(
    {
        "winning_proposal_completeness",
        "bidder_qualification_documents_completeness",
    }
)


def load_residual_policy(*, meta_root: Path | None = None) -> dict[str, Any] | None:
    """Load PO residual-acceptance artifact if present (campaign or meta root)."""
    candidates: list[Path] = []
    _, meta = ensure_roots(meta_root=meta_root)
    candidates.append(meta / "po-decision-residual-and-137.json")
    # Campaign evidence path relative to repo
    repo = Path(__file__).resolve().parents[2]
    candidates.append(
        repo
        / "docs"
        / "ops"
        / "campaigns"
        / "PROCESS-DOCS-01"
        / "vps"
        / "po-decision-residual-and-137.json"
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        accepts = data.get("accepts") or {}
        if data.get("decision") == "ACCEPT_RESIDUAL_WIN_QUAL_OPEN_AND_CLOSE_137" or (
            accepts.get("winning_proposal_completeness_below_85_percent")
            and accepts.get("bidder_qualification_completeness_below_70_percent")
            and accepts.get("full_denominators_retained")
        ):
            return {
                "path": str(path),
                "decision": data.get("decision"),
                "signer": data.get("signer") or data.get("product_owner"),
                "waives": sorted(_RESIDUAL_WAIVABLE_COMPLETENESS),
                "note": (
                    "PO residual acceptance waives gate exit for win/qual only. "
                    "meets_threshold remains false; denominators unchanged."
                ),
                "raw": {
                    "decision": data.get("decision"),
                    "signed_at": data.get("signed_at"),
                    "accepts": accepts,
                },
            }
    return None


def gate_exit_code(
    reports: dict[str, Any],
    *,
    residual_policy: dict[str, Any] | None = None,
) -> int:
    """Return non-zero if any honesty/threshold rule fails for claimed readiness.

    Discovery must be 100%. Other metrics fail the gate when denominators
    exist and ratios are below thresholds; empty denominators also fail closed
    for operational/recall/financial claims.

    When residual_policy waives win/qual completeness (explicit PO acceptance of
    publication limits with full denominators), those two metrics do not force
    exit 6 — but they remain meets_threshold=false in reports.
    """
    discovery = reports.get("discovery") or {}
    if discovery.get("entity_count") != EXPECTED_UNIVERSE:
        return 2
    if discovery.get("unknown_access_count", 0) > 0:
        return 2
    if not discovery.get("meets_100_percent"):
        return 2

    op = reports.get("operational") or {}
    if op.get("denominator", 0) <= 0 or not op.get("meets_threshold"):
        return 3

    recall = reports.get("recall") or {}
    if recall.get("denominator", 0) <= 0 or not recall.get("meets_threshold"):
        return 4

    fin = reports.get("financial") or {}
    if fin.get("total_value", 0) <= 0 or not fin.get("meets_threshold"):
        return 5

    policy = residual_policy if residual_policy is not None else load_residual_policy()
    waived = set((policy or {}).get("waives") or [])

    comp = reports.get("completeness") or {}
    metrics = (comp.get("metrics") or {}) if comp else {}
    for key in (
        "notice_and_annexes_completeness",
        "session_judgment_homologation_completeness",
        "winning_proposal_completeness",
        "bidder_qualification_documents_completeness",
    ):
        m = metrics.get(key) or {}
        if m.get("meets_threshold"):
            continue
        if key in waived and key in _RESIDUAL_WAIVABLE_COMPLETENESS:
            continue
        return 6
    return 0


def full_coverage_bundle(persist: bool = True) -> tuple[dict[str, Any], int]:
    discoveries, discovery_report = discover_all(persist=persist)
    discoveries, activity_report = classify_all_activity(discoveries, persist=persist)
    operational = compute_operational_coverage(discoveries, persist=persist)
    recall = compute_process_recall(persist=persist)
    financial = compute_financial_coverage(persist=persist)
    completeness = compute_completeness(persist=persist)
    gaps = compute_gaps(discoveries, persist=persist)
    residual_policy = load_residual_policy()
    bundle = {
        "discovery": discovery_report,
        "activity": activity_report,
        "operational": operational,
        "recall": recall,
        "financial": financial,
        "completeness": completeness,
        "gaps": gaps,
        "residual_policy": residual_policy,
        "generated_at": _now(),
        "thresholds": THRESHOLDS,
    }
    code = gate_exit_code(bundle, residual_policy=residual_policy)
    bundle["exit_code"] = code
    if residual_policy:
        bundle["residual_waivers_applied"] = residual_policy.get("waives")
        bundle["residual_waiver_note"] = residual_policy.get("note")
    if persist:
        _, meta = ensure_roots()
        write_json(meta / "coverage-bundle.json", bundle)
    return bundle, code
