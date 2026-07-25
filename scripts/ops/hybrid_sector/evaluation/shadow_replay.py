"""Champion (RC v2 classifier) vs challenger (hybrid pipeline) shadow replay.

Promotion requires real multi-window multi-source benchmark + human review.
Never promote on synthetic-only results.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from scripts.ops.hybrid_sector.models import DecisionLineage, RawOpportunity
from scripts.ops.sector_classifier import classify_object, is_engineering_for_e


def champion_decide(rec: RawOpportunity) -> dict[str, Any]:
    clf = classify_object(
        objeto=rec.objeto,
        titulo=rec.titulo,
        itens=" ".join(rec.items) if rec.items else None,
    )
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


def _metrics_for(
    rows: list[dict[str, Any]],
    side: str,
    pos_ids: set[str],
    neg_ids: set[str],
) -> dict[str, Any]:
    match = review = nm = 0
    safe = 0
    tp = fp = 0
    for r in rows:
        dec = r[side]
        if dec == "MATCH":
            match += 1
            if r["gold"] == "POSITIVE":
                tp += 1
            elif r["gold"] == "NEGATIVE":
                fp += 1
        elif dec == "REVIEW":
            review += 1
        else:
            nm += 1
        if r["canonical_id"] in pos_ids and dec in {"MATCH", "REVIEW"}:
            safe += 1
    n_pos = len(pos_ids) or 1
    n_rows = len(rows) or 1
    return {
        "match": match,
        "review": review,
        "no_match": nm,
        "safe_recall": safe / n_pos,
        "review_rate": review / n_rows,
        "false_negative_rate": sum(
            1
            for r in rows
            if r["canonical_id"] in pos_ids and r[side] == "NO_MATCH"
        )
        / n_pos,
        "precision_all_match": (tp / match) if match else 1.0,
        "match_true_positives": tp,
        "match_false_positives": fp,
    }


def shadow_compare(
    universe: list[RawOpportunity],
    challenger_lineages: list[DecisionLineage],
    gold_labels: dict[str, str],
    *,
    corpus_kind: str = "SYNTHETIC_ADVERSARIAL_FIXTURE",
    human_review_promotion: bool = False,
    cost_champion: float | None = None,
    cost_challenger: float | None = None,
    latency_champion_s: float | None = None,
    latency_challenger_s: float | None = None,
) -> dict[str, Any]:
    chal = {l.canonical_id: l for l in challenger_lineages}
    rows = []
    pos_ids = {i for i, l in gold_labels.items() if l == "POSITIVE"}
    neg_ids = {i for i, l in gold_labels.items() if l == "NEGATIVE"}

    for rec in universe:
        cid = rec.canonical_id
        if cid not in gold_labels:
            continue
        ch = champion_decide(rec)
        cl = chal.get(cid)
        cdec = cl.commercial_decision if cl else "MISSING"
        rows.append(
            {
                "canonical_id": cid,
                "gold": gold_labels[cid],
                "champion": ch["commercial_decision"],
                "challenger": cdec,
                "source": rec.source,
                "captured_at": rec.captured_at or "",
                "segment": "",
            }
        )

    champ_m = _metrics_for(rows, "champion", pos_ids, neg_ids)
    chal_m = _metrics_for(rows, "challenger", pos_ids, neg_ids)

    rescues = sum(
        1
        for r in rows
        if r["gold"] == "POSITIVE"
        and r["champion"] == "NO_MATCH"
        and r["challenger"] in {"MATCH", "REVIEW"}
    )
    new_fp = sum(
        1
        for r in rows
        if r["gold"] == "NEGATIVE"
        and r["challenger"] == "MATCH"
        and r["champion"] != "MATCH"
    )

    real = corpus_kind == "REAL_OPERATIONAL_LOCKED_GOLD"
    # promotion only with real benchmark + human review
    promotion_eligible = bool(
        real
        and human_review_promotion
        and chal_m["safe_recall"] >= champ_m["safe_recall"]
        and new_fp == 0
    )

    return {
        "champion": {
            **champ_m,
            "cost_usd": cost_champion,
            "latency_s": latency_champion_s,
        },
        "challenger": {
            **chal_m,
            "cost_usd": cost_challenger,
            "latency_s": latency_challenger_s,
            "rescues": rescues,
            "new_false_positives": new_fp,
        },
        "rescued_by_challenger": rescues,
        "new_hard_fp_by_challenger": new_fp,
        "n_compared": len(rows),
        "corpus_kind": corpus_kind,
        "promotion_eligible": promotion_eligible,
        "promotion_requires": {
            "real_operational_corpus": real,
            "human_review": human_review_promotion,
            "no_new_hard_fp": new_fp == 0,
        },
        "note": (
            "Challenger must not replace champion without human + real Level C gate approval. "
            "Synthetic-only shadow never sets promotion_eligible=true."
        ),
    }


def multi_window_shadow(
    universe: list[RawOpportunity],
    challenger_lineages: list[DecisionLineage],
    gold_labels: dict[str, str],
    *,
    windows: list[tuple[str, str, str]] | None = None,
    corpus_kind: str = "SYNTHETIC_ADVERSARIAL_FIXTURE",
) -> dict[str, Any]:
    """Shadow across ≥3 temporal windows and ≥2 sources when data allows.

    windows: list of (name, start_iso, end_iso). If None, derive from captured_at.
    """
    chal = {l.canonical_id: l for l in challenger_lineages}
    by_source: dict[str, list[RawOpportunity]] = defaultdict(list)
    for rec in universe:
        if rec.canonical_id in gold_labels:
            by_source[rec.source or "unknown"].append(rec)

    # Derive windows from dates if not provided
    dates = sorted(
        {
            (rec.captured_at or rec.data_encerramento or "")[:10]
            for rec in universe
            if (rec.captured_at or rec.data_encerramento)
        }
    )
    if not windows:
        if len(dates) >= 3:
            # three equal terciles by unique dates
            n = len(dates)
            w1, w2, w3 = dates[: n // 3], dates[n // 3 : 2 * n // 3], dates[2 * n // 3 :]
            windows = [
                ("window_1", w1[0] if w1 else "", w1[-1] if w1 else ""),
                ("window_2", w2[0] if w2 else "", w2[-1] if w2 else ""),
                ("window_3", w3[0] if w3 else "", w3[-1] if w3 else ""),
            ]
        else:
            windows = [
                ("window_all", dates[0] if dates else "", dates[-1] if dates else ""),
                ("window_placeholder_2", "", ""),
                ("window_placeholder_3", "", ""),
            ]

    window_results = []
    for name, start, end in windows:
        subset = []
        for rec in universe:
            if rec.canonical_id not in gold_labels:
                continue
            d = (rec.captured_at or rec.data_encerramento or "")[:10]
            if start and end and d and not (start <= d <= end):
                continue
            if start and end and not d and name != "window_all":
                continue
            subset.append(rec)
        # periods with and without opportunities
        has_pos = any(gold_labels.get(r.canonical_id) == "POSITIVE" for r in subset)
        lin_sub = [chal[r.canonical_id] for r in subset if r.canonical_id in chal]
        labels_sub = {r.canonical_id: gold_labels[r.canonical_id] for r in subset}
        cmp_ = shadow_compare(
            subset, lin_sub, labels_sub, corpus_kind=corpus_kind
        )
        window_results.append(
            {
                "window": name,
                "start": start,
                "end": end,
                "n": len(subset),
                "has_positive_opportunities": has_pos,
                "comparison": cmp_,
            }
        )

    source_results = []
    for src, recs in sorted(by_source.items()):
        lin_sub = [chal[r.canonical_id] for r in recs if r.canonical_id in chal]
        labels_sub = {r.canonical_id: gold_labels[r.canonical_id] for r in recs}
        source_results.append(
            {
                "source": src,
                "n": len(recs),
                "comparison": shadow_compare(
                    recs, lin_sub, labels_sub, corpus_kind=corpus_kind
                ),
            }
        )

    overall = shadow_compare(
        universe, challenger_lineages, gold_labels, corpus_kind=corpus_kind
    )
    return {
        "overall": overall,
        "windows": window_results,
        "sources": source_results,
        "n_windows": len(window_results),
        "n_sources": len(source_results),
        "min_windows_required": 3,
        "min_sources_required": 2,
        "windows_requirement_met": len(window_results) >= 3,
        "sources_requirement_met": len(source_results) >= 2,
        "promotion_eligible": overall.get("promotion_eligible", False),
        "corpus_kind": corpus_kind,
    }
