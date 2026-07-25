"""Phase 14 — champion (RC v2 classifier) vs challenger (hybrid pipeline) shadow."""
from __future__ import annotations

from typing import Any

from scripts.ops.sector_classifier import classify_object, is_engineering_for_e
from scripts.ops.hybrid_sector.models import DecisionLineage, RawOpportunity


def champion_decide(rec: RawOpportunity) -> dict[str, Any]:
    clf = classify_object(
        objeto=rec.objeto,
        titulo=rec.titulo,
        itens=" ".join(rec.items) if rec.items else None,
    )
    # Map champion commercial: E_ALLOWED → MATCH-ish, else NO_MATCH
    if is_engineering_for_e(clf):
        commercial = "MATCH" if clf.label == "ENGINEERING_HIGH_CONFIDENCE" else "REVIEW"
    else:
        commercial = "NO_MATCH"
    return {
        "commercial_decision": commercial,
        "label": clf.label,
        "confidence": clf.confidence,
        "reason": clf.reason,
    }


def shadow_compare(
    universe: list[RawOpportunity],
    challenger_lineages: list[DecisionLineage],
    gold_labels: dict[str, str],
) -> dict[str, Any]:
    chal = {l.canonical_id: l for l in challenger_lineages}
    rows = []
    champ_match = champ_review = champ_nm = 0
    chal_match = chal_review = chal_nm = 0
    champ_safe = chal_safe = 0
    pos_ids = {i for i, l in gold_labels.items() if l == "POSITIVE"}

    for rec in universe:
        cid = rec.canonical_id
        if cid not in gold_labels:
            continue
        ch = champion_decide(rec)
        cl = chal.get(cid)
        cdec = cl.commercial_decision if cl else "MISSING"
        if ch["commercial_decision"] == "MATCH":
            champ_match += 1
        elif ch["commercial_decision"] == "REVIEW":
            champ_review += 1
        else:
            champ_nm += 1
        if cdec == "MATCH":
            chal_match += 1
        elif cdec == "REVIEW":
            chal_review += 1
        else:
            chal_nm += 1
        if cid in pos_ids:
            if ch["commercial_decision"] in {"MATCH", "REVIEW"}:
                champ_safe += 1
            if cdec in {"MATCH", "REVIEW"}:
                chal_safe += 1
        rows.append(
            {
                "canonical_id": cid,
                "gold": gold_labels[cid],
                "champion": ch["commercial_decision"],
                "challenger": cdec,
            }
        )

    n_pos = len(pos_ids) or 1
    return {
        "champion": {
            "match": champ_match,
            "review": champ_review,
            "no_match": champ_nm,
            "safe_recall": champ_safe / n_pos,
        },
        "challenger": {
            "match": chal_match,
            "review": chal_review,
            "no_match": chal_nm,
            "safe_recall": chal_safe / n_pos,
        },
        "rescued_by_challenger": sum(
            1
            for r in rows
            if r["gold"] == "POSITIVE"
            and r["champion"] == "NO_MATCH"
            and r["challenger"] in {"MATCH", "REVIEW"}
        ),
        "new_hard_fp_by_challenger": sum(
            1
            for r in rows
            if r["gold"] == "NEGATIVE"
            and r["challenger"] == "MATCH"
            and r["champion"] != "MATCH"
        ),
        "n_compared": len(rows),
        "promotion_eligible": False,  # never auto-promote in this goal
        "note": "Challenger must not replace champion without human + gate approval",
    }
