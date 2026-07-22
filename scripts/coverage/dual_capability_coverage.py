#!/usr/bin/env python3
"""Canonical dual capability monitoring coverage (open_tenders / historical_contracts).

Fail-closed single spine for operational coverage gates. Separates:

* capability_monitoring_coverage(open_tenders)
* capability_monitoring_coverage(historical_contracts)
* data_presence(*) — descriptive only, never a coverage label
* freshness participation in the numerator
* legacy entity_coverage.is_covered / any_row — forbidden as coverage methods

Universe authority: ``scripts.lib.universe.load_canonical_universe``.
Applicability authority: config + optional DB matrix (never silent default applicable).
"""

from __future__ import annotations

# SQL fragments use fixed allowlists only (capability aliases / table names).
# Git sha stamp uses PATH-resolved git binary (optional metadata).
# ruff: noqa: S608,S603,S607
import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.coverage.states import CoverageState  # noqa: E402
from scripts.lib.universe import (  # noqa: E402
    CanonicalEntity,
    CanonicalUniverse,
    load_canonical_universe,
    resolve_default_seed_path,
)

ADAPTER_VERSION = "dual_capability_coverage/1.1.0"
GATE_THRESHOLD = 0.95

CAP_OPEN_TENDERS = "open_tenders"
CAP_HISTORICAL_CONTRACTS = "historical_contracts"
CAPABILITIES: tuple[str, ...] = (CAP_OPEN_TENDERS, CAP_HISTORICAL_CONTRACTS)

CAPABILITY_ALIASES: dict[str, str] = {
    CAP_OPEN_TENDERS: CAP_OPEN_TENDERS,
    CAP_HISTORICAL_CONTRACTS: CAP_HISTORICAL_CONTRACTS,
    "notices_or_bids": CAP_OPEN_TENDERS,
    "bids": CAP_OPEN_TENDERS,
    "editais": CAP_OPEN_TENDERS,
    "contracts": CAP_HISTORICAL_CONTRACTS,
    "historical_contracts": CAP_HISTORICAL_CONTRACTS,
    "contratos": CAP_HISTORICAL_CONTRACTS,
}

# Fallback required sources ONLY when matrix resolution is unavailable.
# Engine prefers applicability matrix / registry-driven required sets.
DEFAULT_REQUIRED_SOURCES: dict[str, tuple[str, ...]] = {
    CAP_OPEN_TENDERS: ("pncp",),
    CAP_HISTORICAL_CONTRACTS: ("pncp",),
}
# Backward-compatible alias used by tests / reports
REQUIRED_SOURCES = DEFAULT_REQUIRED_SOURCES

SLA_HOURS: dict[str, int] = {
    CAP_OPEN_TENDERS: 24,
    CAP_HISTORICAL_CONTRACTS: 24 * 7,
}

MIN_CONTRACT_BACKFILL_YEARS = 3

FORBIDDEN_METHODS = frozenset(
    {
        "entity_coverage.any_row",
        "entity_coverage.is_covered",
        "any_row",
        "is_covered_undifferentiated",
    }
)

DEFAULT_OUTPUT = _PROJECT_ROOT / "output" / "coverage"

ApplicabilityStatus = Literal["applicable", "not_applicable", "unknown", "blocked"]
RequirementRole = Literal["required", "complementary", "gap_fill", "informational"]
SchemaMode = Literal["modern", "legacy", "unknown"]
PresenceStatus = Literal[
    "table_absent",
    "query_failed",
    "column_absent",
    "no_rows",
    "rows_present",
    "unmapped_rows",
]
MappingStatus = Literal["ok", "partial", "fail", "identity_unresolved"]

# Textual/structural failure tokens for success_zero / success_with_data
_ERROR_TOKENS = (
    "403",
    "429",
    "500",
    "502",
    "503",
    "504",
    "5xx",
    "timeout",
    "schema error",
    "schema_error",
    "truncated",
    "partial",
    "rate limit",
    "rate_limit",
    "authentication error",
    "authentication_error",
    "permission denied",
    "permission_denied",
    "unauthorized",
    "forbidden",
)


class DualCoverageError(Exception):
    """Fail-closed calculation error (universe / set integrity / schema / identity)."""


def _safe_rollback(conn: Any) -> None:
    """Best-effort transaction rollback without silent swallow of programming errors."""
    if conn is None:
        return
    try:
        conn.rollback()
    except Exception as rollback_exc:  # noqa: BLE001 — connection already broken
        _ = rollback_exc


def _safe_close(conn: Any) -> None:
    if conn is None:
        return
    try:
        conn.close()
    except Exception as close_exc:  # noqa: BLE001
        _ = close_exc


@dataclass(frozen=True)
class UniverseIdentity:
    entity_count: int
    seed_path: str
    seed_sha256: str
    canonical_ids_sha256: str
    radius_km: float
    radius_rule: str
    as_of: str
    git_sha: str
    schema_version: str
    code_version: str = ADAPTER_VERSION
    entity_ids: tuple[str, ...] = field(default_factory=tuple)
    universe_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["entity_ids_sample"] = list(self.entity_ids[:5])
        d.pop("entity_ids", None)
        return d


@dataclass
class EvidenceObservation:
    """Normalized latest observation for entity×source×capability."""

    entity_id: str
    source: str
    capability: str
    state: str
    applicability: ApplicabilityStatus
    applicability_reason: str = ""
    run_id: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    pages_expected: int | None = None
    pages_processed: int | None = None
    records_fetched: int = 0
    records_persisted: int = 0
    queried_start: str | None = None
    queried_end: str | None = None
    freshness_status: str = "unknown"
    error_code: str = ""
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence_reference: str = ""


@dataclass
class ApplicabilityResolution:
    entity_id: str
    source: str
    capability: str
    applicability_status: ApplicabilityStatus
    requirement_role: RequirementRole
    justification: str
    validated_at: str
    evidence_reference: str
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EntityMappingMetrics:
    db_entities_seen: int = 0
    db_entities_mapped: int = 0
    db_entities_unmapped: int = 0
    unmapped_entity_ids_sample: list[str] = field(default_factory=list)
    mapping_coverage_pct: float = 0.0
    mapping_status: MappingStatus = "ok"
    ambiguous_cnpj8: list[str] = field(default_factory=list)
    identity_unresolved_count: int = 0
    db_id_to_entity_id: dict[int, str] = field(default_factory=dict)
    cnpj8_to_entity_id: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("db_id_to_entity_id", None)
        d.pop("cnpj8_to_entity_id", None)
        return d


@dataclass
class PresenceLoadResult:
    status: PresenceStatus
    entity_ids: set[str] = field(default_factory=set)
    unmapped_count: int = 0
    unmapped_sample: list[str] = field(default_factory=list)
    error: str | None = None
    table_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "entity_count": len(self.entity_ids),
            "unmapped_count": self.unmapped_count,
            "unmapped_sample": self.unmapped_sample[:10],
            "error": self.error,
            "table_name": self.table_name,
        }


@dataclass
class EntityCapabilityResult:
    entity_id: str
    entity_name: str
    capability: str
    applicability: ApplicabilityStatus
    covered: bool
    coverage_state: str
    required_sources: list[str]
    successful_sources: list[str]
    missing_sources: list[str]
    freshness_status: str
    last_success_at: str | None
    blocker: str
    next_action: str
    evidence_reference: str
    has_data_presence: bool = False
    applicability_justification: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CapabilityCoverageResult:
    capability: str
    universe_version: str
    universe_count: int
    applicable_denominator: int
    covered_numerator: int
    coverage_pct: float
    threshold: float
    gate_status: str  # PASS | FAIL | NOT_READY
    as_of: str
    freshness_sla: int
    fresh_count: int
    stale_count: int
    unknown_count: int  # applicability_unknown (compat alias)
    applicability_unknown_count: int
    applicability_blocked_count: int
    blocked_count: int  # source/coverage blocked among applicable
    partial_count: int
    success_zero_count: int
    success_with_data_count: int
    not_applicable_count: int
    pending_count: int
    never_checked_count: int
    error_count: int
    source_blocked_count: int
    identity_unresolved_count: int
    unmapped_evidence_count: int
    data_presence_numerator: int
    data_presence_pct: float
    source_combinations: list[str]
    limitations: list[str]
    git_sha: str
    schema_version: str
    measurement_success: bool
    coverage_gate_pass: bool
    method: str = "dual_capability_coverage"
    reconciliation_ok: bool = True
    reconciliation_errors: list[str] = field(default_factory=list)
    entities: list[EntityCapabilityResult] = field(default_factory=list)

    def to_summary_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("entities", None)
        return d


@dataclass
class DualCoverageReport:
    universe: UniverseIdentity
    capabilities: dict[str, CapabilityCoverageResult]
    measurement_success: bool
    coverage_gate_pass: bool
    pipeline_success: bool
    as_of: str
    limitations: list[str]
    legacy_metric: dict[str, Any] | None = None
    error: str | None = None
    mapping_metrics: dict[str, Any] | None = None
    presence_status: dict[str, Any] | None = None
    schema_compatibility_mode: SchemaMode = "unknown"
    unmapped_evidence_count: int = 0
    outsider_evidence_count: int = 0
    scope_complete: bool = False
    dual_gate_status: str = "NOT_EVALUATED"  # PASS | FAIL | NOT_EVALUATED | NOT_READY
    capabilities_evaluated: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_version": ADAPTER_VERSION,
            "as_of": self.as_of,
            "universe": self.universe.to_dict(),
            "capabilities": {k: v.to_summary_dict() for k, v in self.capabilities.items()},
            "measurement_success": self.measurement_success,
            "coverage_gate_pass": self.coverage_gate_pass,
            "pipeline_success": self.pipeline_success,
            "scope_complete": self.scope_complete,
            "dual_gate_status": self.dual_gate_status,
            "capabilities_evaluated": list(self.capabilities_evaluated),
            "limitations": self.limitations,
            "legacy_metric": self.legacy_metric,
            "error": self.error,
            "mapping_metrics": self.mapping_metrics,
            "presence_status": self.presence_status,
            "schema_compatibility_mode": self.schema_compatibility_mode,
            "unmapped_evidence_count": self.unmapped_evidence_count,
            "outsider_evidence_count": self.outsider_evidence_count,
            "forbidden_methods": sorted(FORBIDDEN_METHODS),
            "claims_forbidden": [
                "entity_coverage.any_row as coverage",
                "entity_coverage.is_covered as general coverage",
                "average of open_tenders and historical_contracts",
                "data_presence labeled as coverage",
                "legacy 214/1093=19.5791% as canonical dual coverage",
                "live 95% without dual-definition proof",
                "silent unmapped evidence as zero coverage",
                "fail-open schema/query errors as empty sets",
            ],
        }


def normalize_capability(name: str | None) -> str | None:
    if not name:
        return None
    return CAPABILITY_ALIASES.get(str(name).strip().lower())


def ordered_ids_sha256(entity_ids: Sequence[str]) -> str:
    payload = "\n".join(sorted(entity_ids)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def git_sha(project_root: Path | None = None) -> str:
    root = project_root or _PROJECT_ROOT
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=str(root),
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()[:40]
    except Exception:  # noqa: S110 — optional stamp
        return "unknown"
    return "unknown"


def schema_version_stamp(project_root: Path | None = None) -> str:
    root = project_root or _PROJECT_ROOT
    mig = root / "db" / "migrations"
    n = len(list(mig.glob("*.sql"))) if mig.is_dir() else 0
    return f"migrations_count={n}"


def universe_version_stamp(seed_sha256: str, ids_sha: str, count: int) -> str:
    return f"{seed_sha256[:12]}:{ids_sha[:12]}:{count}"


def build_universe_identity(
    universe: CanonicalUniverse,
    *,
    as_of: str | None = None,
    project_root: Path | None = None,
    expected_count: int | None = None,
    expected_seed_sha256: str | None = None,
    expected_canonical_ids_sha256: str | None = None,
    expected_universe_version: str | None = None,
) -> UniverseIdentity:
    included = universe.included
    ids = [e.entity_id for e in included]
    if len(ids) != len(set(ids)):
        raise DualCoverageError("duplicate entity_id in canonical universe included set")
    if expected_count is not None and len(ids) != expected_count:
        raise DualCoverageError(f"unexpected denominator: got {len(ids)} expected {expected_count}")
    if not ids:
        raise DualCoverageError("empty included universe")
    ids_sha = ordered_ids_sha256(ids)
    seed_sha = universe.seed_sha256 or ""
    if expected_seed_sha256 is not None and seed_sha != expected_seed_sha256:
        raise DualCoverageError(f"seed_sha256 mismatch: got={seed_sha} expected={expected_seed_sha256}")
    if expected_canonical_ids_sha256 is not None and ids_sha != expected_canonical_ids_sha256:
        raise DualCoverageError(
            f"canonical_ids_sha256 mismatch: got={ids_sha} expected={expected_canonical_ids_sha256}"
        )
    uver = universe_version_stamp(seed_sha, ids_sha, len(ids))
    if expected_universe_version is not None and uver != expected_universe_version:
        raise DualCoverageError(f"universe_version mismatch: got={uver} expected={expected_universe_version}")
    stamp_as_of = as_of or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return UniverseIdentity(
        entity_count=len(ids),
        seed_path=str(universe.seed_path),
        seed_sha256=seed_sha,
        canonical_ids_sha256=ids_sha,
        radius_km=float(universe.radius_km),
        radius_rule=(
            "seed column 'Raio 200km?': SIM = included, NAO = excluded; "
            "missing/unknown remains unresolved and is not in included set"
        ),
        as_of=stamp_as_of,
        git_sha=git_sha(project_root),
        schema_version=schema_version_stamp(project_root),
        entity_ids=tuple(sorted(ids)),
        universe_version=uver,
    )


def _blob_has_error_token(blob: str) -> str | None:
    low = blob.lower()
    for tok in _ERROR_TOKENS:
        if tok in low:
            return tok
    # bare HTTP status patterns
    if re.search(r"\b5\d{2}\b", low):
        return "5xx"
    return None


def observation_error_signal(obs: EvidenceObservation) -> str | None:
    """Detect failure signals in code, message, metadata, HTTP status."""
    parts = [
        str(obs.error_code or ""),
        str(obs.error_message or ""),
        str(obs.state or ""),
    ]
    meta = obs.metadata or {}
    for key in (
        "http_status",
        "status_code",
        "error",
        "errors",
        "page_errors",
        "completion_status",
        "message",
    ):
        if key in meta and meta[key] is not None:
            parts.append(str(meta[key]))
    # nested page errors list
    pe = meta.get("page_errors")
    if isinstance(pe, (list, tuple)):
        parts.extend(str(x) for x in pe)
    return _blob_has_error_token(" | ".join(parts))


def validate_success_zero(obs: EvidenceObservation) -> tuple[bool, str]:
    """Return (ok, reason). Only valid success_zero counts as coverage."""
    if obs.state != CoverageState.SUCCESS_ZERO.value and obs.state != "success_zero":
        return False, "not_success_zero"
    if obs.applicability != "applicable":
        return False, "not_applicable_query"
    if not obs.entity_id:
        return False, "missing_entity_id"
    if not obs.source:
        return False, "missing_source"
    if not obs.capability:
        return False, "missing_capability"
    if not obs.run_id:
        return False, "missing_run_id"
    if obs.started_at is None or obs.completed_at is None:
        return False, "missing_timestamps"
    if not obs.evidence_reference:
        return False, "missing_evidence_reference"
    if obs.records_fetched != 0:
        return False, "success_zero_with_fetched_records"
    if obs.records_persisted != 0:
        return False, "success_zero_with_persisted_records"

    sig = observation_error_signal(obs)
    if sig:
        return False, f"error_signal:{sig}"

    # pagination / completion proof — supports_zero_proof alone is insufficient
    meta = obs.metadata or {}
    if obs.pages_expected is not None and obs.pages_processed is not None:
        if obs.pages_processed < obs.pages_expected:
            return False, "pagination_incomplete"
        if obs.pages_expected <= 0:
            return False, "invalid_pages_expected"
    else:
        completion = str(meta.get("completion_rule") or meta.get("pagination_complete") or "").lower()
        if completion not in {"http_204_complete", "true", "pagination_complete", "1", "complete"}:
            return False, "missing_pagination_proof"
        # require provenance alongside completion claim
        if not meta.get("provenance") and not meta.get("evidence_persisted"):
            if not obs.evidence_reference:
                return False, "missing_provenance"
    # contracts require window
    if normalize_capability(obs.capability) == CAP_HISTORICAL_CONTRACTS:
        if not obs.queried_start or not obs.queried_end:
            return False, "missing_query_window"
    return True, "ok"


def validate_success_with_data(obs: EvidenceObservation) -> tuple[bool, str]:
    if obs.state not in {CoverageState.SUCCESS_WITH_DATA.value, "success_with_data"}:
        return False, "not_success_with_data"
    if obs.applicability != "applicable":
        return False, "not_applicable_query"
    if not obs.entity_id:
        return False, "missing_entity_id"
    if not obs.source:
        return False, "missing_source"
    if not obs.capability:
        return False, "missing_capability"
    if not obs.run_id:
        return False, "missing_run_id"
    if obs.started_at is None or obs.completed_at is None:
        return False, "missing_timestamps"
    if not obs.evidence_reference:
        return False, "missing_evidence_reference"

    sig = observation_error_signal(obs)
    if sig:
        return False, f"error_signal:{sig}"

    if obs.records_fetched <= 0:
        return False, "no_records_fetched"
    if obs.records_persisted <= 0:
        return False, "no_records_persisted"
    meta = obs.metadata or {}
    allow_persist_gt_fetch = bool(meta.get("allow_persisted_gt_fetched"))
    if obs.records_persisted > obs.records_fetched and not allow_persist_gt_fetch:
        return False, "persisted_exceeds_fetched"

    # pagination for tenders
    if normalize_capability(obs.capability) == CAP_OPEN_TENDERS:
        if obs.pages_expected is not None and obs.pages_processed is not None:
            if obs.pages_processed < obs.pages_expected:
                return False, "pagination_incomplete"
        else:
            completion = str(meta.get("completion_rule") or meta.get("pagination_complete") or "").lower()
            if completion not in {"http_204_complete", "true", "pagination_complete", "1", "complete"}:
                # still require either pages or explicit completion for full proof
                if not meta.get("snapshot_reconciled"):
                    return False, "missing_pagination_or_snapshot_proof"

    if normalize_capability(obs.capability) == CAP_HISTORICAL_CONTRACTS:
        if not obs.queried_start or not obs.queried_end:
            return False, "missing_query_window"

    if not meta.get("provenance") and not obs.evidence_reference:
        return False, "missing_provenance"
    return True, "ok"


def is_fresh_observation(
    obs: EvidenceObservation,
    capability: str,
    *,
    as_of: datetime,
) -> tuple[bool, str]:
    sla = SLA_HOURS[capability]
    explicit = (obs.freshness_status or "").lower()
    if explicit in {"stale", "unknown", "overdue", "never", "incomplete"}:
        return False, explicit or "unknown"
    if explicit == "fresh" and obs.completed_at is None:
        return False, "unknown"
    if obs.completed_at is None:
        return False, "unknown"
    completed = obs.completed_at
    if completed.tzinfo is None:
        completed = completed.replace(tzinfo=UTC)
    age = as_of - completed
    if age < timedelta(0):
        return False, "incomplete_future_timestamp"
    if age <= timedelta(hours=sla):
        return True, "fresh"
    return False, "stale"


def contracts_backfill_ok(obs: EvidenceObservation, *, as_of: datetime) -> bool:
    if not obs.queried_start or not obs.queried_end:
        return False
    try:
        start = datetime.fromisoformat(str(obs.queried_start)[:10]).replace(tzinfo=UTC)
        end = datetime.fromisoformat(str(obs.queried_end)[:10]).replace(tzinfo=UTC)
    except ValueError:
        return False
    if end < start:
        return False
    span_years = (end - start).days / 365.25
    if span_years + 1e-9 < MIN_CONTRACT_BACKFILL_YEARS:
        return False
    if as_of - end > timedelta(hours=SLA_HOURS[CAP_HISTORICAL_CONTRACTS]):
        return False
    return True


def observation_counts_as_covered(
    obs: EvidenceObservation,
    capability: str,
    *,
    as_of: datetime,
) -> tuple[bool, str, str]:
    state = obs.state
    if state in {
        CoverageState.BLOCKED.value,
        "blocked",
        CoverageState.PARTIAL.value,
        "partial",
        CoverageState.ERROR.value,
        "error",
        CoverageState.STALE.value,
        "stale",
        CoverageState.PENDING.value,
        "pending",
        "not_investigated",
        "never_checked",
    }:
        return False, state if state else "unknown", "unknown"

    fresh_ok, fresh_label = is_fresh_observation(obs, capability, as_of=as_of)
    if not fresh_ok:
        return False, "stale" if fresh_label == "stale" else state, fresh_label

    if state in {CoverageState.SUCCESS_ZERO.value, "success_zero"}:
        ok, reason = validate_success_zero(obs)
        if not ok:
            return False, "partial" if "pagination" in reason else "error", fresh_label
        if capability == CAP_HISTORICAL_CONTRACTS and not contracts_backfill_ok(obs, as_of=as_of):
            return False, "partial", fresh_label
        return True, "success_zero", fresh_label

    if state in {CoverageState.SUCCESS_WITH_DATA.value, "success_with_data"}:
        ok, reason = validate_success_with_data(obs)
        if not ok:
            return False, "partial", fresh_label
        if capability == CAP_HISTORICAL_CONTRACTS and not contracts_backfill_ok(obs, as_of=as_of):
            return False, "partial", fresh_label
        return True, "success_with_data", fresh_label

    return False, state or "unknown", fresh_label


# ---------------------------------------------------------------------------
# Applicability matrix (entity × source × capability)
# ---------------------------------------------------------------------------


def resolve_required_sources(
    capability: str,
    *,
    entity: CanonicalEntity | None = None,
    source_roles: Mapping[str, RequirementRole] | None = None,
) -> list[str]:
    """Resolve required sources for capability (optionally per-entity later)."""
    _ = entity  # reserved for per-entity overrides
    if source_roles:
        required = [s for s, role in source_roles.items() if role == "required"]
        if required:
            return required
    return list(DEFAULT_REQUIRED_SOURCES.get(capability, ("pncp",)))


def build_applicability_resolutions(
    universe: CanonicalUniverse,
    capabilities: Sequence[str],
    *,
    as_of: str,
    entity_applicability: Mapping[str, Mapping[str, ApplicabilityStatus]] | None = None,
    entity_required_sources: Mapping[str, Mapping[str, Sequence[str]]] | None = None,
    use_config_matrix: bool = True,
    project_root: Path | None = None,
) -> dict[str, dict[str, list[ApplicabilityResolution]]]:
    """cap → entity_id → list of per-source resolutions for required sources.

    When ``entity_applicability`` is provided (tests), it is authoritative per entity.
    Otherwise consult config/source_applicability.yaml via applicability_matrix helpers.
    Missing rule → unknown (never silent applicable).
    """
    root = project_root or _PROJECT_ROOT
    out: dict[str, dict[str, list[ApplicabilityResolution]]] = {c: {} for c in capabilities}

    cfg: dict[str, Any] = {}
    decide_fn = None
    if use_config_matrix and entity_applicability is None:
        try:
            from scripts.coverage.applicability_matrix import (  # type: ignore
                decide_for_entity_source,
                load_applicability_config,
            )

            cfg = load_applicability_config(root / "config" / "source_applicability.yaml")
            decide_fn = decide_for_entity_source
        except Exception:
            decide_fn = None
            cfg = {}

    for cap in capabilities:
        cap_n = normalize_capability(cap) or cap
        for ent in universe.included:
            overrides = (entity_required_sources or {}).get(cap_n, {}).get(ent.entity_id)
            required = list(overrides) if overrides else resolve_required_sources(cap_n, entity=ent)
            resolutions: list[ApplicabilityResolution] = []

            # Entity-level override (tests / pure inject)
            ent_app = None
            if entity_applicability is not None:
                ent_app = entity_applicability.get(cap_n, {}).get(ent.entity_id)

            for src in required:
                if ent_app is not None:
                    resolutions.append(
                        ApplicabilityResolution(
                            entity_id=ent.entity_id,
                            source=src,
                            capability=cap_n,
                            applicability_status=ent_app,
                            requirement_role="required",
                            justification="entity_applicability override",
                            validated_at=as_of,
                            evidence_reference="override:entity_applicability",
                            priority=100,
                        )
                    )
                    continue

                if decide_fn is not None:
                    entity_dict = {
                        "esfera": "municipal",
                        "natureza": (ent.natureza_juridica or "*").lower(),
                        "natureza_juridica": ent.natureza_juridica or "",
                        "municipio": ent.municipio or "",
                    }
                    try:
                        decision = decide_fn(
                            entity=entity_dict,
                            entity_id=ent.entity_id,
                            source_name=src,
                            capability=cap_n,  # type: ignore[arg-type]
                            cfg=cfg,
                            registry_role="required",
                            validated_at=as_of,
                        )
                        status: ApplicabilityStatus
                        if decision.decision == "applicable":
                            status = "applicable"
                        elif decision.decision == "not_applicable":
                            status = "not_applicable"
                        else:
                            status = "unknown"
                        resolutions.append(
                            ApplicabilityResolution(
                                entity_id=ent.entity_id,
                                source=src,
                                capability=cap_n,
                                applicability_status=status,
                                requirement_role="required",
                                justification=decision.justification,
                                validated_at=decision.validated_at,
                                evidence_reference=decision.decision_source,
                                priority=0,
                            )
                        )
                        continue
                    except Exception as exc:
                        resolutions.append(
                            ApplicabilityResolution(
                                entity_id=ent.entity_id,
                                source=src,
                                capability=cap_n,
                                applicability_status="unknown",
                                requirement_role="required",
                                justification=f"matrix_error:{exc}"[:200],
                                validated_at=as_of,
                                evidence_reference="matrix:error",
                                priority=0,
                            )
                        )
                        continue

                # No matrix / no override → unknown (never silent applicable)
                resolutions.append(
                    ApplicabilityResolution(
                        entity_id=ent.entity_id,
                        source=src,
                        capability=cap_n,
                        applicability_status="unknown",
                        requirement_role="required",
                        justification="no proven applicability rule for entity×source×capability",
                        validated_at=as_of,
                        evidence_reference="matrix:missing",
                        priority=0,
                    )
                )
            out[cap_n][ent.entity_id] = resolutions
    return out


def fold_entity_applicability(
    resolutions: Sequence[ApplicabilityResolution],
) -> tuple[ApplicabilityStatus, str, list[str]]:
    """Fold per-source required resolutions into entity×capability status."""
    if not resolutions:
        return "unknown", "no_required_sources_resolved", []
    required = [r for r in resolutions if r.requirement_role == "required"]
    if not required:
        required = list(resolutions)
    sources = [r.source for r in required]
    statuses = [r.applicability_status for r in required]
    if any(s == "blocked" for s in statuses):
        return "blocked", "required_source_blocked", sources
    if any(s == "unknown" for s in statuses):
        return "unknown", "required_source_unknown", sources
    if all(s == "not_applicable" for s in statuses):
        just = "; ".join(r.justification for r in required if r.justification)[:300]
        return "not_applicable", just or "all_required_not_applicable", sources
    if any(s == "not_applicable" for s in statuses) and any(s == "applicable" for s in statuses):
        # mixed required: blocked gate — incomplete definition
        return "unknown", "mixed_required_applicability", sources
    if all(s == "applicable" for s in statuses):
        return "applicable", "all_required_applicable", sources
    return "unknown", "unresolved_applicability", sources


def score_entity_capability(
    entity: CanonicalEntity,
    capability: str,
    observations: Mapping[str, EvidenceObservation],
    *,
    as_of: datetime,
    applicability: ApplicabilityStatus = "unknown",
    has_data_presence: bool = False,
    required_sources: Sequence[str] | None = None,
    applicability_justification: str = "",
) -> EntityCapabilityResult:
    required = list(required_sources or resolve_required_sources(capability, entity=entity))
    if applicability == "not_applicable":
        return EntityCapabilityResult(
            entity_id=entity.entity_id,
            entity_name=entity.razao_social,
            capability=capability,
            applicability=applicability,
            covered=False,
            coverage_state="not_applicable",
            required_sources=required,
            successful_sources=[],
            missing_sources=[],
            freshness_status="not_applicable",
            last_success_at=None,
            blocker="",
            next_action="none_not_applicable",
            evidence_reference="",
            has_data_presence=has_data_presence,
            applicability_justification=applicability_justification,
        )
    if applicability == "blocked":
        return EntityCapabilityResult(
            entity_id=entity.entity_id,
            entity_name=entity.razao_social,
            capability=capability,
            applicability=applicability,
            covered=False,
            coverage_state="blocked",
            required_sources=required,
            successful_sources=[],
            missing_sources=required,
            freshness_status="unknown",
            last_success_at=None,
            blocker="applicability_blocked",
            next_action="resolve_blocker",
            evidence_reference="",
            has_data_presence=has_data_presence,
            applicability_justification=applicability_justification,
        )
    if applicability == "unknown":
        return EntityCapabilityResult(
            entity_id=entity.entity_id,
            entity_name=entity.razao_social,
            capability=capability,
            applicability=applicability,
            covered=False,
            coverage_state="unknown",
            required_sources=required,
            successful_sources=[],
            missing_sources=required,
            freshness_status="unknown",
            last_success_at=None,
            blocker="applicability_unknown",
            next_action="resolve_applicability",
            evidence_reference="",
            has_data_presence=has_data_presence,
            applicability_justification=applicability_justification,
        )

    successful: list[str] = []
    missing: list[str] = []
    last_success: datetime | None = None
    evidence_refs: list[str] = []
    freshness_labels: list[str] = []
    states: list[str] = []
    blockers: list[str] = []

    for src in required:
        obs = observations.get(src)
        if obs is None:
            missing.append(src)
            states.append("never_checked")
            freshness_labels.append("never")
            blockers.append(f"no_evidence:{src}")
            continue
        # Observation applicability cannot silently upgrade entity fold, but can block
        if obs.applicability == "blocked":
            missing.append(src)
            states.append("blocked")
            freshness_labels.append("unknown")
            blockers.append(f"{src}:blocked")
            continue
        ok, st, fl = observation_counts_as_covered(obs, capability, as_of=as_of)
        states.append(st)
        freshness_labels.append(fl)
        evidence_refs.append(obs.evidence_reference or obs.run_id)
        if ok:
            successful.append(src)
            if obs.completed_at and (last_success is None or obs.completed_at > last_success):
                last_success = obs.completed_at
        else:
            missing.append(src)
            blockers.append(f"{src}:{st}:{fl}")

    covered = len(missing) == 0 and len(successful) == len(required) and len(required) > 0
    if covered:
        cov_state = "success_zero" if all(s == "success_zero" for s in states) else "success_with_data"
        next_action = "maintain"
        blocker = ""
    elif "blocked" in states:
        cov_state = "blocked"
        next_action = "unblock_source"
        blocker = ";".join(blockers)[:300]
    elif "error" in states:
        cov_state = "error"
        next_action = "fix_source_error"
        blocker = ";".join(blockers)[:300]
    elif "partial" in states:
        cov_state = "partial"
        next_action = "complete_pagination_or_window"
        blocker = ";".join(blockers)[:300]
    elif "stale" in freshness_labels or "stale" in states:
        cov_state = "stale"
        next_action = "refresh_within_sla"
        blocker = ";".join(blockers)[:300]
    elif all(s == "never_checked" for s in states) or not observations:
        cov_state = "never_checked"
        next_action = "run_required_sources"
        blocker = ";".join(blockers)[:300]
    else:
        cov_state = "pending"
        next_action = "run_required_sources"
        blocker = ";".join(blockers)[:300]

    if covered and all(f == "fresh" for f in freshness_labels):
        freshness_status = "fresh"
    elif "stale" in freshness_labels:
        freshness_status = "stale"
    elif not observations or all(f == "never" for f in freshness_labels):
        freshness_status = "never"
    else:
        freshness_status = freshness_labels[0] if freshness_labels else "unknown"

    return EntityCapabilityResult(
        entity_id=entity.entity_id,
        entity_name=entity.razao_social,
        capability=capability,
        applicability=applicability,
        covered=covered,
        coverage_state=cov_state,
        required_sources=required,
        successful_sources=successful,
        missing_sources=missing,
        freshness_status=freshness_status,
        last_success_at=last_success.isoformat().replace("+00:00", "Z") if last_success else None,
        blocker=blocker,
        next_action=next_action,
        evidence_reference=";".join(r for r in evidence_refs if r)[:500],
        has_data_presence=has_data_presence,
        applicability_justification=applicability_justification,
    )


def _mutual_exclusive_bucket(r: EntityCapabilityResult) -> str:
    """Map applicable entity to one exclusive coverage bucket for reconciliation."""
    if r.covered:
        return "covered"
    st = r.coverage_state
    if st == "stale" or r.freshness_status == "stale":
        return "stale"
    if st == "partial":
        return "partial"
    if st == "error":
        return "error"
    if st == "blocked" or r.applicability == "blocked":
        return "blocked"
    if st == "never_checked":
        return "never_checked"
    if st == "pending":
        return "pending"
    if st in {"success_with_data", "success_zero"} and not r.covered:
        # validated state but failed other gates (freshness etc.)
        if r.freshness_status == "stale":
            return "stale"
        return "partial"
    return "pending"


def aggregate_capability(
    capability: str,
    entities: Sequence[CanonicalEntity],
    results: Sequence[EntityCapabilityResult],
    identity: UniverseIdentity,
    *,
    limitations: list[str] | None = None,
    unmapped_evidence_count: int = 0,
    identity_unresolved_count: int = 0,
) -> CapabilityCoverageResult:
    universe_ids = set(identity.entity_ids)
    result_ids = {r.entity_id for r in results}

    if result_ids != universe_ids:
        missing = sorted(universe_ids - result_ids)[:5]
        extra = sorted(result_ids - universe_ids)[:5]
        if extra:
            raise DualCoverageError(f"entity_id_outside_canonical_universe: {extra}")
        if missing:
            raise DualCoverageError(f"result incomplete vs universe: missing={missing}")

    # evidence entity ids must ⊆ universe (already enforced by result set)
    covered_ids = {r.entity_id for r in results if r.covered}
    applicable_ids = {r.entity_id for r in results if r.applicability == "applicable"}
    if not covered_ids.issubset(applicable_ids):
        bad = sorted(covered_ids - applicable_ids)[:5]
        raise DualCoverageError(f"covered IDs outside A_C: {bad}")

    applicable = [r for r in results if r.applicability == "applicable"]
    covered = [r for r in applicable if r.covered]
    den = len(applicable)
    num = len(covered)
    if num > den:
        raise DualCoverageError(f"numerator {num} > denominator {den}")

    pct = round(100.0 * num / den, 4) if den else 0.0

    appl_unknown = sum(1 for r in results if r.applicability == "unknown")
    appl_blocked = sum(1 for r in results if r.applicability == "blocked")
    not_appl = sum(1 for r in results if r.applicability == "not_applicable")
    universe_count = len(results)

    recon_errors: list[str] = []
    if appl_unknown + appl_blocked + not_appl + den != universe_count:
        recon_errors.append(
            f"applicability_partition: appl={den} na={not_appl} unk={appl_unknown} "
            f"blk={appl_blocked} != universe={universe_count}"
        )

    buckets = {
        "covered": 0,
        "pending": 0,
        "stale": 0,
        "partial": 0,
        "error": 0,
        "blocked": 0,
        "never_checked": 0,
    }
    for r in applicable:
        buckets[_mutual_exclusive_bucket(r)] += 1
    bucket_sum = sum(buckets.values())
    if den and bucket_sum != den:
        recon_errors.append(f"applicable_partition: buckets={bucket_sum} != den={den} detail={buckets}")

    pending_n = buckets["pending"]
    never_n = buckets["never_checked"]
    stale_n = buckets["stale"]
    partial_n = buckets["partial"]
    error_n = buckets["error"]
    source_blocked_n = buckets["blocked"]

    # Gate: need den>0, coverage threshold, zero applicability unknown/blocked, recon ok
    gate_pass = (
        den > 0
        and (num / den) >= GATE_THRESHOLD
        and appl_unknown == 0
        and appl_blocked == 0
        and unmapped_evidence_count == 0
        and identity_unresolved_count == 0
        and not recon_errors
    )
    if den == 0:
        gate_status = "NOT_READY"
    elif gate_pass:
        gate_status = "PASS"
    else:
        gate_status = "FAIL"

    # Distinct required source combinations present in results
    combos = sorted({"+".join(r.required_sources) for r in results if r.required_sources})

    return CapabilityCoverageResult(
        capability=capability,
        universe_version=identity.universe_version
        or f"{identity.seed_sha256[:12]}:{identity.canonical_ids_sha256[:12]}:{identity.entity_count}",
        universe_count=universe_count,
        applicable_denominator=den,
        covered_numerator=num,
        coverage_pct=pct,
        threshold=GATE_THRESHOLD,
        gate_status=gate_status,
        as_of=identity.as_of,
        freshness_sla=SLA_HOURS[capability],
        fresh_count=sum(1 for r in applicable if r.freshness_status == "fresh"),
        stale_count=stale_n,
        unknown_count=appl_unknown,
        applicability_unknown_count=appl_unknown,
        applicability_blocked_count=appl_blocked,
        blocked_count=source_blocked_n,
        partial_count=partial_n,
        success_zero_count=sum(1 for r in covered if r.coverage_state == "success_zero"),
        success_with_data_count=sum(1 for r in covered if r.coverage_state == "success_with_data"),
        not_applicable_count=not_appl,
        pending_count=pending_n,
        never_checked_count=never_n,
        error_count=error_n,
        source_blocked_count=source_blocked_n,
        identity_unresolved_count=identity_unresolved_count,
        unmapped_evidence_count=unmapped_evidence_count,
        data_presence_numerator=sum(1 for r in applicable if r.has_data_presence),
        data_presence_pct=(round(100.0 * sum(1 for r in applicable if r.has_data_presence) / den, 4) if den else 0.0),
        source_combinations=combos or ["+".join(DEFAULT_REQUIRED_SOURCES.get(capability, ()))],
        limitations=list(limitations or []),
        git_sha=identity.git_sha,
        schema_version=identity.schema_version,
        measurement_success=True,
        coverage_gate_pass=gate_pass,
        reconciliation_ok=not recon_errors,
        reconciliation_errors=recon_errors,
        entities=list(results),
    )


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _classify_db_exception(exc: BaseException) -> str:
    """Classify DB/driver exceptions without swallowing them."""
    name = type(exc).__name__
    msg = str(exc).lower()
    # psycopg2 error codes
    pgcode = getattr(exc, "pgcode", None) or getattr(getattr(exc, "diag", None), "sqlstate", None)
    if pgcode == "42703" or "undefinedcolumn" in name.lower() or "column" in msg and "does not exist" in msg:
        return "column_absent"
    if pgcode == "42P01" or "undefinedtable" in name.lower() or "relation" in msg and "does not exist" in msg:
        return "table_absent"
    if pgcode in {"28000", "28P01"} or "password" in msg or "authentication" in msg:
        return "permission"
    if pgcode == "42501" or "permission denied" in msg:
        return "permission"
    if "could not connect" in msg or "connection refused" in msg or "timeout" in msg:
        return "connection"
    if "datatype" in msg or "invalid input" in msg:
        return "type_incompatible"
    return "query_failed"


def _is_legacy_column_absence(exc: BaseException) -> bool:
    """True only when missing columns are the dual modern set (capability/applicability/…)."""
    msg = str(exc).lower()
    modern_markers = ("capability", "applicability", "freshness_status", "pages_expected", "pages_processed")
    return any(m in msg for m in modern_markers) and (
        "does not exist" in msg or "undefinedcolumn" in type(exc).__name__.lower()
    )


def map_db_entities(
    conn: Any,
    universe: CanonicalUniverse,
) -> EntityMappingMetrics:
    """Map sc_public_entities.id → canonical entity_id.

    CNPJ root ambiguity is detected and **never** first-wins. Ambiguous roots are
    excluded from the map; affected entities are counted as identity_unresolved.
    Measurement may continue, but gates fail when unresolved identities remain
    (or when evidence cannot be mapped because of ambiguity).
    """
    # Build cnpj8 → entity_id; detect duplicates (no first-wins)
    cnpj8_to: dict[str, str] = {}
    ambiguous: set[str] = set()
    for ent in universe.included:
        root = (ent.cnpj8 or "").strip()
        if not root or len(root) < 8:
            continue
        root = root[:8]
        if root in cnpj8_to and cnpj8_to[root] != ent.entity_id:
            ambiguous.add(root)
        elif root not in ambiguous and root not in cnpj8_to:
            cnpj8_to[root] = ent.entity_id
        elif root in ambiguous:
            continue
    for root in ambiguous:
        cnpj8_to.pop(root, None)

    # Count entities whose cnpj8 is ambiguous (cannot resolve identity via root)
    unresolved_entities = 0
    for ent in universe.included:
        root = (ent.cnpj8 or "").strip()[:8]
        if root and root in ambiguous:
            unresolved_entities += 1

    metrics = EntityMappingMetrics(
        ambiguous_cnpj8=sorted(ambiguous)[:20],
        identity_unresolved_count=unresolved_entities,
        cnpj8_to_entity_id=dict(cnpj8_to),
    )
    if ambiguous:
        metrics.mapping_status = "identity_unresolved"
        # Do not raise here — publish unresolved state; gate will fail closed.

    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, LEFT(REGEXP_REPLACE(COALESCE(cnpj_8, cnpj, ''), '[^0-9]', '', 'g'), 8)
            FROM sc_public_entities
            WHERE is_active IS TRUE OR is_active IS NULL
            """
        )
        rows = cur.fetchall()
    except Exception as exc:
        kind = _classify_db_exception(exc)
        if kind == "column_absent":
            _safe_rollback(conn)
            # legacy schema: only cnpj_8
            try:
                cur.execute(
                    """
                    SELECT id, LEFT(REGEXP_REPLACE(COALESCE(cnpj_8, ''), '[^0-9]', '', 'g'), 8)
                    FROM sc_public_entities
                    """
                )
                rows = cur.fetchall()
            except Exception as exc2:
                _safe_rollback(conn)
                cur.close()
                raise DualCoverageError(f"map_db_entities query_failed: {exc2}") from exc2
        else:
            _safe_rollback(conn)
            cur.close()
            raise DualCoverageError(f"map_db_entities {kind}: {exc}") from exc

    unmapped: list[str] = []
    for db_id, cnpj8 in rows:
        metrics.db_entities_seen += 1
        root = str(cnpj8 or "")[:8]
        if root and root in cnpj8_to:
            metrics.db_id_to_entity_id[int(db_id)] = cnpj8_to[root]
            metrics.db_entities_mapped += 1
        else:
            metrics.db_entities_unmapped += 1
            unmapped.append(str(db_id))
    cur.close()
    metrics.unmapped_entity_ids_sample = unmapped[:20]
    metrics.mapping_coverage_pct = (
        round(100.0 * metrics.db_entities_mapped / metrics.db_entities_seen, 4) if metrics.db_entities_seen else 0.0
    )
    # identity_unresolved has priority over partial/ok (never lose the signal).
    if metrics.identity_unresolved_count > 0 or metrics.ambiguous_cnpj8:
        metrics.mapping_status = "identity_unresolved"
    elif metrics.db_entities_seen and metrics.db_entities_mapped == 0:
        metrics.mapping_status = "fail"
    elif metrics.db_entities_unmapped:
        metrics.mapping_status = "partial"
    else:
        metrics.mapping_status = "ok"
    return metrics


def load_observations_from_db(
    conn: Any,
    *,
    capability: str,
    cnpj8_to_entity_id: Mapping[str, str],
    db_id_to_entity_id: Mapping[int, str],
    universe_ids: set[str],
) -> tuple[dict[str, dict[str, EvidenceObservation]], SchemaMode, int, int]:
    """Return (entity→source→obs, schema_mode, unmapped_count, outsider_count).

    Fail-closed on unexpected schema/query errors. Legacy fallback only when
    modern columns are proven absent.
    """
    _ = cnpj8_to_entity_id  # reserved for alternate key paths
    cur = conn.cursor()
    # Prefer migration 058 canonical view; fall back to base table if absent.
    cur.execute(
        """
        SELECT 1 FROM information_schema.views
        WHERE table_schema = 'public' AND table_name = 'v_dual_capability_evidence_latest'
        """
    )
    evidence_relation = "v_dual_capability_evidence_latest" if cur.fetchone() else "coverage_evidence"
    aliases = [capability]
    if capability == CAP_OPEN_TENDERS:
        aliases.extend(["notices_or_bids", "bids", "editais"])
    else:
        aliases.extend(["contracts", "contratos", "historical_contracts"])
    placeholders = ",".join(["%s"] * len(aliases))
    schema_mode: SchemaMode = "modern"
    rows: list[Any]
    try:
        cur.execute(
            f"""
            SELECT DISTINCT ON (entity_id, source, COALESCE(capability, data_type))
                entity_id,
                source,
                COALESCE(capability, data_type) AS cap,
                state::text,
                COALESCE(applicability, 'unknown'),
                COALESCE(applicability_reason, ''),
                run_id,
                started_at,
                completed_at,
                pages_expected,
                pages_processed,
                COALESCE(count_obtained, 0),
                COALESCE(count_persisted, 0),
                queried_start::text,
                queried_end::text,
                COALESCE(freshness_status, 'unknown'),
                COALESCE(error_code, ''),
                COALESCE(error_message, ''),
                COALESCE(metadata, '{{}}'::jsonb),
                id
            FROM {evidence_relation}
            WHERE (
                capability IN ({placeholders})
                OR (capability IS NULL AND data_type IN ({placeholders}))
            )
            ORDER BY entity_id, source, COALESCE(capability, data_type), completed_at DESC NULLS LAST
            """,
            aliases + aliases,
        )
        rows = cur.fetchall()
        schema_mode = "modern"
    except Exception as exc:
        kind = _classify_db_exception(exc)
        _safe_rollback(conn)
        if kind == "column_absent" and _is_legacy_column_absence(exc):
            schema_mode = "legacy"
            data_types = ("bids",) if capability == CAP_OPEN_TENDERS else ("contracts",)
            ph = ",".join(["%s"] * len(data_types))
            try:
                cur.execute(
                    f"""
                    SELECT DISTINCT ON (entity_id, source, data_type)
                        entity_id, source, data_type, state::text,
                        'unknown', '', run_id, started_at, completed_at,
                        NULL, NULL,
                        COALESCE(count_obtained, 0), COALESCE(count_persisted, 0),
                        queried_start::text, queried_end::text,
                        'unknown', COALESCE(error_code, ''), COALESCE(error_message, ''),
                        COALESCE(metadata, '{{}}'::jsonb), id
                    FROM coverage_evidence
                    WHERE data_type IN ({ph})
                    ORDER BY entity_id, source, data_type, completed_at DESC NULLS LAST
                    """,
                    data_types,
                )
                rows = cur.fetchall()
            except Exception as exc2:
                _safe_rollback(conn)
                cur.close()
                raise DualCoverageError(
                    f"coverage_evidence legacy query failed: {_classify_db_exception(exc2)}: {exc2}"
                ) from exc2
        elif kind == "table_absent":
            cur.close()
            raise DualCoverageError("coverage_evidence table_absent") from exc
        else:
            cur.close()
            raise DualCoverageError(f"coverage_evidence {kind}: {exc}") from exc

    out: dict[str, dict[str, EvidenceObservation]] = defaultdict(dict)
    unmapped = 0
    outsider = 0
    for row in rows:
        (
            db_entity_id,
            source,
            cap_raw,
            state,
            appl,
            appl_reason,
            run_id,
            started_at,
            completed_at,
            pages_expected,
            pages_processed,
            count_obtained,
            count_persisted,
            q_start,
            q_end,
            freshness_status,
            error_code,
            error_message,
            metadata,
            evidence_id,
        ) = row
        canon_cap = normalize_capability(str(cap_raw)) or capability
        if canon_cap != capability:
            continue
        entity_key: str | None = None
        if db_entity_id is not None:
            try:
                entity_key = db_id_to_entity_id.get(int(db_entity_id))
            except (TypeError, ValueError):
                entity_key = None
        if entity_key is None:
            unmapped += 1
            continue
        if entity_key not in universe_ids:
            outsider += 1
            continue
        appl_norm: ApplicabilityStatus = "unknown"
        if str(appl).lower() in {"applicable", "not_applicable", "unknown", "blocked"}:
            appl_norm = str(appl).lower()  # type: ignore[assignment]
        meta = metadata if isinstance(metadata, dict) else {}
        out[entity_key][str(source).lower() if str(source).lower() == "pncp" else str(source)] = EvidenceObservation(
            entity_id=entity_key,
            source=str(source).lower() if str(source).lower() == "pncp" else str(source),
            capability=capability,
            state=str(state),
            applicability=appl_norm,
            applicability_reason=str(appl_reason or ""),
            run_id=str(run_id or ""),
            started_at=_parse_dt(started_at),
            completed_at=_parse_dt(completed_at),
            pages_expected=int(pages_expected) if pages_expected is not None else None,
            pages_processed=int(pages_processed) if pages_processed is not None else None,
            records_fetched=int(count_obtained or 0),
            records_persisted=int(count_persisted or 0),
            queried_start=q_start,
            queried_end=q_end,
            freshness_status=str(freshness_status or "unknown"),
            error_code=str(error_code or ""),
            error_message=str(error_message or ""),
            metadata=meta,
            evidence_reference=f"coverage_evidence:{evidence_id}",
        )
    cur.close()
    if unmapped > 0:
        raise DualCoverageError(f"unmapped_evidence_count={unmapped} (cannot drop evidence outside identity map)")
    if outsider > 0:
        raise DualCoverageError(f"entity_id_outside_canonical_universe: outsider_evidence_count={outsider}")
    return dict(out), schema_mode, unmapped, outsider


def load_data_presence(
    conn: Any,
    capability: str,
    db_id_to_entity_id: Mapping[int, str],
    universe_ids: set[str],
    *,
    cnpj8_to_entity_id: Mapping[str, str] | None = None,
) -> PresenceLoadResult:
    """Descriptive presence only — never coverage. Fail closed on query errors.

    Schema notes (Extra local datalake):
    * ``pncp_raw_bids`` uses ``matched_entity_id`` (not ``entity_id``) and ``orgao_cnpj``.
    * ``pncp_supplier_contracts`` uses ``orgao_cnpj_8`` / ``orgao_cnpj``.
    """
    cnpj8_to_entity_id = cnpj8_to_entity_id or {}
    cur = conn.cursor()
    table: str | None = None
    mode: Literal["db_id", "cnpj8"] = "db_id"
    try:
        if capability == CAP_OPEN_TENDERS:
            table = "pncp_raw_bids"
            cur.execute(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name=%s
                """,
                (table,),
            )
            if not cur.fetchone():
                cur.close()
                return PresenceLoadResult(status="table_absent", table_name=table, error="table_absent")
            # Prefer matched_entity_id; fall back to orgao_cnpj → cnpj8 map
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='pncp_raw_bids'
                  AND column_name IN ('matched_entity_id', 'entity_id', 'orgao_cnpj')
                """
            )
            cols = {r[0] for r in cur.fetchall()}
            if "matched_entity_id" in cols:
                cur.execute(
                    """
                    SELECT DISTINCT matched_entity_id FROM pncp_raw_bids
                    WHERE matched_entity_id IS NOT NULL
                    """
                )
                mode = "db_id"
            elif "entity_id" in cols:
                cur.execute(
                    """
                    SELECT DISTINCT entity_id FROM pncp_raw_bids
                    WHERE entity_id IS NOT NULL
                    """
                )
                mode = "db_id"
            elif "orgao_cnpj" in cols:
                cur.execute(
                    """
                    SELECT DISTINCT LEFT(REGEXP_REPLACE(COALESCE(orgao_cnpj, ''), '[^0-9]', '', 'g'), 8)
                    FROM pncp_raw_bids
                    WHERE orgao_cnpj IS NOT NULL AND orgao_cnpj <> ''
                    """
                )
                mode = "cnpj8"
            else:
                cur.close()
                return PresenceLoadResult(
                    status="column_absent",
                    table_name=table,
                    error="no matched_entity_id/entity_id/orgao_cnpj",
                )
        else:
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public'
                  AND table_name IN ('pncp_supplier_contracts', 'contracts', 'pncp_contracts')
                """
            )
            tables = [r[0] for r in cur.fetchall()]
            if not tables:
                cur.close()
                return PresenceLoadResult(
                    status="table_absent",
                    table_name=None,
                    error="no contracts table",
                )
            table = tables[0]
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name=%s
                  AND column_name IN ('entity_id', 'matched_entity_id', 'orgao_cnpj_8', 'orgao_cnpj')
                """,
                (table,),
            )
            cols = {r[0] for r in cur.fetchall()}
            if "matched_entity_id" in cols:
                cur.execute(f"SELECT DISTINCT matched_entity_id FROM {table} WHERE matched_entity_id IS NOT NULL")
                mode = "db_id"
            elif "entity_id" in cols:
                cur.execute(f"SELECT DISTINCT entity_id FROM {table} WHERE entity_id IS NOT NULL")
                mode = "db_id"
            elif "orgao_cnpj_8" in cols:
                cur.execute(
                    f"""
                    SELECT DISTINCT LEFT(REGEXP_REPLACE(COALESCE(orgao_cnpj_8, ''), '[^0-9]', '', 'g'), 8)
                    FROM {table}
                    WHERE orgao_cnpj_8 IS NOT NULL AND orgao_cnpj_8 <> ''
                    """
                )
                mode = "cnpj8"
            elif "orgao_cnpj" in cols:
                cur.execute(
                    f"""
                    SELECT DISTINCT LEFT(REGEXP_REPLACE(COALESCE(orgao_cnpj, ''), '[^0-9]', '', 'g'), 8)
                    FROM {table}
                    WHERE orgao_cnpj IS NOT NULL AND orgao_cnpj <> ''
                    """
                )
                mode = "cnpj8"
            else:
                cur.close()
                return PresenceLoadResult(
                    status="column_absent",
                    table_name=table,
                    error="no entity/cnpj identity column",
                )
        raw_keys = [r[0] for r in cur.fetchall()]
    except Exception as exc:
        kind = _classify_db_exception(exc)
        _safe_rollback(conn)
        cur.close()
        raise DualCoverageError(f"presence {capability} {kind}: {exc}") from exc

    present: set[str] = set()
    unmapped = 0
    unmapped_sample: list[str] = []
    outsider = 0
    for raw in raw_keys:
        if raw is None:
            continue
        key: str | None = None
        if mode == "db_id":
            try:
                key = db_id_to_entity_id.get(int(raw))
            except (TypeError, ValueError):
                key = None
        else:
            root = str(raw)[:8]
            key = cnpj8_to_entity_id.get(root)
        if key is None:
            unmapped += 1
            unmapped_sample.append(str(raw))
            continue
        if key not in universe_ids:
            outsider += 1
            continue
        present.add(key)
    cur.close()
    if outsider > 0:
        raise DualCoverageError(f"entity_id_outside_canonical_universe: presence outsider_count={outsider}")
    # Unmapped descriptive rows are reported; only fail measurement when we
    # cannot interpret presence at all. Partial unmapped keeps mapped set but
    # flags unmapped_rows (caller may fail_on_unmapped_presence).
    if unmapped > 0 and not present:
        return PresenceLoadResult(
            status="unmapped_rows",
            entity_ids=set(),
            unmapped_count=unmapped,
            unmapped_sample=unmapped_sample[:20],
            table_name=table,
            error=f"unmapped_rows={unmapped}",
        )
    if unmapped > 0:
        return PresenceLoadResult(
            status="unmapped_rows",
            entity_ids=present,
            unmapped_count=unmapped,
            unmapped_sample=unmapped_sample[:20],
            table_name=table,
            error=f"unmapped_rows={unmapped}",
        )
    if not present:
        return PresenceLoadResult(status="no_rows", entity_ids=set(), table_name=table)
    return PresenceLoadResult(status="rows_present", entity_ids=present, table_name=table)


def _assert_observation_universe_integrity(
    observations_by_cap: Mapping[str, Mapping[str, Mapping[str, EvidenceObservation]]],
    presence_by_cap: Mapping[str, set[str]],
    universe_ids: set[str],
) -> None:
    for cap, by_ent in observations_by_cap.items():
        for eid in by_ent:
            if eid not in universe_ids:
                raise DualCoverageError(f"entity_id_outside_canonical_universe: obs capability={cap} entity_id={eid}")
        for eid, by_src in by_ent.items():
            for src, obs in by_src.items():
                if obs.entity_id not in universe_ids:
                    raise DualCoverageError(f"entity_id_outside_canonical_universe: obs.entity_id={obs.entity_id}")
                if obs.entity_id != eid:
                    raise DualCoverageError(f"observation entity_id mismatch map_key={eid} obs={obs.entity_id}")
    for cap, ids in presence_by_cap.items():
        for eid in ids:
            if eid not in universe_ids:
                raise DualCoverageError(
                    f"entity_id_outside_canonical_universe: presence capability={cap} entity_id={eid}"
                )


def compute_dual_coverage(
    *,
    universe: CanonicalUniverse | None = None,
    seed_path: str | Path | None = None,
    conn: Any | None = None,
    dsn: str | None = None,
    capabilities: Sequence[str] = CAPABILITIES,
    project_root: Path | None = None,
    expected_denominator: int | None = None,
    expected_seed_sha256: str | None = None,
    expected_canonical_ids_sha256: str | None = None,
    expected_entity_count: int | None = None,
    expected_universe_version: str | None = None,
    as_of: datetime | None = None,
    observations_by_cap: Mapping[str, Mapping[str, Mapping[str, EvidenceObservation]]] | None = None,
    presence_by_cap: Mapping[str, set[str]] | None = None,
    entity_applicability: Mapping[str, Mapping[str, ApplicabilityStatus]] | None = None,
    entity_required_sources: Mapping[str, Mapping[str, Sequence[str]]] | None = None,
    include_legacy_stamp: bool = True,
    use_config_matrix: bool = True,
    fail_on_unmapped_presence: bool = True,
) -> DualCoverageReport:
    """Compute dual capability coverage. Pure when observations provided; else loads DB."""
    root = project_root or _PROJECT_ROOT
    as_of_dt = as_of or datetime.now(UTC)
    as_of_s = as_of_dt.isoformat().replace("+00:00", "Z")
    limitations: list[str] = [
        "Presence is descriptive and is never coverage.",
        "Complementary sources do not replace required source combinations.",
        "entity_coverage.is_covered / any_row are forbidden as coverage methods.",
        "Applicability without proven rule is unknown (never silent applicable).",
        "Gate PASS requires coverage>=95%, zero applicability unknown/blocked, zero unmapped evidence.",
    ]
    exp_count = expected_entity_count if expected_entity_count is not None else expected_denominator

    try:
        if universe is None:
            seed = Path(seed_path) if seed_path else resolve_default_seed_path(root)
            universe = load_canonical_universe(seed_path=seed)
        identity = build_universe_identity(
            universe,
            as_of=as_of_s,
            project_root=root,
            expected_count=exp_count,
            expected_seed_sha256=expected_seed_sha256,
            expected_canonical_ids_sha256=expected_canonical_ids_sha256,
            expected_universe_version=expected_universe_version,
        )
    except DualCoverageError as exc:
        empty_id = UniverseIdentity(
            entity_count=0,
            seed_path=str(seed_path or ""),
            seed_sha256="",
            canonical_ids_sha256="",
            radius_km=200.0,
            radius_rule="",
            as_of=as_of_s,
            git_sha=git_sha(root),
            schema_version=schema_version_stamp(root),
        )
        return DualCoverageReport(
            universe=empty_id,
            capabilities={},
            measurement_success=False,
            coverage_gate_pass=False,
            pipeline_success=False,
            as_of=as_of_s,
            limitations=limitations,
            error=str(exc),
        )
    except Exception as exc:
        empty_id = UniverseIdentity(
            entity_count=0,
            seed_path=str(seed_path or ""),
            seed_sha256="",
            canonical_ids_sha256="",
            radius_km=200.0,
            radius_rule="",
            as_of=as_of_s,
            git_sha=git_sha(root),
            schema_version=schema_version_stamp(root),
        )
        return DualCoverageReport(
            universe=empty_id,
            capabilities={},
            measurement_success=False,
            coverage_gate_pass=False,
            pipeline_success=False,
            as_of=as_of_s,
            limitations=limitations,
            error=str(exc)[:300],
        )

    universe_ids = set(identity.entity_ids)
    mapping_metrics: EntityMappingMetrics | None = None
    presence_status: dict[str, Any] = {}
    schema_mode: SchemaMode = "unknown"
    unmapped_evidence = 0
    outsider_evidence = 0
    legacy_metric = None

    owns_conn = False
    if observations_by_cap is None:
        if conn is None:
            if not dsn:
                raise DualCoverageError("dsn or conn or observations_by_cap required")
            import psycopg2

            try:
                conn = psycopg2.connect(dsn, connect_timeout=10)
            except Exception as exc:
                return DualCoverageReport(
                    universe=identity,
                    capabilities={},
                    measurement_success=False,
                    coverage_gate_pass=False,
                    pipeline_success=False,
                    as_of=as_of_s,
                    limitations=limitations,
                    error=f"connection: {exc}"[:300],
                )
            owns_conn = True
        if conn is None:
            raise DualCoverageError("connection is None")
        try:
            mapping_metrics = map_db_entities(conn, universe)
            obs_map: dict[str, dict[str, dict[str, EvidenceObservation]]] = {}
            pres_map: dict[str, set[str]] = {}
            modes: list[SchemaMode] = []
            for cap in capabilities:
                cap_n = normalize_capability(cap) or cap
                loaded, mode, unm, out_c = load_observations_from_db(
                    conn,
                    capability=cap_n,
                    cnpj8_to_entity_id=mapping_metrics.cnpj8_to_entity_id,
                    db_id_to_entity_id=mapping_metrics.db_id_to_entity_id,
                    universe_ids=universe_ids,
                )
                obs_map[cap_n] = loaded
                modes.append(mode)
                unmapped_evidence += unm
                outsider_evidence += out_c
                pres = load_data_presence(
                    conn,
                    cap_n,
                    mapping_metrics.db_id_to_entity_id,
                    universe_ids,
                    cnpj8_to_entity_id=mapping_metrics.cnpj8_to_entity_id,
                )
                presence_status[cap_n] = pres.to_dict()
                if pres.status in {"query_failed", "column_absent"}:
                    raise DualCoverageError(f"presence_load {cap_n}: {pres.status} {pres.error}")
                # Unmapped descriptive rows are not coverage; fail only when
                # every presence key is unmapped AND rows exist (cannot audit).
                if (
                    pres.status == "unmapped_rows"
                    and fail_on_unmapped_presence
                    and not pres.entity_ids
                    and pres.unmapped_count > 0
                ):
                    # still allow measurement with descriptive zero + limitation
                    limitations.append(
                        f"presence {cap_n}: all {pres.unmapped_count} rows unmapped "
                        f"(descriptive presence zero; not coverage)"
                    )
                # only no_rows / rows_present / table_absent (empty descriptive) may yield zero set
                if pres.status == "table_absent":
                    limitations.append(f"presence table_absent for {cap_n}: descriptive zero")
                    pres_map[cap_n] = set()
                else:
                    pres_map[cap_n] = set(pres.entity_ids)
            observations_by_cap = obs_map
            presence_by_cap = pres_map
            if modes and all(m == "legacy" for m in modes):
                schema_mode = "legacy"
                limitations.append("schema_compatibility_mode=legacy")
            elif modes and all(m == "modern" for m in modes):
                schema_mode = "modern"
            else:
                schema_mode = modes[0] if modes else "unknown"
            legacy_metric = _legacy_entity_coverage_stamp(conn) if include_legacy_stamp else None
        except DualCoverageError as exc:
            if owns_conn and conn is not None:
                conn.close()
            return DualCoverageReport(
                universe=identity,
                capabilities={},
                measurement_success=False,
                coverage_gate_pass=False,
                pipeline_success=False,
                as_of=as_of_s,
                limitations=limitations,
                mapping_metrics=mapping_metrics.to_dict() if mapping_metrics else None,
                presence_status=presence_status or None,
                schema_compatibility_mode=schema_mode,
                error=str(exc),
            )
        finally:
            if owns_conn and conn is not None:
                _safe_close(conn)
    else:
        if presence_by_cap is None:
            presence_by_cap = {}
        schema_mode = "modern"

    if observations_by_cap is None or presence_by_cap is None:
        raise DualCoverageError("observations_by_cap and presence_by_cap required after load")

    try:
        _assert_observation_universe_integrity(observations_by_cap, presence_by_cap, universe_ids)
    except DualCoverageError as exc:
        return DualCoverageReport(
            universe=identity,
            capabilities={},
            measurement_success=False,
            coverage_gate_pass=False,
            pipeline_success=False,
            as_of=as_of_s,
            limitations=limitations,
            mapping_metrics=mapping_metrics.to_dict() if mapping_metrics else None,
            presence_status=presence_status or None,
            schema_compatibility_mode=schema_mode,
            error=str(exc),
        )

    # Build applicability matrix actually consulted by engine
    appl_matrix = build_applicability_resolutions(
        universe,
        list(capabilities),
        as_of=as_of_s,
        entity_applicability=entity_applicability,
        entity_required_sources=entity_required_sources,
        use_config_matrix=use_config_matrix and entity_applicability is None,
        project_root=root,
    )

    caps_out: dict[str, CapabilityCoverageResult] = {}
    try:
        for cap in capabilities:
            cap_n = normalize_capability(cap) or cap
            if cap_n not in CAPABILITIES:
                raise DualCoverageError(f"unsupported capability: {cap}")
            entity_obs = observations_by_cap.get(cap_n, {})
            presence = presence_by_cap.get(cap_n, set())
            results: list[EntityCapabilityResult] = []
            for ent in universe.included:
                obs_for_ent = entity_obs.get(ent.entity_id, {})
                resolutions = list(appl_matrix.get(cap_n, {}).get(ent.entity_id, []))
                # Observation may refine fold ONLY for blocked / justified not_applicable.
                # Observation applicability=unknown must NOT remove an entity from A_C
                # (would inflate coverage % when DB defaults COALESCE to unknown).
                for src, o in obs_for_ent.items():
                    if o.applicability == "blocked":
                        resolutions.append(
                            ApplicabilityResolution(
                                entity_id=ent.entity_id,
                                source=src,
                                capability=cap_n,
                                applicability_status="blocked",
                                requirement_role="required"
                                if src in resolve_required_sources(cap_n, entity=ent)
                                else "informational",
                                justification=o.applicability_reason or "obs:blocked",
                                validated_at=as_of_s,
                                evidence_reference=o.evidence_reference or o.run_id,
                                priority=50,
                            )
                        )
                    elif o.applicability == "not_applicable" and o.applicability_reason:
                        resolutions.append(
                            ApplicabilityResolution(
                                entity_id=ent.entity_id,
                                source=src,
                                capability=cap_n,
                                applicability_status="not_applicable",
                                requirement_role="required"
                                if src in resolve_required_sources(cap_n, entity=ent)
                                else "informational",
                                justification=o.applicability_reason,
                                validated_at=as_of_s,
                                evidence_reference=o.evidence_reference or o.run_id,
                                priority=50,
                            )
                        )
                    # unknown on observation: ignore for A_C fold (stay matrix decision)
                appl, just, required = fold_entity_applicability(resolutions)
                # required sources from matrix resolutions
                req_sources = required or resolve_required_sources(cap_n, entity=ent)
                if entity_required_sources and ent.entity_id in entity_required_sources.get(cap_n, {}):
                    req_sources = list(entity_required_sources[cap_n][ent.entity_id])
                results.append(
                    score_entity_capability(
                        ent,
                        cap_n,
                        obs_for_ent,
                        as_of=as_of_dt,
                        applicability=appl,
                        has_data_presence=ent.entity_id in presence,
                        required_sources=req_sources,
                        applicability_justification=just,
                    )
                )
            caps_out[cap_n] = aggregate_capability(
                cap_n,
                universe.included,
                results,
                identity,
                limitations=limitations,
                unmapped_evidence_count=unmapped_evidence,
                identity_unresolved_count=(mapping_metrics.identity_unresolved_count if mapping_metrics else 0),
            )
            if not caps_out[cap_n].reconciliation_ok:
                raise DualCoverageError(f"reconciliation failed for {cap_n}: {caps_out[cap_n].reconciliation_errors}")
    except DualCoverageError as exc:
        return DualCoverageReport(
            universe=identity,
            capabilities=caps_out,
            measurement_success=False,
            coverage_gate_pass=False,
            pipeline_success=False,
            as_of=as_of_s,
            limitations=limitations,
            legacy_metric=legacy_metric,
            mapping_metrics=mapping_metrics.to_dict() if mapping_metrics else None,
            presence_status=presence_status or None,
            schema_compatibility_mode=schema_mode,
            unmapped_evidence_count=unmapped_evidence,
            outsider_evidence_count=outsider_evidence,
            error=str(exc),
        )

    evaluated = tuple(sorted(caps_out.keys()))
    scope_complete = set(CAPABILITIES).issubset(set(evaluated))
    identity_n = 0
    identity_bad = False
    if mapping_metrics is not None:
        identity_n = int(mapping_metrics.identity_unresolved_count or 0)
        identity_bad = identity_n > 0 or mapping_metrics.mapping_status == "identity_unresolved"
    measurement_ok = (
        (not identity_bad)
        and unmapped_evidence == 0
        and outsider_evidence == 0
        and all(c.reconciliation_ok for c in caps_out.values())
    )
    err_msg = None
    if identity_bad:
        amb = list(mapping_metrics.ambiguous_cnpj8[:5]) if mapping_metrics else []
        err_msg = f"identity_unresolved: count={identity_n} ambiguous_cnpj8={amb}"

    per_cap_gate = all(c.coverage_gate_pass for c in caps_out.values()) if caps_out else False
    if not scope_complete:
        dual_gate_status = "NOT_EVALUATED"
        coverage_gate_pass = False
        pipeline_success = False
        limitations = list(limitations) + [
            f"scope_complete=false evaluated={list(evaluated)}; dual pipeline not eligible"
        ]
    elif not measurement_ok:
        dual_gate_status = "NOT_READY"
        coverage_gate_pass = False
        pipeline_success = False
    elif per_cap_gate:
        dual_gate_status = "PASS"
        coverage_gate_pass = True
        pipeline_success = True
    else:
        dual_gate_status = "FAIL"
        coverage_gate_pass = False
        pipeline_success = False

    return DualCoverageReport(
        universe=identity,
        capabilities=caps_out,
        measurement_success=measurement_ok,
        coverage_gate_pass=coverage_gate_pass,
        pipeline_success=pipeline_success,
        as_of=as_of_s,
        limitations=limitations,
        legacy_metric=legacy_metric,
        mapping_metrics=mapping_metrics.to_dict() if mapping_metrics else None,
        presence_status=presence_status or None,
        schema_compatibility_mode=schema_mode,
        unmapped_evidence_count=unmapped_evidence,
        outsider_evidence_count=outsider_evidence,
        error=err_msg,
        scope_complete=scope_complete,
        dual_gate_status=dual_gate_status,
        capabilities_evaluated=evaluated,
    )


def _legacy_entity_coverage_stamp(conn: Any) -> dict[str, Any]:
    """Historical stamp only — never used as canonical coverage."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT count(DISTINCT entity_id) FROM entity_coverage WHERE is_covered IS TRUE")
        num_cov = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT count(DISTINCT entity_id) FROM entity_coverage")
        num_any = int(cur.fetchone()[0] or 0)
    except Exception as exc:
        _safe_rollback(conn)
        return {
            "status": "unavailable",
            "canonical": False,
            "note": f"legacy entity_coverage not readable: {_classify_db_exception(exc)}",
        }
    finally:
        cur.close()
    return {
        "status": "legacy_non_canonical",
        "canonical": False,
        "method_is_covered": num_cov,
        "method_any_row": num_any,
        "note": (
            "Superseded by dual_capability_coverage. "
            "Historical claim 214/1093=19.5791% used is_covered without set equality "
            "and without capability split. See ERRATA-19-5791.md."
        ),
        "forbidden_as_coverage": True,
    }


def write_reports(
    report: DualCoverageReport,
    output_dir: Path,
    *,
    capabilities: Sequence[str] | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    summary_path = output_dir / "dual-capability-coverage-summary.json"
    summary_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["summary"] = summary_path

    caps = list(capabilities or report.capabilities.keys())
    for cap in caps:
        result = report.capabilities.get(cap)
        if result is None:
            continue
        cap_json = output_dir / f"dual-coverage-{cap}.json"
        cap_json.write_text(
            json.dumps(result.to_summary_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        paths[f"{cap}_json"] = cap_json

        gaps_json = output_dir / f"dual-coverage-gaps-{cap}.json"
        all_rows = [e.to_dict() for e in result.entities]
        gaps_json.write_text(json.dumps(all_rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths[f"{cap}_gaps_json"] = gaps_json

        gaps_csv = output_dir / f"dual-coverage-gaps-{cap}.csv"
        fields = [
            "entity_id",
            "entity_name",
            "capability",
            "applicability",
            "applicability_justification",
            "covered",
            "coverage_state",
            "required_sources",
            "successful_sources",
            "missing_sources",
            "freshness_status",
            "last_success_at",
            "blocker",
            "next_action",
            "evidence_reference",
            "has_data_presence",
        ]
        with gaps_csv.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for row in all_rows:
                out = {k: row.get(k) for k in fields}
                for list_key in ("required_sources", "successful_sources", "missing_sources"):
                    val = out.get(list_key)
                    if isinstance(val, list):
                        out[list_key] = "|".join(val)
                w.writerow(out)
        paths[f"{cap}_gaps_csv"] = gaps_csv
    return paths


def assert_method_not_forbidden(method: str | None) -> None:
    if method and method in FORBIDDEN_METHODS:
        raise DualCoverageError(f"forbidden coverage method: {method}")


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Dual capability monitoring coverage (canonical)")
    p.add_argument(
        "--capability",
        choices=["open_tenders", "historical_contracts", "both"],
        default="both",
    )
    p.add_argument("--dsn", default=os.getenv("LOCAL_DATALAKE_DSN"))
    p.add_argument("--seed", default=None)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--expected-denominator", type=int, default=None)
    p.add_argument("--expected-entity-count", type=int, default=None)
    p.add_argument("--expected-seed-sha256", default=None)
    p.add_argument("--expected-canonical-ids-sha256", default=None)
    p.add_argument("--expected-universe-version", default=None)
    p.add_argument("--require-gate", action="store_true", help="Exit 2 if coverage gate fails")
    p.add_argument("--json-stdout", action="store_true")
    args = p.parse_args(list(argv) if argv is not None else None)

    caps: list[str]
    if args.capability == "both":
        caps = list(CAPABILITIES)
    else:
        caps = [args.capability]

    if not args.dsn:
        print("LOCAL_DATALAKE_DSN / --dsn required for live calculation", file=sys.stderr)
        return 1

    report = compute_dual_coverage(
        dsn=args.dsn,
        seed_path=args.seed,
        capabilities=caps,
        expected_denominator=args.expected_denominator,
        expected_entity_count=args.expected_entity_count,
        expected_seed_sha256=args.expected_seed_sha256,
        expected_canonical_ids_sha256=args.expected_canonical_ids_sha256,
        expected_universe_version=args.expected_universe_version,
    )
    paths = write_reports(report, args.output_dir, capabilities=caps)
    payload = report.to_dict()
    payload["artifact_paths"] = {k: str(v) for k, v in paths.items()}
    if args.json_stdout:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"measurement_success={report.measurement_success}")
        print(f"coverage_gate_pass={report.coverage_gate_pass}")
        print(f"schema_compatibility_mode={report.schema_compatibility_mode}")
        for cap, res in report.capabilities.items():
            print(
                f"{cap}: universe={res.universe_count} den={res.applicable_denominator} "
                f"num={res.covered_numerator} pct={res.coverage_pct} gate={res.gate_status} "
                f"presence={res.data_presence_pct} pending={res.pending_count} "
                f"never={res.never_checked_count} stale={res.stale_count} "
                f"unk={res.applicability_unknown_count} blocked={res.applicability_blocked_count} "
                f"error={res.error_count}"
            )
        print(f"summary={paths.get('summary')}")
        if report.error:
            print(f"error={report.error}", file=sys.stderr)

    if not report.measurement_success:
        return 1
    if args.require_gate and not report.coverage_gate_pass:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
