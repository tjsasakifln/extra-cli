"""Gold corpus loaders — synthetic Level B vs real Level C.

Synthetic adversarial fixtures remain valid only as SYNTHETIC_ADVERSARIAL_FIXTURE.
They must never be reported as operational gold.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.ops.hybrid_sector.evaluation.real_corpus import (
    BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS,
    BLOCKED_INVALID_EVALUATION_CORPUS,
    CORPUS_KIND_SYNTHETIC,
    audit_real_corpus,
    classify_corpus,
    is_operational_gold,
)


def near_dup_key(objeto: str) -> str:
    t = " ".join((objeto or "").lower().split())
    return hashlib.sha1(t.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def load_gold_corpus(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "records" not in data:
        raise ValueError(f"invalid gold corpus: {path}")
    # Ensure kind is stamped
    if not data.get("corpus_kind"):
        data["corpus_kind"] = classify_corpus(data)
    return data


def corpus_manifest(path: Path, corpus: dict[str, Any] | None = None) -> dict[str, Any]:
    corpus = corpus or load_gold_corpus(path)
    kind = classify_corpus(corpus)
    audit = audit_real_corpus(corpus)
    return {
        "path": str(path),
        "corpus_id": corpus.get("corpus_id"),
        "corpus_kind": kind,
        "evaluation_level": audit.get("evaluation_level"),
        "operational_gold": is_operational_gold(corpus),
        "operational_gold_eligible": audit.get("operational_gold_eligible"),
        "split_stats": split_stats(corpus),
        "locked_adequacy": locked_test_adequacy(corpus),
        "real_corpus_audit": audit,
        "labels_independent_of_classifier": True,
        "synthetic_only_for": (
            ["unit_regression", "adversarial_attacks", "level_B_benchmark"]
            if kind == CORPUS_KIND_SYNTHETIC
            else []
        ),
        "not_for_operational_claims": kind == CORPUS_KIND_SYNTHETIC,
    }


def split_stats(corpus: dict[str, Any]) -> dict[str, Any]:
    records = corpus.get("records") or []
    by_split: dict[str, dict[str, int]] = {}
    for r in records:
        sp = r.get("split") or "unknown"
        lab = r.get("label") or "unknown"
        by_split.setdefault(sp, {})
        by_split[sp][lab] = by_split[sp].get(lab, 0) + 1
        by_split[sp]["total"] = by_split[sp].get("total", 0) + 1
    return by_split


def locked_test_adequacy(
    corpus: dict[str, Any], *, cfg: dict[str, int] | None = None
) -> dict[str, Any]:
    """Count quotas on locked split.

    For SYNTHETIC corpora this reports numeric adequacy only — it does NOT
    clear operational gold requirements.
    """
    cfg = {
        "locked_min_positives": 300,
        "locked_min_hard_negatives": 300,
        "locked_min_ambiguous": 150,
        "locked_min_positives_without_keywords": 100,
        **(cfg or {}),
    }
    locked = [r for r in corpus.get("records") or [] if r.get("split") == "locked"]
    pos = [r for r in locked if r.get("label") == "POSITIVE"]
    neg = [r for r in locked if r.get("label") == "NEGATIVE"]
    amb = [r for r in locked if r.get("label") == "AMBIGUOUS"]
    pos_no_kw = [r for r in pos if not r.get("has_keyword")]

    checks = {
        "positives": (len(pos), cfg["locked_min_positives"]),
        "hard_negatives": (len(neg), cfg["locked_min_hard_negatives"]),
        "ambiguous": (len(amb), cfg["locked_min_ambiguous"]),
        "positives_without_keywords": (
            len(pos_no_kw),
            cfg["locked_min_positives_without_keywords"],
        ),
    }
    ok = all(have >= need for have, need in checks.values())
    kind = classify_corpus(corpus)
    return {
        "ok": ok,
        "checks": {
            k: {"have": h, "need": n, "ok": h >= n} for k, (h, n) in checks.items()
        },
        "dual_review_rate": _dual_review_rate_legacy_bool(locked),
        "corpus_kind": kind,
        "operational_gold": is_operational_gold(corpus),
        "numeric_quotas_only": kind == CORPUS_KIND_SYNTHETIC,
        "blockers": (
            [BLOCKED_INVALID_EVALUATION_CORPUS]
            if kind == CORPUS_KIND_SYNTHETIC
            else (
                [BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS]
                if not ok
                else []
            )
        ),
        "note": (
            "SYNTHETIC_ADVERSARIAL_FIXTURE: numeric counts may pass but this is NOT "
            "operational gold. Level C requires real public records + dual human review."
            if kind == CORPUS_KIND_SYNTHETIC
            else (
                "Labels for operational gold require structured dual review provenance."
            )
        ),
    }


def _dual_review_rate_legacy_bool(records: list[dict[str, Any]]) -> float:
    """Legacy synthetic rate (bool second_review). Not proof of human dual review."""
    if not records:
        return 0.0
    dual = sum(
        1
        for r in records
        if r.get("second_review") is True
        or (
            isinstance(r.get("second_review"), dict)
            and r["second_review"].get("reviewer_id")
        )
    )
    return dual / len(records)


def gold_index(
    corpus: dict[str, Any], *, split: str = "locked"
) -> tuple[dict[str, str], dict[str, dict[str, Any]], set[str]]:
    """Return labels, meta, critical positive ids for a split."""
    labels: dict[str, str] = {}
    meta: dict[str, dict[str, Any]] = {}
    critical: set[str] = set()
    for r in corpus.get("records") or []:
        if r.get("split") != split:
            continue
        cid = r["canonical_id"]
        labels[cid] = r["label"]
        meta[cid] = r
        if r.get("label") == "POSITIVE" and r.get("criticality") == "high":
            critical.add(cid)
    return labels, meta, critical


def adjudicated_match_ids(corpus: dict[str, Any], *, split: str = "locked") -> set[str]:
    """IDs with explicit adjudication final_decision (for conservative precision)."""
    out: set[str] = set()
    for r in corpus.get("records") or []:
        if r.get("split") != split:
            continue
        adj = r.get("adjudication")
        if isinstance(adj, dict) and adj.get("final_decision"):
            out.add(r["canonical_id"])
    return out


def records_as_universe(
    corpus: dict[str, Any], *, split: str | None = None
) -> list[dict[str, Any]]:
    out = []
    for r in corpus.get("records") or []:
        if split and r.get("split") != split:
            continue
        out.append(
            {
                "source": r.get("source") or "gold",
                "official_id": r.get("official_id")
                or r["canonical_id"].split("::")[-1],
                "objeto": r.get("objeto") or "",
                "titulo": r.get("titulo") or "",
                "items": r.get("items") or [],
                "categories": r.get("categories") or [],
                "orgao": r.get("orgao") or "",
                "municipio": r.get("municipio") or "",
                "uf": r.get("uf") or "SC",
                "modalidade": r.get("modalidade") or "",
                "valor_estimado": r.get("valor_estimado"),
                "data_encerramento": r.get("data_encerramento"),
                "urls": r.get("urls") or [],
                "has_edital": bool(r.get("has_edital")),
                "has_tr": bool(r.get("has_tr")),
                "has_etp": bool(r.get("has_etp")),
                "has_anexos": bool(r.get("has_anexos")),
                "captured_at": r.get("captured_at") or "",
                "source_coverage_status": r.get("source_coverage_status") or "fixture",
                "source_freshness_status": r.get("source_freshness_status") or "fixture",
            }
        )
    return out
