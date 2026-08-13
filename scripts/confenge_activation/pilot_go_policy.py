"""Canonical CONFENGE universe and controlled-pilot GO policy.

The policy deliberately separates three concepts that older closure packs
conflated:

* the complete historical datalake population;
* the quality and human-acceptance gates for a controlled pilot; and
* the 10-business-day send-ready reserve used for continuous operation.

Top-N samples and rolling hot sets are validation/dispatch windows only.  They
must never be used as universe denominators or materialization limits.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from scripts.confenge_contact_resolution.human_review import (
    HUMAN_REVIEW_APPROVED,
    HUMAN_REVIEW_REJECTED,
    is_forbidden_reviewer,
)
from scripts.confenge_target_fit import (
    TARGET_CONFIRMED,
    TARGET_INSUFFICIENT_EVIDENCE,
    TARGET_OUT_OF_SCOPE,
    TARGET_PROBABLE_RESEARCH,
)

UNIVERSE_SCHEMA = "confenge.universe_manifest.v3"
GO_NO_GO_SCHEMA = "confenge.go_no_go.v2"
TERMINAL_AUTHORITY = "scripts.confenge_activation.pilot_go_policy.evaluate_pilot_go"

TARGET_CLASS_KEYS = (
    TARGET_CONFIRMED,
    TARGET_PROBABLE_RESEARCH,
    TARGET_OUT_OF_SCOPE,
    TARGET_INSUFFICIENT_EVIDENCE,
)
TARGET_OPERATIONAL_STATE_KEYS = ("REFRESH_FAILED", "RECOMPUTE_REQUIRED")
SECTOR_CLASS_KEYS = (
    "CONSTRUCTION_CONFIRMED",
    "CONSTRUCTION_PROBABLE",
    "NON_CONSTRUCTION",
    "SECTOR_INSUFFICIENT_EVIDENCE",
)

MINIMUM_HUMAN_REVIEWED = 20
MINIMUM_HUMAN_APPROVED = 10


def _nonnegative(value: Any) -> int:
    return max(0, int(value or 0))


def _integer(value: Any) -> int:
    """Parse a count without laundering an invalid negative measurement."""
    return int(value or 0)


def build_universe_manifest(
    *,
    supplier_roots_observed: int,
    sector_classes: dict[str, int],
    target_fit_population: int,
    materialized_roots: int,
    target_classes: dict[str, int],
    source_contract_rows: int,
    datalake_watermark: str,
    source_cdc_watermark: str,
    database_snapshot: str,
    transaction_timestamp: str,
    construction_universe_derivation: str,
    construction_evidence_version: str,
    query_sha256: str,
    construction_classifier_sha256: str,
    target_fit_classifier_sha256: str,
    target_fit_version: str,
    target_operational_states: dict[str, int] | None = None,
    sector_materialized_roots: int | None = None,
    full_scale: bool = True,
    truncated: bool = False,
    pagination_exhausted_normally: bool = True,
    unexplained_missing: int = 0,
    orphan_materialized_roots: int = 0,
    duplicate_cnpj_root: int = 0,
    invalid_cnpj_root: int = 0,
    sector_version_mismatch: int = 0,
    sector_classifier_mismatch: int = 0,
    target_version_mismatch: int = 0,
    target_classifier_mismatch: int = 0,
) -> dict[str, Any]:
    """Build a closed, versioned universe ledger from one atomic watermark.

    Construction membership is computed only from ``sector_classes``. Target
    classes close their own population and never define the construction set.
    """
    observed = _integer(supplier_roots_observed)
    materialized = _integer(materialized_roots)
    sector_materialized = _integer(
        sector_materialized_roots
        if sector_materialized_roots is not None
        else sum(sector_classes.values())
    )
    contracts = _integer(source_contract_rows)
    classes = {key: _integer(target_classes.get(key)) for key in TARGET_CLASS_KEYS}
    operational_states = {
        key: _integer((target_operational_states or {}).get(key))
        for key in TARGET_OPERATIONAL_STATE_KEYS
    }
    sectors = {key: _integer(sector_classes.get(key)) for key in SECTOR_CLASS_KEYS}
    unknown_classes = sorted(set(target_classes) - set(TARGET_CLASS_KEYS))
    unknown_sector_classes = sorted(set(sector_classes) - set(SECTOR_CLASS_KEYS))
    class_sum = sum(classes.values())
    sector_sum = sum(sectors.values())
    construction = sectors["CONSTRUCTION_CONFIRMED"] + sectors["CONSTRUCTION_PROBABLE"]
    non_construction = sectors["NON_CONSTRUCTION"]
    unresolved_sector = sectors["SECTOR_INSUFFICIENT_EVIDENCE"]
    target_population = _integer(target_fit_population)
    watermark = str(datalake_watermark or "").strip()
    snapshot = str(database_snapshot).strip()
    cdc_watermark = str(source_cdc_watermark).strip()
    captured_at = str(transaction_timestamp).strip()
    version = str(target_fit_version or "").strip()
    derivation = str(construction_universe_derivation).strip()
    construction_version = str(construction_evidence_version).strip()
    query_hash = str(query_sha256).removeprefix("sha256:").strip()
    construction_hash = str(construction_classifier_sha256).removeprefix("sha256:").strip()
    target_hash = str(target_fit_classifier_sha256).removeprefix("sha256:").strip()

    diagnostic_counts = {
        "unexplained_missing": _integer(unexplained_missing),
        "orphan_materialized_roots": _integer(orphan_materialized_roots),
        "duplicate_cnpj_root": _integer(duplicate_cnpj_root),
        "invalid_cnpj_root": _integer(invalid_cnpj_root),
        "sector_version_mismatch": _integer(sector_version_mismatch),
        "sector_classifier_mismatch": _integer(sector_classifier_mismatch),
        "target_version_mismatch": _integer(target_version_mismatch),
        "target_classifier_mismatch": _integer(target_classifier_mismatch),
    }
    all_counts = [
        observed,
        materialized,
        sector_materialized,
        contracts,
        *classes.values(),
        *operational_states.values(),
        *sectors.values(),
        *diagnostic_counts.values(),
    ]
    invariants = {
        "all_counts_nonnegative": all(value >= 0 for value in all_counts),
        "positive_observed_supplier_universe": observed > 0,
        "source_contract_rows_cover_roots": contracts >= observed > 0,
        "sector_sum_equals_observed_supplier_roots": sector_sum == observed,
        "construction_partition_is_sector_derived": construction + non_construction + unresolved_sector == observed,
        "target_class_sum_equals_target_fit_population": class_sum == target_population,
        "target_operational_states_eq_0": not any(operational_states.values()),
        "target_fit_population_equals_observed_supplier_roots": target_population == observed,
        "materialized_equals_observed_supplier_roots": materialized == observed,
        "sector_materialized_equals_observed_supplier_roots": sector_materialized == observed,
        "construction_universe_within_observed": 0 < construction <= observed,
        "pagination_exhausted_normally": bool(pagination_exhausted_normally),
        "full_scale": bool(full_scale),
        "not_truncated": not bool(truncated),
        "unexplained_missing_eq_0": diagnostic_counts["unexplained_missing"] == 0,
        "orphan_materialized_roots_eq_0": diagnostic_counts["orphan_materialized_roots"] == 0,
        "duplicate_cnpj_root_eq_0": diagnostic_counts["duplicate_cnpj_root"] == 0,
        "invalid_cnpj_root_eq_0": diagnostic_counts["invalid_cnpj_root"] == 0,
        "sector_version_mismatch_eq_0": diagnostic_counts["sector_version_mismatch"] == 0,
        "sector_classifier_mismatch_eq_0": diagnostic_counts["sector_classifier_mismatch"] == 0,
        "target_version_mismatch_eq_0": diagnostic_counts["target_version_mismatch"] == 0,
        "target_classifier_mismatch_eq_0": diagnostic_counts["target_classifier_mismatch"] == 0,
        "single_watermark_present": bool(watermark and cdc_watermark and captured_at),
        "atomic_database_snapshot_present": bool(snapshot) if full_scale else True,
        "classifier_versions_present": bool(version and construction_version),
        "lineage_hashes_present": all(len(value) == 64 for value in (query_hash, construction_hash, target_hash)),
        "construction_derivation_is_sector_only": bool(derivation) and "TARGET_" not in derivation.upper(),
        "no_unknown_target_classes": not unknown_classes,
        "no_unknown_sector_classes": not unknown_sector_classes,
    }
    return {
        "schema": UNIVERSE_SCHEMA,
        "source_contract_rows": contracts,
        "supplier_roots_observed": observed,
        "construction_roots": construction,
        "non_construction_roots": non_construction,
        "genuinely_unresolved_sector_roots": unresolved_sector,
        "construction_universe_derivation": derivation,
        "construction_evidence_version": construction_version,
        "target_fit_population": target_population,
        "target_classes": classes,
        "target_operational_states": operational_states,
        "sector_classes": sectors,
        "materialized_roots": materialized,
        "sector_materialized_roots": sector_materialized,
        "datalake_watermark": watermark or None,
        "database_snapshot": snapshot or None,
        "source_cdc_watermark": cdc_watermark or None,
        "transaction_timestamp": captured_at or None,
        "target_class_sum": class_sum,
        "sector_class_sum": sector_sum,
        "unknown_target_classes": unknown_classes,
        "unknown_sector_classes": unknown_sector_classes,
        "target_fit_version": version or None,
        "query_sha256": query_hash,
        "construction_classifier_sha256": construction_hash,
        "target_fit_classifier_sha256": target_hash,
        "full_scale": bool(full_scale),
        "truncated": bool(truncated),
        "pagination_exhausted_normally": bool(pagination_exhausted_normally),
        **diagnostic_counts,
        "invariants": invariants,
        "FULLY_RECONCILED": all(invariants.values()),
        "subset_policy": {
            "samples_are_validation_only": True,
            "hot_set_controls_dispatch_velocity_only": True,
            "subsets_may_not_change_universe_counts": True,
            "uncontactable_leads_remain_reconsiderable": True,
        },
    }


def validate_universe_manifest(manifest: dict[str, Any] | None) -> list[str]:
    """Return fail-closed violations for a universe-manifest v3 document."""
    if not isinstance(manifest, dict):
        return ["universe_manifest_missing"]
    errors: list[str] = []
    if manifest.get("schema") != UNIVERSE_SCHEMA:
        errors.append(f"schema_must_be_{UNIVERSE_SCHEMA}")
    invariants = manifest.get("invariants")
    if not isinstance(invariants, dict):
        errors.append("invariants_missing")
    else:
        errors.extend(f"invariant_false:{key}" for key, ok in invariants.items() if not ok)
    if not manifest.get("FULLY_RECONCILED"):
        errors.append("FULLY_RECONCILED_false")
    required = (
        "source_contract_rows",
        "supplier_roots_observed",
        "construction_roots",
        "non_construction_roots",
        "construction_universe_derivation",
        "construction_evidence_version",
        "target_fit_population",
        "target_classes",
        "target_operational_states",
        "sector_classes",
        "materialized_roots",
        "sector_materialized_roots",
        "genuinely_unresolved_sector_roots",
        "sector_version_mismatch",
        "sector_classifier_mismatch",
        "target_version_mismatch",
        "target_classifier_mismatch",
        "datalake_watermark",
        "source_cdc_watermark",
        "database_snapshot",
        "transaction_timestamp",
        "query_sha256",
        "construction_classifier_sha256",
        "target_fit_classifier_sha256",
    )
    errors.extend(f"required_field_missing:{key}" for key in required if manifest.get(key) in (None, ""))
    target_classes = manifest.get("target_classes") or {}
    target_operational_states = manifest.get("target_operational_states") or {}
    sector_classes = manifest.get("sector_classes") or {}
    if not isinstance(target_classes, dict):
        errors.append("target_classes_not_object")
        target_classes = {}
    if not isinstance(target_operational_states, dict):
        errors.append("target_operational_states_not_object")
        target_operational_states = {}
    if not isinstance(sector_classes, dict):
        errors.append("sector_classes_not_object")
        sector_classes = {}
    if set(target_classes) != set(TARGET_CLASS_KEYS):
        errors.append("target_class_keys_not_closed")
    if set(target_operational_states) != set(TARGET_OPERATIONAL_STATE_KEYS):
        errors.append("target_operational_state_keys_not_closed")
    if set(sector_classes) != set(SECTOR_CLASS_KEYS):
        errors.append("sector_class_keys_not_closed")

    invalid_counts: list[str] = []

    def count(value: Any, field: str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            invalid_counts.append(field)
            return -1
        if parsed < 0:
            invalid_counts.append(field)
        return parsed

    observed = count(manifest.get("supplier_roots_observed"), "supplier_roots_observed")
    contracts = count(manifest.get("source_contract_rows"), "source_contract_rows")
    target_population = count(manifest.get("target_fit_population"), "target_fit_population")
    materialized = count(manifest.get("materialized_roots"), "materialized_roots")
    sector_materialized = count(manifest.get("sector_materialized_roots"), "sector_materialized_roots")
    construction = count(manifest.get("construction_roots"), "construction_roots")
    non_construction = count(manifest.get("non_construction_roots"), "non_construction_roots")
    unresolved = count(
        manifest.get("genuinely_unresolved_sector_roots"),
        "genuinely_unresolved_sector_roots",
    )
    target_counts = {
        key: count(target_classes.get(key), f"target_classes.{key}") for key in TARGET_CLASS_KEYS
    }
    operational_counts = {
        key: count(
            target_operational_states.get(key),
            f"target_operational_states.{key}",
        )
        for key in TARGET_OPERATIONAL_STATE_KEYS
    }
    sector_counts = {
        key: count(sector_classes.get(key), f"sector_classes.{key}") for key in SECTOR_CLASS_KEYS
    }
    if sum(target_counts.values()) != target_population:
        errors.append("target_class_sum_mismatch")
    if any(operational_counts.values()):
        errors.append("target_operational_states_not_zero")
    if sum(sector_counts.values()) != observed:
        errors.append("sector_class_sum_mismatch")
    expected_construction = (
        sector_counts["CONSTRUCTION_CONFIRMED"] + sector_counts["CONSTRUCTION_PROBABLE"]
    )
    if expected_construction != construction:
        errors.append("construction_roots_not_sector_derived")
    if sector_counts["NON_CONSTRUCTION"] != non_construction:
        errors.append("non_construction_roots_mismatch")
    if sector_counts["SECTOR_INSUFFICIENT_EVIDENCE"] != unresolved:
        errors.append("unresolved_sector_roots_mismatch")
    if construction + non_construction + unresolved != observed:
        errors.append("sector_partition_not_closed")
    if target_population != observed:
        errors.append("target_fit_population_not_supplier_population")
    if materialized != observed:
        errors.append("materialized_roots_not_supplier_population")
    if sector_materialized != observed:
        errors.append("sector_materialized_roots_not_supplier_population")
    if contracts < observed or observed <= 0:
        errors.append("source_contract_rows_do_not_cover_supplier_roots")
    if manifest.get("full_scale") is not True:
        errors.append("full_scale_false")
    if manifest.get("truncated") is not False:
        errors.append("truncated_true_or_missing")
    if manifest.get("pagination_exhausted_normally") is not True:
        errors.append("pagination_not_exhausted_normally")
    for field in (
        "unexplained_missing",
        "orphan_materialized_roots",
        "duplicate_cnpj_root",
        "invalid_cnpj_root",
        "sector_version_mismatch",
        "sector_classifier_mismatch",
        "target_version_mismatch",
        "target_classifier_mismatch",
    ):
        if count(manifest.get(field), field) != 0:
            errors.append(f"{field}_not_zero")
    if invalid_counts:
        errors.extend(f"invalid_count:{field}" for field in sorted(set(invalid_counts)))
    if "TARGET_" in str(manifest.get("construction_universe_derivation") or "").upper():
        errors.append("construction_derivation_uses_target_fit")
    hexdigits = set("0123456789abcdef")
    for field in (
        "query_sha256",
        "construction_classifier_sha256",
        "target_fit_classifier_sha256",
    ):
        value = str(manifest.get(field) or "").removeprefix("sha256:").lower()
        if len(value) != 64 or not set(value) <= hexdigits:
            errors.append(f"invalid_sha256:{field}")
    return list(dict.fromkeys(errors))


def lead_key(row: dict[str, Any]) -> str:
    root = "".join(
        ch
        for ch in str(row.get("cnpj_raiz") or row.get("cnpj_root") or row.get("CNPJ") or row.get("cnpj") or "")
        if ch.isdigit()
    )[:8]
    email = str(row.get("email") or "").strip().lower()
    return f"{root}|{email}" if root and email else ""


def load_human_review_decisions(
    path: Path | None,
    *,
    eligible_rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Load append-only decisions; the latest valid decision wins per lead.

    Invalid or automation-attributed records are reported and never contribute
    to pilot acceptance.  Decisions for leads outside the current ESR remain in
    history but are not eligible for the current hot set.
    """
    eligible_order = list(dict.fromkeys(key for row in eligible_rows if (key := lead_key(row))))
    eligible = set(eligible_order)
    latest: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    blocking_errors: list[str] = []

    def record_error(message: str, *, key: str | None = None) -> None:
        errors.append(message)
        # Structurally corrupt rows cannot be scoped and therefore remain
        # blocking. Attributable errors block only the active ESR lead.
        if key is None or key in eligible:
            blocking_errors.append(message)

    historical_rows = 0
    if path and path.is_file():
        for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            historical_rows += 1
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                record_error(f"line_{line_no}:invalid_json")
                continue
            if not isinstance(row, dict):
                record_error(f"line_{line_no}:not_object")
                continue
            key = lead_key(row)
            status = str(row.get("review_status") or row.get("status") or "").upper()
            reviewer = str(row.get("reviewer") or "").strip()
            if not key:
                record_error(f"line_{line_no}:lead_key_missing")
                continue
            if status not in {HUMAN_REVIEW_APPROVED, HUMAN_REVIEW_REJECTED}:
                # SKIP/PENDING is useful history but never a completed review.
                continue
            if is_forbidden_reviewer(reviewer):
                record_error(
                    f"line_{line_no}:forbidden_or_missing_reviewer",
                    key=key,
                )
                continue
            if not row.get("reviewed_at") or not row.get("evidence_inspected"):
                record_error(f"line_{line_no}:attribution_incomplete", key=key)
                continue
            latest[key] = row

    current = {key: row for key, row in latest.items() if key in eligible}
    reviewed_keys = [key for key in eligible_order if key in current]
    approved_keys = [
        key
        for key in reviewed_keys
        if str(current[key].get("review_status") or current[key].get("status") or "").upper() == HUMAN_REVIEW_APPROVED
    ]
    rejected_keys = [key for key in reviewed_keys if key not in set(approved_keys)]
    return {
        "schema": "confenge.human_review_summary.v1",
        "decisions_path": str(path) if path else None,
        "historical_rows": historical_rows,
        "latest_valid_decisions": len(latest),
        "reviewed_current_esr": len(reviewed_keys),
        "approved_current_esr": len(approved_keys),
        "rejected_current_esr": len(rejected_keys),
        "reviewed_keys": reviewed_keys,
        "approved_keys": approved_keys,
        "rejected_keys": rejected_keys,
        "latest_by_key": current,
        "errors": errors,
        "blocking_errors": blocking_errors,
        "top20_review_complete": len(reviewed_keys) >= MINIMUM_HUMAN_REVIEWED,
        "hot_set_10_approved": len(approved_keys) >= MINIMUM_HUMAN_APPROVED,
    }


def evaluate_pilot_go(
    *,
    universe_manifest: dict[str, Any],
    technical_gates: dict[str, bool],
    human_review: dict[str, Any],
    email_send_ready: int,
    minimum_operational_reserve: int,
) -> dict[str, Any]:
    """Evaluate controlled pilot independently from national reserve health."""
    universe_errors = validate_universe_manifest(universe_manifest)
    universe_ok = not universe_errors
    tech = {str(k): bool(v) for k, v in technical_gates.items()}
    technical_ok = universe_ok and bool(tech) and all(tech.values())
    human_ok = (
        bool(human_review.get("top20_review_complete"))
        and bool(human_review.get("hot_set_10_approved"))
        and not bool(human_review.get("blocking_errors", human_review.get("errors")))
    )
    pilot_go = technical_ok and human_ok
    national_reserve_healthy = technical_ok and _nonnegative(email_send_ready) >= _nonnegative(
        minimum_operational_reserve
    )
    terminal = (
        "GO_FOR_REAL_CONFENGE_EMAIL_PILOT"
        if pilot_go
        else "READY_FOR_TIAGO_HUMAN_REVIEW"
        if technical_ok
        else "ENGINEERING_IN_PROGRESS"
    )
    return {
        "schema": GO_NO_GO_SCHEMA,
        "UNIVERSE_HEALTH": "FULLY_RECONCILED" if universe_ok else "NOT_RECONCILED",
        "UNIVERSE_ERRORS": universe_errors,
        "PILOT_QUALITY": "PASS" if technical_ok else "FAIL",
        "HUMAN_ACCEPTANCE": "PASS" if human_ok else "PENDING_OR_INVALID",
        "PILOT_GO": pilot_go,
        "NATIONAL_RESERVOIR_HEALTH": ("HEALTHY" if national_reserve_healthy else "BELOW_CONTINUOUS_OPERATION_TARGET"),
        "NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY": national_reserve_healthy,
        "terminal_state": terminal,
        "technical_gates": tech,
        "human_review": {key: value for key, value in human_review.items() if key != "latest_by_key"},
        "dispatch": {
            "state": "PAUSED_MANUAL_START",
            "channel": "EMAIL_ONLY",
            "whatsapp": "OFF",
            "emails_per_hour": 10,
            "approved_hot_set_keys": list(human_review.get("approved_keys") or [])[:MINIMUM_HUMAN_APPROVED],
        },
    }


__all__ = [
    "GO_NO_GO_SCHEMA",
    "MINIMUM_HUMAN_APPROVED",
    "MINIMUM_HUMAN_REVIEWED",
    "TARGET_CLASS_KEYS",
    "TARGET_OPERATIONAL_STATE_KEYS",
    "TERMINAL_AUTHORITY",
    "UNIVERSE_SCHEMA",
    "build_universe_manifest",
    "evaluate_pilot_go",
    "lead_key",
    "load_human_review_decisions",
    "validate_universe_manifest",
]
