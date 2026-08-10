"""State transition classification for target-fit materialization.

Upgrades and downgrades are first-class. Never monotonic-only.
"""

from __future__ import annotations

from typing import Any

from scripts.confenge_target_fit import (
    CLASS_RANK,
    EVT_CONFIRMED,
    EVT_DOWNGRADE,
    EVT_EVIDENCE_CHANGED,
    EVT_LOST,
    EVT_RESEARCH_REQUIRED,
    EVT_UNCHANGED,
    EVT_UPGRADE,
    EVT_VERSION_RECOMPUTED,
    TARGET_CONFIRMED,
    TARGET_INSUFFICIENT_EVIDENCE,
    TARGET_OUT_OF_SCOPE,
    TARGET_PROBABLE_RESEARCH,
)
from scripts.confenge_target_fit.fingerprint import changed_evidence_ids


def transition_label(old_class: str | None, new_class: str | None) -> str:
    o = old_class or "(none)"
    n = new_class or "(none)"
    if o == n:
        return "UNCHANGED"
    return f"{_short(o)}→{_short(n)}"


def _short(cls: str) -> str:
    mapping = {
        TARGET_CONFIRMED: "CONFIRMED",
        TARGET_PROBABLE_RESEARCH: "PROBABLE",
        TARGET_INSUFFICIENT_EVIDENCE: "INSUFFICIENT",
        TARGET_OUT_OF_SCOPE: "OUT",
        "REFRESH_FAILED": "FAILED",
        "RECOMPUTE_REQUIRED": "RECOMPUTE",
    }
    return mapping.get(cls, cls)


def is_downgrade(old_class: str | None, new_class: str | None) -> bool:
    if not old_class or not new_class:
        return False
    return CLASS_RANK.get(new_class, -99) < CLASS_RANK.get(old_class, -99)


def is_upgrade(old_class: str | None, new_class: str | None) -> bool:
    if not old_class or not new_class:
        return bool(new_class and new_class == TARGET_CONFIRMED and not old_class)
    return CLASS_RANK.get(new_class, -99) > CLASS_RANK.get(old_class, -99)


def classify_event_type(
    *,
    old_class: str | None,
    new_class: str | None,
    old_version: str | None,
    new_version: str,
    old_evidence: list[dict[str, Any]] | None,
    new_evidence: list[dict[str, Any]] | None,
) -> str:
    if old_class is None:
        if new_class == TARGET_CONFIRMED:
            return EVT_CONFIRMED
        if new_class == TARGET_PROBABLE_RESEARCH:
            return EVT_RESEARCH_REQUIRED
        return EVT_UNCHANGED if new_class == TARGET_OUT_OF_SCOPE else EVT_UPGRADE

    if old_class == new_class:
        if changed_evidence_ids(old_evidence, new_evidence):
            return EVT_EVIDENCE_CHANGED
        if old_version and old_version != new_version:
            return EVT_VERSION_RECOMPUTED
        return EVT_UNCHANGED

    if is_downgrade(old_class, new_class):
        if old_class == TARGET_CONFIRMED:
            return EVT_LOST if new_class == TARGET_OUT_OF_SCOPE else EVT_DOWNGRADE
        return EVT_DOWNGRADE

    if new_class == TARGET_CONFIRMED:
        return EVT_CONFIRMED
    if new_class == TARGET_PROBABLE_RESEARCH:
        return EVT_RESEARCH_REQUIRED
    return EVT_UPGRADE


def transition_key(old_class: str | None, new_class: str | None) -> str:
    """Stable key for metrics breakdown e.g. OUT→CONFIRMED."""
    return transition_label(old_class, new_class)
