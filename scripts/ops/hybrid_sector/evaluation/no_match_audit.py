"""Phase 12 — stratified NO_MATCH audit sampling."""
from __future__ import annotations

import hashlib
from typing import Any

from scripts.ops.hybrid_sector.models import CandidateRecord, DecisionLineage


def audit_sample_size(total_no_match: int) -> int:
    if total_no_match < 200:
        return total_no_match
    return min(1000, max(200, int(0.05 * total_no_match)))


def select_no_match_audit_sample(
    no_match_lineages: list[DecisionLineage],
    candidates_by_id: dict[str, CandidateRecord],
    *,
    seed: str = "hybrid-sector-audit-v1",
) -> list[dict[str, Any]]:
    """Stratified mix: random, semantic, no-kw, short, high value, organ, category, conflicts."""
    if not no_match_lineages:
        return []
    n = audit_sample_size(len(no_match_lineages))
    buckets: dict[str, list[DecisionLineage]] = {
        "random": [],
        "semantic": [],
        "no_keyword": [],
        "short": [],
        "high_value": [],
        "organ": [],
        "category": [],
        "channel_divergence": [],
    }
    for lin in no_match_lineages:
        cand = candidates_by_id.get(lin.canonical_id)
        retrieved = set((lin.retrieval or {}).get("retrieved_by") or [])
        buckets["random"].append(lin)
        if "semantic" in retrieved:
            buckets["semantic"].append(lin)
        if "lexical" not in retrieved:
            buckets["no_keyword"].append(lin)
        if lin.deterministic and lin.deterministic.short_text:
            buckets["short"].append(lin)
        if cand and cand.record.valor_estimado and cand.record.valor_estimado >= 500_000:
            buckets["high_value"].append(lin)
        if "organ_history" in retrieved:
            buckets["organ"].append(lin)
        if cand and cand.record.categories:
            buckets["category"].append(lin)
        if len(retrieved) >= 2:
            buckets["channel_divergence"].append(lin)

    selected: dict[str, DecisionLineage] = {}
    # Round-robin from strata then fill random
    order = [
        "high_value",
        "semantic",
        "no_keyword",
        "short",
        "organ",
        "category",
        "channel_divergence",
        "random",
    ]
    per = max(1, n // len(order))
    for name in order:
        pool = sorted(
            buckets[name],
            key=lambda lin: hashlib.sha1(f"{seed}:{lin.canonical_id}".encode(), usedforsecurity=False).hexdigest(),
        )
        for lin in pool[:per]:
            selected[lin.canonical_id] = lin
            if len(selected) >= n:
                break
        if len(selected) >= n:
            break

    if len(selected) < n:
        for lin in sorted(
            no_match_lineages,
            key=lambda lin: hashlib.sha1(f"{seed}:{lin.canonical_id}".encode(), usedforsecurity=False).hexdigest(),
        ):
            selected[lin.canonical_id] = lin
            if len(selected) >= n:
                break

    out = []
    for lin in selected.values():
        out.append(
            {
                "canonical_id": lin.canonical_id,
                "strata_hints": [
                    k
                    for k, v in buckets.items()
                    if any(x.canonical_id == lin.canonical_id for x in v)
                ],
                "lineage": lin.to_dict(),
            }
        )
    return out
