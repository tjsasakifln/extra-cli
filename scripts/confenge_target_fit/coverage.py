"""National target-fit coverage watermark and reservoir health modes.

TARGET_FIT_COVERAGE =
  target_fit_materialized_company_roots / canonical_eligible_company_roots

Honest modes (do not claim FULL_NATIONAL_READY without a proven full reconcile):

  BOOTSTRAPPING  — no full reconcile completed yet
  PARTIAL        — reconcile in progress or coverage below threshold
  FULLY_RECONCILED — full reconcile done, coverage ≥ 99.5% or gaps fully explained
  STALE          — last full reconcile older than SLO or watermark lag high
  DEGRADED       — errors / dead queue / auto-pause signals

Coverage never hard-codes national universe size; live counts only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# Known exclusion/gap labels only — never UNKNOWN.
KNOWN_GAP_STATES = frozenset(
    {
        "DNC",
        "INVALID_CNPJ",
        "NO_CONSTRUCTION_EVIDENCE",
        "MERGED_ROOT",
        "DATA_ERROR",
        "RETRY_PENDING",
        "CLASSIFIER_ERROR",
        "EXPLICIT_EXCLUSION",
    }
)

COVERAGE_MODE_BOOTSTRAPPING = "BOOTSTRAPPING"
COVERAGE_MODE_PARTIAL = "PARTIAL"
COVERAGE_MODE_FULLY_RECONCILED = "FULLY_RECONCILED"
COVERAGE_MODE_STALE = "STALE"
COVERAGE_MODE_DEGRADED = "DEGRADED"

# After a completed full reconcile, coverage must meet this ratio
# (or every missing root must be labeled with KNOWN_GAP_STATES).
TARGET_FIT_COVERAGE_THRESHOLD = 0.995

CONTROL_KEY_COVERAGE = "target_fit_coverage"
CONTROL_KEY_FULL_RECONCILE = "full_reconcile"


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def coverage_ratio(
    *,
    materialized_company_count: int,
    canonical_company_count: int,
) -> float | None:
    if canonical_company_count <= 0:
        return None
    return float(materialized_company_count) / float(canonical_company_count)


def classify_coverage_mode(
    *,
    coverage: float | None,
    last_full_reconcile_completed_at: str | None,
    unexplained_missing: int,
    pagination_exhausted_normally: bool,
    auto_paused: bool = False,
    dead: int = 0,
    lag_seconds: float | None = None,
    max_lag_seconds: float = 86_400.0,
    stale_after_seconds: float = 7 * 86_400.0,
    now: datetime | None = None,
) -> str:
    """Derive honest reservoir coverage mode (independent of worker HEALTHY)."""
    if auto_paused or dead > 1000:
        return COVERAGE_MODE_DEGRADED

    if not last_full_reconcile_completed_at:
        return COVERAGE_MODE_BOOTSTRAPPING

    now = now or datetime.now(UTC)
    try:
        completed = datetime.fromisoformat(
            last_full_reconcile_completed_at.replace("Z", "+00:00")
        )
        age = (now - completed).total_seconds()
        if age > stale_after_seconds:
            return COVERAGE_MODE_STALE
    except ValueError:
        return COVERAGE_MODE_BOOTSTRAPPING

    if lag_seconds is not None and lag_seconds > max_lag_seconds:
        return COVERAGE_MODE_STALE

    if unexplained_missing > 0 or not pagination_exhausted_normally:
        return COVERAGE_MODE_PARTIAL

    if coverage is None:
        return COVERAGE_MODE_PARTIAL

    if coverage + 1e-12 >= TARGET_FIT_COVERAGE_THRESHOLD:
        return COVERAGE_MODE_FULLY_RECONCILED

    return COVERAGE_MODE_PARTIAL


def build_coverage_snapshot(
    *,
    canonical_company_count: int,
    materialized_company_count: int,
    expected_company_roots: int,
    visited_company_roots: int,
    unexplained_missing: int,
    pagination_exhausted_normally: bool,
    explicit_exclusions: int = 0,
    gap_breakdown: dict[str, int] | None = None,
    last_full_reconcile_completed_at: str | None = None,
    async_mode: str = "SHADOW",
    auto_paused: bool = False,
    dead: int = 0,
    lag_seconds: float | None = None,
    population_source: str = "shadow",
) -> dict[str, Any]:
    """Machine-readable coverage watermark (real counts only — no hard-coded N)."""
    ratio = coverage_ratio(
        materialized_company_count=materialized_company_count,
        canonical_company_count=canonical_company_count,
    )
    gaps = dict(gap_breakdown or {})
    # Reject UNKNOWN labels if present
    unknown = {k: v for k, v in gaps.items() if k not in KNOWN_GAP_STATES}
    if unknown:
        # Fold unknown into DATA_ERROR for honesty rather than inventing acceptance
        gaps["DATA_ERROR"] = int(gaps.get("DATA_ERROR", 0)) + sum(int(v) for v in unknown.values())
        for k in list(unknown):
            gaps.pop(k, None)

    mode = classify_coverage_mode(
        coverage=ratio,
        last_full_reconcile_completed_at=last_full_reconcile_completed_at,
        unexplained_missing=int(unexplained_missing),
        pagination_exhausted_normally=bool(pagination_exhausted_normally),
        auto_paused=auto_paused,
        dead=dead,
        lag_seconds=lag_seconds,
    )
    full_national_ready = mode == COVERAGE_MODE_FULLY_RECONCILED and unexplained_missing == 0
    return {
        "schema": "confenge.target_fit_coverage.v1",
        "canonical_company_count": int(canonical_company_count),
        "materialized_company_count": int(materialized_company_count),
        "coverage_ratio": ratio,
        "coverage_threshold": TARGET_FIT_COVERAGE_THRESHOLD,
        "expected_company_roots": int(expected_company_roots),
        "visited_company_roots": int(visited_company_roots),
        "explicit_exclusions": int(explicit_exclusions),
        "unexplained_missing": int(unexplained_missing),
        "pagination_exhausted_normally": bool(pagination_exhausted_normally),
        "last_full_reconcile_completed_at": last_full_reconcile_completed_at,
        "last_full_reconcile_unexplained_missing": int(unexplained_missing),
        "gap_breakdown": gaps,
        "population_source": population_source,
        "async_mode": async_mode,
        "coverage_mode": mode,
        "FULL_NATIONAL_READY": full_national_ready,
        "as_of": _utcnow_iso(),
    }


def load_coverage_control(conn: Any) -> dict[str, Any]:
    from scripts.confenge_target_fit.store import get_control

    cov = get_control(conn, CONTROL_KEY_COVERAGE)
    fr = get_control(conn, CONTROL_KEY_FULL_RECONCILE)
    out = dict(cov or {})
    if fr:
        out.setdefault(
            "last_full_reconcile_completed_at",
            fr.get("completed_at") or fr.get("last_full_reconcile_completed_at"),
        )
        if "unexplained_missing" in fr:
            out.setdefault(
                "last_full_reconcile_unexplained_missing",
                fr.get("unexplained_missing"),
            )
        if "pagination_exhausted_normally" in fr:
            out.setdefault(
                "pagination_exhausted_normally",
                fr.get("pagination_exhausted_normally"),
            )
    return out


def persist_coverage_control(conn: Any, snapshot: dict[str, Any]) -> None:
    from scripts.confenge_target_fit.store import set_control

    set_control(conn, CONTROL_KEY_COVERAGE, snapshot)
    if snapshot.get("pagination_exhausted_normally") and int(
        snapshot.get("unexplained_missing") or 0
    ) == 0:
        set_control(
            conn,
            CONTROL_KEY_FULL_RECONCILE,
            {
                "completed_at": snapshot.get("as_of")
                or snapshot.get("last_full_reconcile_completed_at"),
                "unexplained_missing": 0,
                "pagination_exhausted_normally": True,
                "expected_company_roots": snapshot.get("expected_company_roots"),
                "visited_company_roots": snapshot.get("visited_company_roots"),
                "materialized_company_count": snapshot.get("materialized_company_count"),
                "canonical_company_count": snapshot.get("canonical_company_count"),
                "coverage_ratio": snapshot.get("coverage_ratio"),
            },
        )
