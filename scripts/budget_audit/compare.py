"""Cross-workbook / proposal comparison with explicit match types."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from scripts.budget_audit.units import units_compatible


def _norm_text(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def description_similarity(a: str | None, b: str | None) -> float:
    return SequenceMatcher(None, _norm_text(a), _norm_text(b)).ratio()


def match_items(
    left_items: list[dict[str, Any]],
    right_items: list[dict[str, Any]],
    *,
    left_label: str = "left",
    right_label: str = "right",
) -> dict[str, Any]:
    """Match budget items between two sets. Ambiguous/unmatched stay in denominator."""
    pairs: list[dict[str, Any]] = []
    used_right: set[str] = set()

    right_by_code: dict[str, list[dict[str, Any]]] = {}
    for r in right_items:
        if r.get("code"):
            right_by_code.setdefault(str(r["code"]), []).append(r)

    matched_left: set[str] = set()

    for left in left_items:
        lid = left.get("item_id")
        code = str(left.get("code")) if left.get("code") else None
        candidates = right_by_code.get(code, []) if code else []

        if code and candidates:
            # prefer same unit
            same_unit = [
                c
                for c in candidates
                if c.get("item_id") not in used_right
                and units_compatible(left.get("unit"), c.get("unit"))
            ]
            if same_unit:
                right = same_unit[0]
                match_type = "EXACT_CODE_UNIT"
            else:
                free = [c for c in candidates if c.get("item_id") not in used_right]
                if not free:
                    continue
                right = free[0]
                match_type = "EXACT_CODE_DIFFERENT_UNIT"
            used_right.add(right["item_id"])
            matched_left.add(lid)
            pairs.append(_pair(left, right, match_type, left_label, right_label))
            continue

        # text fallback — reviewable only
        best = None
        best_score = 0.0
        for r in right_items:
            if r.get("item_id") in used_right:
                continue
            score = description_similarity(left.get("description"), r.get("description"))
            if score > best_score:
                best_score = score
                best = r
        if best and best_score >= 0.92:
            if not units_compatible(left.get("unit"), best.get("unit")):
                pairs.append(
                    _pair(
                        left,
                        best,
                        "AMBIGUOUS",
                        left_label,
                        right_label,
                        limitations=["unit_incompatible_blocks_auto_accept"],
                        force_status="AMBIGUOUS",
                    )
                )
                # do not mark used — ambiguous
                matched_left.add(lid)
            else:
                used_right.add(best["item_id"])
                matched_left.add(lid)
                pairs.append(
                    _pair(
                        left,
                        best,
                        "REVIEWABLE_TEXT",
                        left_label,
                        right_label,
                        sim=best_score,
                    )
                )
        elif best and best_score >= 0.75:
            pairs.append(
                _pair(
                    left,
                    best,
                    "AMBIGUOUS",
                    left_label,
                    right_label,
                    sim=best_score,
                    limitations=["similarity_below_auto_threshold"],
                )
            )
            matched_left.add(lid)

    unmatched_left = [i for i in left_items if i.get("item_id") not in matched_left]
    unmatched_right = [i for i in right_items if i.get("item_id") not in used_right]

    for u in unmatched_left:
        pairs.append(
            {
                "match_type": "UNMATCHED",
                "left_item": u.get("item_id"),
                "right_item": None,
                "code_match": False,
                "description_match": 0.0,
                "unit_match": False,
                "limitations": ["no_match"],
                "classification": "UNMATCHED",
            }
        )
    for u in unmatched_right:
        pairs.append(
            {
                "match_type": "UNMATCHED",
                "left_item": None,
                "right_item": u.get("item_id"),
                "code_match": False,
                "description_match": 0.0,
                "unit_match": False,
                "limitations": ["no_match_right_only"],
                "classification": "UNMATCHED",
            }
        )

    denominator = len(left_items) + len(unmatched_right)
    matched_exact = sum(1 for p in pairs if p["match_type"] in {"EXACT_CODE_UNIT", "DETERMINISTIC_COMPOSITE"})
    return {
        "left_count": len(left_items),
        "right_count": len(right_items),
        "pair_count": len(pairs),
        "matched_exact": matched_exact,
        "unmatched_left": len(unmatched_left),
        "unmatched_right": len(unmatched_right),
        "denominator": denominator,
        "pairs": pairs,
        "rules": [
            "Similar name does not override incompatible unit",
            "Ambiguous and unmatched remain in denominator",
            "No hard items removed to improve metrics",
        ],
    }


def _pair(
    left: dict[str, Any],
    right: dict[str, Any],
    match_type: str,
    left_label: str,
    right_label: str,
    *,
    sim: float | None = None,
    limitations: list[str] | None = None,
    force_status: str | None = None,
) -> dict[str, Any]:
    unit_ok = units_compatible(left.get("unit"), right.get("unit"))
    lq = left.get("quantity")
    rq = right.get("quantity")
    lpu = left.get("unit_sale_price") or left.get("unit_direct_cost")
    rpu = right.get("unit_sale_price") or right.get("unit_direct_cost")
    lt = left.get("total_sale_price") or left.get("total_direct_cost")
    rt = right.get("total_sale_price") or right.get("total_direct_cost")
    diff_pct = None
    if isinstance(lpu, (int, float)) and isinstance(rpu, (int, float)) and lpu != 0:
        diff_pct = ((float(rpu) - float(lpu)) / abs(float(lpu))) * 100.0

    classification = force_status or match_type
    lim = list(limitations or [])
    if not unit_ok:
        lim.append("unit_mismatch")
    if match_type == "REVIEWABLE_TEXT":
        lim.append("text_match_requires_human_review")

    return {
        "match_type": match_type,
        "left_label": left_label,
        "right_label": right_label,
        "left_item": left.get("item_id"),
        "right_item": right.get("item_id"),
        "code_match": bool(left.get("code") and left.get("code") == right.get("code")),
        "description_match": sim if sim is not None else description_similarity(
            left.get("description"), right.get("description")
        ),
        "unit_match": unit_ok,
        "quantity_left": lq,
        "quantity_right": rq,
        "unit_price_left": lpu,
        "unit_price_right": rpu,
        "total_left": lt,
        "total_right": rt,
        "difference_pct": diff_pct,
        "classification": classification,
        "limitations": lim,
        "note": "Price difference alone does not prove over/under pricing",
    }
