"""Conflict-of-interest gate — absence of data ≠ absence of conflict."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT = _ROOT / "config/commercial/conflict_of_interest.yaml"

STATE_PENDING = "CONFLICT_CHECK_PENDING"
STATE_REVIEW = "CONFLICT_REVIEW_REQUIRED"
STATE_BLOCKED = "CONFLICT_BLOCKED"
STATE_CLEARED = "CONFLICT_CLEARED_BY_HUMAN_REVIEW"


@dataclass
class ConflictAssessment:
    state: str
    agency_id: str | None
    cnpj14: str | None
    matched_rules: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    human_review_required: bool = True
    cleared_by: str | None = None
    cleared_at: str | None = None
    clearance_note: str | None = None
    cannot_assert_no_conflict: bool = True
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_conflict_config(path: Path | None = None) -> dict[str, Any]:
    p = path or _DEFAULT
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def config_hash(path: Path | None = None) -> str:
    p = path or _DEFAULT
    return hashlib.sha256(p.read_bytes()).hexdigest()


def assess_conflict(
    *,
    agency_id: str | None = None,
    cnpj14: str | None = None,
    official_name: str | None = None,
    human_clearance: dict[str, Any] | None = None,
    known_conflict: bool = False,
    known_conflict_reason: str | None = None,
    path: Path | None = None,
) -> ConflictAssessment:
    cfg = load_conflict_config(path)
    blocked_ids = {str(x) for x in (cfg.get("blocked_agency_ids") or [])}
    blocked_cnpj = {str(x) for x in (cfg.get("blocked_cnpj14") or [])}
    blocked_markers = [str(x).upper() for x in (cfg.get("blocked_name_markers") or [])]
    review_markers = [str(x).upper() for x in (cfg.get("review_required_name_markers") or [])]

    matched: list[str] = []
    reasons: list[str] = []
    name_u = (official_name or "").upper()

    if known_conflict:
        return ConflictAssessment(
            state=STATE_BLOCKED,
            agency_id=agency_id,
            cnpj14=cnpj14,
            matched_rules=["known_conflict"],
            reasons=[known_conflict_reason or "known_conflict_declared"],
            human_review_required=True,
            notes="Conflito conhecido — outreach bloqueado.",
        )

    if agency_id and agency_id in blocked_ids:
        matched.append("blocked_agency_id")
        reasons.append(f"agency_id={agency_id} in blocked list")
    if cnpj14 and cnpj14 in blocked_cnpj:
        matched.append("blocked_cnpj14")
        reasons.append(f"cnpj14={cnpj14} in blocked list")
    for m in blocked_markers:
        if m and m in name_u:
            matched.append("blocked_name_marker")
            reasons.append(f"name matches blocked marker: {m}")

    if matched:
        return ConflictAssessment(
            state=STATE_BLOCKED,
            agency_id=agency_id,
            cnpj14=cnpj14,
            matched_rules=matched,
            reasons=reasons,
            human_review_required=True,
            notes="Bloqueio automático de conflito.",
        )

    for m in review_markers:
        if m and m in name_u:
            matched.append("review_required_name_marker")
            reasons.append(f"name matches review marker: {m}")

    if human_clearance and human_clearance.get("cleared") is True:
        reviewer = str(human_clearance.get("reviewer") or "")
        note = str(human_clearance.get("note") or "")
        if not reviewer or not note:
            return ConflictAssessment(
                state=STATE_REVIEW,
                agency_id=agency_id,
                cnpj14=cnpj14,
                matched_rules=matched + ["incomplete_clearance"],
                reasons=reasons + ["clearance missing reviewer or note"],
                human_review_required=True,
                notes="Clearance incompleto — não eleva para CLEARED.",
            )
        return ConflictAssessment(
            state=STATE_CLEARED,
            agency_id=agency_id,
            cnpj14=cnpj14,
            matched_rules=matched,
            reasons=reasons,
            human_review_required=False,
            cleared_by=reviewer,
            cleared_at=str(
                human_clearance.get("cleared_at")
                or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            ),
            clearance_note=note,
            cannot_assert_no_conflict=False,
            notes="Clearance humano documentado.",
        )

    if matched:
        return ConflictAssessment(
            state=STATE_REVIEW,
            agency_id=agency_id,
            cnpj14=cnpj14,
            matched_rules=matched,
            reasons=reasons,
            human_review_required=True,
            notes="Marcadores exigem revisão humana.",
        )

    # Default: pending — never assert no conflict from empty data
    return ConflictAssessment(
        state=STATE_PENDING,
        agency_id=agency_id,
        cnpj14=cnpj14,
        matched_rules=[],
        reasons=["no_automated_match_insufficient_to_clear"],
        human_review_required=True,
        cannot_assert_no_conflict=True,
        notes=(
            "Sem match automático de bloqueio. Isso NÃO prova ausência de conflito. "
            "Outreach exige CONFLICT_CLEARED_BY_HUMAN_REVIEW."
        ),
    )


def blocks_outreach(assessment: ConflictAssessment) -> bool:
    return assessment.state in {STATE_PENDING, STATE_REVIEW, STATE_BLOCKED}
