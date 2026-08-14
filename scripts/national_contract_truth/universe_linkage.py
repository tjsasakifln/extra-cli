"""#300 — link 1.093 canonical universe IDs to datalake entities.

Fail-closed: unmatched is a named blocker, not a silent null.
Root 00394494 is never collapsed. Entities outside the active run
never enter the readiness denominator.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

FORBIDDEN_COLLAPSE_ROOT = "00394494"

LinkStatus = Literal["matched", "changed", "ambiguous", "unmatched", "excluded"]


@dataclass(frozen=True)
class UniverseRow:
    canonical_entity_key: str
    cnpj14: str | None
    cnpj8: str | None
    legal_name: str | None
    municipality: str | None
    included: bool
    previous_db_entity_id: str | None = None


@dataclass(frozen=True)
class LakeRow:
    db_entity_id: str
    cnpj14: str | None
    cnpj8: str | None
    legal_name: str | None
    municipality: str | None
    active: bool = True


@dataclass(frozen=True)
class LinkDecision:
    canonical_entity_key: str
    status: LinkStatus
    db_entity_id: str | None
    match_method: str | None
    blocker: str | None


@dataclass(frozen=True)
class LinkageLedger:
    decisions: tuple[LinkDecision, ...]

    @property
    def matched(self) -> tuple[LinkDecision, ...]:
        return tuple(d for d in self.decisions if d.status in ("matched", "changed"))

    @property
    def ambiguous(self) -> tuple[LinkDecision, ...]:
        return tuple(d for d in self.decisions if d.status == "ambiguous")

    @property
    def unmatched(self) -> tuple[LinkDecision, ...]:
        return tuple(d for d in self.decisions if d.status == "unmatched")

    @property
    def excluded(self) -> tuple[LinkDecision, ...]:
        return tuple(d for d in self.decisions if d.status == "excluded")

    @property
    def denominator_keys(self) -> frozenset[str]:
        return frozenset(d.canonical_entity_key for d in self.decisions if d.status != "excluded")


@dataclass(frozen=True)
class Readiness:
    ready: bool
    resolved: int
    denominator: int
    blockers: tuple[str, ...]


def _norm(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().casefold().split())


def _digits(value: str | None, width: int | None = None) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if width is not None:
        return digits.zfill(width) if digits else ""
    return digits


def decide_universe_link(
    row: UniverseRow,
    candidates: Iterable[LakeRow],
    *,
    active_run_keys: frozenset[str],
) -> LinkDecision:
    """Resolve one included universe row against active datalake entities."""
    if not row.included or row.canonical_entity_key not in active_run_keys:
        return LinkDecision(
            canonical_entity_key=row.canonical_entity_key,
            status="excluded",
            db_entity_id=None,
            match_method=None,
            blocker=None,
        )

    active = [c for c in candidates if c.active]
    cnpj14 = _digits(row.cnpj14, 14)
    cnpj8 = _digits(row.cnpj8, 8) or (cnpj14[:8] if cnpj14 else "")

    if cnpj14:
        exact = [c for c in active if _digits(c.cnpj14, 14) == cnpj14]
        if len(exact) == 1:
            return _matched(row, exact[0], "cnpj14")
        if len(exact) > 1:
            return _ambiguous(row, "multiple_cnpj14")

    name = _norm(row.legal_name)
    mun = _norm(row.municipality)
    if cnpj8 and name and mun:
        composite = [
            c
            for c in active
            if (_digits(c.cnpj8, 8) or _digits(c.cnpj14, 14)[:8]) == cnpj8
            and _norm(c.legal_name) == name
            and _norm(c.municipality) == mun
        ]
        if len(composite) == 1:
            return _matched(row, composite[0], "cnpj8_name_municipality")
        if len(composite) > 1:
            return _ambiguous(row, "multiple_composite")

    if cnpj8 == FORBIDDEN_COLLAPSE_ROOT:
        return _ambiguous(row, "refuse_collapse_00394494")

    if cnpj8:
        by_root = [c for c in active if (_digits(c.cnpj8, 8) or _digits(c.cnpj14, 14)[:8]) == cnpj8]
        if len(by_root) == 1:
            return _matched(row, by_root[0], "cnpj8")
        if len(by_root) > 1:
            return _ambiguous(row, "ambiguous_cnpj8")

    return LinkDecision(
        canonical_entity_key=row.canonical_entity_key,
        status="unmatched",
        db_entity_id=None,
        match_method=None,
        blocker="NO_DATALAKE_ENTITY",
    )


def _matched(row: UniverseRow, lake: LakeRow, method: str) -> LinkDecision:
    status: LinkStatus = (
        "changed" if row.previous_db_entity_id and row.previous_db_entity_id != lake.db_entity_id else "matched"
    )
    return LinkDecision(
        canonical_entity_key=row.canonical_entity_key,
        status=status,
        db_entity_id=lake.db_entity_id,
        match_method=method,
        blocker=None,
    )


def _ambiguous(row: UniverseRow, blocker: str) -> LinkDecision:
    return LinkDecision(
        canonical_entity_key=row.canonical_entity_key,
        status="ambiguous",
        db_entity_id=None,
        match_method=None,
        blocker=blocker,
    )


def link_included_to_datalake(
    rows: Iterable[UniverseRow],
    lake: Iterable[LakeRow],
    *,
    active_run_keys: Iterable[str],
) -> LinkageLedger:
    """Idempotent ledger for the active universe run only."""
    keys = frozenset(active_run_keys)
    lake_rows = tuple(lake)
    decisions = tuple(decide_universe_link(row, lake_rows, active_run_keys=keys) for row in rows)
    return LinkageLedger(decisions=decisions)


def evaluate_readiness(ledger: LinkageLedger) -> Readiness:
    """Readiness requires 100% of the active included set resolved."""
    denom = ledger.denominator_keys
    resolved = [d for d in ledger.decisions if d.canonical_entity_key in denom and d.status in ("matched", "changed")]
    blockers = tuple(
        f"{d.canonical_entity_key}:{d.blocker or d.status}"
        for d in ledger.decisions
        if d.canonical_entity_key in denom and d.status not in ("matched", "changed")
    )
    return Readiness(
        ready=len(resolved) == len(denom) and len(denom) > 0 and not blockers,
        resolved=len(resolved),
        denominator=len(denom),
        blockers=blockers,
    )
