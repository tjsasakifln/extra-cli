#!/usr/bin/env python3
"""Stable identifiers for DOD.md checkboxes.

Identity = SHA1(section|normalized_text)[:12], independent of line numbers.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any


_EVIDENCE_SPLIT = re.compile(
    r"\s*(?:Evid[eê]ncia\s*:|Evidence\s*:|`PARTIAL`|PARTIAL\s*[—\-])",
    re.IGNORECASE,
)


def core_requirement_text(body: str) -> str:
    """Strip trailing evidence annotations so IDs stay stable after flips."""
    text = body or ""
    # Keep only the requirement clause before evidence notes
    parts = _EVIDENCE_SPLIT.split(text, maxsplit=1)
    core = parts[0] if parts else text
    # Also strip trailing period-only noise after core requirement
    return core.strip()


def normalize_text(body: str) -> str:
    core = core_requirement_text(body)
    norm = re.sub(r"\s+", " ", core).strip().lower()
    norm = re.sub(r"[`*_#\[\]()]", "", norm)
    # drop trailing punctuation differences after flip
    norm = norm.rstrip(" .;:")
    return norm


def stable_dod_id(section: str, body: str) -> str:
    key = f"{(section or '').strip()}|{normalize_text(body)}"
    return f"dod:{hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]}"


def slice_id_for_section(section: str, open_ids: list[str]) -> str:
    """Deterministic slice id from section + sorted open item ids."""
    payload = f"{section}|{'|'.join(sorted(open_ids))}"
    return f"slice:{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:12]}"


def classify_truth_state(
    item: dict[str, Any],
    *,
    evidence_paths: list[str] | None = None,
    active_conflicts: list[str] | None = None,
    blocked_patterns: list[str] | None = None,
) -> str:
    """Conservative truth class for an open/checked item."""
    if item.get("checkbox") or item.get("checked"):
        return "DONE"
    text = (item.get("text") or "") + " " + (item.get("section") or "")
    low = text.lower()
    if item.get("classification") == "BLOCKED" or "blocked" in low:
        return "BLOCKED_EXTERNAL"
    if "partial" in low or item.get("classification") == "PARTIAL":
        return "PARTIAL"
    if active_conflicts:
        return "CONFLICT_ACTIVE_WORK"
    for pat in blocked_patterns or []:
        if pat.lower() in low:
            if "vps" in pat.lower() or "provision" in pat.lower():
                return "BLOCKED_HUMAN_DECISION"
            if "live" in pat.lower() or "credencial" in pat.lower():
                return "BLOCKED_EXTERNAL"
            return "NOT_UNLOCKED"
    if evidence_paths:
        return "EVIDENCE_REQUIRED"  # code/evidence may exist; still needs flip proof
    return "IMPLEMENTATION_REQUIRED"
