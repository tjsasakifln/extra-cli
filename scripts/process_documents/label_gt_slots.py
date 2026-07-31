"""Structural labeling of bid_readiness GT slots from collected evidence.

IMPORTANT: These labels are **structural / evidence-based**, not human legal
judgment of bid readiness. They do NOT authorize READY_TO_SUBMIT or #137 close.

Label rules (deterministic):
- document_sha256 present in CAS/runs → present
- document_sha256 missing / empty → missing
- title/category signals for expired/wrong_entity are left for human when ambiguous
- every slot retains human_review_required=True until human confirms

Outputs updated queue + FP/FN report without closing #137.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.process_documents.classify_docs import classify_document_record
from scripts.process_documents.storage import ensure_roots, write_json


def _index_docs(meta: Path) -> dict[str, dict[str, Any]]:
    """sha256 → doc meta; process_id → set of categories."""
    by_sha: dict[str, dict[str, Any]] = {}
    by_proc: dict[str, set[str]] = defaultdict(set)
    for p in (meta / "runs").glob("*/result.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for doc in data.get("documents") or []:
            sha = (doc.get("sha256") or "").strip()
            pid = str(doc.get("procurement_id") or doc.get("notice_id") or "")
            cat = classify_document_record(doc)
            if pid:
                by_proc[pid].add(cat)
            if sha:
                by_sha[sha] = {
                    "process_id": pid,
                    "category": cat,
                    "title": doc.get("original_title"),
                    "source_id": doc.get("source_id"),
                    "size_bytes": doc.get("size_bytes"),
                }
    return {"by_sha": by_sha, "by_proc": by_proc}


def label_gt_queue(
    *,
    meta_root: Path | None = None,
    min_slots: int = 500,
) -> dict[str, Any]:
    _, meta = ensure_roots(meta_root=meta_root)
    idx = _index_docs(meta)
    by_sha = idx["by_sha"]
    by_proc = idx["by_proc"]

    queue_path = meta / "bid-readiness-human-gt-queue.jsonl"
    if not queue_path.is_file():
        raise FileNotFoundError(f"missing GT queue: {queue_path}")

    slots: list[dict[str, Any]] = []
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            slots.append(json.loads(line))

    label_counts: Counter[str] = Counter()
    labeled: list[dict[str, Any]] = []
    for slot in slots:
        sha = (slot.get("document_sha256") or "").strip()
        pid = str(slot.get("process_id") or "")
        evidence = by_sha.get(sha)
        if sha and evidence:
            structural = "present"
            conf = "high"
            note = "document blob present in process_documents CAS/runs"
        elif sha:
            structural = "missing"
            conf = "medium"
            note = "sha referenced but not found in current run index"
        else:
            structural = "missing"
            conf = "high"
            note = "no document hash on slot"
        # Soft signals for human attention (not automatic critical claims)
        flags: list[str] = []
        title = str(slot.get("original_title") or (evidence or {}).get("title") or "").lower()
        if any(k in title for k in ("vencid", "expirad", "cancelad")):
            flags.append("possible_expired_signal_in_title")
        if evidence and evidence.get("process_id") and pid and evidence["process_id"] != pid:
            flags.append("process_id_mismatch")
            structural = "wrong_entity"
            conf = "medium"
            note = "document process_id differs from slot process_id"

        out = {
            **slot,
            "structural_label": structural,
            "label": structural,  # provisional structural label
            "label_source": "automated_structural_from_cas",
            "label_confidence": conf,
            "label_note": note,
            "flags": flags,
            "human_review_required": True,  # always until human confirms
            "human_confirmed": False,
            "status": "structural_labeled_awaiting_human_confirm",
            "labeled_at": datetime.now(UTC).isoformat(),
        }
        label_counts[structural] += 1
        labeled.append(out)

    # Write labeled queue
    labeled_path = meta / "bid-readiness-human-gt-queue-labeled.jsonl"
    with labeled_path.open("w", encoding="utf-8") as fh:
        for row in labeled:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    # FP/FN analysis (structural, not bid-readiness legal)
    false_positives = []
    false_negatives = []
    critical_risks = []
    for row in labeled:
        cats = by_proc.get(str(row.get("process_id") or ""), set())
        # FP risk: sparse pack that must never auto READY_TO_SUBMIT
        if row["structural_label"] == "present" and not cats.intersection(
            {"edital", "termo_referencia", "aviso"}
        ):
            false_positives.append(
                {
                    "process_id": row.get("process_id"),
                    "kind": "document_present_without_notice_core",
                    "severity": "critical_if_auto_submit",
                    "human_review_required": True,
                }
            )
        # FN risk: engineering-ish title without edital/TR
        title = str(row.get("original_title") or "").lower()
        if any(k in title for k in ("obra", "paviment", "engenharia", "reforma", "constru")):
            if not cats.intersection({"edital", "termo_referencia"}):
                false_negatives.append(
                    {
                        "process_id": row.get("process_id"),
                        "kind": "engineering_signal_without_notice_pack",
                        "severity": "high",
                        "human_review_required": True,
                    }
                )
        if row.get("flags"):
            critical_risks.append(
                {
                    "process_id": row.get("process_id"),
                    "flags": row["flags"],
                    "severity": "medium",
                    "human_review_required": True,
                }
            )

    fp_fn = {
        "generated_at": datetime.now(UTC).isoformat(),
        "methodology": "automated_structural_from_cas + category heuristics",
        "false_positives": false_positives[:80],
        "false_negatives": false_negatives[:80],
        "critical_errors": critical_risks[:80],
        "automated_candidate_counts": {
            "false_positive_candidates": len(false_positives),
            "false_negative_candidates": len(false_negatives),
            "critical_risk_candidates": len(critical_risks),
            "structural_labels": dict(label_counts),
        },
        "policy": {
            "READY_TO_SUBMIT_without_human_review": "forbidden",
            "automated_labels_are_not_ground_truth": True,
            "human_confirmation_required": True,
            "expired_cert_as_valid": "critical",
            "wrong_cnpj_accepted": "critical",
            "missing_mandatory_ignored": "critical",
        },
        "status": "structural_labeled_awaiting_human_confirm",
        "human_ground_truth_complete": False,
        "human_confirmed_count": 0,
        "ready_to_submit_allowed": False,
        "issue_137_close_allowed": False,
        "process_count": len(by_proc),
        "annotation_count": len(labeled),
        "slots_labeled_structurally": len(labeled),
        "meets_min_500_slots": len(labeled) >= min_slots,
        "note": (
            "Structural labels filled from CAS presence. "
            "Human must confirm before #137 close. READY_TO_SUBMIT forbidden."
        ),
    }
    write_json(meta / "bid-readiness-fp-fn-report.json", fp_fn)

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "queue_path": str(labeled_path),
        "slots": len(labeled),
        "structural_label_counts": dict(label_counts),
        "human_confirmed_count": 0,
        "human_ground_truth_complete": False,
        "meets_min_slots": len(labeled) >= min_slots,
        "issue_137_close_allowed": False,
        "ready_to_submit_allowed": False,
        "status": "structural_labeled_awaiting_human_confirm",
        "fp_fn_path": str(meta / "bid-readiness-fp-fn-report.json"),
        "note": "Automated structural labeling only. Human confirmation still required.",
    }
    write_json(meta / "bid-readiness-human-gt-manifest.json", manifest)
    return {
        "slots": len(labeled),
        "label_counts": dict(label_counts),
        "fp_fn": fp_fn["automated_candidate_counts"],
        "manifest": manifest,
    }


if __name__ == "__main__":
    print(json.dumps(label_gt_queue(), indent=2))
