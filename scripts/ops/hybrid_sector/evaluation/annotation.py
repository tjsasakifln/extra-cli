"""Annotation provenance, agreement, and adjudication for operational gold.

Real operational labels require dual review rules — not a lone boolean.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_LABEL_FIELDS = (
    "annotator_id",
    "annotation_date",
    "decision",
    "justification",
    "evidence",
    "segment",
    "criticality",
    "documents_needed",
    "second_review",  # structured object, not bare bool
)

REQUIRED_SECOND_REVIEW_FIELDS = (
    "reviewer_id",
    "review_date",
    "decision",
    "agreement",
)


def _as_second_review(raw: Any) -> dict[str, Any] | None:
    """Normalize second_review to structured form; bare bool is invalid for operational gold."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None  # boolean alone is NOT proof of dual review
    if isinstance(raw, dict):
        return raw
    return None


def extract_annotation_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Extract labeling provenance for one record (operational schema)."""
    second = _as_second_review(rec.get("second_review"))
    annotation = rec.get("annotation") if isinstance(rec.get("annotation"), dict) else {}
    return {
        "canonical_id": rec.get("canonical_id"),
        "annotator_id": annotation.get("annotator_id") or rec.get("annotator_id"),
        "annotation_date": annotation.get("annotation_date")
        or rec.get("annotation_date")
        or rec.get("date"),
        "decision": annotation.get("decision") or rec.get("label"),
        "justification": annotation.get("justification")
        or rec.get("justificativa")
        or "",
        "evidence": annotation.get("evidence") or rec.get("evidence_span") or "",
        "segment": annotation.get("segment") or rec.get("segment") or "",
        "criticality": annotation.get("criticality") or rec.get("criticality") or "medium",
        "documents_needed": annotation.get("documents_needed")
        or rec.get("documents_needed")
        or [],
        "second_review": second,
        "adjudication": rec.get("adjudication")
        if isinstance(rec.get("adjudication"), dict)
        else None,
        "label_origin": rec.get("label_origin") or annotation.get("label_origin") or "",
    }


def validate_dual_review_rules(
    records: list[dict[str, Any]],
    *,
    dual_rest_min_rate: float = 0.20,
) -> dict[str, Any]:
    """Enforce dual review for critical positives, all ambiguous, ≥20% of rest."""
    locked = [r for r in records if r.get("split") == "locked"]
    if not locked:
        locked = list(records)

    if not locked:
        return {
            "ok": False,
            "checks": {
                "empty_corpus": {
                    "have": 0,
                    "need": 1,
                    "ok": False,
                }
            },
            "disagreements": [],
            "note": "Empty corpus cannot satisfy dual-review rules.",
        }

    critical_pos = [
        r
        for r in locked
        if r.get("label") == "POSITIVE"
        and str(r.get("criticality") or "").lower() in {"high", "critical"}
    ]
    ambiguous = [r for r in locked if r.get("label") == "AMBIGUOUS"]
    rest = [
        r
        for r in locked
        if r not in critical_pos and r not in ambiguous
    ]

    def has_dual(r: dict[str, Any]) -> bool:
        ann = extract_annotation_record(r)
        second = ann.get("second_review")
        if not isinstance(second, dict):
            return False
        return bool(second.get("reviewer_id") and second.get("decision") is not None)

    crit_dual = sum(1 for r in critical_pos if has_dual(r))
    amb_dual = sum(1 for r in ambiguous if has_dual(r))
    rest_dual = sum(1 for r in rest if has_dual(r))
    rest_rate = rest_dual / len(rest) if rest else 1.0

    disagreements = []
    for r in locked:
        ann = extract_annotation_record(r)
        second = ann.get("second_review")
        if not isinstance(second, dict):
            continue
        if second.get("decision") and second.get("decision") != ann.get("decision"):
            if second.get("agreement") is False or second.get("decision") != ann.get(
                "decision"
            ):
                adj = ann.get("adjudication")
                resolved = bool(adj and adj.get("final_decision"))
                disagreements.append(
                    {
                        "canonical_id": r.get("canonical_id"),
                        "primary": ann.get("decision"),
                        "secondary": second.get("decision"),
                        "adjudicated": resolved,
                        "final_decision": (adj or {}).get("final_decision"),
                    }
                )

    unresolved = [d for d in disagreements if not d["adjudicated"]]
    checks = {
        "critical_positives_dual": {
            "have": crit_dual,
            "need": len(critical_pos),
            "ok": crit_dual == len(critical_pos),
        },
        "ambiguous_dual": {
            "have": amb_dual,
            "need": len(ambiguous),
            "ok": amb_dual == len(ambiguous),
        },
        "rest_dual_rate": {
            "have": rest_rate,
            "need": dual_rest_min_rate,
            "ok": rest_rate + 1e-12 >= dual_rest_min_rate,
            "dual_count": rest_dual,
            "rest_count": len(rest),
        },
        "disagreements_resolved": {
            "total_disagreements": len(disagreements),
            "unresolved": len(unresolved),
            "ok": len(unresolved) == 0,
        },
    }
    ok = all(c.get("ok") for c in checks.values())
    return {
        "ok": ok,
        "checks": checks,
        "disagreements": disagreements,
        "note": (
            "Bare boolean second_review is NOT dual review. "
            "Operational gold requires structured second_review + adjudications."
        ),
    }


def build_annotation_artifacts(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build provenance, agreement, adjudications payloads."""
    provenance_rows = [extract_annotation_record(r) for r in records]
    dual = validate_dual_review_rules(records)

    # Agreement matrix
    pairs = []
    for row in provenance_rows:
        second = row.get("second_review")
        if not isinstance(second, dict):
            continue
        pairs.append(
            {
                "canonical_id": row["canonical_id"],
                "primary": row.get("decision"),
                "secondary": second.get("decision"),
                "agree": second.get("decision") == row.get("decision"),
            }
        )
    agree_n = sum(1 for p in pairs if p["agree"])
    agreement = {
        "n_dual_reviewed": len(pairs),
        "n_agree": agree_n,
        "raw_agreement": (agree_n / len(pairs)) if pairs else None,
        "pairs_preview": pairs[:50],
        "dual_review_rules": dual,
    }

    adjudications = []
    for row in provenance_rows:
        if row.get("adjudication"):
            adjudications.append(
                {
                    "canonical_id": row["canonical_id"],
                    **row["adjudication"],
                }
            )
        else:
            # unresolved disagreement should appear as pending
            for d in dual.get("disagreements") or []:
                if d["canonical_id"] == row["canonical_id"] and not d["adjudicated"]:
                    adjudications.append(
                        {
                            "canonical_id": row["canonical_id"],
                            "status": "PENDING",
                            "primary": d["primary"],
                            "secondary": d["secondary"],
                        }
                    )

    return {
        "annotation-provenance.json": {
            "schema_version": "annotation-provenance/1.0",
            "n_records": len(provenance_rows),
            "required_fields": list(REQUIRED_LABEL_FIELDS),
            "required_second_review_fields": list(REQUIRED_SECOND_REVIEW_FIELDS),
            "records": provenance_rows,
        },
        "annotation-agreement.json": {
            "schema_version": "annotation-agreement/1.0",
            **agreement,
        },
        "annotation-adjudications.json": {
            "schema_version": "annotation-adjudications/1.0",
            "n": len(adjudications),
            "adjudications": adjudications,
        },
    }


def write_annotation_artifacts(
    records: list[dict[str, Any]],
    out_dir: Path,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    arts = build_annotation_artifacts(records)
    paths: dict[str, Path] = {}
    for name, payload in arts.items():
        p = out_dir / name
        p.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        paths[name] = p
    return paths


def synthetic_has_only_boolean_second_review(records: list[dict[str, Any]]) -> bool:
    """True when corpus uses bare bool second_review (synthetic fixture pattern)."""
    if not records:
        return False
    bool_count = sum(1 for r in records if isinstance(r.get("second_review"), bool))
    struct_count = sum(1 for r in records if isinstance(r.get("second_review"), dict))
    return bool_count > 0 and struct_count == 0
