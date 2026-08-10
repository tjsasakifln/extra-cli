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

import hashlib
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

UNIVERSE_SCHEMA = "confenge.universe_manifest.v2"
GO_NO_GO_SCHEMA = "confenge.go_no_go.v2"

TARGET_CLASS_KEYS = (
    TARGET_CONFIRMED,
    TARGET_PROBABLE_RESEARCH,
    TARGET_OUT_OF_SCOPE,
    TARGET_INSUFFICIENT_EVIDENCE,
)

MINIMUM_HUMAN_REVIEWED = 20
MINIMUM_HUMAN_APPROVED = 10


def _nonnegative(value: Any) -> int:
    return max(0, int(value or 0))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_universe_manifest(
    *,
    observed_supplier_roots: int,
    materialized_roots: int,
    target_classes: dict[str, int],
    source_contract_rows: int,
    datalake_watermark: str,
    target_fit_version: str,
    database_snapshot: str | None = None,
    source_cdc_watermark: str | None = None,
    construction_commercial_roots: int | None = None,
    construction_commercial_derivation: str | None = None,
    query_sha256: str | None = None,
    classifier_sha256: str | None = None,
    full_scale: bool = True,
    truncated: bool = False,
    pagination_exhausted_normally: bool = True,
    unexplained_missing: int = 0,
    orphan_materialized_roots: int = 0,
    duplicate_cnpj_root: int = 0,
    invalid_cnpj_root: int = 0,
) -> dict[str, Any]:
    """Build a closed, versioned universe ledger from one atomic watermark.

    ``construction_commercial_roots`` is a measured classification result, not
    a configured target.  If the upstream full construction assessor does not
    provide it, CONFIRMED+PROBABLE is the conservative live derivation.
    """
    observed = _nonnegative(observed_supplier_roots)
    materialized = _nonnegative(materialized_roots)
    contracts = _nonnegative(source_contract_rows)
    classes = {key: _nonnegative(target_classes.get(key)) for key in TARGET_CLASS_KEYS}
    unknown_classes = sorted(set(target_classes) - set(TARGET_CLASS_KEYS))
    class_sum = sum(classes.values())
    commercial = (
        _nonnegative(construction_commercial_roots)
        if construction_commercial_roots is not None
        else classes[TARGET_CONFIRMED] + classes[TARGET_PROBABLE_RESEARCH]
    )
    watermark = str(datalake_watermark or "").strip()
    snapshot = str(database_snapshot or "").strip()
    cdc_watermark = str(source_cdc_watermark or "").strip()
    version = str(target_fit_version or "").strip()
    query_hash = str(query_sha256 or "").strip() or _sha256_text(
        "pncp_supplier_contracts:distinct-valid-fornecedor-cnpj-root:full-history:v2"
    )
    classifier_hash = str(classifier_sha256 or "").strip() or _sha256_text(version)

    invariants = {
        "positive_observed_supplier_universe": observed > 0,
        "source_contract_rows_cover_roots": contracts >= observed > 0,
        "class_sum_equals_observed_supplier_roots": class_sum == observed,
        "materialized_equals_observed_supplier_roots": materialized == observed,
        "commercial_universe_within_observed": 0 < commercial <= observed,
        "pagination_exhausted_normally": bool(pagination_exhausted_normally),
        "full_scale": bool(full_scale),
        "not_truncated": not bool(truncated),
        "unexplained_missing_eq_0": _nonnegative(unexplained_missing) == 0,
        "orphan_materialized_roots_eq_0": _nonnegative(orphan_materialized_roots) == 0,
        "duplicate_cnpj_root_eq_0": _nonnegative(duplicate_cnpj_root) == 0,
        "invalid_cnpj_root_eq_0": _nonnegative(invalid_cnpj_root) == 0,
        "single_watermark_present": bool(watermark),
        "atomic_database_snapshot_present": bool(snapshot) if full_scale else True,
        "classifier_version_present": bool(version),
        "no_unknown_target_classes": not unknown_classes,
    }
    return {
        "schema": UNIVERSE_SCHEMA,
        "datalake_watermark": watermark or None,
        "database_snapshot": snapshot or None,
        "source_cdc_watermark": cdc_watermark or None,
        "source_contract_rows": contracts,
        "observed_supplier_roots": observed,
        "construction_commercial_roots": commercial,
        "construction_commercial_derivation": (
            str(construction_commercial_derivation or "").strip()
            or (
                "caller_measured"
                if construction_commercial_roots is not None
                else "TARGET_CONFIRMED+TARGET_PROBABLE_RESEARCH"
            )
        ),
        "materialized_roots": materialized,
        "target_classes": classes,
        "target_class_sum": class_sum,
        "unknown_target_classes": unknown_classes,
        "target_fit_version": version or None,
        "query_sha256": query_hash,
        "classifier_sha256": classifier_hash,
        "full_scale": bool(full_scale),
        "truncated": bool(truncated),
        "pagination_exhausted_normally": bool(pagination_exhausted_normally),
        "unexplained_missing": _nonnegative(unexplained_missing),
        "orphan_materialized_roots": _nonnegative(orphan_materialized_roots),
        "duplicate_cnpj_root": _nonnegative(duplicate_cnpj_root),
        "invalid_cnpj_root": _nonnegative(invalid_cnpj_root),
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
    """Return fail-closed violations for a universe-manifest v2 document."""
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
    if not manifest.get("query_sha256") or not manifest.get("classifier_sha256"):
        errors.append("lineage_hash_missing")
    return errors


def lead_key(row: dict[str, Any]) -> str:
    root = "".join(
        ch
        for ch in str(row.get("cnpj_raiz") or row.get("cnpj_root") or row.get("CNPJ") or row.get("cnpj") or "")
        if ch.isdigit()
    )[:8]
    email = str(row.get("email") or "").strip().lower()
    return f"{root}|{email}" if root else ""


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
    historical_rows = 0
    if path and path.is_file():
        for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            historical_rows += 1
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                errors.append(f"line_{line_no}:invalid_json")
                continue
            if not isinstance(row, dict):
                errors.append(f"line_{line_no}:not_object")
                continue
            key = lead_key(row)
            status = str(row.get("review_status") or row.get("status") or "").upper()
            reviewer = str(row.get("reviewer") or "").strip()
            if not key:
                errors.append(f"line_{line_no}:lead_key_missing")
                continue
            if status not in {HUMAN_REVIEW_APPROVED, HUMAN_REVIEW_REJECTED}:
                # SKIP/PENDING is useful history but never a completed review.
                continue
            if is_forbidden_reviewer(reviewer):
                errors.append(f"line_{line_no}:forbidden_or_missing_reviewer")
                continue
            if not row.get("reviewed_at") or not row.get("evidence_inspected"):
                errors.append(f"line_{line_no}:attribution_incomplete")
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
        and not bool(human_review.get("errors"))
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
    "UNIVERSE_SCHEMA",
    "build_universe_manifest",
    "evaluate_pilot_go",
    "lead_key",
    "load_human_review_decisions",
    "validate_universe_manifest",
]
