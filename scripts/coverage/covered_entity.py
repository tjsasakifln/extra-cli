"""Single covered-entity formula for every client-facing coverage surface.

Issue #280: panel, PDF, Excel, manifest and QA must derive "ente coberto"
from one function. FAILED/BLOCKED/ERROR/PARTIAL never become covered.

Issue #350: source-wide aggregated evidence (NULL entity identity) is not a
numerator row. Dual-coverage numerators require canonical identity; otherwise
the measurement is fail-closed MISSING_EVIDENCE.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from scripts.coverage.states import COVERED_STATES, CoverageState

FORMULA_ID = "covered-entity-v1"
FORMULA_VERSION = 1

# Explicit states that compose coverage. Never include failed/blocked/error.
COVERED_STATE_VALUES: frozenset[str] = frozenset(state.value for state in COVERED_STATES)

NON_COVERED_STATE_VALUES: frozenset[str] = frozenset(
    {
        CoverageState.NOT_APPLICABLE.value,
        CoverageState.PENDING.value,
        CoverageState.RUNNING.value,
        CoverageState.PARTIAL.value,
        CoverageState.ERROR.value,
        CoverageState.BLOCKED.value,
        CoverageState.STALE.value,
        "failed",
        "fail",
        "failure",
        "FOUND",
        "found",
        "any_row",
    }
)

IDENTITY_MAPPED = "IDENTITY_MAPPED"
SOURCE_WIDE_AGGREGATE = "SOURCE_WIDE_AGGREGATE"
UNMAPPABLE = "UNMAPPABLE"
MISSING_EVIDENCE = "MISSING_EVIDENCE"


class CoverageFormulaDivergenceError(ValueError):
    """Two surfaces published different covered-entity counts for the same rows."""


@dataclass(frozen=True)
class CoverageKpis:
    """One covered-entity result shared by every surface."""

    formula_id: str
    formula_version: int
    covered_entity_ids: frozenset[str]
    covered_count: int
    total_entities: int
    excluded_entity_ids: frozenset[str]
    state_counts: dict[str, int]
    non_covered_claims_rejected: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "formula_id": self.formula_id,
            "formula_version": self.formula_version,
            "covered_count": self.covered_count,
            "total_entities": self.total_entities,
            "covered_entity_ids": sorted(self.covered_entity_ids),
            "excluded_entity_ids": sorted(self.excluded_entity_ids),
            "state_counts": dict(self.state_counts),
            "non_covered_claims_rejected": list(self.non_covered_claims_rejected),
        }


def normalize_coverage_state(state: Any) -> str:
    if state is None:
        return ""
    if isinstance(state, CoverageState):
        return state.value
    return str(state).strip().lower()


def is_covered_state(state: Any) -> bool:
    """Return True only for success_with_data / success_zero."""
    value = normalize_coverage_state(state)
    if not value:
        return False
    if value in NON_COVERED_STATE_VALUES and value not in COVERED_STATE_VALUES:
        return False
    return value in COVERED_STATE_VALUES


def classify_evidence_identity(
    *,
    entity_id: Any = None,
    canonical_entity_key: Any = None,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    """Classify whether evidence can enter a dual-coverage numerator.

    IDENTITY_MAPPED: has entity_id or canonical_entity_key.
    SOURCE_WIDE_AGGREGATE: source-level rollup with no entity identity.
    UNMAPPABLE: residual without identity and without aggregate markers.
    """
    key = str(canonical_entity_key or "").strip()
    if key:
        return IDENTITY_MAPPED
    if entity_id is not None and str(entity_id).strip() not in {"", "None", "null"}:
        return IDENTITY_MAPPED

    meta = metadata or {}
    aggregate_markers = (
        str(meta.get("pipeline") or ""),
        str(meta.get("scope") or ""),
        str(meta.get("aggregation") or ""),
        str(meta.get("grain") or ""),
    )
    if any(
        token.lower() in {"resilient_cycle", "source_wide", "source-wide", "aggregate", "aggregated"}
        for token in aggregate_markers
    ):
        return SOURCE_WIDE_AGGREGATE
    # NULL identity with counts is a source-wide rollup, not an entity fact.
    return SOURCE_WIDE_AGGREGATE if not key else UNMAPPABLE


def numerator_row_has_identity(row: Mapping[str, Any]) -> bool:
    return classify_evidence_identity(
        entity_id=row.get("entity_id"),
        canonical_entity_key=row.get("canonical_entity_key"),
        metadata=row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {},
    ) == IDENTITY_MAPPED


def _entity_key(row: Mapping[str, Any]) -> str:
    for field_name in ("canonical_entity_key", "entity_id", "entity_key", "id"):
        value = row.get(field_name)
        if value is not None and str(value).strip() not in {"", "None", "null"}:
            return str(value).strip()
    return ""


def compute_coverage_kpis(rows: Iterable[Mapping[str, Any]]) -> CoverageKpis:
    """Canonical covered-entity KPI. All surfaces must call this function."""
    by_entity: dict[str, list[str]] = defaultdict(list)
    rejected: list[str] = []
    for raw in rows:
        row = dict(raw)
        entity = _entity_key(row)
        state = row.get("state") or row.get("coverage_state") or row.get("result")
        if not entity:
            identity = classify_evidence_identity(
                entity_id=row.get("entity_id"),
                canonical_entity_key=row.get("canonical_entity_key"),
                metadata=row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {},
            )
            rejected.append(f"{identity}:missing_entity")
            continue
        if state is None and row.get("is_covered") is True:
            # Boolean-only flag without state cannot prove coverage.
            rejected.append(f"{entity}:boolean_without_state")
            by_entity[entity].append("unknown")
            continue
        normalized = normalize_coverage_state(state)
        by_entity[entity].append(normalized or "unknown")
        if normalized in NON_COVERED_STATE_VALUES and not is_covered_state(normalized):
            rejected.append(f"{entity}:{normalized}")

    covered: set[str] = set()
    excluded: set[str] = set()
    state_counts: dict[str, int] = defaultdict(int)
    for entity, states in by_entity.items():
        for state in states:
            state_counts[state or "unknown"] += 1
        if any(is_covered_state(state) for state in states):
            covered.add(entity)
        else:
            excluded.add(entity)

    return CoverageKpis(
        formula_id=FORMULA_ID,
        formula_version=FORMULA_VERSION,
        covered_entity_ids=frozenset(covered),
        covered_count=len(covered),
        total_entities=len(by_entity),
        excluded_entity_ids=frozenset(excluded),
        state_counts=dict(state_counts),
        non_covered_claims_rejected=tuple(rejected),
    )


def assert_surfaces_agree(surface_kpis: Mapping[str, CoverageKpis]) -> CoverageKpis:
    """Fail if any named surface disagrees on the covered set."""
    if not surface_kpis:
        raise CoverageFormulaDivergenceError("no coverage surfaces provided")
    names = list(surface_kpis)
    reference = surface_kpis[names[0]]
    for name in names[1:]:
        other = surface_kpis[name]
        if (
            other.covered_entity_ids != reference.covered_entity_ids
            or other.covered_count != reference.covered_count
            or other.formula_id != reference.formula_id
        ):
            raise CoverageFormulaDivergenceError(
                f"{names[0]} covered={sorted(reference.covered_entity_ids)} "
                f"count={reference.covered_count} vs {name} "
                f"covered={sorted(other.covered_entity_ids)} count={other.covered_count}"
            )
    return reference


def dual_coverage_evidence_gate(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Decide whether dual-coverage numerators may use the given evidence rows.

    Identified rows may enter numerators. Source-wide aggregates are recorded
    and never counted. Truly unmappable identity-bearing rows stay fail-closed.
    """
    identified: list[dict[str, Any]] = []
    source_wide: list[dict[str, Any]] = []
    unmappable: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        kind = classify_evidence_identity(
            entity_id=row.get("entity_id"),
            canonical_entity_key=row.get("canonical_entity_key"),
            metadata=row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {},
        )
        if kind == IDENTITY_MAPPED:
            identified.append(row)
        elif kind == SOURCE_WIDE_AGGREGATE:
            source_wide.append(row)
        else:
            unmappable.append(row)

    if unmappable:
        return {
            "classification": MISSING_EVIDENCE,
            "reason": "unmappable_evidence_cannot_drop",
            "numerator_rows": [],
            "source_wide_count": len(source_wide),
            "unmapped_count": len(unmappable),
            "identified_count": len(identified),
            "measurement_success": False,
        }
    if source_wide and not identified:
        return {
            "classification": MISSING_EVIDENCE,
            "reason": "source_wide_aggregate_without_identity",
            "numerator_rows": [],
            "source_wide_count": len(source_wide),
            "unmapped_count": 0,
            "identified_count": 0,
            "measurement_success": False,
        }
    return {
        "classification": "IDENTITY_READY",
        "reason": "ok",
        "numerator_rows": identified,
        "source_wide_count": len(source_wide),
        "unmapped_count": 0,
        "identified_count": len(identified),
        "measurement_success": True,
    }


def load_coverage_state_rows(conn: Any) -> list[dict[str, Any]]:
    """Load state-bearing rows that every published coverage surface must use."""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COALESCE(canonical_entity_key, entity_id::text) AS entity_id,
                   state::text AS state,
                   source,
                   metadata
            FROM coverage_evidence
            """
        )
        fetched = list(cur.fetchall() or [])
        return [
            {
                "entity_id": row[0],
                "state": row[1],
                "source": row[2] if len(row) > 2 else "",
                "metadata": row[3] if len(row) > 3 and isinstance(row[3], Mapping) else {},
            }
            for row in fetched
        ]
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
        try:
            cur.execute(
                """
                SELECT entity_id::text, NULL::text AS state, source
                FROM entity_coverage
                """
            )
            fetched = list(cur.fetchall() or [])
            return [
                {"entity_id": row[0], "state": row[1], "source": row[2] if len(row) > 2 else ""}
                for row in fetched
            ]
        except Exception:
            if callable(rollback):
                rollback()
            return []
    finally:
        close = getattr(cur, "close", None)
        if callable(close):
            close()


def published_coverage_kpis(conn: Any) -> CoverageKpis:
    """Single published KPI entry point for panel, PDF, Excel, manifest and QA."""
    return compute_coverage_kpis(load_coverage_state_rows(conn))


# Surfaces must bind this exact function so QA can prove they share a formula.
COVERED_ENTITY_FORMULA = compute_coverage_kpis

__all__ = [
    "COVERED_ENTITY_FORMULA",
    "COVERED_STATE_VALUES",
    "CoverageFormulaDivergenceError",
    "CoverageKpis",
    "FORMULA_ID",
    "IDENTITY_MAPPED",
    "MISSING_EVIDENCE",
    "SOURCE_WIDE_AGGREGATE",
    "UNMAPPABLE",
    "assert_surfaces_agree",
    "classify_evidence_identity",
    "compute_coverage_kpis",
    "load_coverage_state_rows",
    "published_coverage_kpis",
    "dual_coverage_evidence_gate",
    "is_covered_state",
    "numerator_row_has_identity",
]
