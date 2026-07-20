#!/usr/bin/env python3
"""Entity-level freshness by capability (editais / contracts).

Pure classification + dual report generation for the 1.093-entity universe.

Rules (ADR-028 / ENTITY-FRESHNESS-01):
  - One row per entity per capability report
  - Statuses: FRESH STALE NEVER INCOMPLETE BLOCKED NOT_APPLICABLE UNKNOWN
  - UNKNOWN/NEVER/BLOCKED/INCOMPLETE and unprovenanced rows never become FRESH
  - age_hours absence stays None (never coerced to 0)
  - Global MAX(ingested_at) must not promote individual entities
  - List identity: exactly EXPECTED_UNIVERSE distinct entity_ids

Usage::

    python3 -m scripts.coverage.freshness_by_entity \\
        --registry data/entity_source_registry.jsonl \\
        --output-dir output/coverage/
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

EXPECTED_UNIVERSE = 1093
UNIVERSE_VERSION = "extra-sc-raio-200km-v1"
ADAPTER_VERSION = "freshness_by_entity/1.0.0"
MIGRATION_VERSION = "058_entity_source_binding_capability"

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

# Statuses that must never be promoted / never count as covered fresh
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
    status_hint: str | None = None  # e.g. blocked binding


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
    expected: int
    unique_entity_count: int
    duplicate_count: int
    covered: int
    uncovered: int
    ok: bool
    reason: str = ""

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
    adapter_version: str = ADAPTER_VERSION
    migration_version: str = MIGRATION_VERSION
    universe_version: str = UNIVERSE_VERSION
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
            "adapter_version": self.adapter_version,
            "migration_version": self.migration_version,
            "universe_version": self.universe_version,
            "limitations": list(self.limitations),
            "claims_allowed": list(self.claims_allowed),
            "claims_forbidden": list(self.claims_forbidden),
        }


class FreshnessIdentityError(ValueError):
    """Raised when list identity fails (duplicates or wrong cardinality)."""


class FreshnessReportIncompleteError(ValueError):
    """Raised when a report is missing fields or incomplete for strict mode."""


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
        if line.endswith(":") and ":" == line[-1] and line.count(":") == 1:
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
    hours_key = str(cap_cfg.get("hours_key") or (
        "open_opportunities_hours"
        if capability == CAPABILITY_EDITAIS
        else "contracts_amendments_hours"
    ))
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
    """Provenance required for FRESH: run_id + content_hash + success timestamp."""
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
    """Classify one entity observation. Pure. Never promotes garbage to FRESH.

    Returns (freshness_status, age_hours).
    """
    age = calculate_age_hours(last_success_at, as_of=as_of)

    if applicability == "not_applicable":
        return "NOT_APPLICABLE", age

    if status_hint == "blocked" or status_hint == "BLOCKED":
        return "BLOCKED", age

    if partial_execution:
        return "INCOMPLETE", age

    if last_success_at is None:
        # Attempt without success → NEVER (not zero, not FRESH)
        return "NEVER", None

    if age is not None and age < 0:
        # Future timestamp — incomplete / unreliable
        return "INCOMPLETE", age

    provenanced = has_provenance(
        run_id=run_id,
        content_hash=content_hash,
        last_success_at=last_success_at,
    )
    if not provenanced:
        # Timestamp without provenance cannot be FRESH
        if age is not None and age <= float(sla_hours):
            return "INCOMPLETE", age
        if age is not None and age > float(sla_hours):
            return "STALE", age
        return "UNKNOWN", age

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

    # Fail-closed: never allow FRESH if hard non-fresh conditions
    if status == "FRESH" and not has_provenance(
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
        source_id=obs.source_id,  # explicit None preserved
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


def assert_list_identity(
    records: Sequence[EntityFreshnessRecord],
    *,
    expected: int = EXPECTED_UNIVERSE,
) -> ListIdentity:
    """Validate list identity. Raises FreshnessIdentityError on failure."""
    ids = [r.entity_id for r in records]
    unique = set(ids)
    dup = len(ids) - len(unique)
    covered = sum(1 for r in records if r.freshness_status == "FRESH")
    # NOT_APPLICABLE is neither covered nor "missing" in the freshness numerator;
    # uncovered = all non-FRESH (including N/A) for cardinality: covered+uncovered == n
    uncovered = len(records) - covered
    ok = (
        len(ids) == expected
        and len(unique) == expected
        and dup == 0
        and covered + uncovered == expected
    )
    reason = ""
    if len(unique) != expected:
        reason = f"unique_entity_count={len(unique)} expected={expected}"
    elif dup > 0:
        reason = f"duplicates={dup}"
    elif len(ids) != expected:
        reason = f"row_count={len(ids)} expected={expected}"
    identity = ListIdentity(
        expected=expected,
        unique_entity_count=len(unique),
        duplicate_count=dup,
        covered=covered,
        uncovered=uncovered,
        ok=ok,
        reason=reason,
    )
    if not ok:
        raise FreshnessIdentityError(
            f"list identity failed: {reason or 'unknown'}; "
            f"rows={len(ids)} unique={len(unique)} dups={dup}"
        )
    return identity


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


def build_capability_report(
    observations: Sequence[EntityObservation],
    *,
    capability: str,
    as_of: datetime | None = None,
    sla_doc: Mapping[str, Any] | None = None,
    expected_universe: int = EXPECTED_UNIVERSE,
    partial_execution: bool = False,
    strict_identity: bool = True,
    limitations: Sequence[str] | None = None,
) -> CapabilityReport:
    """Build dual-metric report for one capability. Deterministic for same inputs."""
    as_of = as_of or datetime.now(UTC)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)
    sla = resolve_sla(capability, sla_doc)

    # Dedup by entity_id preserving first occurrence order for determinism
    # (caller should pass stable sorted list)
    by_id: dict[str, EntityObservation] = {}
    for obs in observations:
        if obs.capability and obs.capability != capability:
            continue
        eid = str(obs.entity_id)
        if eid in by_id:
            if strict_identity:
                raise FreshnessIdentityError(f"duplicate entity_id in input: {eid}")
            continue
        by_id[eid] = obs

    # Sort for deterministic output
    ordered = [by_id[k] for k in sorted(by_id.keys())]
    records = [
        classify_observation(
            obs,
            sla=sla,
            as_of=as_of,
            partial_execution=partial_execution,
        )
        for obs in ordered
    ]

    status_counts: dict[str, int] = {s: 0 for s in sorted(ALLOWED_STATUSES)}
    for r in records:
        status_counts[r.freshness_status] = status_counts.get(r.freshness_status, 0) + 1

    if strict_identity:
        identity = assert_list_identity(records, expected=expected_universe)
    else:
        ids = [r.entity_id for r in records]
        unique = set(ids)
        covered = sum(1 for r in records if r.freshness_status == "FRESH")
        identity = ListIdentity(
            expected=expected_universe,
            unique_entity_count=len(unique),
            duplicate_count=len(ids) - len(unique),
            covered=covered,
            uncovered=len(records) - covered,
            ok=len(unique) == expected_universe and len(ids) == expected_universe,
            reason="" if len(unique) == expected_universe else "cardinality_mismatch",
        )

    claims_allowed = [
        "freshness é mensurável por entidade",
        f"{len(records)} entidades estão representadas neste relatório"
        if identity.ok
        else "relatório presente mas list identity inválida",
        "editais e contratos são separados",
        "estado observado e gaps são nominais",
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
        "MAX(ingested_at) global como freshness de 1.093 entidades",
    ]

    lim = list(limitations or [])
    lim.append(
        "Entity-level freshness; source-level MAX(ingested_at) does not promote entities"
    )
    lim.append(f"SLA version={sla.sla_version} sla_id={sla.sla_id} hours={sla.sla_hours}")

    return CapabilityReport(
        capability=capability,
        as_of=_iso(as_of) or as_of.isoformat(),
        sla_version=sla.sla_version,
        sla_id=sla.sla_id,
        sla_hours=sla.sla_hours,
        denominator=expected_universe,
        unique_entity_count=identity.unique_entity_count,
        status_counts=status_counts,
        covered=identity.covered,
        uncovered=identity.uncovered,
        list_identity=identity,
        entities=records,
        limitations=lim,
        claims_allowed=claims_allowed,
        claims_forbidden=claims_forbidden,
    )


def validate_capability_report_strict(report: CapabilityReport | Mapping[str, Any]) -> list[str]:
    """Return blockers if report is incomplete for strict consultive use."""
    blockers: list[str] = []
    data = report.to_dict() if isinstance(report, CapabilityReport) else dict(report)

    entities = data.get("entities") or []
    if not entities:
        blockers.append("freshness_report_empty")
        return blockers

    unique_ids = {str(e.get("entity_id")) for e in entities if isinstance(e, dict)}
    if len(entities) != EXPECTED_UNIVERSE:
        blockers.append(
            f"freshness_report_cardinality:{data.get('capability')}:{len(entities)}"
        )
    if len(unique_ids) != EXPECTED_UNIVERSE:
        blockers.append(
            f"freshness_report_unique:{data.get('capability')}:{len(unique_ids)}"
        )
    if len(entities) != len(unique_ids):
        blockers.append(f"freshness_report_duplicates:{data.get('capability')}")

    for e in entities:
        if not isinstance(e, dict):
            blockers.append("freshness_report_invalid_row")
            continue
        if not e.get("capability"):
            blockers.append("freshness_report_missing_capability")
        status = e.get("freshness_status")
        if status not in ALLOWED_STATUSES:
            blockers.append(f"freshness_report_invalid_status:{status}")
        if status == "FRESH":
            if not e.get("run_id") or not e.get("content_hash") or not e.get("last_success_at"):
                blockers.append("freshness_report_fresh_without_provenance")

    covered = int(data.get("covered") or 0)
    uncovered = int(data.get("uncovered") or 0)
    if covered + uncovered != EXPECTED_UNIVERSE and len(entities) == EXPECTED_UNIVERSE:
        blockers.append("freshness_report_covered_uncovered_mismatch")

    # Dedup
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
) -> list[str]:
    """Strict evaluation of both capability reports. Empty list = ok."""
    blockers: list[str] = []
    if editais_report is None:
        blockers.append("freshness_report_missing:notices_or_bids")
    else:
        blockers.extend(validate_capability_report_strict(editais_report))
    if contracts_report is None:
        blockers.append("freshness_report_missing:contracts")
    else:
        blockers.extend(validate_capability_report_strict(contracts_report))
    return blockers


# ---------------------------------------------------------------------------
# Registry / observation loading (capability-aware, provenance-preserving)
# ---------------------------------------------------------------------------

# Source ids that may back each capability observation. Contracts must not
# reuse notices-only promote rows (and vice-versa) — dual metric is observation-level.
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

# Evidence types that carry crawl provenance usable for freshness.
PROVENANCE_EVIDENCE_TYPES: frozenset[str] = frozenset(
    {
        "pipeline_evidence_promote",
    }
)


def load_entity_ids_from_registry(path: Path | str | None = None) -> list[str]:
    """Load ordered unique canonical_ids from JSONL registry (or seed CSV fallback)."""
    reg = Path(path) if path else DEFAULT_REGISTRY
    ids: list[str] = []
    if reg.is_file() and reg.suffix == ".jsonl":
        with reg.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                cid = row.get("canonical_id") or row.get("entity_id")
                if cid:
                    ids.append(str(cid))
        return ids

    seed = _PROJECT_ROOT / "config" / "target_entities_200km.csv"
    if seed.is_file():
        import csv

        with seed.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                cnpj = (row.get("cnpj") or "").strip()
                name = (row.get("canonical_name") or row.get("name") or "").strip()
                slug = (
                    name.upper()
                    .replace(" ", "_")
                    .replace("-", "_")
                    .replace("/", "_")
                )
                # Match builder convention when possible
                cid = row.get("canonical_id")
                if not cid:
                    cid = f"{cnpj}:{slug}" if cnpj else slug
                ids.append(str(cid))
        return ids

    raise FileNotFoundError(f"No registry or seed at {reg} / {seed}")


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
        # Pure contracts evidence, or mixed promote that includes contracts source
        return bool(srcs & cap_sources)
    # notices_or_bids: need at least one notices source; pure contracts-only does NOT match
    if ev_cap in {"notices_or_bids", "open_opportunities", "bids", "editais"}:
        return True
    srcs = _evidence_sources(ev)
    notices_hit = bool(srcs & CAPABILITY_SOURCE_IDS[CAPABILITY_EDITAIS])
    contracts_only = bool(srcs) and srcs <= CAPABILITY_SOURCE_IDS[CAPABILITY_CONTRACTS]
    if contracts_only:
        return False
    return notices_hit


def _extract_capability_evidence(
    row: Mapping[str, Any],
    capability: str,
) -> dict[str, Any] | None:
    """Pick the best per-entity evidence for one capability (never global MAX).

    Prefers pipeline_evidence_promote rows whose sources match the capability.
    Returns a flat dict with last_success_at, run_id, content_hash, raw_uri, source_id.
    """
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
        ts = _parse_dt(ev.get("last_seen_at") or ev.get("last_success_at") or ev.get("attempted_at"))
        if ts is None:
            # Provenance without timestamp still useful for incomplete classification
            ts = datetime.min.replace(tzinfo=UTC)
        candidates.append((ts, ev))

    if not candidates:
        return None

    # Most recent last_seen for this capability only
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_ts, best = candidates[0]
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
    """Use registry last_success_at only when plataformas imply this capability.

    Does not invent provenance (run_id/hash) — classifier will yield
    INCOMPLETE/STALE/NEVER rather than FRESH without hash+run.
    """
    last = _parse_dt(row.get("last_success_at"))
    if last is None:
        return None
    plats = {str(p) for p in (row.get("plataformas") or []) if p}
    cap_sources = CAPABILITY_SOURCE_IDS.get(capability, frozenset())
    if not (plats & cap_sources):
        return None
    # For contracts require explicit contracts platform — never promote from
    # notices-only last_success_at
    if capability == CAPABILITY_CONTRACTS:
        if not (plats & CAPABILITY_SOURCE_IDS[CAPABILITY_CONTRACTS]):
            return None
    return last


def observation_from_registry_row(
    row: Mapping[str, Any],
    *,
    capability: str,
    override: Mapping[str, Any] | None = None,
) -> EntityObservation:
    """Build one capability observation from a single ESR row. Pure-ish helper."""
    ov = dict(override or {})
    eid = str(row.get("canonical_id") or row.get("entity_id") or "")
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
        entity_id=eid,
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
    )


def observations_from_registry(
    path: Path | str | None = None,
    *,
    capability: str,
    per_entity_overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[EntityObservation]:
    """Build observations for every registry entity for one capability.

    - Reads per-entity ``pipeline_evidence_promote`` (run_id, raw_sha256, last_seen_at).
    - Capability filters sources: notices_or_bids vs contracts are observation-level.
    - Never applies a global MAX(ingested_at) to all entities.
    - Absence stays explicit (NEVER); timestamp without provenance → not FRESH.
    """
    if capability not in CAPABILITIES:
        raise ValueError(f"unknown capability: {capability}")

    reg = Path(path) if path else DEFAULT_REGISTRY
    overrides = dict(per_entity_overrides or {})
    observations: list[EntityObservation] = []

    if reg.is_file() and reg.suffix == ".jsonl":
        with reg.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                eid = str(row.get("canonical_id") or row.get("entity_id"))
                observations.append(
                    observation_from_registry_row(
                        row,
                        capability=capability,
                        override=overrides.get(eid),
                    )
                )
        return observations

    # Fallback: ids only (no evidence)
    for eid in load_entity_ids_from_registry(reg if reg.is_file() else None):
        ov = overrides.get(eid) or {}
        observations.append(
            EntityObservation(
                entity_id=eid,
                capability=capability,
                source_id=ov.get("source_id"),
                applicability=str(ov.get("applicability") or "unknown"),
                last_attempt_at=_parse_dt(ov.get("last_attempt_at")),
                last_success_at=_parse_dt(ov.get("last_success_at")),
                last_verified_at=_parse_dt(ov.get("last_verified_at")),
                run_id=ov.get("run_id"),
                raw_uri=ov.get("raw_uri"),
                artifact_ref=ov.get("artifact_ref"),
                content_hash=ov.get("content_hash"),
                blocker=ov.get("blocker"),
                next_action=ov.get("next_action"),
                status_hint=ov.get("status_hint"),
            )
        )
    return observations


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


def write_reports(
    output_dir: Path | str,
    *,
    registry_path: Path | str | None = None,
    as_of: datetime | None = None,
    sla_path: Path | str | None = None,
) -> dict[str, Path]:
    """Generate both capability reports under output_dir."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    as_of = as_of or datetime.now(UTC)
    sla_doc = load_sla_document(sla_path)
    written: dict[str, Path] = {}
    for capability in CAPABILITIES:
        obs = observations_from_registry(registry_path, capability=capability)
        report = build_capability_report(
            obs,
            capability=capability,
            as_of=as_of,
            sla_doc=sla_doc,
            expected_universe=EXPECTED_UNIVERSE,
            strict_identity=True,
        )
        path = out / REPORT_FILENAMES[capability]
        path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        written[capability] = path
    return written


def load_report(path: Path | str) -> dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"freshness report must be a JSON object: {path}")
    return raw


def report_content_fingerprint(report: Mapping[str, Any]) -> str:
    """Stable fingerprint ignoring wall-clock-only noise if any — full sorted JSON."""
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Entity-level freshness by capability (editais / contracts)"
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="Path to entity_source_registry.jsonl",
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
        help="Exit non-zero if reports fail list identity or field completeness",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    as_of = _parse_dt(args.as_of) if args.as_of else datetime.now(UTC)
    try:
        written = write_reports(
            args.output_dir,
            registry_path=args.registry,
            as_of=as_of,
            sla_path=args.sla,
        )
    except (FreshnessIdentityError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    editais = load_report(written[CAPABILITY_EDITAIS])
    contracts = load_report(written[CAPABILITY_CONTRACTS])
    blockers = evaluate_entity_freshness_reports(
        editais_report=editais,
        contracts_report=contracts,
    )
    print(
        json.dumps(
            {
                "written": {k: str(v) for k, v in written.items()},
                "editais_unique": editais.get("unique_entity_count"),
                "contracts_unique": contracts.get("unique_entity_count"),
                "editais_status_counts": editais.get("status_counts"),
                "contracts_status_counts": contracts.get("status_counts"),
                "blockers": blockers,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.strict and blockers:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
