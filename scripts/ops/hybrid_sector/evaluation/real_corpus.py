"""Level C — real public operational gold corpus validation.

Never fill quotas with invented phrases. If counts short → BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.ops.hybrid_sector.evaluation.annotation import (
    validate_dual_review_rules,
    write_annotation_artifacts,
)

CORPUS_KIND_SYNTHETIC = "SYNTHETIC_ADVERSARIAL_FIXTURE"
CORPUS_KIND_REAL = "REAL_OPERATIONAL_LOCKED_GOLD"
CORPUS_KIND_UNIT = "UNIT_FIXTURE"

REQUIRED_PUBLIC_FIELDS = (
    "canonical_id",
    "official_id",
    "source",
    "urls",  # official URL
    "objeto",
    "titulo",
    "items",
    "categories",
    "orgao",
    "municipio",
    "uf",
    "modalidade",
    "valor_estimado",
    "data_encerramento",
    "captured_at",
)

# Document availability flags (at least presence fields)
DOC_FLAGS = ("has_edital", "has_tr", "has_etp", "has_anexos")

BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS = "BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS"
BLOCKED_INVALID_EVALUATION_CORPUS = "BLOCKED_INVALID_EVALUATION_CORPUS"


def classify_corpus(corpus: dict[str, Any]) -> str:
    kind = corpus.get("corpus_kind") or ""
    if kind:
        return str(kind)
    # Heuristic: example.local or fixture coverage → synthetic
    records = corpus.get("records") or []
    if not records:
        return CORPUS_KIND_REAL  # empty scaffold
    sample = records[:50]
    synthetic_signals = 0
    for r in sample:
        urls = r.get("urls") or []
        blob = " ".join(str(u) for u in urls)
        if "example.local" in blob:
            synthetic_signals += 1
        if r.get("source_coverage_status") == "fixture":
            synthetic_signals += 1
    if synthetic_signals >= max(1, len(sample) // 2):
        return CORPUS_KIND_SYNTHETIC
    return CORPUS_KIND_REAL


def is_operational_gold(corpus: dict[str, Any]) -> bool:
    if corpus.get("operational_gold") is False:
        return False
    return classify_corpus(corpus) == CORPUS_KIND_REAL


def load_real_or_any_corpus(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "records" not in data:
        raise ValueError(f"invalid corpus: {path}")
    return data


def record_has_required_public_fields(rec: dict[str, Any]) -> tuple[bool, list[str]]:
    missing = []
    for f in REQUIRED_PUBLIC_FIELDS:
        val = rec.get(f)
        if f == "urls":
            if not val:
                missing.append(f)
        elif f == "valor_estimado":
            if val is None:
                missing.append(f)
        elif f in {"items", "categories"}:
            # may be empty list if source has none — field must exist
            if f not in rec:
                missing.append(f)
        elif val is None or val == "":
            # titulo may be empty string on some sources — still require key
            if f == "titulo" and f in rec:
                continue
            if f not in rec or val is None:
                missing.append(f)
    # docs available: at least one doc flag key present
    if not any(f in rec for f in DOC_FLAGS):
        missing.append("documents_available_flags")
    return len(missing) == 0, missing


def real_locked_quota_checks(
    corpus: dict[str, Any],
    *,
    cfg: dict[str, int] | None = None,
) -> dict[str, Any]:
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
    return {
        "ok": ok,
        "checks": {
            k: {"have": h, "need": n, "ok": h >= n} for k, (h, n) in checks.items()
        },
        "locked_count": len(locked),
    }


def audit_real_corpus(corpus: dict[str, Any], *, cfg: dict | None = None) -> dict[str, Any]:
    """Full Level C audit. Never invents records."""
    kind = classify_corpus(corpus)
    records = list(corpus.get("records") or [])
    locked = [r for r in records if r.get("split") == "locked"] or records

    field_ok = 0
    field_fail = 0
    missing_examples: list[dict[str, Any]] = []
    private_flags = 0
    for r in locked:
        ok, missing = record_has_required_public_fields(r)
        if ok:
            field_ok += 1
        else:
            field_fail += 1
            if len(missing_examples) < 10:
                missing_examples.append(
                    {"canonical_id": r.get("canonical_id"), "missing": missing}
                )
        # Heuristic: Extra private markers
        blob = json.dumps(r, ensure_ascii=False).lower()
        if any(
            s in blob
            for s in (
                "extra consultoria confidencial",
                "cliente_extra_private",
                "internal_only",
            )
        ):
            private_flags += 1

    quotas = real_locked_quota_checks(corpus, cfg=cfg)
    dual = validate_dual_review_rules(locked)
    synthetic = kind == CORPUS_KIND_SYNTHETIC

    blockers: list[str] = []
    if synthetic:
        blockers.append(BLOCKED_INVALID_EVALUATION_CORPUS)
    if not quotas["ok"]:
        blockers.append(BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS)
    if not dual["ok"] and not synthetic:
        blockers.append(BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS)
    if private_flags:
        blockers.append(BLOCKED_INVALID_EVALUATION_CORPUS)
    if field_fail and not synthetic:
        blockers.append(BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS)

    return {
        "corpus_kind": kind,
        "evaluation_level": "C" if kind == CORPUS_KIND_REAL else ("B" if synthetic else "A"),
        "operational_gold_eligible": (
            kind == CORPUS_KIND_REAL
            and quotas["ok"]
            and dual["ok"]
            and private_flags == 0
            and field_fail == 0
        ),
        "quotas": quotas,
        "dual_review": dual,
        "fields": {
            "ok_count": field_ok,
            "fail_count": field_fail,
            "missing_examples": missing_examples,
        },
        "private_data_flags": private_flags,
        "blockers": sorted(set(blockers)),
        "n_records": len(records),
        "n_locked": len(locked),
        "invented_fill_forbidden": True,
        "note": (
            "Level C only. Synthetic fixtures are Level B and cannot sustain "
            "operational recall/precision claims."
        ),
    }


def empty_real_corpus_scaffold() -> dict[str, Any]:
    """Scaffold for operational gold — zero invented rows."""
    return {
        "corpus_id": "hybrid-sector-real-operational-locked-v0",
        "version": "0.0.0",
        "corpus_kind": CORPUS_KIND_REAL,
        "evaluation_level": "C",
        "operational_gold": True,
        "label_policy": (
            "Independent human dual labeling of real public opportunities only. "
            "No invented objects. No Extra-private data."
        ),
        "dual_review_policy": (
            "All critical POSITIVE dual-reviewed; all AMBIGUOUS dual-reviewed; "
            "≥20% of remaining dual-reviewed; disagreements explicitly adjudicated."
        ),
        "quota_targets": {
            "positives": 300,
            "hard_negatives": 300,
            "ambiguous_mixed": 150,
            "positives_without_keywords": 100,
        },
        "splits": {"locked": "blocked evaluation only"},
        "records": [],
        "status": BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS,
    }


def ensure_real_corpus_file(path: Path) -> dict[str, Any]:
    """Create empty scaffold if missing; never invent content rows."""
    if path.is_file():
        return load_real_or_any_corpus(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = empty_real_corpus_scaffold()
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    # empty annotation artifacts
    write_annotation_artifacts([], path.parent)
    return data
