#!/usr/bin/env python3
"""Canonical dual capability monitoring coverage (open_tenders / historical_contracts).

This module is the single spine for operational coverage gates. It deliberately
separates:

* capability_monitoring_coverage(open_tenders)
* capability_monitoring_coverage(historical_contracts)
* data_presence(*)  — descriptive only, never a coverage label
* freshness participation in the numerator
* legacy entity_coverage.is_covered / any_row — forbidden as coverage methods

Universe authority: ``scripts.lib.universe.load_canonical_universe``.
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

ADAPTER_VERSION = "dual_capability_coverage/1.0.0"
GATE_THRESHOLD = 0.95

CAP_OPEN_TENDERS = "open_tenders"
CAP_HISTORICAL_CONTRACTS = "historical_contracts"
CAPABILITIES: tuple[str, ...] = (CAP_OPEN_TENDERS, CAP_HISTORICAL_CONTRACTS)

# Map freshness/registry aliases → canonical gate names
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

# Minimal required source combination per capability (all must pass).
# Complementary sources never silently replace required ones.
REQUIRED_SOURCES: dict[str, tuple[str, ...]] = {
    CAP_OPEN_TENDERS: ("pncp",),
    CAP_HISTORICAL_CONTRACTS: ("pncp",),
}

# SLA for freshness to count in numerator
SLA_HOURS: dict[str, int] = {
    CAP_OPEN_TENDERS: 24,
    CAP_HISTORICAL_CONTRACTS: 24 * 7,  # incremental ≤7d
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
CoverageStateName = str


class DualCoverageError(Exception):
    """Fail-closed calculation error (universe / set integrity)."""


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
class EntityCapabilityResult:
    entity_id: str
    entity_name: str
    capability: str
    applicability: ApplicabilityStatus
    covered: bool
    coverage_state: CoverageStateName
    required_sources: list[str]
    successful_sources: list[str]
    missing_sources: list[str]
    freshness_status: str
    last_success_at: str | None
    blocker: str
    next_action: str
    evidence_reference: str
    has_data_presence: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CapabilityCoverageResult:
    capability: str
    universe_version: str
    applicable_denominator: int
    covered_numerator: int
    coverage_pct: float
    threshold: float
    gate_status: str  # PASS | FAIL | NOT_READY
    as_of: str
    freshness_sla: int
    fresh_count: int
    stale_count: int
    unknown_count: int
    blocked_count: int
    partial_count: int
    success_zero_count: int
    success_with_data_count: int
    not_applicable_count: int
    data_presence_numerator: int
    data_presence_pct: float
    source_combinations: list[str]
    limitations: list[str]
    git_sha: str
    schema_version: str
    measurement_success: bool
    coverage_gate_pass: bool
    method: str = "dual_capability_coverage"
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
    coverage_gate_pass: bool  # both gates pass
    pipeline_success: bool
    as_of: str
    limitations: list[str]
    legacy_metric: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_version": ADAPTER_VERSION,
            "as_of": self.as_of,
            "universe": self.universe.to_dict(),
            "capabilities": {k: v.to_summary_dict() for k, v in self.capabilities.items()},
            "measurement_success": self.measurement_success,
            "coverage_gate_pass": self.coverage_gate_pass,
            "pipeline_success": self.pipeline_success,
            "limitations": self.limitations,
            "legacy_metric": self.legacy_metric,
            "error": self.error,
            "forbidden_methods": sorted(FORBIDDEN_METHODS),
            "claims_forbidden": [
                "entity_coverage.any_row as coverage",
                "entity_coverage.is_covered as general coverage",
                "average of open_tenders and historical_contracts",
                "data_presence labeled as coverage",
                "legacy 214/1093=19.5791% as canonical dual coverage",
                "live 95% without dual-definition proof",
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
        r = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=str(root),
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()[:40]
    except Exception:  # noqa: S110 — git metadata is optional for coverage stamps
        return "unknown"
    return "unknown"


def schema_version_stamp(project_root: Path | None = None) -> str:
    root = project_root or _PROJECT_ROOT
    mig = root / "db" / "migrations"
    n = len(list(mig.glob("*.sql"))) if mig.is_dir() else 0
    return f"migrations_count={n}"


def build_universe_identity(
    universe: CanonicalUniverse,
    *,
    as_of: str | None = None,
    project_root: Path | None = None,
    expected_count: int | None = None,
) -> UniverseIdentity:
    included = universe.included
    ids = [e.entity_id for e in included]
    if len(ids) != len(set(ids)):
        raise DualCoverageError("duplicate entity_id in canonical universe included set")
    if expected_count is not None and len(ids) != expected_count:
        raise DualCoverageError(f"unexpected denominator: got {len(ids)} expected {expected_count}")
    if not ids:
        raise DualCoverageError("empty included universe")
    stamp_as_of = as_of or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return UniverseIdentity(
        entity_count=len(ids),
        seed_path=str(universe.seed_path),
        seed_sha256=universe.seed_sha256,
        canonical_ids_sha256=ordered_ids_sha256(ids),
        radius_km=float(universe.radius_km),
        radius_rule=(
            "seed column 'Raio 200km?': SIM = included, NAO = excluded; "
            "missing/unknown remains unresolved and is not in included set"
        ),
        as_of=stamp_as_of,
        git_sha=git_sha(project_root),
        schema_version=schema_version_stamp(project_root),
        entity_ids=tuple(sorted(ids)),
    )


def validate_success_zero(obs: EvidenceObservation) -> tuple[bool, str]:
    """Return (ok, reason). Only valid success_zero counts as coverage."""
    if obs.state != CoverageState.SUCCESS_ZERO.value and obs.state != "success_zero":
        return False, "not_success_zero"
    if obs.applicability != "applicable":
        return False, "not_applicable_query"
    if not obs.run_id:
        return False, "missing_run_id"
    if obs.started_at is None or obs.completed_at is None:
        return False, "missing_timestamps"
    if obs.error_code or (obs.error_message and "timeout" in obs.error_message.lower()):
        code = (obs.error_code or "").lower()
        if any(x in code for x in ("403", "429", "5", "timeout", "schema")):
            return False, f"error_code:{obs.error_code}"
    # pagination proof
    if obs.pages_expected is not None and obs.pages_processed is not None:
        if obs.pages_processed < obs.pages_expected:
            return False, "pagination_incomplete"
    else:
        # Without pagination numbers, require explicit completion metadata
        meta = obs.metadata or {}
        completion = str(meta.get("completion_rule") or meta.get("pagination_complete") or "")
        if completion not in {"http_204_complete", "true", "pagination_complete", "1"}:
            if not meta.get("supports_zero_proof"):
                return False, "missing_pagination_proof"
    if obs.records_fetched > 0:
        return False, "success_zero_with_records"
    return True, "ok"


def validate_success_with_data(obs: EvidenceObservation) -> tuple[bool, str]:
    if obs.state not in {CoverageState.SUCCESS_WITH_DATA.value, "success_with_data"}:
        return False, "not_success_with_data"
    if obs.applicability != "applicable":
        return False, "not_applicable_query"
    if not obs.run_id:
        return False, "missing_run_id"
    if obs.completed_at is None:
        return False, "missing_completed_at"
    if obs.records_persisted <= 0 and obs.records_fetched <= 0:
        return False, "no_records"
    return True, "ok"


def is_fresh_observation(
    obs: EvidenceObservation,
    capability: str,
    *,
    as_of: datetime,
) -> tuple[bool, str]:
    """Freshness must participate in numerator — stale/unknown never covered."""
    sla = SLA_HOURS[capability]
    explicit = (obs.freshness_status or "").lower()
    if explicit in {"stale", "unknown", "overdue", "never", "incomplete"}:
        return False, explicit or "unknown"
    if explicit == "fresh":
        # still verify clock when completed_at present
        if obs.completed_at is None:
            return True, "fresh"
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
    """historical_contracts requires ≥3y window proof when period is present."""
    if not obs.queried_start or not obs.queried_end:
        # without window proof, cannot claim full backfill coverage
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
    # end should be recent relative to as_of (within incremental SLA)
    if as_of - end > timedelta(hours=SLA_HOURS[CAP_HISTORICAL_CONTRACTS]):
        return False
    return True


def observation_counts_as_covered(
    obs: EvidenceObservation,
    capability: str,
    *,
    as_of: datetime,
) -> tuple[bool, str, str]:
    """Return (covered, coverage_state, freshness_label)."""
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
    }:
        return False, state if state else "unknown", "unknown"

    fresh_ok, fresh_label = is_fresh_observation(obs, capability, as_of=as_of)
    if not fresh_ok:
        return False, "stale" if fresh_label == "stale" else state, fresh_label

    if state in {CoverageState.SUCCESS_ZERO.value, "success_zero"}:
        ok, reason = validate_success_zero(obs)
        if not ok:
            return False, "partial" if "pagination" in reason else "unknown", fresh_label
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


def score_entity_capability(
    entity: CanonicalEntity,
    capability: str,
    observations: Mapping[str, EvidenceObservation],
    *,
    as_of: datetime,
    applicability: ApplicabilityStatus = "applicable",
    has_data_presence: bool = False,
) -> EntityCapabilityResult:
    required = list(REQUIRED_SOURCES[capability])
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
            states.append("pending")
            freshness_labels.append("never")
            blockers.append(f"no_evidence:{src}")
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

    covered = len(missing) == 0 and len(successful) == len(required)
    # overall state
    if covered:
        cov_state = "success_zero" if all(s == "success_zero" for s in states) else "success_with_data"
        next_action = "maintain"
        blocker = ""
    elif "blocked" in states:
        cov_state = "blocked"
        next_action = "unblock_source"
        blocker = ";".join(blockers)[:300]
    elif "partial" in states:
        cov_state = "partial"
        next_action = "complete_pagination_or_window"
        blocker = ";".join(blockers)[:300]
    elif "stale" in freshness_labels or "stale" in states:
        cov_state = "stale"
        next_action = "refresh_within_sla"
        blocker = ";".join(blockers)[:300]
    else:
        # Missing evidence is pending/never — not applicability-unknown.
        cov_state = states[0] if states else "pending"
        next_action = "run_required_sources"
        blocker = ";".join(blockers)[:300]

    # freshness aggregate: only fresh if all successful and labels fresh
    if covered and all(f == "fresh" for f in freshness_labels):
        freshness_status = "fresh"
    elif "stale" in freshness_labels:
        freshness_status = "stale"
    elif not observations:
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
    )


def aggregate_capability(
    capability: str,
    entities: Sequence[CanonicalEntity],
    results: Sequence[EntityCapabilityResult],
    identity: UniverseIdentity,
    *,
    limitations: list[str] | None = None,
) -> CapabilityCoverageResult:
    # Set equality: every result entity_id must be in universe
    universe_ids = set(identity.entity_ids)
    result_ids = {r.entity_id for r in results}
    if not result_ids.issubset(universe_ids):
        extra = sorted(result_ids - universe_ids)[:5]
        raise DualCoverageError(f"numerator/result IDs outside universe: {extra}")

    applicable = [r for r in results if r.applicability == "applicable"]
    covered = [r for r in applicable if r.covered]
    den = len(applicable)
    num = len(covered)
    if num > den:
        raise DualCoverageError(f"numerator {num} > denominator {den}")

    pct = round(100.0 * num / den, 4) if den else 0.0
    gate_pass = den > 0 and (num / den) >= GATE_THRESHOLD
    # unknowns / blocked remain visible and prevent silent READY if any unknown
    # Applicability-unknown / blocked remain visible and block silent PASS.
    unknown_n = sum(1 for r in results if r.applicability == "unknown")
    blocked_n = sum(1 for r in results if r.applicability == "blocked" or r.coverage_state == "blocked")
    if unknown_n > 0 and gate_pass:
        # unknown applicability must not disappear from the gate
        gate_pass = False
    gate_status = "PASS" if gate_pass else ("FAIL" if den > 0 else "NOT_READY")

    return CapabilityCoverageResult(
        capability=capability,
        universe_version=f"{identity.seed_sha256[:12]}:{identity.canonical_ids_sha256[:12]}:{identity.entity_count}",
        applicable_denominator=den,
        covered_numerator=num,
        coverage_pct=pct,
        threshold=GATE_THRESHOLD,
        gate_status=gate_status,
        as_of=identity.as_of,
        freshness_sla=SLA_HOURS[capability],
        fresh_count=sum(1 for r in applicable if r.freshness_status == "fresh"),
        stale_count=sum(1 for r in applicable if r.freshness_status == "stale"),
        unknown_count=unknown_n,
        blocked_count=blocked_n,
        partial_count=sum(1 for r in applicable if r.coverage_state == "partial"),
        success_zero_count=sum(1 for r in covered if r.coverage_state == "success_zero"),
        success_with_data_count=sum(1 for r in covered if r.coverage_state == "success_with_data"),
        not_applicable_count=sum(1 for r in results if r.applicability == "not_applicable"),
        data_presence_numerator=sum(1 for r in applicable if r.has_data_presence),
        data_presence_pct=round(100.0 * sum(1 for r in applicable if r.has_data_presence) / den, 4) if den else 0.0,
        source_combinations=["+".join(REQUIRED_SOURCES[capability])],
        limitations=list(limitations or []),
        git_sha=identity.git_sha,
        schema_version=identity.schema_version,
        measurement_success=True,
        coverage_gate_pass=gate_pass,
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


def load_observations_from_db(
    conn: Any,
    *,
    capability: str,
    cnpj8_to_entity_id: Mapping[str, str],
    db_id_to_entity_id: Mapping[int, str],
) -> dict[str, dict[str, EvidenceObservation]]:
    """Return entity_id -> source -> latest observation for capability."""
    cur = conn.cursor()
    # Prefer capability column; fall back to data_type mapping
    aliases = [capability]
    if capability == CAP_OPEN_TENDERS:
        aliases.extend(["notices_or_bids", "bids", "editais"])
    else:
        aliases.extend(["contracts", "contratos", "historical_contracts"])
    placeholders = ",".join(["%s"] * len(aliases))
    try:
        cur.execute(  # noqa: S608
            f"""
            SELECT DISTINCT ON (entity_id, source, COALESCE(capability, data_type))
                entity_id,
                source,
                COALESCE(capability, data_type) AS cap,
                state::text,
                COALESCE(applicability, 'applicable'),
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
            FROM coverage_evidence
            WHERE (
                capability IN ({placeholders})
                OR (capability IS NULL AND data_type IN ({placeholders}))
            )
            ORDER BY entity_id, source, COALESCE(capability, data_type), completed_at DESC NULLS LAST
            """,
            aliases + aliases,
        )
        rows = cur.fetchall()
    except Exception:
        # Older schema without capability columns
        conn.rollback()
        data_types = ("bids",) if capability == CAP_OPEN_TENDERS else ("contracts",)
        ph = ",".join(["%s"] * len(data_types))
        cur.execute(  # noqa: S608
            f"""
            SELECT DISTINCT ON (entity_id, source, data_type)
                entity_id, source, data_type, state::text,
                'applicable', '', run_id, started_at, completed_at,
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

    out: dict[str, dict[str, EvidenceObservation]] = defaultdict(dict)
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
        if db_entity_id is not None and int(db_entity_id) in db_id_to_entity_id:
            entity_key = db_id_to_entity_id[int(db_entity_id)]
        if entity_key is None:
            # skip unmapped — cannot silently count outside universe
            continue
        appl_norm: ApplicabilityStatus = "applicable"
        if str(appl).lower() in {"applicable", "not_applicable", "unknown", "blocked"}:
            appl_norm = str(appl).lower()  # type: ignore[assignment]
        meta = metadata if isinstance(metadata, dict) else {}
        out[entity_key][str(source)] = EvidenceObservation(
            entity_id=entity_key,
            source=str(source),
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
    return out


def load_data_presence(
    conn: Any,
    capability: str,
    db_id_to_entity_id: Mapping[int, str],
) -> set[str]:
    """Descriptive presence only — never coverage."""
    cur = conn.cursor()
    present: set[str] = set()
    try:
        if capability == CAP_OPEN_TENDERS:
            cur.execute(
                """
                SELECT DISTINCT entity_id FROM pncp_raw_bids
                WHERE entity_id IS NOT NULL
                """
            )
        else:
            # contracts tables vary by schema
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
                return present
            table = tables[0]
            # try entity_id column
            cur.execute(  # noqa: S608 — table from fixed allowlist only
                f"SELECT DISTINCT entity_id FROM {table} WHERE entity_id IS NOT NULL"
            )
        for (db_id,) in cur.fetchall():
            if db_id is None:
                continue
            try:
                key = db_id_to_entity_id.get(int(db_id))
            except (TypeError, ValueError):
                key = None
            if key:
                present.add(key)
    except Exception:
        conn.rollback()
    cur.close()
    return present


def map_db_entities(
    conn: Any,
    universe: CanonicalUniverse,
) -> tuple[dict[str, str], dict[int, str]]:
    """Map cnpj8 and sc_public_entities.id → canonical entity_id."""
    cnpj8_to: dict[str, str] = {}
    for ent in universe.included:
        if ent.cnpj8:
            # first wins; ambiguous roots handled conservatively later
            cnpj8_to.setdefault(ent.cnpj8, ent.entity_id)

    db_id_to: dict[int, str] = {}
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, LEFT(REGEXP_REPLACE(COALESCE(cnpj_8, cnpj, ''), '[^0-9]', '', 'g'), 8)
            FROM sc_public_entities
            WHERE is_active IS TRUE OR is_active IS NULL
            """
        )
        for db_id, cnpj8 in cur.fetchall():
            if not cnpj8 or len(str(cnpj8)) < 8:
                continue
            root = str(cnpj8)[:8]
            if root in cnpj8_to:
                db_id_to[int(db_id)] = cnpj8_to[root]
    except Exception:
        conn.rollback()
        try:
            cur.execute(
                """
                SELECT id, LEFT(REGEXP_REPLACE(COALESCE(cnpj_8, ''), '[^0-9]', '', 'g'), 8)
                FROM sc_public_entities
                """
            )
            for db_id, cnpj8 in cur.fetchall():
                root = str(cnpj8 or "")[:8]
                if root in cnpj8_to:
                    db_id_to[int(db_id)] = cnpj8_to[root]
        except Exception:
            conn.rollback()
    cur.close()
    return cnpj8_to, db_id_to


def compute_dual_coverage(
    *,
    universe: CanonicalUniverse | None = None,
    seed_path: str | Path | None = None,
    conn: Any | None = None,
    dsn: str | None = None,
    capabilities: Sequence[str] = CAPABILITIES,
    project_root: Path | None = None,
    expected_denominator: int | None = None,
    as_of: datetime | None = None,
    observations_by_cap: Mapping[str, Mapping[str, Mapping[str, EvidenceObservation]]] | None = None,
    presence_by_cap: Mapping[str, set[str]] | None = None,
    include_legacy_stamp: bool = True,
) -> DualCoverageReport:
    """Compute dual capability coverage. Pure when observations provided; else loads DB."""
    root = project_root or _PROJECT_ROOT
    as_of_dt = as_of or datetime.now(UTC)
    as_of_s = as_of_dt.isoformat().replace("+00:00", "Z")
    limitations: list[str] = [
        "Presence is descriptive and is never coverage.",
        "Complementary sources do not replace required source combinations.",
        "entity_coverage.is_covered / any_row are forbidden as coverage methods.",
        "Gate PASS requires coverage>=95% and zero unknown applicability rows in results.",
    ]

    try:
        if universe is None:
            seed = Path(seed_path) if seed_path else resolve_default_seed_path(root)
            universe = load_canonical_universe(seed_path=seed)
        identity = build_universe_identity(
            universe,
            as_of=as_of_s,
            project_root=root,
            expected_count=expected_denominator,
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

    owns_conn = False
    if observations_by_cap is None:
        if conn is None:
            if not dsn:
                raise DualCoverageError("dsn or conn or observations_by_cap required")
            import psycopg2

            conn = psycopg2.connect(dsn, connect_timeout=10)
            owns_conn = True
        if conn is None:
            raise DualCoverageError("connection is None")
        try:
            _cnpj_map, db_id_map = map_db_entities(conn, universe)
            obs_map: dict[str, dict[str, dict[str, EvidenceObservation]]] = {}
            pres_map: dict[str, set[str]] = {}
            for cap in capabilities:
                cap_n = normalize_capability(cap) or cap
                obs_map[cap_n] = load_observations_from_db(
                    conn,
                    capability=cap_n,
                    cnpj8_to_entity_id=_cnpj_map,
                    db_id_to_entity_id=db_id_map,
                )
                pres_map[cap_n] = load_data_presence(conn, cap_n, db_id_map)
            observations_by_cap = obs_map
            presence_by_cap = pres_map
            legacy_metric = _legacy_entity_coverage_stamp(conn) if include_legacy_stamp else None
        finally:
            if owns_conn:
                conn.close()
    else:
        legacy_metric = None
        if presence_by_cap is None:
            presence_by_cap = {}

    if observations_by_cap is None or presence_by_cap is None:
        raise DualCoverageError("observations_by_cap and presence_by_cap required after load")

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
                # default applicability: applicable (all radius public entities)
                appl: ApplicabilityStatus = "applicable"
                # Honor explicit applicability on required sources (priority: blocked > not_applicable > unknown).
                for src in REQUIRED_SOURCES[cap_n]:
                    o = obs_for_ent.get(src)
                    if not o:
                        continue
                    if o.applicability == "blocked":
                        appl = "blocked"
                    elif o.applicability == "not_applicable":
                        if not o.applicability_reason:
                            raise DualCoverageError(
                                f"not_applicable without justification: {ent.entity_id}/{src}/{cap_n}"
                            )
                        if appl != "blocked":
                            appl = "not_applicable"
                    elif o.applicability == "unknown":
                        if appl == "applicable":
                            appl = "unknown"
                results.append(
                    score_entity_capability(
                        ent,
                        cap_n,
                        obs_for_ent,
                        as_of=as_of_dt,
                        applicability=appl,
                        has_data_presence=ent.entity_id in presence,
                    )
                )
            caps_out[cap_n] = aggregate_capability(
                cap_n,
                universe.included,
                results,
                identity,
                limitations=limitations,
            )
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
            error=str(exc),
        )

    gate_pass = all(c.coverage_gate_pass for c in caps_out.values()) if caps_out else False
    return DualCoverageReport(
        universe=identity,
        capabilities=caps_out,
        measurement_success=True,
        coverage_gate_pass=gate_pass,
        pipeline_success=gate_pass,  # pipeline ops success requires gates when dual is mandatory
        as_of=as_of_s,
        limitations=limitations,
        legacy_metric=legacy_metric,
        error=None,
    )


def _legacy_entity_coverage_stamp(conn: Any) -> dict[str, Any]:
    """Historical stamp only — never used as canonical coverage."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT count(DISTINCT entity_id) FROM entity_coverage WHERE is_covered IS TRUE")
        num_cov = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT count(DISTINCT entity_id) FROM entity_coverage")
        num_any = int(cur.fetchone()[0] or 0)
    except Exception:
        conn.rollback()
        return {
            "status": "unavailable",
            "canonical": False,
            "note": "legacy entity_coverage not readable",
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
        gap_rows = [e.to_dict() for e in result.entities if not e.covered or e.applicability != "applicable"]
        # full nominal list for audit
        all_rows = [e.to_dict() for e in result.entities]
        gaps_json.write_text(json.dumps(all_rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths[f"{cap}_gaps_json"] = gaps_json

        gaps_csv = output_dir / f"dual-coverage-gaps-{cap}.csv"
        fields = [
            "entity_id",
            "entity_name",
            "capability",
            "applicability",
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
        _ = gap_rows  # reserved for filtered exports
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
    )
    paths = write_reports(report, args.output_dir, capabilities=caps)
    payload = report.to_dict()
    payload["artifact_paths"] = {k: str(v) for k, v in paths.items()}
    if args.json_stdout:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"measurement_success={report.measurement_success}")
        print(f"coverage_gate_pass={report.coverage_gate_pass}")
        for cap, res in report.capabilities.items():
            print(
                f"{cap}: den={res.applicable_denominator} num={res.covered_numerator} "
                f"pct={res.coverage_pct} gate={res.gate_status} "
                f"presence={res.data_presence_pct} fresh={res.fresh_count} "
                f"stale={res.stale_count} unknown={res.unknown_count} blocked={res.blocked_count}"
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
