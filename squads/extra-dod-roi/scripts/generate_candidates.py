#!/usr/bin/env python3
"""Dynamic candidate generation from open DOD.md checkboxes.

Produces section-coherent slices with ROI dimensions. Does not mutate DOD.md.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from dod_ids import slice_id_for_section

# Sections that require human infra / live / VPS — never auto-unlock as free work
BLOCKED_SECTION_PATTERNS = [
    r"\b16\b.*[Dd]ecis",
    r"\b17\b.*[Pp]rovision",
    r"\b18\b.*[Hh]ardening",
    r"\b19\b.*[Dd]eploy",
    r"\b20\b.*[Mm]igra",
    r"\b21\b.*[Ss]ervi[cç]os e timers",
    r"\b22\b.*[Bb]ackup e disaster recovery na VPS",
    r"\b24\b.*[Oo]pera[cç][aã]o cont[ií]nua",
    r"VPS",
    r"provisionamento",
]

# Items matching these are blocked externally even in local sections
BLOCKED_ITEM_PATTERNS = [
    r"cobertura operacional\s*≥\s*95",
    r"cobertura operacional >= 95",
    r"1\.039/1\.093",
    r"1039/1093",
    r"recall.*≥\s*95",
    r"PRE_VPS_FINAL_READY",
    r"LOCAL_RESILIENCE_READY",
    r"VPS_OPERATIONAL",
    r"PROJECT_DONE",
    r"live canary",
    r"Tiago consegue",  # manual accept
    r"credencial",
    r"decis[aã]o humana",
]

# High local ROI section boosts (keyword -> value bias)
SECTION_BIAS: list[tuple[str, dict[str, int], dict[str, int]]] = [
    # (section regex, value dims, cost dims)
    (
        r"^13\.4",
        {"gate_value": 5, "unlock_power": 4, "operational_impact": 3, "risk_reduction": 4, "evidence_gain": 5},
        {"effort": 2, "uncertainty": 1, "external_dependency": 1, "change_surface": 1},
    ),
    (
        r"^13\.1",
        {"gate_value": 4, "unlock_power": 3, "operational_impact": 2, "risk_reduction": 3, "evidence_gain": 5},
        {"effort": 2, "uncertainty": 2, "external_dependency": 1, "change_surface": 2},
    ),
    (
        r"^14\b",
        {"gate_value": 4, "unlock_power": 3, "operational_impact": 3, "risk_reduction": 5, "evidence_gain": 5},
        {"effort": 3, "uncertainty": 2, "external_dependency": 2, "change_surface": 2},
    ),
    (
        r"^12\.1",
        {"gate_value": 4, "unlock_power": 4, "operational_impact": 4, "risk_reduction": 3, "evidence_gain": 4},
        {"effort": 3, "uncertainty": 3, "external_dependency": 2, "change_surface": 3},
    ),
    (
        r"^12\.2",
        {"gate_value": 3, "unlock_power": 3, "operational_impact": 4, "risk_reduction": 2, "evidence_gain": 4},
        {"effort": 3, "uncertainty": 2, "external_dependency": 2, "change_surface": 2},
    ),
    (
        r"^25\b",
        {"gate_value": 5, "unlock_power": 3, "operational_impact": 2, "risk_reduction": 5, "evidence_gain": 4},
        {"effort": 2, "uncertainty": 1, "external_dependency": 1, "change_surface": 1},
    ),
    (
        r"^29\b",
        {"gate_value": 3, "unlock_power": 3, "operational_impact": 3, "risk_reduction": 4, "evidence_gain": 5},
        {"effort": 2, "uncertainty": 2, "external_dependency": 1, "change_surface": 2},
    ),
    (
        r"^27\b",
        {"gate_value": 2, "unlock_power": 2, "operational_impact": 3, "risk_reduction": 3, "evidence_gain": 3},
        {"effort": 3, "uncertainty": 2, "external_dependency": 1, "change_surface": 3},
    ),
    (
        r"^31\b",
        {"gate_value": 2, "unlock_power": 2, "operational_impact": 4, "risk_reduction": 2, "evidence_gain": 4},
        {"effort": 2, "uncertainty": 1, "external_dependency": 1, "change_surface": 1},
    ),
    (
        r"^23\b",
        {"gate_value": 3, "unlock_power": 3, "operational_impact": 4, "risk_reduction": 3, "evidence_gain": 4},
        {"effort": 3, "uncertainty": 2, "external_dependency": 2, "change_surface": 2},
    ),
    (
        r"^1\b|^2\b",
        {"gate_value": 3, "unlock_power": 2, "operational_impact": 1, "risk_reduction": 4, "evidence_gain": 3},
        {"effort": 2, "uncertainty": 2, "external_dependency": 1, "change_surface": 1},
    ),
    (
        r"cobertura|coverage|pending_collection|fonte",
        {"gate_value": 4, "unlock_power": 5, "operational_impact": 5, "risk_reduction": 3, "evidence_gain": 4},
        {"effort": 4, "uncertainty": 3, "external_dependency": 3, "change_surface": 3},
    ),
]

DEFAULT_VALUE = {
    "gate_value": 2,
    "unlock_power": 2,
    "operational_impact": 2,
    "risk_reduction": 2,
    "evidence_gain": 3,
}
DEFAULT_COST = {
    "effort": 3,
    "uncertainty": 3,
    "external_dependency": 2,
    "change_surface": 2,
}

MAX_ITEMS_PER_SLICE = 8
MAX_DYNAMIC_SLICES = 40


def _section_blocked(section: str) -> bool:
    for pat in BLOCKED_SECTION_PATTERNS:
        if re.search(pat, section, re.I):
            return True
    return False


def _item_blocked(text: str) -> bool:
    for pat in BLOCKED_ITEM_PATTERNS:
        if re.search(pat, text, re.I):
            return True
    return False


def _bias_for_section(section: str) -> tuple[dict[str, int], dict[str, int]]:
    for pat, value, cost in SECTION_BIAS:
        if re.search(pat, section, re.I):
            return dict(value), dict(cost)
    return dict(DEFAULT_VALUE), dict(DEFAULT_COST)


def _chunk(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def generate_dynamic_candidates(
    matrix: dict[str, Any],
    *,
    root: Path | None = None,
    max_slices: int = MAX_DYNAMIC_SLICES,
    completed_dod_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (unlocked_candidates, blocked_entries) from open DOD items."""
    completed_dod_ids = completed_dod_ids or set()
    open_items = [
        it
        for it in (matrix.get("items") or [])
        if not it.get("checkbox") and it.get("classification") not in {"DONE"}
    ]
    by_section: dict[str, list[dict[str, Any]]] = defaultdict(list)
    blocked: list[dict[str, Any]] = []

    for it in open_items:
        sid = it.get("id") or ""
        if sid in completed_dod_ids:
            continue
        section = it.get("section") or "(no-section)"
        text = it.get("text") or ""
        if _section_blocked(section) or _item_blocked(text):
            blocked.append(
                {
                    "id": f"blk-dyn-{sid}",
                    "title": text[:120],
                    "status": "BLOCKED",
                    "owner": "campaign-planner",
                    "cause": "Section/item requires external resource, human accept, or forbidden seal",
                    "dod_item_id": sid,
                    "section": section,
                    "unlock_condition": "Human decision, live env, or formal scope change",
                    "next_test": "re-rank after unlock resource available",
                }
            )
            continue
        if it.get("classification") in {"BLOCKED", "PARTIAL", "NOT_APPLICABLE"}:
            blocked.append(
                {
                    "id": f"blk-dyn-{sid}",
                    "title": text[:120],
                    "status": it.get("classification"),
                    "owner": "truth-auditor",
                    "cause": f"classification={it.get('classification')}",
                    "dod_item_id": sid,
                    "section": section,
                }
            )
            continue
        by_section[section].append(it)

    candidates: list[dict[str, Any]] = []
    # Prefer sections with higher bias (quality, backup, tests) by sorting
    def section_rank(sec: str) -> float:
        value, cost = _bias_for_section(sec)
        v = sum(value.values())
        c = sum(cost.values()) or 1
        return v / c

    ordered_sections = sorted(by_section.keys(), key=section_rank, reverse=True)

    for section in ordered_sections:
        items = by_section[section]
        # keep document order
        items = sorted(items, key=lambda x: int(x.get("line") or 0))
        value, cost = _bias_for_section(section)
        for chunk in _chunk(items, MAX_ITEMS_PER_SLICE):
            ids = [c["id"] for c in chunk]
            slice_id = slice_id_for_section(section, ids)
            title_bits = [c.get("text", "")[:60] for c in chunk[:3]]
            title = f"[{section[:50]}] " + " · ".join(title_bits)
            if len(chunk) > 3:
                title += f" (+{len(chunk)-3} more)"
            candidates.append(
                {
                    "id": f"cand-dyn-{slice_id}",
                    "title": title[:200],
                    "status": "UNLOCKED",
                    "source": "dynamic-dod",
                    "dod_refs": [section] + [c.get("text", "")[:80] for c in chunk[:5]],
                    "dod_item_ids": ids,
                    "dod_items": [
                        {
                            "id": c["id"],
                            "line": c.get("line"),
                            "section": section,
                            "text": c.get("text"),
                        }
                        for c in chunk
                    ],
                    "why_unlocked": (
                        f"Open local-stage items in section '{section}' without "
                        "VPS/live/human-accept blocker patterns"
                    ),
                    "value": value,
                    "cost": cost,
                    "justification": (
                        f"Dynamic slice of {len(chunk)} open DoD items; ROI biased by section heuristics"
                    ),
                    "risks": [
                        "Over-marking without real evidence",
                        "Partial implementation mistaken for done",
                    ],
                    "dependencies": [],
                    "conflicts": [],
                    "acceptance_criteria": [
                        f"Each of {len(chunk)} dod_item_ids proven with evidence or left open",
                        "No NOT_APPLICABLE used to hit campaign meta",
                        "Independent QA PASS before any [x] flip",
                    ],
                    "test_commands": [
                        "python3 -m pytest -q --tb=no -x  # scope to slice tests",
                    ],
                    "planned_files": ["DOD.md", "docs/ops/session-*/", "tests/*", "scripts/*"],
                    "truth_class": "IMPLEMENTATION_REQUIRED",
                }
            )
            if len(candidates) >= max_slices:
                return candidates, blocked
    return candidates, blocked


def load_campaign_accepted_ids(root: Path) -> set[str]:
    path = root / "squads" / "extra-dod-roi" / "state" / "campaigns" / "dod-50-current.json"
    if not path.is_file():
        return set()
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    accepted = set()
    for entry in data.get("accepted") or []:
        if isinstance(entry, dict):
            did = entry.get("dod_item_id") or entry.get("id")
            if did:
                accepted.add(did)
        elif isinstance(entry, str):
            accepted.add(entry)
    for entry in data.get("matrix") or []:
        if isinstance(entry, dict) and entry.get("dod_item_id"):
            accepted.add(entry["dod_item_id"])
    # baseline done must never count as campaign work
    baseline = data.get("baseline") or {}
    for did in baseline.get("done_ids") or []:
        accepted.add(did)
    return accepted
