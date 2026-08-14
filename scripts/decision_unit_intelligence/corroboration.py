"""Conflict preservation. Highest confidence does not erase disagreement."""

from __future__ import annotations

from collections import defaultdict

from scripts.decision_unit_intelligence.models import (
    ChannelObservation,
    ConflictRecord,
    EpistemicClass,
    PersonObservation,
    stable_id,
)


def independent_source_count(items: list[PersonObservation | ChannelObservation]) -> int:
    keys = set()
    for item in items:
        keys.add((item.source_type, item.source_url or item.document_id or item.observation_id))
    return len(keys)


def detect_person_conflicts(observations: list[PersonObservation]) -> list[ConflictRecord]:
    conflicts: list[ConflictRecord] = []
    by_name: dict[str, list[PersonObservation]] = defaultdict(list)
    for obs in observations:
        if obs.person_name:
            by_name[obs.person_name.strip().lower()].append(obs)
    for name, group in by_name.items():
        roles = {(g.normalized_role_class.value, g.observed_role) for g in group}
        if len({r[0] for r in roles if r[0] != "unknown"}) > 1:
            values = sorted({r[0] for r in roles})
            conflicts.append(
                ConflictRecord(
                    conflict_id=stable_id("role", name, *values),
                    topic="role",
                    left=values[0],
                    right=values[1],
                    resolution="PRESERVE_BOTH",
                    reason_codes=["CONFLICTING_OBSERVED_ROLES"],
                )
            )
    return conflicts


def detect_channel_conflicts(observations: list[ChannelObservation]) -> list[ConflictRecord]:
    conflicts: list[ConflictRecord] = []
    emails = [o for o in observations if o.channel_value and "@" in o.channel_value]
    by_person: dict[str, set[str]] = defaultdict(set)
    for obs in emails:
        if obs.person_name and obs.epistemic_class != EpistemicClass.INFERRED:
            by_person[obs.person_name.strip().lower()].add((obs.channel_value or "").lower())
    for person, addrs in by_person.items():
        if len(addrs) > 1:
            values = sorted(addrs)
            conflicts.append(
                ConflictRecord(
                    conflict_id=stable_id("email", person, *values),
                    topic="email",
                    left=values[0],
                    right=values[1],
                    resolution="PRESERVE_BOTH",
                    reason_codes=["MULTIPLE_OBSERVED_EMAILS"],
                )
            )
    return conflicts


def evidence_quality_label(*, source_count: int, has_document: bool, contradicted: bool) -> str:
    if contradicted:
        return "LOW"
    if source_count >= 2 and has_document:
        return "HIGH"
    if source_count >= 1 and has_document:
        return "MEDIUM"
    if source_count >= 1:
        return "LOW"
    return "UNKNOWN"
