"""Simple baseline rankings for comparison (not superiority claims)."""

from __future__ import annotations

from typing import Any

from scripts.commercial_leads.scoring import LeadScore


def baseline_by_value(candidates: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    rows = sorted(candidates, key=lambda r: (-float(r.get("total_value") or 0), r.get("cnpj14") or ""))
    out = []
    for i, r in enumerate(rows[:limit], start=1):
        out.append(
            {
                "rank": i,
                "cnpj14": r.get("cnpj14"),
                "razao_social": r.get("razao_social"),
                "metric": "total_value_contracted",
                "metric_value": r.get("total_value"),
            }
        )
    return out


def baseline_by_recency(candidates: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    rows = sorted(
        candidates,
        key=lambda r: (r.get("last_publication") or "", r.get("cnpj14") or ""),
        reverse=True,
    )
    out = []
    for i, r in enumerate(rows[:limit], start=1):
        out.append(
            {
                "rank": i,
                "cnpj14": r.get("cnpj14"),
                "razao_social": r.get("razao_social"),
                "metric": "last_publication",
                "metric_value": r.get("last_publication"),
            }
        )
    return out


def baseline_by_quantity(candidates: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    rows = sorted(
        candidates,
        key=lambda r: (-int(r.get("contract_count") or 0), r.get("cnpj14") or ""),
    )
    out = []
    for i, r in enumerate(rows[:limit], start=1):
        out.append(
            {
                "rank": i,
                "cnpj14": r.get("cnpj14"),
                "razao_social": r.get("razao_social"),
                "metric": "contract_count",
                "metric_value": r.get("contract_count"),
            }
        )
    return out


def _label_metrics(
    ordered_cnpjs: list[str],
    labels: dict[str, str],
    *,
    k10: int = 10,
    k20: int = 20,
) -> dict[str, Any]:
    """Human-label metrics. Labels: CLEAR_FIT|POSSIBLE_FIT|OUT_OF_SCOPE|INSUFFICIENT_EVIDENCE."""
    if not labels:
        return {
            "status": "BLOCKED_INSUFFICIENT_HUMAN_LABELS",
            "labeled_count": 0,
            "precision_at_10": None,
            "precision_at_20": None,
            "out_of_scope_rate": None,
            "unknown_rate": None,
            "mean_relevance_grade": None,
        }

    def grade(lab: str) -> float:
        return {
            "CLEAR_FIT": 1.0,
            "POSSIBLE_FIT": 0.5,
            "INSUFFICIENT_EVIDENCE": 0.25,
            "OUT_OF_SCOPE": 0.0,
        }.get(lab, 0.0)

    def precision_at(k: int, accept: set[str]) -> float | None:
        slice_ = ordered_cnpjs[:k]
        if not slice_:
            return None
        labeled = [c for c in slice_ if c in labels]
        if len(labeled) < min(k, 5):
            return None
        return sum(1 for c in labeled if labels[c] in accept) / len(labeled)

    top = ordered_cnpjs[:20]
    labeled_top = [c for c in top if c in labels]
    oos = sum(1 for c in labeled_top if labels[c] == "OUT_OF_SCOPE")
    unk = sum(1 for c in labeled_top if labels[c] in ("INSUFFICIENT_EVIDENCE", "UNKNOWN"))
    grades = [grade(labels[c]) for c in labeled_top]
    return {
        "status": "OK" if len(labeled_top) >= 10 else "BLOCKED_INSUFFICIENT_HUMAN_LABELS",
        "labeled_count": len(labeled_top),
        "precision_at_10": precision_at(k10, {"CLEAR_FIT", "POSSIBLE_FIT"}),
        "precision_at_20": precision_at(k20, {"CLEAR_FIT", "POSSIBLE_FIT"}),
        "precision_at_10_clear_only": precision_at(k10, {"CLEAR_FIT"}),
        "out_of_scope_rate": (oos / len(labeled_top)) if labeled_top else None,
        "unknown_rate": (unk / len(labeled_top)) if labeled_top else None,
        "mean_relevance_grade": (sum(grades) / len(grades)) if grades else None,
    }


def compare_to_baselines(
    ranked: list[LeadScore],
    candidates: list[dict[str, Any]],
    *,
    limit: int = 20,
    human_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    proposed = [L.cnpj14 for L in ranked]
    b_val = baseline_by_value(candidates, limit=limit)
    b_rec = baseline_by_recency(candidates, limit=limit)
    b_qty = baseline_by_quantity(candidates, limit=limit)

    def overlap(base: list[dict[str, Any]]) -> dict[str, Any]:
        s = {r["cnpj14"] for r in base}
        inter = [c for c in proposed if c in s]
        only_prop = [c for c in proposed if c not in s]
        only_base = [r["cnpj14"] for r in base if r["cnpj14"] not in set(proposed)]
        return {
            "overlap_count": len(inter),
            "overlap_cnpjs": inter,
            "only_proposed": only_prop,
            "only_baseline": only_base,
            "jaccard": (len(inter) / len(set(proposed) | s)) if (proposed or s) else 0.0,
        }

    labels = human_labels or {}
    # Prefer labels embedded on candidates when present
    if not labels:
        for c in candidates:
            lab = c.get("manual_sector_label") or c.get("human_label")
            if lab and c.get("cnpj14"):
                labels[str(c["cnpj14"])] = str(lab)

    proposed_metrics = _label_metrics(proposed, labels)
    val_metrics = _label_metrics([r["cnpj14"] for r in b_val], labels)
    rec_metrics = _label_metrics([r["cnpj14"] for r in b_rec], labels)
    qty_metrics = _label_metrics([r["cnpj14"] for r in b_qty], labels)

    ranking_status = "DESCRIPTIVE_ONLY"
    if proposed_metrics.get("status") == "BLOCKED_INSUFFICIENT_HUMAN_LABELS":
        ranking_status = "BLOCKED_INSUFFICIENT_HUMAN_LABELS"
    elif proposed_metrics.get("precision_at_10") is not None and val_metrics.get("precision_at_10") is not None:
        # Superior only if beats simple baselines on human precision@10 and lower OOS rate
        p10 = proposed_metrics["precision_at_10"]
        oos = proposed_metrics.get("out_of_scope_rate")
        base_p10 = max(
            m.get("precision_at_10") or 0.0 for m in (val_metrics, rec_metrics, qty_metrics)
        )
        base_oos = min(
            (m.get("out_of_scope_rate") if m.get("out_of_scope_rate") is not None else 1.0)
            for m in (val_metrics, rec_metrics, qty_metrics)
        )
        if p10 > base_p10 and (oos is None or oos <= base_oos):
            ranking_status = "SUPERIOR_ON_HUMAN_METRICS"
        elif p10 < base_p10 or (oos is not None and oos > base_oos + 0.05):
            ranking_status = "FAIL_RANKING_NOT_BETTER_THAN_SIMPLE_BASELINE"
        else:
            ranking_status = "NOT_PROVEN_SUPERIOR"

    return {
        "language_note": (
            "Comparação usa labels humanas quando disponíveis. "
            "Jaccard sozinho NÃO prova qualidade comercial."
        ),
        "proposed_count": len(proposed),
        "proposed_cnpjs": proposed,
        "baselines": {
            "by_value": b_val,
            "by_recency": b_rec,
            "by_quantity": b_qty,
        },
        "comparison": {
            "vs_value": overlap(b_val),
            "vs_recency": overlap(b_rec),
            "vs_quantity": overlap(b_qty),
        },
        "human_metrics": {
            "proposed": proposed_metrics,
            "baseline_value": val_metrics,
            "baseline_recency": rec_metrics,
            "baseline_quantity": qty_metrics,
        },
        "ranking_quality_status": ranking_status,
        "hypotheses": [
            "Ranking setorial deve reduzir OUT_OF_SCOPE vs valor/recência/quantidade brutos.",
            "Sobreposição alta com valor não prova qualidade comercial.",
        ],
    }
