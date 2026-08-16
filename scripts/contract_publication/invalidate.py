"""Directed invalidation: only candidates whose material fingerprint changed."""

from __future__ import annotations

from typing import Any


def invalidation_report(
    previous: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> dict[str, Any]:
    previous_by_id = {item.get("analysis_candidate_id"): item for item in previous}
    current_by_id = {item.get("analysis_candidate_id"): item for item in current}
    invalidated: list[str] = []
    unchanged: list[str] = []
    added: list[str] = []
    removed: list[str] = []
    for candidate_id, item in current_by_id.items():
        prior = previous_by_id.get(candidate_id)
        if prior is None:
            added.append(candidate_id)
            continue
        same_material = prior.get("material_fingerprint") == item.get("material_fingerprint")
        same_pack = prior.get("evidence_pack_hash") == item.get("evidence_pack_hash")
        if same_material and same_pack:
            unchanged.append(candidate_id)
        else:
            invalidated.append(candidate_id)
    for candidate_id in previous_by_id:
        if candidate_id not in current_by_id:
            removed.append(candidate_id)
    return {
        "invalidated": sorted(invalidated),
        "unchanged": sorted(unchanged),
        "added": sorted(added),
        "removed": sorted(removed),
        "invalidation_scope": "affected_candidate_only",
    }
