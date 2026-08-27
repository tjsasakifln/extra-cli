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

Two acceptance levels are deliberately distinct and must never be conflated:

  RECONCILE_ACCEPTABLE — the reconciler may treat the snapshot as usable
    operational state (coverage >= TARGET_FIT_COVERAGE_THRESHOLD, i.e. 99.5%).
  PUBLICATION_READY    — the snapshot may back a commercial outreach feed
    (coverage == PUBLICATION_COVERAGE_THRESHOLD, i.e. complete, with zero
    unexplained missing roots and zero accounting defects).

A PARTIAL population that merely exceeds 0.995 is RECONCILE_ACCEPTABLE and is
never PUBLICATION_READY. Outreach publication reads PUBLICATION_READY only.
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

# Commercial outreach publication is stricter than reconciliation: the feed may
# only be built from a complete population. This is intentionally not the same
# number as TARGET_FIT_COVERAGE_THRESHOLD and must never be relaxed to it.
PUBLICATION_COVERAGE_THRESHOLD = 1.0

CONTROL_KEY_COVERAGE = "target_fit_coverage"
CONTROL_KEY_FULL_RECONCILE = "full_reconcile"


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def coverage_ratio(
    *,
    materialized_company_count: int,
    canonical_company_count: int,
    clamp: bool = True,
) -> float | None:
    """Coverage of valid materialized roots over canonical roots.

    Invariant: when clamp=True (default), result is always in [0, 1].
    Over-materialization must be reported via orphan/overcount fields, never
    as coverage_ratio > 1.
    """
    if canonical_company_count <= 0:
        return None
    raw = float(materialized_company_count) / float(canonical_company_count)
    if clamp:
        if raw < 0:
            return 0.0
        if raw > 1.0:
            return 1.0
    return raw


def reconcile_accounting(
    *,
    canonical_roots: int,
    materialized_roots: int,
    orphan_materialized_roots: int = 0,
    duplicate_cnpj_root: int = 0,
    invalid_cnpj_root: int = 0,
    explicit_exclusions: int = 0,
    exclusion_reason_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Closed-form universe accounting with hard invariants.

    valid_materialized = materialized - orphans - invalid (duplicates counted separately)
    0 <= coverage_ratio <= 1
    valid_materialized <= canonical
    unexplained_missing = max(0, canonical - valid_materialized - explicit_exclusions)
    """
    orphans = max(0, int(orphan_materialized_roots))
    dups = max(0, int(duplicate_cnpj_root))
    invalid = max(0, int(invalid_cnpj_root))
    exclusions = max(0, int(explicit_exclusions))
    mat = max(0, int(materialized_roots))
    canon = max(0, int(canonical_roots))
    valid_materialized = max(0, mat - orphans - invalid)
    # Duplicates inflate mat without adding unique roots; surface but don't
    # double-subtract if orphan pass already used distinct roots.
    if valid_materialized > canon:
        overcount = valid_materialized - canon
        valid_materialized = canon
    else:
        overcount = 0
    unexplained = max(0, canon - valid_materialized - exclusions)
    ratio = coverage_ratio(
        materialized_company_count=valid_materialized,
        canonical_company_count=canon,
        clamp=True,
    )
    equation_ok = (valid_materialized + exclusions + unexplained) == canon
    invariants = {
        "coverage_ratio_in_0_1": ratio is None or (0.0 <= ratio <= 1.0 + 1e-12),
        "valid_materialized_le_canonical": valid_materialized <= canon,
        "orphan_materialized_roots_eq_0": orphans == 0,
        "duplicate_cnpj_root_eq_0": dups == 0,
        "invalid_cnpj_root_eq_0": invalid == 0,
        "unexplained_missing_eq_0": unexplained == 0,
        "equation_closed": equation_ok,
    }
    return {
        "schema": "confenge.universe_accounting.v1",
        "canonical_roots": canon,
        "materialized_roots": mat,
        "materialized_valid_roots": valid_materialized,
        "orphan_materialized_roots": orphans,
        "duplicate_cnpj_root": dups,
        "invalid_cnpj_root": invalid,
        "explicit_exclusions": exclusions,
        "exclusion_reason_counts": dict(exclusion_reason_counts or {}),
        "unexplained_missing": unexplained,
        "overcount_clamped": overcount,
        "coverage_ratio": ratio,
        "invariants": invariants,
        "FULLY_RECONCILED": all(invariants.values()),
    }


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
    orphan_materialized_roots: int = 0,
    duplicate_cnpj_root: int = 0,
    invalid_cnpj_root: int = 0,
    exclusion_reason_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Machine-readable coverage watermark (real counts only — no hard-coded N)."""
    accounting = reconcile_accounting(
        canonical_roots=int(canonical_company_count),
        materialized_roots=int(materialized_company_count),
        orphan_materialized_roots=int(orphan_materialized_roots),
        duplicate_cnpj_root=int(duplicate_cnpj_root),
        invalid_cnpj_root=int(invalid_cnpj_root),
        explicit_exclusions=int(explicit_exclusions),
        exclusion_reason_counts=exclusion_reason_counts,
    )
    # Prefer closed-form unexplained from accounting when stricter
    unexplained = max(int(unexplained_missing), int(accounting["unexplained_missing"]))
    # If orphans present, they explain overcount but also fail FULLY_RECONCILED
    ratio = accounting["coverage_ratio"]
    gaps = dict(gap_breakdown or {})
    if orphan_materialized_roots:
        gaps["ORPHAN_MATERIALIZED"] = int(orphan_materialized_roots)
    if duplicate_cnpj_root:
        gaps["DUPLICATE_CNPJ_ROOT"] = int(duplicate_cnpj_root)
    if invalid_cnpj_root:
        gaps["INVALID_CNPJ"] = int(gaps.get("INVALID_CNPJ", 0)) + int(invalid_cnpj_root)
    # Reject UNKNOWN labels if present
    unknown = {k: v for k, v in gaps.items() if k not in KNOWN_GAP_STATES and k not in {
        "ORPHAN_MATERIALIZED",
        "DUPLICATE_CNPJ_ROOT",
    }}
    if unknown:
        # Fold unknown into DATA_ERROR for honesty rather than inventing acceptance
        gaps["DATA_ERROR"] = int(gaps.get("DATA_ERROR", 0)) + sum(int(v) for v in unknown.values())
        for k in list(unknown):
            gaps.pop(k, None)

    mode = classify_coverage_mode(
        coverage=ratio,
        last_full_reconcile_completed_at=last_full_reconcile_completed_at,
        unexplained_missing=int(unexplained),
        pagination_exhausted_normally=bool(pagination_exhausted_normally),
        auto_paused=auto_paused,
        dead=dead,
        lag_seconds=lag_seconds,
    )
    if orphan_materialized_roots > 0 or duplicate_cnpj_root > 0 or invalid_cnpj_root > 0:
        # Cannot be fully reconciled with accounting defects
        if mode == COVERAGE_MODE_FULLY_RECONCILED:
            mode = COVERAGE_MODE_PARTIAL
    full_national_ready = (
        mode == COVERAGE_MODE_FULLY_RECONCILED
        and unexplained == 0
        and orphan_materialized_roots == 0
        and duplicate_cnpj_root == 0
        and invalid_cnpj_root == 0
        and (ratio is None or ratio <= 1.0 + 1e-12)
    )
    return {
        "schema": "confenge.target_fit_coverage.v1",
        "canonical_company_count": int(canonical_company_count),
        "materialized_company_count": int(materialized_company_count),
        "materialized_valid_roots": int(accounting["materialized_valid_roots"]),
        "orphan_materialized_roots": int(orphan_materialized_roots),
        "duplicate_cnpj_root": int(duplicate_cnpj_root),
        "invalid_cnpj_root": int(invalid_cnpj_root),
        "coverage_ratio": ratio,
        "coverage_ratio_raw_unclamped": (
            float(materialized_company_count) / float(canonical_company_count)
            if canonical_company_count > 0
            else None
        ),
        "coverage_threshold": TARGET_FIT_COVERAGE_THRESHOLD,
        "expected_company_roots": int(expected_company_roots),
        "visited_company_roots": int(visited_company_roots),
        "explicit_exclusions": int(explicit_exclusions),
        "exclusion_reason_counts": dict(exclusion_reason_counts or {}),
        "unexplained_missing": int(unexplained),
        "pagination_exhausted_normally": bool(pagination_exhausted_normally),
        "last_full_reconcile_completed_at": last_full_reconcile_completed_at,
        "last_full_reconcile_unexplained_missing": int(unexplained),
        "gap_breakdown": gaps,
        "population_source": population_source,
        "async_mode": async_mode,
        "coverage_mode": mode,
        "FULL_NATIONAL_READY": full_national_ready,
        "FULLY_RECONCILED": bool(accounting["FULLY_RECONCILED"] and full_national_ready),
        "RECONCILE_ACCEPTABLE": bool(
            mode == COVERAGE_MODE_FULLY_RECONCILED
            and ratio is not None
            and ratio + 1e-12 >= TARGET_FIT_COVERAGE_THRESHOLD
        ),
        "PUBLICATION_READY": bool(
            accounting["FULLY_RECONCILED"]
            and full_national_ready
            and unexplained == 0
            and ratio is not None
            and ratio + 1e-12 >= PUBLICATION_COVERAGE_THRESHOLD
        ),
        "publication_coverage_threshold": PUBLICATION_COVERAGE_THRESHOLD,
        "accounting": accounting,
        "as_of": _utcnow_iso(),
    }


def reconcile_acceptable(snapshot: dict[str, Any] | None) -> bool:
    """Operational acceptance: the reconciler may keep using this snapshot."""
    snapshot = snapshot or {}
    if "RECONCILE_ACCEPTABLE" in snapshot:
        return bool(snapshot["RECONCILE_ACCEPTABLE"])
    ratio = snapshot.get("coverage_ratio")
    return bool(
        snapshot.get("coverage_mode") == COVERAGE_MODE_FULLY_RECONCILED
        and ratio is not None
        and float(ratio) + 1e-12 >= TARGET_FIT_COVERAGE_THRESHOLD
    )


def publication_ready(snapshot: dict[str, Any] | None) -> bool:
    """Commercial acceptance: this snapshot may back an outreach feed.

    Deliberately stricter than :func:`reconcile_acceptable`. A snapshot that is
    merely above TARGET_FIT_COVERAGE_THRESHOLD is not publishable, and older
    snapshots that predate the PUBLICATION_READY field are recomputed here from
    their own recorded counts rather than assumed acceptable.
    """
    snapshot = snapshot or {}
    if "PUBLICATION_READY" in snapshot:
        return bool(snapshot["PUBLICATION_READY"])
    ratio = snapshot.get("coverage_ratio")
    if ratio is None:
        return False
    return bool(
        snapshot.get("FULLY_RECONCILED")
        and snapshot.get("FULL_NATIONAL_READY")
        and int(snapshot.get("unexplained_missing") or 0) == 0
        and int(snapshot.get("orphan_materialized_roots") or 0) == 0
        and int(snapshot.get("duplicate_cnpj_root") or 0) == 0
        and int(snapshot.get("invalid_cnpj_root") or 0) == 0
        and bool(snapshot.get("pagination_exhausted_normally"))
        and float(ratio) + 1e-12 >= PUBLICATION_COVERAGE_THRESHOLD
    )


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
