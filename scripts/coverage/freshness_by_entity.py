#!/usr/bin/env python3
"""Entity-level freshness by capability (editais / contracts).

Population/denominator authority: ``scripts.lib.universe.load_canonical_universe``.
Registry supplies observations only; each row is reconciled to a canonical entity_id.

Rules (ADR-028 / ENTITY-FRESHNESS-CANONICAL-ACCEPTANCE-01):
  - One row per canonical entity per capability report
  - entity_id set of each report == load_canonical_universe(...).included (set equality)
  - Statuses: FRESH STALE NEVER INCOMPLETE BLOCKED NOT_APPLICABLE UNKNOWN
  - FRESH and STALE require entity-scoped timestamp + run_id + content_hash
  - Missing timestamp → NEVER (age_hours=None, never coerced to 0)
  - Missing run_id/content_hash or future timestamp → INCOMPLETE
  - Editais observations never promote contracts and vice versa
  - len==1093 alone is never acceptance

Usage::

    python3 -m scripts.coverage.freshness_by_entity \\
        --seed "Extra - alvos de licitação. R-0.xlsx" \\
        --registry data/entity_source_registry.jsonl \\
        --output-dir output/coverage \\
        --strict \\
        --evidence-manifest docs/ops/campaigns/ENTITY-FRESHNESS-01/evidence/acceptance-manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.universe import (  # noqa: E402
    DEFAULT_SEED_PATH,
    CanonicalUniverse,
    load_canonical_universe,
    normalize_cnpj8,
    normalize_identity_text,
    sha256_file,
)

ADAPTER_VERSION = "freshness_by_entity/2.0.0-canonical"
# Historical constant only — never used as acceptance denominator.
HISTORICAL_UNIVERSE_HINT = 1093

CAPABILITY_EDITAIS = "notices_or_bids"
CAPABILITY_CONTRACTS = "contracts"
CAPABILITIES: tuple[str, ...] = (CAPABILITY_EDITAIS, CAPABILITY_CONTRACTS)

ALLOWED_STATUSES: frozenset[str] = frozenset(
    {
        "FRESH",
        "STALE",
        "NEVER",
        "INCOMPLETE",
        "BLOCKED",
        "NOT_APPLICABLE",
        "UNKNOWN",
    }
)

NON_FRESH_HARD: frozenset[str] = frozenset(
    {"UNKNOWN", "NEVER", "BLOCKED", "INCOMPLETE"}
)

REQUIRED_FIELDS: tuple[str, ...] = (
    "entity_id",
    "capability",
    "source_id",
    "applicability",
    "last_attempt_at",
    "last_success_at",
    "last_verified_at",
    "sla_id",
    "sla_hours",
    "age_hours",
    "freshness_status",
    "run_id",
    "raw_uri",
    "artifact_ref",
    "content_hash",
    "blocker",
    "next_action",
    "as_of",
    "adapter_version",
)

DEFAULT_SLA_PATH = _PROJECT_ROOT / "config" / "coverage_slas.yaml"
DEFAULT_REGISTRY = _PROJECT_ROOT / "data" / "entity_source_registry.jsonl"
DEFAULT_OUTPUT = _PROJECT_ROOT / "output" / "coverage"
DEFAULT_SEED = _PROJECT_ROOT / str(DEFAULT_SEED_PATH)

REPORT_FILENAMES = {
    CAPABILITY_EDITAIS: "freshness-editais.json",
    CAPABILITY_CONTRACTS: "freshness-contracts.json",
}


@dataclass(frozen=True)
class SlaResolution:
    sla_id: str
    sla_hours: int
    sla_version: str
    capability: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EntityObservation:
    """Per-entity observation for one capability. Absence is explicit None."""

    entity_id: str
    capability: str
    source_id: str | None = None
    applicability: str = "unknown"
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_verified_at: datetime | None = None
    run_id: str | None = None
    raw_uri: str | None = None
    artifact_ref: str | None = None
    content_hash: str | None = None
    blocker: str | None = None
    next_action: str | None = None
    status_hint: str | None = None
    registry_canonical_id: str | None = None
    reconcile_method: str | None = None


@dataclass
class EntityFreshnessRecord:
    entity_id: str
    capability: str
    source_id: str | None
    applicability: str
    last_attempt_at: str | None
    last_success_at: str | None
    last_verified_at: str | None
    sla_id: str
    sla_hours: int
    age_hours: float | None
    freshness_status: str
    run_id: str | None
    raw_uri: str | None
    artifact_ref: str | None
    content_hash: str | None
    blocker: str | None
    next_action: str | None
    as_of: str
    adapter_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ListIdentity:
    """Set-equality identity against the canonical included population."""

    expected_count: int
    observed_count: int
    unique_entity_count: int
    duplicate_count: int
    missing_count: int
    extra_count: int
    covered: int
    uncovered: int
    expected_ids_sha256: str
    observed_ids_sha256: str
    ok: bool
    reason: str = ""
    missing_ids: list[str] = field(default_factory=list)
    extra_ids: list[str] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CapabilityReport:
    capability: str
    as_of: str
    sla_version: str
    sla_id: str
    sla_hours: int
    denominator: int
    unique_entity_count: int
    status_counts: dict[str, int]
    covered: int
    uncovered: int
    list_identity: ListIdentity
    entities: list[EntityFreshnessRecord] = field(default_factory=list)
    breaches: list[dict[str, Any]] = field(default_factory=list)
    adapter_version: str = ADAPTER_VERSION
    universe_version: str = ""
    seed_path: str = ""
    seed_sha256: str = ""
    limitations: list[str] = field(default_factory=list)
    claims_allowed: list[str] = field(default_factory=list)
    claims_forbidden: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "as_of": self.as_of,
            "sla_version": self.sla_version,
            "sla_id": self.sla_id,
            "sla_hours": self.sla_hours,
            "denominator": self.denominator,
            "unique_entity_count": self.unique_entity_count,
            "status_counts": dict(self.status_counts),
            "covered": self.covered,
            "uncovered": self.uncovered,
            "list_identity": self.list_identity.to_dict(),
            "entities": [e.to_dict() for e in self.entities],
            "breaches": list(self.breaches),
            "adapter_version": self.adapter_version,
            "universe_version": self.universe_version,
            "seed_path": self.seed_path,
            "seed_sha256": self.seed_sha256,
            "limitations": list(self.limitations),
            "claims_allowed": list(self.claims_allowed),
            "claims_forbidden": list(self.claims_forbidden),
        }


@dataclass
class ReconcileResult:
    entity_id: str | None
    method: str
    registry_id: str
    error: str | None = None


class FreshnessIdentityError(ValueError):
    """Raised when set equality / reconcile fails."""


class FreshnessReportIncompleteError(ValueError):
    """Raised when a report is incomplete for strict mode."""


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Minimal YAML subset for sla config without PyYAML dependency."""
    result: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(0, result)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while stack and indent < stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.endswith(":") and line.count(":") == 1:
            key = line[:-1].strip()
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent + 2, child))
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if val == "":
            child = {}
            parent[key] = child
            stack.append((indent + 2, child))
            continue
        if val.isdigit() or (val.startswith("-") and val[1:].isdigit()):
            parent[key] = int(val)
        else:
            parent[key] = val
    return result


def load_sla_document(path: Path | str | None = None) -> dict[str, Any]:
    sla_path = Path(path) if path else DEFAULT_SLA_PATH
    if not sla_path.is_file():
        return {
            "sla_version": "coverage-sla-v0-defaults",
            "open_opportunities_hours": 24,
            "contracts_amendments_hours": 72,
            "capabilities": {
                CAPABILITY_EDITAIS: {
                    "sla_id": "sla.notices_or_bids.open_opportunities",
                    "hours_key": "open_opportunities_hours",
                },
                CAPABILITY_CONTRACTS: {
                    "sla_id": "sla.contracts.amendments",
                    "hours_key": "contracts_amendments_hours",
                },
            },
        }
    text = sla_path.read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError:
        return _parse_simple_yaml(text)
    try:
        loaded = yaml.safe_load(text) or {}
    except Exception:
        return _parse_simple_yaml(text)
    if isinstance(loaded, dict):
        return loaded
    return _parse_simple_yaml(text)


def resolve_sla(capability: str, sla_doc: Mapping[str, Any] | None = None) -> SlaResolution:
    """Resolve versioned SLA for a capability. Pure."""
    doc = dict(sla_doc) if sla_doc is not None else load_sla_document()
    if capability not in CAPABILITIES:
        raise ValueError(f"unknown capability: {capability!r}")
    caps = doc.get("capabilities") or {}
    cap_cfg = caps.get(capability) or {}
    hours_key = str(
        cap_cfg.get("hours_key")
        or (
            "open_opportunities_hours"
            if capability == CAPABILITY_EDITAIS
            else "contracts_amendments_hours"
        )
    )
    default_hours = 24 if capability == CAPABILITY_EDITAIS else 72
    hours = int(doc.get(hours_key, default_hours))
    sla_id = str(
        cap_cfg.get("sla_id")
        or (
            "sla.notices_or_bids.open_opportunities"
            if capability == CAPABILITY_EDITAIS
            else "sla.contracts.amendments"
        )
    )
    sla_version = str(doc.get("sla_version") or "coverage-sla-v0-defaults")
    return SlaResolution(
        sla_id=sla_id,
        sla_hours=hours,
        sla_version=sla_version,
        capability=capability,
    )


def calculate_age_hours(
    last_success_at: datetime | None,
    *,
    as_of: datetime,
) -> float | None:
    """Return age in hours, or None when timestamp is absent. Never coerce to 0."""
    if last_success_at is None:
        return None
    ts = last_success_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    now = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=UTC)
    return (now - ts).total_seconds() / 3600.0


def has_provenance(
    *,
    run_id: str | None,
    content_hash: str | None,
    last_success_at: datetime | None,
) -> bool:
    """Provenance required for FRESH and STALE."""
    if not run_id or not str(run_id).strip():
        return False
    if not content_hash or not str(content_hash).strip():
        return False
    if last_success_at is None:
        return False
    return True


def classify_freshness_status(
    *,
    last_success_at: datetime | None,
    as_of: datetime,
    sla_hours: int,
    applicability: str = "unknown",
    status_hint: str | None = None,
    run_id: str | None = None,
    content_hash: str | None = None,
    partial_execution: bool = False,
) -> tuple[str, float | None]:
    """Classify one entity observation. Pure. Never promotes garbage to FRESH/STALE.

    Returns (freshness_status, age_hours).
    FRESH and STALE both require full provenance (timestamp + run_id + content_hash).
    """
    age = calculate_age_hours(last_success_at, as_of=as_of)

    if applicability == "not_applicable":
        return "NOT_APPLICABLE", age

    if status_hint in {"blocked", "BLOCKED"}:
        return "BLOCKED", age

    if partial_execution:
        return "INCOMPLETE", age

    if last_success_at is None:
        return "NEVER", None

    if age is not None and age < 0:
        return "INCOMPLETE", age

    provenanced = has_provenance(
        run_id=run_id,
        content_hash=content_hash,
        last_success_at=last_success_at,
    )
    if not provenanced:
        # Timestamp without correlatable provenance cannot be FRESH or STALE
        return "INCOMPLETE", age

    if age is not None and age <= float(sla_hours):
        return "FRESH", age
    return "STALE", age


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def classify_observation(
    obs: EntityObservation,
    *,
    sla: SlaResolution,
    as_of: datetime,
    partial_execution: bool = False,
) -> EntityFreshnessRecord:
    """Build one entity freshness record from an observation. Pure."""
    status, age = classify_freshness_status(
        last_success_at=obs.last_success_at,
        as_of=as_of,
        sla_hours=sla.sla_hours,
        applicability=obs.applicability,
        status_hint=obs.status_hint,
        run_id=obs.run_id,
        content_hash=obs.content_hash,
        partial_execution=partial_execution,
    )
    if status not in ALLOWED_STATUSES:
        status = "UNKNOWN"

    if status in {"FRESH", "STALE"} and not has_provenance(
        run_id=obs.run_id,
        content_hash=obs.content_hash,
        last_success_at=obs.last_success_at,
    ):
        status = "INCOMPLETE"

    blocker = obs.blocker
    next_action = obs.next_action
    if status == "NEVER":
        blocker = blocker or "no_success_observation"
        next_action = next_action or "collect_and_verify"
    elif status == "STALE":
        blocker = blocker or "sla_exceeded"
        next_action = next_action or "refresh_source"
    elif status == "INCOMPLETE":
        blocker = blocker or "incomplete_provenance_or_partial"
        next_action = next_action or "complete_pipeline_and_hash"
    elif status == "BLOCKED":
        blocker = blocker or "source_blocked"
        next_action = next_action or "unblock_source"
    elif status == "UNKNOWN":
        blocker = blocker or "unknown_state"
        next_action = next_action or "map_and_observe"
    elif status == "NOT_APPLICABLE":
        blocker = blocker or "not_applicable"
        next_action = next_action or "none"
    elif status == "FRESH":
        blocker = blocker or None
        next_action = next_action or "monitor"

    return EntityFreshnessRecord(
        entity_id=str(obs.entity_id),
        capability=sla.capability,
        source_id=obs.source_id,
        applicability=obs.applicability,
        last_attempt_at=_iso(obs.last_attempt_at),
        last_success_at=_iso(obs.last_success_at),
        last_verified_at=_iso(obs.last_verified_at),
        sla_id=sla.sla_id,
        sla_hours=sla.sla_hours,
        age_hours=round(age, 6) if age is not None else None,
        freshness_status=status,
        run_id=obs.run_id,
        raw_uri=obs.raw_uri,
        artifact_ref=obs.artifact_ref,
        content_hash=obs.content_hash,
        blocker=blocker,
        next_action=next_action,
        as_of=_iso(as_of) or as_of.isoformat(),
        adapter_version=ADAPTER_VERSION,
    )


def ordered_ids_sha256(ids: Sequence[str]) -> str:
    payload = "\n".join(sorted(str(i) for i in ids)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def assert_set_identity(
    records: Sequence[EntityFreshnessRecord],
    *,
    canonical_entity_ids: Sequence[str],
) -> ListIdentity:
    """Validate set equality with the canonical included population."""
    expected_sorted = sorted(str(i) for i in canonical_entity_ids)
    expected_set = set(expected_sorted)
    if len(expected_set) != len(expected_sorted):
        raise FreshnessIdentityError(
            "canonical_entity_ids contain duplicates; load_canonical_universe.included must be unique"
        )

    observed_ids = [str(r.entity_id) for r in records]
    observed_set = set(observed_ids)
    from collections import Counter

    counts = Counter(observed_ids)
    duplicate_ids = sorted(eid for eid, n in counts.items() if n > 1)
    missing_ids = sorted(expected_set - observed_set)
    extra_ids = sorted(observed_set - expected_set)
    covered = sum(1 for r in records if r.freshness_status == "FRESH")
    uncovered = len(records) - covered

    ok = (
        not duplicate_ids
        and not missing_ids
        and not extra_ids
        and len(observed_ids) == len(expected_sorted)
        and observed_set == expected_set
    )
    reason_parts: list[str] = []
    if duplicate_ids:
        reason_parts.append(f"duplicates={len(duplicate_ids)}")
    if missing_ids:
        reason_parts.append(f"missing={len(missing_ids)}")
    if extra_ids:
        reason_parts.append(f"extra={len(extra_ids)}")
    if len(observed_ids) != len(expected_sorted):
        reason_parts.append(
            f"row_count={len(observed_ids)} expected={len(expected_sorted)}"
        )
    reason = ";".join(reason_parts)
    identity = ListIdentity(
        expected_count=len(expected_sorted),
        observed_count=len(observed_ids),
        unique_entity_count=len(observed_set),
        duplicate_count=len(duplicate_ids),
        missing_count=len(missing_ids),
        extra_count=len(extra_ids),
        covered=covered,
        uncovered=uncovered,
        expected_ids_sha256=ordered_ids_sha256(expected_sorted),
        observed_ids_sha256=ordered_ids_sha256(observed_ids),
        ok=ok,
        reason=reason,
        missing_ids=missing_ids[:50],
        extra_ids=extra_ids[:50],
        duplicate_ids=duplicate_ids[:50],
    )
    if not ok:
        raise FreshnessIdentityError(
            f"set identity failed: {reason or 'unknown'}; "
            f"expected={len(expected_sorted)} observed={len(observed_ids)} "
            f"unique={len(observed_set)} dups={len(duplicate_ids)}"
        )
    return identity


# Back-compat alias used by some tests / callers
def assert_list_identity(
    records: Sequence[EntityFreshnessRecord],
    *,
    expected: int | None = None,
    canonical_entity_ids: Sequence[str] | None = None,
) -> ListIdentity:
    if canonical_entity_ids is not None:
        return assert_set_identity(records, canonical_entity_ids=canonical_entity_ids)
    if expected is None:
        raise TypeError("expected or canonical_entity_ids required")
    # Cardinality-only path is intentionally weak; still fail on dups / wrong count
    synthetic = [f"__syn_{i:04d}" for i in range(expected)]
    # Remap: only check counts when synthetic used — prefer real IDs when present
    ids = [r.entity_id for r in records]
    if len(ids) == expected and len(set(ids)) == expected:
        return assert_set_identity(records, canonical_entity_ids=ids)
    return assert_set_identity(records, canonical_entity_ids=synthetic)


def validate_record_fields(record: EntityFreshnessRecord) -> list[str]:
    """Return list of missing required field names (empty if complete)."""
    data = record.to_dict()
    missing: list[str] = []
    for key in REQUIRED_FIELDS:
        if key not in data:
            missing.append(key)
    if record.freshness_status not in ALLOWED_STATUSES:
        missing.append(f"invalid_status:{record.freshness_status}")
    if not record.capability:
        missing.append("capability")
    return missing


def empty_observation(entity_id: str, capability: str) -> EntityObservation:
    return EntityObservation(
        entity_id=entity_id,
        capability=capability,
        applicability="unknown",
    )


def build_capability_report(
    observations: Sequence[EntityObservation],
    *,
    capability: str,
    canonical_entity_ids: Sequence[str],
    as_of: datetime | None = None,
    sla_doc: Mapping[str, Any] | None = None,
    partial_execution: bool = False,
    strict_identity: bool = True,
    limitations: Sequence[str] | None = None,
    seed_path: str = "",
    seed_sha256: str = "",
    universe_version: str = "",
) -> CapabilityReport:
    """Build report for one capability over the canonical population.

    Observations are matched by entity_id (must already be canonical).
    Every canonical id appears exactly once; missing obs → NEVER.
    Extra non-canonical ids fail closed when strict_identity=True.
    """
    as_of = as_of or datetime.now(UTC)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)
    sla = resolve_sla(capability, sla_doc)

    expected_sorted = sorted(str(i) for i in canonical_entity_ids)
    expected_set = set(expected_sorted)
    if len(expected_set) != len(expected_sorted):
        raise FreshnessIdentityError("duplicate ids in canonical_entity_ids")

    by_id: dict[str, EntityObservation] = {}
    extras: list[str] = []
    for obs in observations:
        if obs.capability and obs.capability != capability:
            # Observation for another capability — ignore (no cross-promotion)
            continue
        eid = str(obs.entity_id)
        if eid not in expected_set:
            extras.append(eid)
            continue
        if eid in by_id:
            if strict_identity:
                raise FreshnessIdentityError(f"duplicate entity_id in input: {eid}")
            continue
        by_id[eid] = obs

    if extras and strict_identity:
        raise FreshnessIdentityError(
            f"non-canonical entity_ids rejected: count={len(extras)} sample={extras[:5]}"
        )

    records: list[EntityFreshnessRecord] = []
    for eid in expected_sorted:
        obs = by_id.get(eid) or empty_observation(eid, capability)
        # Force capability on empty rows
        if not obs.capability:
            obs.capability = capability
        records.append(
            classify_observation(
                obs,
                sla=sla,
                as_of=as_of,
                partial_execution=partial_execution,
            )
        )

    status_counts: dict[str, int] = {s: 0 for s in sorted(ALLOWED_STATUSES)}
    for r in records:
        status_counts[r.freshness_status] = status_counts.get(r.freshness_status, 0) + 1

    if strict_identity:
        identity = assert_set_identity(records, canonical_entity_ids=expected_sorted)
    else:
        identity = ListIdentity(
            expected_count=len(expected_sorted),
            observed_count=len(records),
            unique_entity_count=len({r.entity_id for r in records}),
            duplicate_count=0,
            missing_count=0,
            extra_count=len(extras),
            covered=sum(1 for r in records if r.freshness_status == "FRESH"),
            uncovered=0,
            expected_ids_sha256=ordered_ids_sha256(expected_sorted),
            observed_ids_sha256=ordered_ids_sha256([r.entity_id for r in records]),
            ok=False,
            reason="strict_identity_disabled",
        )
        identity.uncovered = len(records) - identity.covered

    breaches: list[dict[str, Any]] = []
    for r in records:
        if r.freshness_status in {"FRESH", "NOT_APPLICABLE"}:
            continue
        breaches.append(
            {
                "entity_id": r.entity_id,
                "capability": r.capability,
                "freshness_status": r.freshness_status,
                "age_hours": r.age_hours,
                "blocker": r.blocker,
                "next_action": r.next_action,
            }
        )

    claims_allowed = [
        "freshness é mensurável por entidade",
        "população derivada exclusivamente de load_canonical_universe",
        "igualdade exata de entity_ids com o universo canônico incluído",
        "editais e contratos são capabilities distintas",
        "breaches e ausências são nominais com entity_id",
        "modo strict falha fechado",
    ]
    claims_forbidden = [
        "cobertura operacional ≥95%",
        "freshness ≥95%",
        "recall ≥95%",
        "LOCAL_READY",
        "VPS_OPERATIONAL",
        "PROJECT_DONE",
        "proxy de presença como cobertura operacional",
        "MAX(ingested_at) global como freshness de entidades",
        "len==1093 sem igualdade de conjuntos",
        "migration 058 como spine de aceite",
        "entity_source_binding como spine de aceite",
    ]

    lim = list(limitations or [])
    lim.append(
        "Entity-level freshness; source-level MAX(ingested_at) does not promote entities"
    )
    lim.append(f"SLA version={sla.sla_version} sla_id={sla.sla_id} hours={sla.sla_hours}")
    lim.append("Denominator from load_canonical_universe.included (set equality)")
    lim.append("Registry is observation source only after explicit reconcile")

    return CapabilityReport(
        capability=capability,
        as_of=_iso(as_of) or as_of.isoformat(),
        sla_version=sla.sla_version,
        sla_id=sla.sla_id,
        sla_hours=sla.sla_hours,
        denominator=len(expected_sorted),
        unique_entity_count=identity.unique_entity_count,
        status_counts=status_counts,
        covered=identity.covered,
        uncovered=identity.uncovered,
        list_identity=identity,
        entities=records,
        breaches=breaches,
        limitations=lim,
        claims_allowed=claims_allowed,
        claims_forbidden=claims_forbidden,
        seed_path=seed_path,
        seed_sha256=seed_sha256,
        universe_version=universe_version
        or f"canonical-included-{len(expected_sorted)}",
    )


def validate_capability_report_strict(
    report: CapabilityReport | Mapping[str, Any],
    *,
    canonical_entity_ids: Sequence[str] | None = None,
) -> list[str]:
    """Return blockers if report is incomplete for strict consultive use."""
    blockers: list[str] = []
    data = report.to_dict() if isinstance(report, CapabilityReport) else dict(report)

    entities = data.get("entities") or []
    if not entities:
        blockers.append("freshness_report_empty")
        return blockers

    unique_ids = {str(e.get("entity_id")) for e in entities if isinstance(e, dict)}
    if len(entities) != len(unique_ids):
        blockers.append(f"freshness_report_duplicates:{data.get('capability')}")

    if canonical_entity_ids is not None:
        expected = set(str(i) for i in canonical_entity_ids)
        if unique_ids != expected:
            blockers.append(
                f"freshness_report_set_mismatch:{data.get('capability')}:"
                f"missing={len(expected - unique_ids)}:extra={len(unique_ids - expected)}"
            )
        if len(entities) != len(expected):
            blockers.append(
                f"freshness_report_cardinality:{data.get('capability')}:{len(entities)}"
            )
    else:
        # Without canonical set, only enforce internal consistency (not len==1093 alone)
        li = data.get("list_identity") or {}
        if isinstance(li, dict) and li.get("ok") is False:
            blockers.append(f"freshness_report_list_identity_not_ok:{data.get('capability')}")

    for e in entities:
        if not isinstance(e, dict):
            blockers.append("freshness_report_invalid_row")
            continue
        if not e.get("capability"):
            blockers.append("freshness_report_missing_capability")
        status = e.get("freshness_status")
        if status not in ALLOWED_STATUSES:
            blockers.append(f"freshness_report_invalid_status:{status}")
        if status in {"FRESH", "STALE"}:
            if not e.get("run_id") or not e.get("content_hash") or not e.get("last_success_at"):
                blockers.append(f"freshness_report_{status.lower()}_without_provenance")

    covered = int(data.get("covered") or 0)
    uncovered = int(data.get("uncovered") or 0)
    if covered + uncovered != len(entities) and entities:
        blockers.append("freshness_report_covered_uncovered_mismatch")

    seen: set[str] = set()
    out: list[str] = []
    for b in blockers:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out


def evaluate_entity_freshness_reports(
    *,
    editais_report: CapabilityReport | Mapping[str, Any] | None,
    contracts_report: CapabilityReport | Mapping[str, Any] | None,
    canonical_entity_ids: Sequence[str] | None = None,
) -> list[str]:
    """Strict evaluation of both capability reports. Empty list = ok."""
    blockers: list[str] = []
    if editais_report is None:
        blockers.append("freshness_report_missing:notices_or_bids")
    else:
        blockers.extend(
            validate_capability_report_strict(
                editais_report, canonical_entity_ids=canonical_entity_ids
            )
        )
    if contracts_report is None:
        blockers.append("freshness_report_missing:contracts")
    else:
        blockers.extend(
            validate_capability_report_strict(
                contracts_report, canonical_entity_ids=canonical_entity_ids
            )
        )
    # Both reports must share the same entity set
    if (
        editais_report is not None
        and contracts_report is not None
        and canonical_entity_ids is None
    ):
        e_data = (
            editais_report.to_dict()
            if isinstance(editais_report, CapabilityReport)
            else dict(editais_report)
        )
        c_data = (
            contracts_report.to_dict()
            if isinstance(contracts_report, CapabilityReport)
            else dict(contracts_report)
        )
        e_ids = {str(x.get("entity_id")) for x in (e_data.get("entities") or []) if isinstance(x, dict)}
        c_ids = {str(x.get("entity_id")) for x in (c_data.get("entities") or []) if isinstance(x, dict)}
        if e_ids != c_ids:
            blockers.append("freshness_reports_entity_set_divergence")
    return blockers


# ---------------------------------------------------------------------------
# Canonical universe + reconciliation
# ---------------------------------------------------------------------------


def load_canonical_population(
    seed_path: Path | str | None = None,
) -> tuple[list[str], CanonicalUniverse]:
    """Return sorted included entity_ids and the universe snapshot."""
    path = Path(seed_path) if seed_path else DEFAULT_SEED
    universe = load_canonical_universe(path)
    ids = sorted(entity.entity_id for entity in universe.included)
    if not ids:
        raise FreshnessIdentityError(f"canonical included population is empty: {path}")
    if len(ids) != len(set(ids)):
        raise FreshnessIdentityError("canonical included population has duplicate entity_ids")
    return ids, universe


def reconcile_registry_row(
    row: Mapping[str, Any],
    universe: CanonicalUniverse,
) -> ReconcileResult:
    """Map one registry row to a canonical entity_id. Fail closed on ambiguity."""
    registry_id = str(row.get("canonical_id") or row.get("entity_id") or "")
    # Direct hit if registry already uses canonical ids
    by_id = universe.by_entity_id()
    if registry_id in by_id and by_id[registry_id].within_radius is True:
        return ReconcileResult(
            entity_id=registry_id,
            method="direct_entity_id",
            registry_id=registry_id,
        )

    cnpj = normalize_cnpj8(str(row.get("cnpj") or row.get("cnpj8") or ""))
    if not cnpj:
        return ReconcileResult(
            entity_id=None,
            method="unreconciled",
            registry_id=registry_id,
            error="missing_cnpj",
        )

    candidates = universe.included_by_cnpj8().get(cnpj, [])
    if not candidates:
        return ReconcileResult(
            entity_id=None,
            method="unreconciled",
            registry_id=registry_id,
            error="cnpj_root_not_in_included",
        )
    if len(candidates) == 1:
        return ReconcileResult(
            entity_id=candidates[0].entity_id,
            method="cnpj8_unique",
            registry_id=registry_id,
        )

    name = normalize_identity_text(
        str(row.get("razao_social") or row.get("nome_fantasia") or "")
    )
    city = normalize_identity_text(str(row.get("municipio") or ""))
    exact = [
        e
        for e in candidates
        if normalize_identity_text(e.razao_social) == name
        and normalize_identity_text(e.municipio) == city
    ]
    if len(exact) == 1:
        return ReconcileResult(
            entity_id=exact[0].entity_id,
            method="cnpj8_name_municipality",
            registry_id=registry_id,
        )
    by_name = [
        e for e in candidates if normalize_identity_text(e.razao_social) == name
    ]
    if len(by_name) == 1:
        return ReconcileResult(
            entity_id=by_name[0].entity_id,
            method="cnpj8_name",
            registry_id=registry_id,
        )
    by_city = [
        e for e in candidates if normalize_identity_text(e.municipio) == city
    ]
    if len(by_city) == 1:
        return ReconcileResult(
            entity_id=by_city[0].entity_id,
            method="cnpj8_municipality",
            registry_id=registry_id,
        )
    return ReconcileResult(
        entity_id=None,
        method="unreconciled",
        registry_id=registry_id,
        error=f"ambiguous_duplicate_cnpj_root:{cnpj}:{len(candidates)}",
    )


# Source ids that may back each capability observation.
CAPABILITY_SOURCE_IDS: dict[str, frozenset[str]] = {
    CAPABILITY_EDITAIS: frozenset(
        {
            "pncp",
            "pcp",
            "sc_compras",
            "ciga_dom",
            "ciga_ckan",
            "dom_sc",
            "doe_sc",
            "compras_gov",
            "transparencia",
            "tce_sc",
        }
    ),
    CAPABILITY_CONTRACTS: frozenset(
        {
            "pncp_contracts",
            "contracts",
        }
    ),
}

PROVENANCE_EVIDENCE_TYPES: frozenset[str] = frozenset(
    {
        "pipeline_evidence_promote",
    }
)


def _evidence_sources(ev: Mapping[str, Any]) -> set[str]:
    raw = ev.get("sources") or []
    if isinstance(raw, str):
        return {raw}
    return {str(s) for s in raw if s}


def _evidence_matches_capability(ev: Mapping[str, Any], capability: str) -> bool:
    """True when this evidence row is attributable to the capability."""
    cap_sources = CAPABILITY_SOURCE_IDS.get(capability, frozenset())
    ev_cap = str(ev.get("capability") or "")
    if capability == CAPABILITY_CONTRACTS:
        if ev_cap in {"contracts", "historical_contracts", CAPABILITY_CONTRACTS}:
            return True
        srcs = _evidence_sources(ev)
        return bool(srcs & cap_sources)
    if ev_cap in {"notices_or_bids", "open_opportunities", "bids", "editais"}:
        return True
    srcs = _evidence_sources(ev)
    notices_hit = bool(srcs & CAPABILITY_SOURCE_IDS[CAPABILITY_EDITAIS])
    contracts_only = bool(srcs) and srcs <= CAPABILITY_SOURCE_IDS[CAPABILITY_CONTRACTS]
    if contracts_only:
        return False
    return notices_hit


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _extract_capability_evidence(
    row: Mapping[str, Any],
    capability: str,
) -> dict[str, Any] | None:
    """Pick best per-entity evidence for one capability (never global MAX)."""
    evidences = row.get("evidences") or []
    if not isinstance(evidences, list):
        return None

    candidates: list[tuple[datetime, dict[str, Any]]] = []
    for ev in evidences:
        if not isinstance(ev, dict):
            continue
        ev_type = str(ev.get("type") or "")
        if ev_type not in PROVENANCE_EVIDENCE_TYPES and not (
            ev.get("run_id") or ev.get("pipeline_run_id")
        ):
            continue
        if not _evidence_matches_capability(ev, capability):
            continue
        ts = _parse_dt(
            ev.get("last_seen_at") or ev.get("last_success_at") or ev.get("attempted_at")
        )
        if ts is None:
            ts = datetime.min.replace(tzinfo=UTC)
        candidates.append((ts, ev))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    _best_ts, best = candidates[0]
    srcs = sorted(_evidence_sources(best))
    cap_sources = CAPABILITY_SOURCE_IDS.get(capability, frozenset())
    preferred = [s for s in srcs if s in cap_sources]
    source_id = preferred[0] if preferred else (srcs[0] if srcs else None)
    run_id = best.get("run_id") or best.get("pipeline_run_id")
    content_hash = best.get("raw_sha256") or best.get("content_hash")
    raw_uri = best.get("raw_uri")
    artifact_ref = best.get("provenance_source") or best.get("reconciliation_id")
    last_success = _parse_dt(best.get("last_seen_at") or best.get("last_success_at"))
    last_attempt = _parse_dt(best.get("attempted_at") or best.get("last_attempt_at"))
    stages_raw = best.get("stages")
    stages: dict[str, Any] = stages_raw if isinstance(stages_raw, dict) else {}
    last_verified = last_success if stages.get("verified_within_sla") else None

    return {
        "source_id": source_id,
        "last_success_at": last_success,
        "last_attempt_at": last_attempt,
        "last_verified_at": last_verified,
        "run_id": str(run_id) if run_id else None,
        "content_hash": str(content_hash) if content_hash else None,
        "raw_uri": str(raw_uri) if raw_uri else None,
        "artifact_ref": str(artifact_ref) if artifact_ref else None,
        "partial_execution": bool(
            stages
            and not all(
                stages.get(k) is True
                for k in ("mapped", "accessible", "collected", "normalized", "reconciled")
            )
        ),
    }


def _fallback_capability_timestamp(
    row: Mapping[str, Any],
    capability: str,
) -> datetime | None:
    """Use registry last_success_at only when platforms imply this capability."""
    last = _parse_dt(row.get("last_success_at"))
    if last is None:
        return None
    plats = {str(p) for p in (row.get("plataformas") or []) if p}
    cap_sources = CAPABILITY_SOURCE_IDS.get(capability, frozenset())
    if not (plats & cap_sources):
        return None
    if capability == CAPABILITY_CONTRACTS:
        if not (plats & CAPABILITY_SOURCE_IDS[CAPABILITY_CONTRACTS]):
            return None
    return last


def observation_from_registry_row(
    row: Mapping[str, Any],
    *,
    capability: str,
    entity_id: str,
    reconcile_method: str | None = None,
    override: Mapping[str, Any] | None = None,
) -> EntityObservation:
    """Build one capability observation for a reconciled canonical entity_id."""
    ov = dict(override or {})
    registry_id = str(row.get("canonical_id") or row.get("entity_id") or "")
    extracted = _extract_capability_evidence(row, capability) or {}

    def _ov_or_ext(key: str) -> Any:
        if key in ov:
            return ov.get(key)
        return extracted.get(key)

    last_success = _parse_dt(_ov_or_ext("last_success_at"))
    if last_success is None and "last_success_at" not in ov and not extracted:
        last_success = _fallback_capability_timestamp(row, capability)

    last_attempt = _parse_dt(_ov_or_ext("last_attempt_at"))
    if last_attempt is None:
        last_attempt = _parse_dt(row.get("last_attempt_at"))

    last_verified = _parse_dt(_ov_or_ext("last_verified_at"))

    run_id = _ov_or_ext("run_id")
    content_hash = _ov_or_ext("content_hash")
    raw_uri = _ov_or_ext("raw_uri")
    artifact_ref = _ov_or_ext("artifact_ref")
    source_id = _ov_or_ext("source_id")

    if source_id is None:
        plats = [str(p) for p in (row.get("plataformas") or []) if p]
        cap_sources = CAPABILITY_SOURCE_IDS.get(capability, frozenset())
        preferred = [p for p in plats if p in cap_sources]
        source_id = preferred[0] if preferred else None

    status_hint = ov.get("status_hint") if "status_hint" in ov else None
    if status_hint is None and row.get("access_status") == "blocked":
        status_hint = "blocked"

    applicability = str(
        ov.get("applicability")
        or (
            "not_applicable"
            if row.get("current_blocker") == "not_applicable"
            else "unknown"
        )
    )

    return EntityObservation(
        entity_id=entity_id,
        capability=capability,
        source_id=str(source_id) if source_id else None,
        applicability=applicability,
        last_attempt_at=last_attempt,
        last_success_at=last_success,
        last_verified_at=last_verified,
        run_id=str(run_id) if run_id else None,
        raw_uri=str(raw_uri) if raw_uri else None,
        artifact_ref=str(artifact_ref) if artifact_ref else None,
        content_hash=str(content_hash) if content_hash else None,
        blocker=ov.get("blocker") if "blocker" in ov else row.get("current_blocker"),
        next_action=ov.get("next_action") if "next_action" in ov else row.get("next_action"),
        status_hint=str(status_hint) if status_hint else None,
        registry_canonical_id=registry_id or None,
        reconcile_method=reconcile_method,
    )


def observations_from_registry(
    path: Path | str | None = None,
    *,
    capability: str,
    universe: CanonicalUniverse,
    strict: bool = True,
    per_entity_overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[list[EntityObservation], dict[str, Any]]:
    """Build observations reconciled to canonical entity_ids for one capability.

    Returns (observations, reconcile_stats).
    """
    if capability not in CAPABILITIES:
        raise ValueError(f"unknown capability: {capability}")

    reg = Path(path) if path else DEFAULT_REGISTRY
    overrides = dict(per_entity_overrides or {})
    observations: list[EntityObservation] = []
    unreconciled: list[str] = []
    methods: dict[str, int] = {}
    target_hits: dict[str, str] = {}
    duplicate_targets: list[str] = []

    if not reg.is_file():
        raise FileNotFoundError(f"registry not found: {reg}")

    with reg.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            result = reconcile_registry_row(row, universe)
            methods[result.method] = methods.get(result.method, 0) + 1
            if result.entity_id is None:
                unreconciled.append(result.registry_id or result.error or "unknown")
                continue
            if result.entity_id in target_hits:
                duplicate_targets.append(result.entity_id)
                if strict:
                    raise FreshnessIdentityError(
                        f"duplicate reconcile target entity_id={result.entity_id} "
                        f"registry_ids=[{target_hits[result.entity_id]}, {result.registry_id}]"
                    )
                continue
            target_hits[result.entity_id] = result.registry_id
            ov = overrides.get(result.entity_id) or overrides.get(result.registry_id)
            observations.append(
                observation_from_registry_row(
                    row,
                    capability=capability,
                    entity_id=result.entity_id,
                    reconcile_method=result.method,
                    override=ov,
                )
            )

    stats = {
        "registry_rows_reconciled": len(observations),
        "unreconciled_count": len(unreconciled),
        "unreconciled_ids": unreconciled[:50],
        "duplicate_target_count": len(duplicate_targets),
        "duplicate_targets": duplicate_targets[:50],
        "methods": methods,
    }
    if strict and unreconciled:
        raise FreshnessIdentityError(
            f"unreconciled registry rows: {len(unreconciled)} sample={unreconciled[:5]}"
        )
    return observations, stats


def write_reports(
    output_dir: Path | str,
    *,
    seed_path: Path | str | None = None,
    registry_path: Path | str | None = None,
    as_of: datetime | None = None,
    sla_path: Path | str | None = None,
    strict: bool = True,
) -> tuple[dict[str, Path], dict[str, CapabilityReport], dict[str, Any]]:
    """Generate both capability reports under output_dir from canonical universe."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    as_of = as_of or datetime.now(UTC)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)
    sla_doc = load_sla_document(sla_path)

    seed = Path(seed_path) if seed_path else DEFAULT_SEED
    canonical_ids, universe = load_canonical_population(seed)
    seed_sha = universe.seed_sha256
    seed_str = str(Path(universe.seed_path))

    written: dict[str, Path] = {}
    reports: dict[str, CapabilityReport] = {}
    reconcile_by_cap: dict[str, Any] = {}

    for capability in CAPABILITIES:
        obs, stats = observations_from_registry(
            registry_path,
            capability=capability,
            universe=universe,
            strict=strict,
        )
        reconcile_by_cap[capability] = stats
        report = build_capability_report(
            obs,
            capability=capability,
            canonical_entity_ids=canonical_ids,
            as_of=as_of,
            sla_doc=sla_doc,
            strict_identity=strict,
            seed_path=seed_str,
            seed_sha256=seed_sha,
            universe_version=f"canonical-included-{len(canonical_ids)}",
        )
        path = out / REPORT_FILENAMES[capability]
        path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        written[capability] = path
        reports[capability] = report

    meta = {
        "canonical_count": len(canonical_ids),
        "canonical_ids_sha256": ordered_ids_sha256(canonical_ids),
        "seed_path": seed_str,
        "seed_sha256": seed_sha,
        "reconcile": reconcile_by_cap,
    }
    return written, reports, meta


def load_report(path: Path | str) -> dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"freshness report must be a JSON object: {path}")
    return raw


def report_content_fingerprint(report: Mapping[str, Any]) -> str:
    """Stable fingerprint of full sorted JSON."""
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path | str) -> str:
    return sha256_file(path)


def _resolve_git_dir(root: Path) -> Path | None:
    """Resolve .git directory, including git-worktree pointer files."""
    git_path = root / ".git"
    if git_path.is_dir():
        return git_path
    if git_path.is_file():
        try:
            content = git_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if content.startswith("gitdir:"):
            target = content.split(":", 1)[1].strip()
            path = Path(target)
            if not path.is_absolute():
                path = (root / path).resolve()
            return path if path.is_dir() else None
    return None


def _git_sha() -> str:
    """Resolve HEAD without shelling out (ruff S603/S607 safe)."""
    git_dir = _resolve_git_dir(_PROJECT_ROOT)
    if git_dir is None:
        return "unknown"
    try:
        head_path = git_dir / "HEAD"
        if not head_path.is_file():
            return "unknown"
        head = head_path.read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            ref_path = git_dir / ref
            if ref_path.is_file():
                return ref_path.read_text(encoding="utf-8").strip()
            # Common refs may live in the main repo for worktrees
            common = git_dir / "commondir"
            search_roots = [git_dir]
            if common.is_file():
                common_dir = Path(common.read_text(encoding="utf-8").strip())
                if not common_dir.is_absolute():
                    common_dir = (git_dir / common_dir).resolve()
                search_roots.append(common_dir)
                ref_path = common_dir / ref
                if ref_path.is_file():
                    return ref_path.read_text(encoding="utf-8").strip()
            for base in search_roots:
                packed = base / "packed-refs"
                if not packed.is_file():
                    continue
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) == 2 and parts[1] == ref:
                        return parts[0]
            return "unknown"
        return head
    except OSError:
        return "unknown"


def build_acceptance_manifest(
    *,
    seed_path: Path | str,
    registry_path: Path | str,
    as_of: datetime,
    sla_version: str,
    command: list[str],
    exit_code: int,
    written: Mapping[str, Path],
    reports: Mapping[str, CapabilityReport],
    meta: Mapping[str, Any],
) -> dict[str, Any]:
    """Sealed compact evidence for Git (ADR-020: full reports stay outside)."""
    editais_path = Path(written[CAPABILITY_EDITAIS])
    contracts_path = Path(written[CAPABILITY_CONTRACTS])
    editais_hash = file_sha256(editais_path)
    contracts_hash = file_sha256(contracts_path)

    e_report = reports[CAPABILITY_EDITAIS]
    c_report = reports[CAPABILITY_CONTRACTS]
    e_ids = {r.entity_id for r in e_report.entities}
    c_ids = {r.entity_id for r in c_report.entities}
    sets_equal = e_ids == c_ids

    unreconciled: list[str] = []
    for cap_stats in (meta.get("reconcile") or {}).values():
        if isinstance(cap_stats, dict):
            unreconciled.extend(cap_stats.get("unreconciled_ids") or [])

    return {
        "campaign": "ENTITY-FRESHNESS-CANONICAL-ACCEPTANCE-01",
        "git_sha": _git_sha(),
        "seed_path": str(seed_path),
        "seed_sha256": meta.get("seed_sha256") or file_sha256(seed_path),
        "registry_path": str(registry_path),
        "registry_sha256": file_sha256(registry_path),
        "as_of": _iso(as_of),
        "sla_version": sla_version,
        "command": list(command),
        "exit_code": exit_code,
        "adapter_version": ADAPTER_VERSION,
        "reports": {
            CAPABILITY_EDITAIS: {
                "path": str(editais_path),
                "sha256": editais_hash,
                "content_fingerprint": report_content_fingerprint(e_report.to_dict()),
                "denominator": e_report.denominator,
                "unique_entity_count": e_report.unique_entity_count,
                "status_counts": dict(e_report.status_counts),
                "covered": e_report.covered,
                "uncovered": e_report.uncovered,
                "breach_count": len(e_report.breaches),
            },
            CAPABILITY_CONTRACTS: {
                "path": str(contracts_path),
                "sha256": contracts_hash,
                "content_fingerprint": report_content_fingerprint(c_report.to_dict()),
                "denominator": c_report.denominator,
                "unique_entity_count": c_report.unique_entity_count,
                "status_counts": dict(c_report.status_counts),
                "covered": c_report.covered,
                "uncovered": c_report.uncovered,
                "breach_count": len(c_report.breaches),
            },
        },
        "identity": {
            "canonical_count": meta.get("canonical_count"),
            "canonical_ids_sha256": meta.get("canonical_ids_sha256"),
            "editais_ids_sha256": e_report.list_identity.observed_ids_sha256,
            "contracts_ids_sha256": c_report.list_identity.observed_ids_sha256,
            "sets_equal_across_capabilities": sets_equal,
            "duplicate_count": e_report.list_identity.duplicate_count
            + c_report.list_identity.duplicate_count,
            "missing_count": e_report.list_identity.missing_count
            + c_report.list_identity.missing_count,
            "extra_count": e_report.list_identity.extra_count
            + c_report.list_identity.extra_count,
            "list_identity_ok": e_report.list_identity.ok and c_report.list_identity.ok,
        },
        "unreconciled_ids": sorted(set(unreconciled)),
        "unreconciled_count": len(set(unreconciled)),
        "breaches_nominal": {
            CAPABILITY_EDITAIS: e_report.breaches[:20],
            CAPABILITY_CONTRACTS: c_report.breaches[:20],
            "note": "Full breach lists live in report JSON under output/coverage (ADR-020)",
        },
        "claims_allowed": list(e_report.claims_allowed),
        "claims_forbidden": list(e_report.claims_forbidden),
        "out_of_scope": [
            "migration_058",
            "entity_source_binding",
            "coverage_95",
            "recall_95",
            "LOCAL_READY",
            "VPS_OPERATIONAL",
            "PROJECT_DONE",
        ],
    }


def verify_manifest_against_reports(
    manifest: Mapping[str, Any],
    *,
    editais_path: Path | str,
    contracts_path: Path | str,
) -> list[str]:
    """Return blockers if report files no longer match sealed hashes."""
    blockers: list[str] = []
    reports = manifest.get("reports") or {}
    e_meta = reports.get(CAPABILITY_EDITAIS) or {}
    c_meta = reports.get(CAPABILITY_CONTRACTS) or {}
    e_hash = file_sha256(editais_path)
    c_hash = file_sha256(contracts_path)
    if e_meta.get("sha256") != e_hash:
        blockers.append("editais_sha256_mismatch")
    if c_meta.get("sha256") != c_hash:
        blockers.append("contracts_sha256_mismatch")
    return blockers


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Entity-level freshness by capability (canonical universe denominator)"
    )
    parser.add_argument(
        "--seed",
        type=Path,
        default=DEFAULT_SEED,
        help="Canonical seed spreadsheet (Extra - alvos de licitação. R-0.xlsx)",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="Path to entity_source_registry.jsonl (observations only)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Directory for freshness-editais.json and freshness-contracts.json",
    )
    parser.add_argument(
        "--sla",
        type=Path,
        default=DEFAULT_SLA_PATH,
        help="Path to coverage_slas.yaml",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="ISO timestamp for classification (default: now UTC)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if set identity, reconcile, or field completeness fails",
    )
    parser.add_argument(
        "--evidence-manifest",
        type=Path,
        default=None,
        help="Write sealed acceptance manifest JSON to this path",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    as_of = _parse_dt(args.as_of) if args.as_of else datetime.now(UTC)
    if as_of is None:
        print("ERROR: invalid --as-of", file=sys.stderr)
        return 1

    command = [
        "python",
        "-m",
        "scripts.coverage.freshness_by_entity",
        "--seed",
        str(args.seed),
        "--registry",
        str(args.registry),
        "--output-dir",
        str(args.output_dir),
        "--sla",
        str(args.sla),
        "--as-of",
        _iso(as_of) or "",
    ]
    if args.strict:
        command.append("--strict")
    if args.evidence_manifest:
        command.extend(["--evidence-manifest", str(args.evidence_manifest)])

    exit_code = 0
    try:
        written, reports, meta = write_reports(
            args.output_dir,
            seed_path=args.seed,
            registry_path=args.registry,
            as_of=as_of,
            sla_path=args.sla,
            strict=True,
        )
    except (FreshnessIdentityError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    editais = reports[CAPABILITY_EDITAIS].to_dict()
    contracts = reports[CAPABILITY_CONTRACTS].to_dict()
    canonical_ids, _universe = load_canonical_population(args.seed)
    blockers = evaluate_entity_freshness_reports(
        editais_report=editais,
        contracts_report=contracts,
        canonical_entity_ids=canonical_ids,
    )
    if args.strict and blockers:
        exit_code = 2

    sla_version = str(editais.get("sla_version") or "unknown")
    summary = {
        "written": {k: str(v) for k, v in written.items()},
        "seed_sha256": meta.get("seed_sha256"),
        "canonical_count": meta.get("canonical_count"),
        "canonical_ids_sha256": meta.get("canonical_ids_sha256"),
        "editais_unique": editais.get("unique_entity_count"),
        "contracts_unique": contracts.get("unique_entity_count"),
        "editais_status_counts": editais.get("status_counts"),
        "contracts_status_counts": contracts.get("status_counts"),
        "editais_breaches": len(editais.get("breaches") or []),
        "contracts_breaches": len(contracts.get("breaches") or []),
        "list_identity_ok": {
            CAPABILITY_EDITAIS: (editais.get("list_identity") or {}).get("ok"),
            CAPABILITY_CONTRACTS: (contracts.get("list_identity") or {}).get("ok"),
        },
        "blockers": blockers,
        "exit_code": exit_code,
    }

    if args.evidence_manifest is not None:
        manifest = build_acceptance_manifest(
            seed_path=args.seed,
            registry_path=args.registry,
            as_of=as_of,
            sla_version=sla_version,
            command=command,
            exit_code=exit_code,
            written=written,
            reports=reports,
            meta=meta,
        )
        man_path = Path(args.evidence_manifest)
        man_path.parent.mkdir(parents=True, exist_ok=True)
        man_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        summary["evidence_manifest"] = str(man_path)
        summary["report_hashes"] = {
            CAPABILITY_EDITAIS: manifest["reports"][CAPABILITY_EDITAIS]["sha256"],
            CAPABILITY_CONTRACTS: manifest["reports"][CAPABILITY_CONTRACTS]["sha256"],
        }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
