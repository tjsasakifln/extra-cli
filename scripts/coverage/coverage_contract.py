"""Formal coverage contract — separate, non-conflated metrics.

This module defines the authoritative metric IDs and formulas for monitoring
coverage of the 200 km target universe. It deliberately SEPARATES commercial
signal from coverage:

  - ``entities_with_recent_commercial_signal`` is a commercial signal metric.
    It is NEVER labeled "coverage".
  - Real coverage metrics (source mapping, operational source, freshness)
    measure monitoring infrastructure health, not commercial opportunity count.

Denominator is FIXED at the canonical universe size (1093 when seed matches).
Never shrink the denominator to inflate percentages.
"""

from __future__ import annotations

import csv
import json
import os
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SLA_PATH = PROJECT_ROOT / "config" / "coverage_slas.yaml"
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "data" / "entity_source_registry.jsonl"
DEFAULT_ENTITIES_CSV = PROJECT_ROOT / "config" / "target_entities_200km.csv"
DEFAULT_SESSION_DIR = PROJECT_ROOT / "docs" / "ops" / "session-2026-07-17"
DEFAULT_OUTPUT_SESSION = PROJECT_ROOT / "output" / "session-2026-07-17"

# Historical fixed denominator. New code derives it, but when seed matches
# this value it is stamped as FIXED_CANONICAL_DENOMINATOR.
FIXED_CANONICAL_DENOMINATOR = 1093

# ---------------------------------------------------------------------------
# Metric IDs (constants — never rename commercial signal to "coverage")
# ---------------------------------------------------------------------------

METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL = "entities_with_recent_commercial_signal"
METRIC_SOURCE_MAPPING_COVERAGE = "source_mapping_coverage"
METRIC_OPERATIONAL_SOURCE_COVERAGE = "operational_source_coverage"
METRIC_FRESHNESS_COVERAGE = "freshness_coverage"
METRIC_OPPORTUNITY_RECALL = "opportunity_recall"
METRIC_REQUIRED_FIELD_COMPLETENESS = "required_field_completeness"

# Backward-compat alias for the commercial signal metric (NOT a coverage label).
LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY = "commercial_opportunity_any"

ALL_METRIC_IDS: tuple[str, ...] = (
    METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL,
    METRIC_SOURCE_MAPPING_COVERAGE,
    METRIC_OPERATIONAL_SOURCE_COVERAGE,
    METRIC_FRESHNESS_COVERAGE,
    METRIC_OPPORTUNITY_RECALL,
    METRIC_REQUIRED_FIELD_COMPLETENESS,
)

# Headline metric for session pipeline (commercial signal, not coverage).
HEADLINE_METRIC = METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL

# Decision fields for required_field_completeness.
# Absence is recorded explicitly — missing ≠ zero inventado.
DECISION_FIELDS: tuple[str, ...] = (
    "entity",
    "cnpj",
    "process",
    "edital",
    "objeto",
    "modalidade",
    "situacao",
    "datas",
    "valor",
    "local",
    "url",
    "docs",
    "fonte",
    "collected_at",
    "commercial_class",
    "sector_class",
    "ranking_evidence",
)

# Commercial statuses that count as recent commercial signal.
COMMERCIAL_SIGNAL_STATUSES: frozenset[str] = frozenset(
    {
        "OPEN_OPPORTUNITY",
        "UPCOMING_OPPORTUNITY",
        "RECENT_NOTICE",
        "OPEN",
        "UPCOMING",
        "RECENT",
    }
)

# Operational pipeline stages required for operational_source_coverage.
OPERATIONAL_STAGES: tuple[str, ...] = (
    "mapped",
    "accessible",
    "collected",
    "normalized",
    "reconciled",
    "verified_within_sla",
    "recent_evidence",
)


class MetricStatus(StrEnum):
    """Readiness of a metric computation."""

    READY = "READY"
    NOT_READY = "NOT_READY"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


class MetricKind(StrEnum):
    """Semantic kind — commercial signal is never kind=coverage."""

    COMMERCIAL_SIGNAL = "commercial_signal"
    COVERAGE = "coverage"
    RECALL = "recall"
    COMPLETENESS = "completeness"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


# Semantic contract for readiness labels (DoD §25).
READY_SEMANTICS = (
    "READY means the metric was executed against current inputs and validated "
    "(numerator/denominator/pct computed or explicitly unavailable fields set). "
    "Code existence alone never yields READY."
)
NOT_READY_SEMANTICS = (
    "NOT_READY means the metric could not be computed from available inputs "
    "(missing session, incomplete sample, entity-level gap, etc.)."
)
BLOCKED_SEMANTICS = (
    "BLOCKED means computation is impeded by an external or technical dependency "
    "(credentials, network, missing source access)."
)


@dataclass(frozen=True)
class MetricDefinition:
    """Immutable definition of one contract metric.

    Every catalog indicator MUST expose:
    definition, formula, denominator_policy, as_of_policy, source_policy,
    and readiness semantics (via status on MetricResult).
    """

    metric_id: str
    kind: MetricKind
    label: str
    definition: str
    formula: str
    denominator_policy: str
    as_of_policy: str
    source_policy: str
    target_pct: float | None
    notes: str = ""
    legacy_aliases: tuple[str, ...] = ()

    def required_fields_present(self) -> bool:
        return all(
            [
                bool(self.metric_id.strip()),
                bool(self.label.strip()),
                bool(self.definition.strip()),
                bool(self.formula.strip()),
                bool(self.denominator_policy.strip()),
                bool(self.as_of_policy.strip()),
                bool(self.source_policy.strip()),
            ]
        )


_AS_OF_POLICY = (
    "Report-level `as_of` (ISO date) on CoverageContractReport; "
    "metric values are interpreted at that cut date."
)
_DENOM_UNIVERSE = (
    "Fixed canonical universe size from load_canonical_universe / seed / "
    f"FIXED_CANONICAL_DENOMINATOR ({FIXED_CANONICAL_DENOMINATOR}); never reduced "
    "to inflate percentages."
)


METRIC_DEFINITIONS: dict[str, MetricDefinition] = {
    METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL: MetricDefinition(
        metric_id=METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL,
        kind=MetricKind.COMMERCIAL_SIGNAL,
        label="Entities with recent commercial signal",
        definition=(
            "Count of universe entities that have ≥1 matched opportunity in "
            "OPEN/UPCOMING/RECENT commercial statuses. Commercial signal only — "
            "never labeled coverage."
        ),
        formula=(
            "entities with ≥1 OPEN/UPCOMING/RECENT matched opportunity / "
            "canonical_universe_denominator"
        ),
        denominator_policy=_DENOM_UNIVERSE,
        as_of_policy=_AS_OF_POLICY,
        source_policy=(
            "session coverage_canonical commercial_entity_ids and/or PostgreSQL "
            "opportunity matches reconciled to universe entities."
        ),
        target_pct=None,
        notes=(
            "NOT a coverage metric. Renamed from commercial_opportunity_any. "
            "Do not label this as 'coverage'."
        ),
        legacy_aliases=(LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY,),
    ),
    METRIC_SOURCE_MAPPING_COVERAGE: MetricDefinition(
        metric_id=METRIC_SOURCE_MAPPING_COVERAGE,
        kind=MetricKind.COVERAGE,
        label="Source mapping coverage",
        definition=(
            "Share of universe entities with an explicit entity_source_registry "
            "record (including status=source_not_identified)."
        ),
        formula=(
            "entities with explicit source registry record "
            "(including status=source_not_identified) / denominator"
        ),
        denominator_policy=_DENOM_UNIVERSE,
        as_of_policy=_AS_OF_POLICY,
        source_policy="data/entity_source_registry.jsonl (+ optional DB sync).",
        target_pct=100.0,
        notes="Target 100%. Registry may mark source_not_identified — that still counts as mapped.",
    ),
    METRIC_OPERATIONAL_SOURCE_COVERAGE: MetricDefinition(
        metric_id=METRIC_OPERATIONAL_SOURCE_COVERAGE,
        kind=MetricKind.COVERAGE,
        label="Operational source coverage",
        definition=(
            "Share of universe entities with ≥1 official source that completed "
            "all operational pipeline stages (mapped→recent_evidence) within SLA."
        ),
        formula=(
            "entities with ≥1 official source: mapped + accessible + collected + "
            "normalized + reconciled + verified within SLA + recent evidence / denominator"
        ),
        denominator_policy=_DENOM_UNIVERSE,
        as_of_policy=_AS_OF_POLICY,
        source_policy=(
            "entity_source_registry operational stages + provenance "
            "(run_id, raw, hash, normalized, reconciliation)."
        ),
        target_pct=95.0,
        notes="Target 95%. Requires full operational pipeline stages.",
    ),
    METRIC_FRESHNESS_COVERAGE: MetricDefinition(
        metric_id=METRIC_FRESHNESS_COVERAGE,
        kind=MetricKind.COVERAGE,
        label="Freshness coverage",
        definition=(
            "Share of universe entities whose last verification is within the "
            "applicable SLA window from config/coverage_slas.yaml."
        ),
        formula="entities verified within applicable SLA / denominator",
        denominator_policy=_DENOM_UNIVERSE,
        as_of_policy=_AS_OF_POLICY,
        source_policy=(
            "entity-level last_seen_at / coverage_evidence.observed_at; "
            "source-level freshness_manifest alone is insufficient."
        ),
        target_pct=None,
        notes="SLA windows from config/coverage_slas.yaml.",
    ),
    METRIC_OPPORTUNITY_RECALL: MetricDefinition(
        metric_id=METRIC_OPPORTUNITY_RECALL,
        kind=MetricKind.RECALL,
        label="Opportunity recall",
        definition=(
            "Recall of relevant opportunities against an independent stratified "
            "gold sample — never inferred from raw DB opportunity counts."
        ),
        formula="true positives in stratified benchmark sample / sample positives",
        denominator_policy=(
            "Sample positives in the stratified gold benchmark (not universe size)."
        ),
        as_of_policy=_AS_OF_POLICY + " Sample version/date must be recorded in limitations.",
        source_policy="docs/qa/recall sample + independent labeling strata.",
        target_pct=None,
        notes=(
            "Computed from stratified benchmark sample ONLY. "
            "Never derived from database opportunity counts."
        ),
    ),
    METRIC_REQUIRED_FIELD_COMPLETENESS: MetricDefinition(
        metric_id=METRIC_REQUIRED_FIELD_COMPLETENESS,
        kind=MetricKind.COMPLETENESS,
        label="Required field completeness",
        definition=(
            "Mean completeness of decision fields across scored opportunity "
            "records; absence is explicit (missing ≠ invented zero)."
        ),
        formula=(
            "mean over opportunities of (present decision fields / "
            f"{len(DECISION_FIELDS)} decision fields); absence is explicit"
        ),
        denominator_policy=(
            f"{len(DECISION_FIELDS)} decision fields per opportunity record "
            "(field-level); report also records universe context separately."
        ),
        as_of_policy=_AS_OF_POLICY,
        source_policy="scored opportunity records from commercial/session pipeline.",
        target_pct=None,
        notes="Decision fields listed in DECISION_FIELDS. Missing fields are explicit absences.",
    ),
}


def validate_indicator_catalog() -> dict[str, Any]:
    """Return structural proof that every catalog indicator has required fields."""
    issues: list[dict[str, str]] = []
    for metric_id in ALL_METRIC_IDS:
        if metric_id not in METRIC_DEFINITIONS:
            issues.append(
                {"metric_id": metric_id, "issue": "missing_from_METRIC_DEFINITIONS"}
            )
            continue
        definition = METRIC_DEFINITIONS[metric_id]
        if not definition.required_fields_present():
            issues.append(
                {
                    "metric_id": metric_id,
                    "issue": "required_fields_blank",
                }
            )
        if definition.metric_id != metric_id:
            issues.append(
                {
                    "metric_id": metric_id,
                    "issue": "metric_id_mismatch",
                }
            )
    return {
        "ok": len(issues) == 0,
        "indicator_count": len(ALL_METRIC_IDS),
        "definitions": len(METRIC_DEFINITIONS),
        "ready_semantics": READY_SEMANTICS,
        "not_ready_semantics": NOT_READY_SEMANTICS,
        "blocked_semantics": BLOCKED_SEMANTICS,
        "required_fields": [
            "definition",
            "formula",
            "denominator_policy",
            "as_of_policy",
            "source_policy",
            "readiness_status_on_result",
        ],
        "issues": issues,
        "metric_ids": list(ALL_METRIC_IDS),
    }


def export_indicator_catalog() -> dict[str, Any]:
    """Machine-readable catalog for reports and DoD evidence."""
    catalog = validate_indicator_catalog()
    items = []
    for metric_id in ALL_METRIC_IDS:
        d = METRIC_DEFINITIONS[metric_id]
        items.append(
            {
                "metric_id": d.metric_id,
                "kind": d.kind.value,
                "label": d.label,
                "definition": d.definition,
                "formula": d.formula,
                "denominator_policy": d.denominator_policy,
                "as_of_policy": d.as_of_policy,
                "source_policy": d.source_policy,
                "target_pct": d.target_pct,
                "notes": d.notes,
                "legacy_aliases": list(d.legacy_aliases),
            }
        )
    catalog["items"] = items
    return catalog


@dataclass
class SLAConfig:
    """Configurable SLA windows for freshness and operational checks."""

    open_opportunities_hours: int = 24
    official_diaries_hours: int = 24
    contracts_amendments_hours: int = 72
    historical_consolidated_days: int = 7
    cadastral_data_days: int = 30

    def default_freshness_hours(self) -> int:
        """Most permissive operational freshness window for entity-level checks.

        Uses the open-opportunities SLA (tightest daily operational requirement)
        as the primary entity freshness gate for the contract report.
        """
        return int(self.open_opportunities_hours)

    def default_freshness_timedelta(self) -> timedelta:
        return timedelta(hours=self.default_freshness_hours())

    def historical_timedelta(self) -> timedelta:
        return timedelta(days=self.historical_consolidated_days)

    def cadastral_timedelta(self) -> timedelta:
        return timedelta(days=self.cadastral_data_days)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MetricResult:
    """Computed result for one contract metric."""

    metric_id: str
    kind: str
    label: str
    status: str
    numerator: int | float | None
    denominator: int | None
    pct: float | None
    formula: str
    target_pct: float | None = None
    reason: str | None = None
    limitations: list[str] = field(default_factory=list)
    sample_size: int | None = None
    field_breakdown: dict[str, Any] | None = None
    legacy_aliases: list[str] = field(default_factory=list)
    is_coverage_metric: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "pct": self.pct,
            "formula": self.formula,
            "target_pct": self.target_pct,
            "reason": self.reason,
            "limitations": list(self.limitations),
            "sample_size": self.sample_size,
            "field_breakdown": self.field_breakdown,
            "legacy_aliases": list(self.legacy_aliases),
            "is_coverage_metric": self.is_coverage_metric,
        }


@dataclass
class DenominatorResolution:
    """How the fixed denominator was obtained."""

    value: int
    source: str
    fixed_canonical: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CoverageContractReport:
    """Full contract report with all separate metrics."""

    generated_at: str
    as_of: str
    denominator: DenominatorResolution
    slas: dict[str, Any]
    metrics: dict[str, dict[str, Any]]
    headline_metric: str
    headline_is_coverage: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "as_of": self.as_of,
            "denominator": self.denominator.to_dict(),
            "slas": self.slas,
            "headline_metric": self.headline_metric,
            "headline_is_coverage": self.headline_is_coverage,
            "metrics": self.metrics,
            "metric_order": list(ALL_METRIC_IDS),
            "notes": list(self.notes),
            # Backward-compat field: same commercial signal under legacy name.
            "legacy_aliases": {
                LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY: METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL,
            },
        }


# ---------------------------------------------------------------------------
# SLA loading
# ---------------------------------------------------------------------------


def load_sla_config(path: Path | str | None = None) -> SLAConfig:
    """Load SLA windows from YAML. Falls back to defaults if file missing."""
    sla_path = Path(path) if path else DEFAULT_SLA_PATH
    if not sla_path.is_file():
        return SLAConfig()

    raw: dict[str, Any]
    try:
        import yaml  # type: ignore[import-untyped]

        with sla_path.open(encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
        if not isinstance(loaded, dict):
            return SLAConfig()
        raw = loaded
    except ImportError:
        raw = _parse_simple_yaml(sla_path.read_text(encoding="utf-8"))
    except Exception:
        return SLAConfig()

    return SLAConfig(
        open_opportunities_hours=int(raw.get("open_opportunities_hours", 24)),
        official_diaries_hours=int(raw.get("official_diaries_hours", 24)),
        contracts_amendments_hours=int(raw.get("contracts_amendments_hours", 72)),
        historical_consolidated_days=int(raw.get("historical_consolidated_days", 7)),
        cadastral_data_days=int(raw.get("cadastral_data_days", 30)),
    )


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Minimal YAML subset parser (key: int) for environments without PyYAML."""
    result: dict[str, Any] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip().split("#", 1)[0].strip()
        if not key:
            continue
        try:
            result[key] = int(value)
        except ValueError:
            try:
                result[key] = float(value)
            except ValueError:
                result[key] = value
    return result


# ---------------------------------------------------------------------------
# Denominator resolution
# ---------------------------------------------------------------------------


def resolve_denominator(
    *,
    conn: Any | None = None,
    seed_path: Path | str | None = None,
    csv_path: Path | str | None = None,
    prefer_fixed_when_match: bool = True,
) -> DenominatorResolution:
    """Resolve universe denominator without gaming percentages.

    Preference order:
      1. ``scripts.lib.universe.load_canonical_universe`` (seed spreadsheet)
      2. DB count: sc_public_entities WHERE is_active AND raio_200km
      3. CSV ``config/target_entities_200km.csv``

    When the resolved count equals FIXED_CANONICAL_DENOMINATOR (1093), the
    result is stamped as fixed_canonical=True. The denominator is NEVER
    reduced to improve a percentage.
    """
    # 1) Canonical universe seed
    try:
        from scripts.lib.universe import (  # noqa: WPS433
            CANONICAL_UNIVERSE,
            load_canonical_universe,
        )

        kwargs: dict[str, Any] = {}
        if seed_path is not None:
            kwargs["seed_path"] = seed_path
        if conn is not None:
            kwargs["conn"] = conn
        universe = load_canonical_universe(**kwargs)
        # Prefer included (within radius); fall back to conservative population.
        count = len(universe.included) or len(universe.conservative_monitoring_population)
        if count > 0:
            fixed = prefer_fixed_when_match and count == FIXED_CANONICAL_DENOMINATOR
            # Stamp historical constant when it matches
            if fixed:
                count = FIXED_CANONICAL_DENOMINATOR
            elif prefer_fixed_when_match and count == getattr(CANONICAL_UNIVERSE, "__int__", lambda: CANONICAL_UNIVERSE)():
                count = int(CANONICAL_UNIVERSE)
                fixed = count == FIXED_CANONICAL_DENOMINATOR
            return DenominatorResolution(
                value=count,
                source="load_canonical_universe",
                fixed_canonical=fixed or count == FIXED_CANONICAL_DENOMINATOR,
                notes=(
                    f"seed={universe.seed_path}; sha256={universe.seed_sha256[:12]}…; "
                    f"included={len(universe.included)}"
                ),
            )
    except FileNotFoundError as exc:
        seed_error = str(exc)
    except Exception as exc:  # seed missing / openpyxl / parse errors
        seed_error = f"{type(exc).__name__}: {exc}"
    else:
        seed_error = "empty_included_set"

    # 2) Database
    if conn is not None:
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*) FROM sc_public_entities
                WHERE is_active = TRUE AND raio_200km = TRUE
                """
            )
            row = cur.fetchone()
            cur.close()
            count = int(row[0]) if row else 0
            if count > 0:
                return DenominatorResolution(
                    value=count,
                    source="sc_public_entities.is_active_and_raio_200km",
                    fixed_canonical=count == FIXED_CANONICAL_DENOMINATOR,
                    notes=f"seed_fallback_reason={seed_error}",
                )
        except Exception as exc:
            db_error = f"{type(exc).__name__}: {exc}"
        else:
            db_error = "db_count_zero"
    else:
        db_error = "no_db_connection"

    # 3) CSV fallback
    entities_csv = Path(csv_path) if csv_path else DEFAULT_ENTITIES_CSV
    if entities_csv.is_file():
        with entities_csv.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            count = sum(1 for _ in reader)
        if count > 0:
            return DenominatorResolution(
                value=count,
                source=str(entities_csv.relative_to(PROJECT_ROOT))
                if entities_csv.is_relative_to(PROJECT_ROOT)
                else str(entities_csv),
                fixed_canonical=count == FIXED_CANONICAL_DENOMINATOR,
                notes=f"seed_fallback={seed_error}; db_fallback={db_error}",
            )

    # Last resort: fixed canonical constant (explicit limitation)
    return DenominatorResolution(
        value=FIXED_CANONICAL_DENOMINATOR,
        source="FIXED_CANONICAL_DENOMINATOR_constant",
        fixed_canonical=True,
        notes=(
            f"All resolvers failed (seed={seed_error}; db={db_error}; "
            f"csv_missing={not entities_csv.is_file()}). Using historical 1093."
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pct(numerator: int | float, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator) * 100.0, 2)


def _not_ready(
    metric_id: str,
    reason: str,
    *,
    denominator: int | None = None,
    limitations: list[str] | None = None,
) -> MetricResult:
    definition = METRIC_DEFINITIONS[metric_id]
    return MetricResult(
        metric_id=metric_id,
        kind=definition.kind.value,
        label=definition.label,
        status=MetricStatus.NOT_READY.value,
        numerator=None,
        denominator=denominator,
        pct=None,
        formula=definition.formula,
        target_pct=definition.target_pct,
        reason=reason,
        limitations=list(limitations or []),
        legacy_aliases=list(definition.legacy_aliases),
        is_coverage_metric=definition.kind == MetricKind.COVERAGE,
    )


def _ready(
    metric_id: str,
    numerator: int | float,
    denominator: int,
    *,
    limitations: list[str] | None = None,
    sample_size: int | None = None,
    field_breakdown: dict[str, Any] | None = None,
    reason: str | None = None,
) -> MetricResult:
    definition = METRIC_DEFINITIONS[metric_id]
    return MetricResult(
        metric_id=metric_id,
        kind=definition.kind.value,
        label=definition.label,
        status=MetricStatus.READY.value,
        numerator=numerator,
        denominator=denominator,
        pct=_pct(numerator, denominator),
        formula=definition.formula,
        target_pct=definition.target_pct,
        reason=reason,
        limitations=list(limitations or []),
        sample_size=sample_size,
        field_breakdown=field_breakdown,
        legacy_aliases=list(definition.legacy_aliases),
        is_coverage_metric=definition.kind == MetricKind.COVERAGE,
    )


def _find_session_dir(explicit: Path | str | None = None) -> Path | None:
    if explicit is not None:
        p = Path(explicit)
        return p if p.is_dir() else None
    for candidate in (DEFAULT_SESSION_DIR, DEFAULT_OUTPUT_SESSION):
        if candidate.is_dir():
            return candidate
    # Latest output/session-* directory
    out = PROJECT_ROOT / "output"
    if out.is_dir():
        sessions = sorted(out.glob("session-*"), reverse=True)
        for s in sessions:
            if s.is_dir():
                return s
    return None


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def _parse_ts(value: Any) -> datetime | None:
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
        try:
            d = date.fromisoformat(text[:10])
            return datetime(d.year, d.month, d.day, tzinfo=UTC)
        except ValueError:
            return None


def _field_present(record: dict[str, Any], field_name: str) -> bool:
    """Return True when a decision field has a non-empty value.

    Supports both flat keys and nested commercial/sector dicts. Absence is
    explicit: missing key, None, empty string, empty list/dict → False.
    """
    aliases: dict[str, tuple[str, ...]] = {
        "entity": ("entity", "entity_id", "canonical_entity_id", "orgao_nome", "razao_social"),
        "cnpj": ("cnpj", "cnpj_8", "orgao_cnpj"),
        "process": ("process", "processo", "numero_processo", "process_id"),
        "edital": ("edital", "numero_edital", "edital_number"),
        "objeto": ("objeto", "title", "objeto_compra", "objetoCompra"),
        "modalidade": ("modalidade", "modalidade_nome"),
        "situacao": ("situacao", "status_official", "commercial_status", "status"),
        "datas": (
            "datas",
            "publication_date",
            "data_publicacao",
            "data_abertura",
            "data_encerramento",
            "dataAberturaProposta",
            "dataEncerramentoProposta",
        ),
        "valor": ("valor", "valor_estimado", "valor_total", "value"),
        "local": ("local", "municipio", "uf", "localidade"),
        "url": ("url", "link", "link_pncp", "linkSistemaOrigem"),
        "docs": ("docs", "documents", "document_urls", "anexos"),
        "fonte": ("fonte", "source", "source_id"),
        "collected_at": ("collected_at", "generated_at", "ingested_at"),
        "commercial_class": ("commercial_class", "commercial_status", "commercial"),
        "sector_class": ("sector_class", "sector", "sector_match"),
        "ranking_evidence": ("ranking_evidence", "score", "ranking", "recommendation"),
    }
    keys = aliases.get(field_name, (field_name,))
    for key in keys:
        if key not in record:
            continue
        val = record[key]
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        if isinstance(val, (list, dict)) and len(val) == 0:
            continue
        if isinstance(val, dict):
            # Nested commercial/sector objects count if they carry status/score
            if any(v not in (None, "", [], {}) for v in val.values()):
                return True
            continue
        return True
    return False


def compute_field_completeness(
    records: list[dict[str, Any]],
    fields: tuple[str, ...] = DECISION_FIELDS,
) -> dict[str, Any]:
    """Mean completeness of decision fields; absence is explicit.

    Returns numerator as mean filled-ratio * 100 (percentage points scale via
    pct), denominator as number of decision fields, plus per-field rates.
    """
    if not records:
        return {
            "mean_completeness_pct": None,
            "records": 0,
            "fields": list(fields),
            "per_field": {f: {"present": 0, "absent": 0, "rate_pct": None} for f in fields},
            "per_record_ratios": [],
        }

    per_field_present: dict[str, int] = {f: 0 for f in fields}
    per_record_ratios: list[float] = []

    for rec in records:
        present_count = 0
        for f in fields:
            ok = _field_present(rec, f)
            if ok:
                per_field_present[f] += 1
                present_count += 1
        per_record_ratios.append(present_count / len(fields))

    n = len(records)
    per_field: dict[str, Any] = {}
    for f in fields:
        present = per_field_present[f]
        absent = n - present
        per_field[f] = {
            "present": present,
            "absent": absent,
            "rate_pct": round(present / n * 100.0, 2) if n else None,
            "absence_explicit": True,
        }

    mean_ratio = sum(per_record_ratios) / n if n else 0.0
    return {
        "mean_completeness_pct": round(mean_ratio * 100.0, 2),
        "records": n,
        "fields": list(fields),
        "field_count": len(fields),
        "per_field": per_field,
        "per_record_ratios": per_record_ratios,
    }


# ---------------------------------------------------------------------------
# Individual metric calculators
# ---------------------------------------------------------------------------


def compute_commercial_signal(
    denominator: int,
    *,
    session_dir: Path | None = None,
    conn: Any | None = None,
    commercial_entity_ids: set[int] | None = None,
) -> MetricResult:
    """entities_with_recent_commercial_signal — NOT a coverage metric."""
    metric_id = METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL
    limitations: list[str] = []

    if commercial_entity_ids is not None:
        num = len(commercial_entity_ids)
        return _ready(
            metric_id,
            num,
            denominator,
            reason="computed_from_provided_entity_id_set",
        )

    # Session artifact path
    sess = session_dir or _find_session_dir()
    if sess is not None:
        canonical = _load_json(sess / "coverage_canonical.json")
        if canonical:
            ids = canonical.get("commercial_entity_ids")
            if isinstance(ids, list) and ids:
                num = len({int(x) for x in ids})
                limitations.append(f"source=session_artifact:{sess / 'coverage_canonical.json'}")
                return _ready(
                    metric_id,
                    num,
                    denominator,
                    limitations=limitations,
                    reason="session_coverage_canonical.commercial_entity_ids",
                )
            # Fall back to metric list
            for met in canonical.get("metrics") or []:
                name = met.get("name") or met.get("metric_id")
                if name in (
                    METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL,
                    LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY,
                ):
                    num = int(met.get("numerator") or 0)
                    limitations.append(
                        f"source=session_metric:{name}; "
                        "legacy alias commercial_opportunity_any accepted"
                    )
                    return _ready(
                        metric_id,
                        num,
                        denominator,
                        limitations=limitations,
                        reason=f"session_metric:{name}",
                    )
            if canonical.get("commercial_numerator") is not None:
                num = int(canonical["commercial_numerator"])
                limitations.append("source=session_commercial_numerator")
                return _ready(
                    metric_id,
                    num,
                    denominator,
                    limitations=limitations,
                    reason="session_commercial_numerator",
                )

        covered = _iter_jsonl(sess / "entities_covered.jsonl")
        if covered:
            # Prefer commercial_covered flag when present
            ids_set: set[int] = set()
            for row in covered:
                if row.get("commercial_covered") is False:
                    continue
                eid = row.get("entity_id") or row.get("canonical_entity_id")
                if eid is not None:
                    ids_set.add(int(eid))
            if ids_set:
                limitations.append(f"source=entities_covered.jsonl:{sess}")
                return _ready(
                    metric_id,
                    len(ids_set),
                    denominator,
                    limitations=limitations,
                    reason="session_entities_covered_jsonl",
                )

    # DB fallback: entities with is_covered on raio_200km (weaker proxy)
    if conn is not None:
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(DISTINCT e.id)
                FROM sc_public_entities e
                JOIN entity_coverage ec ON e.id = ec.entity_id
                WHERE e.is_active = TRUE
                  AND e.raio_200km = TRUE
                  AND ec.is_covered = TRUE
                """
            )
            row = cur.fetchone()
            cur.close()
            num = int(row[0]) if row else 0
            limitations.append(
                "DB proxy via entity_coverage.is_covered — weaker than "
                "OPEN/UPCOMING/RECENT commercial classification"
            )
            return _ready(
                metric_id,
                num,
                denominator,
                limitations=limitations,
                reason="db_entity_coverage_is_covered_proxy",
            )
        except Exception as exc:
            return _not_ready(
                metric_id,
                reason=f"db_query_failed: {type(exc).__name__}: {exc}",
                denominator=denominator,
            )

    return _not_ready(
        metric_id,
        reason=(
            "No commercial signal source available "
            "(no session artifacts, no commercial_entity_ids, no DB)"
        ),
        denominator=denominator,
    )


def compute_source_mapping_coverage(
    denominator: int,
    *,
    registry_path: Path | str | None = None,
) -> MetricResult:
    """% of entities with an explicit source registry record.

    Records with status ``source_not_identified`` still count as mapped.
    If the registry file does not exist, returns NOT_READY (never invent 0%).
    """
    metric_id = METRIC_SOURCE_MAPPING_COVERAGE
    path = Path(registry_path) if registry_path else DEFAULT_REGISTRY_PATH

    if not path.is_file():
        return _not_ready(
            metric_id,
            reason=(
                f"entity source registry not found at {path}. "
                "Metric is NOT_READY — do not treat as 0% covered. "
                "Await sibling agent producing data/entity_source_registry.jsonl."
            ),
            denominator=denominator,
            limitations=["registry_file_missing"],
        )

    rows = _iter_jsonl(path)
    if not rows:
        # Empty file is distinct from missing: explicit zero after registry exists
        return _ready(
            metric_id,
            0,
            denominator,
            reason="registry_exists_but_empty",
            limitations=[f"registry={path}"],
        )

    # Count distinct entities that have ANY registry record.
    entity_keys: set[str] = set()
    for row in rows:
        key = (
            row.get("entity_id")
            or row.get("canonical_entity_id")
            or row.get("canonical_id")
            or row.get("cnpj_8")
            or row.get("cnpj")
            or row.get("identity_key")
        )
        if key is not None and str(key).strip():
            entity_keys.add(str(key).strip())

    return _ready(
        metric_id,
        len(entity_keys),
        denominator,
        reason="entity_source_registry.jsonl",
        limitations=[f"registry={path}", f"records={len(rows)}"],
    )


def compute_operational_source_coverage(
    denominator: int,
    slas: SLAConfig,
    *,
    conn: Any | None = None,
    session_dir: Path | None = None,
    as_of: datetime | None = None,
    registry_path: Path | None = None,
) -> MetricResult:
    """Entities with ≥1 official source through full operational pipeline.

    Prefer entity source registry operational statuses over commercial-signal proxies.
    Never treat entities_with_recent_commercial_signal as operational coverage.
    """
    metric_id = METRIC_OPERATIONAL_SOURCE_COVERAGE
    now = as_of or datetime.now(UTC)
    limitations: list[str] = []

    # 0) Entity source registry — ONLY verified/operational with complete,
    # recent and auditable evidence. `accessible`/`collected` are intermediate
    # states and never satisfy §3.2 by themselves.
    reg_path = Path(registry_path) if registry_path else DEFAULT_REGISTRY_PATH
    if reg_path.exists():
        operational_statuses = {"verified", "operational"}
        try:
            covered_entities: set[str] = set()
            total = 0
            dry_run_false_positives = 0
            accessible_only = 0
            with reg_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    total += 1
                    row = json.loads(line)
                    st = str(row.get("access_status") or "").lower()
                    if st == "accessible":
                        accessible_only += 1
                    if st not in operational_statuses:
                        continue
                    evidences = row.get("evidences") or []
                    required_stages = {
                        "mapped",
                        "accessible",
                        "collected",
                        "normalized",
                        "reconciled",
                        "verified_within_sla",
                    }
                    complete_evidence = any(
                        isinstance(e, dict)
                        and e.get("dry_run") is False
                        and required_stages.issubset((e.get("stages") or {}).keys())
                        and all((e.get("stages") or {}).get(stage) is True for stage in required_stages)
                        and bool(e.get("pipeline_run_id") or e.get("run_id"))
                        and bool(e.get("raw_uri"))
                        and bool(e.get("raw_sha256"))
                        and bool(e.get("normalized_record_ids"))
                        and bool(e.get("reconciliation_id"))
                        for e in evidences
                    )
                    only_dry_run_probe = any(
                        isinstance(e, dict)
                        and (e.get("dry_run") is True or e.get("use_network") is False)
                        and e.get("type") in {"pncp_orgao_probe", "ciga_municipio_expand"}
                        for e in evidences
                    ) and not complete_evidence
                    if only_dry_run_probe:
                        dry_run_false_positives += 1
                        continue
                    if not row.get("last_success_at"):
                        continue
                    if not complete_evidence:
                        dry_run_false_positives += 1
                        continue
                    last_success = _parse_ts(row.get("last_success_at"))
                    sla_hours = int(row.get("sla_hours") or slas.default_freshness_hours())
                    if last_success is None or last_success < now - timedelta(hours=sla_hours):
                        continue
                    entity_key = (
                        row.get("canonical_id")
                        or row.get("canonical_entity_id")
                        or row.get("entity_id")
                    )
                    if entity_key:
                        covered_entities.add(str(entity_key))
            if total > 0:
                limitations.append(
                    "Operational = verified/operational with seven stages true, "
                    "per-source SLA, run/raw/hash/normalized/reconciliation provenance. "
                    f"accessible_only_excluded={accessible_only}; "
                    f"dry_run_rejected={dry_run_false_positives}; registry_rows={total}. "
                    "Mapped/accessible ≠ §3.2 pipeline."
                )
                return _ready(
                    metric_id,
                    len(covered_entities),
                    denominator,
                    limitations=limitations,
                    reason="entity_source_registry_strict_operational",
                )
        except (OSError, json.JSONDecodeError) as exc:
            limitations.append(f"registry_read_error: {type(exc).__name__}: {exc}")

    # No registry proof means no defensible operational claim. Historical
    # ``entity_coverage`` rows and session opportunity lists are deliberately
    # not accepted as substitutes for the seven-stage evidence contract.
    return _not_ready(
        metric_id,
        reason=(
            "No usable entity-source registry evidence with all seven stages, "
            "per-source SLA and auditable provenance. Proxy counts are forbidden."
        ),
        denominator=denominator,
        limitations=limitations + [
            "entity_coverage_and_session_proxies_rejected",
            "requires_run_raw_hash_normalized_and_reconciliation_ids",
        ],
    )

    # Legacy fallbacks retained below for backwards code archaeology only;
    # fail-closed return above prevents them from producing operational claims.
    if conn is not None:
        try:
            cur = conn.cursor()
            # Prefer coverage_evidence success states within SLA when table exists.
            freshness_hours = slas.default_freshness_hours()
            try:
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT e.id)
                    FROM sc_public_entities e
                    JOIN coverage_evidence ce ON ce.entity_id = e.id
                    WHERE e.is_active = TRUE
                      AND e.raio_200km = TRUE
                      AND ce.evidence_state LIKE 'success%%'
                      AND ce.observed_at >= (NOW() - (%s || ' hours')::interval)
                    """,
                    (str(freshness_hours),),
                )
                row = cur.fetchone()
                num = int(row[0]) if row else 0
                cur.close()
                limitations.append(
                    "operational stages approximated via coverage_evidence "
                    f"success_* within {freshness_hours}h SLA"
                )
                return _ready(
                    metric_id,
                    num,
                    denominator,
                    limitations=limitations,
                    reason="coverage_evidence_success_within_sla",
                )
            except Exception as evidence_exc:
                # Fall back to entity_coverage.is_covered + last_seen within SLA
                limitations.append(
                    f"coverage_evidence query unavailable: {type(evidence_exc).__name__}"
                )
                with suppress(Exception):
                    conn.rollback()
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT e.id)
                    FROM sc_public_entities e
                    JOIN entity_coverage ec ON e.id = ec.entity_id
                    WHERE e.is_active = TRUE
                      AND e.raio_200km = TRUE
                      AND ec.is_covered = TRUE
                      AND ec.last_seen_at IS NOT NULL
                      AND ec.last_seen_at >= (NOW() - (%s || ' hours')::interval)
                    """,
                    (str(freshness_hours),),
                )
                row = cur.fetchone()
                num = int(row[0]) if row else 0
                cur.close()
                limitations.append(
                    "coverage_evidence unavailable; approximated via "
                    f"entity_coverage.is_covered + last_seen_at ≤ {freshness_hours}h. "
                    "Stages mapped/accessible/collected/normalized/reconciled not fully verified."
                )
                return _ready(
                    metric_id,
                    num,
                    denominator,
                    limitations=limitations,
                    reason="entity_coverage_is_covered_fresh_proxy",
                )
        except Exception as exc:
            limitations.append(f"db_error: {type(exc).__name__}: {exc}")

    # Session artifact fallback with honest limitations
    sess = session_dir or _find_session_dir()
    if sess is not None:
        covered = _iter_jsonl(sess / "entities_covered.jsonl")
        if covered:
            # Count commercial-covered as weak operational proxy
            ids = {
                int(r["entity_id"])
                for r in covered
                if r.get("entity_id") is not None
                and r.get("commercial_covered", r.get("is_covered", True))
            }
            limitations.append(
                f"DB unavailable or failed; session artifact proxy at {sess}. "
                "Does NOT prove mapped+accessible+collected+normalized+reconciled+verified. "
                "Honest limitation: operational stages not fully evidenced."
            )
            return _ready(
                metric_id,
                len(ids),
                denominator,
                limitations=limitations,
                reason="session_entities_covered_proxy",
            )

        summary = _load_json(sess / "session_summary.json")
        if summary and summary.get("final_db_covered") is not None:
            num = int(summary["final_db_covered"])
            limitations.append(
                f"DB unavailable; session_summary.final_db_covered proxy at {sess}. "
                "Operational stages not fully evidenced."
            )
            return _ready(
                metric_id,
                num,
                denominator,
                limitations=limitations,
                reason="session_summary_final_db_covered_proxy",
            )

    if conn is None and sess is None:
        return _not_ready(
            metric_id,
            reason=(
                "Database unavailable and no session artifacts found. "
                "Cannot compute operational_source_coverage."
            ),
            denominator=denominator,
            limitations=limitations,
        )

    return _not_ready(
        metric_id,
        reason="Unable to compute operational_source_coverage from available sources",
        denominator=denominator,
        limitations=limitations,
    )


def compute_freshness_coverage(
    denominator: int,
    slas: SLAConfig,
    *,
    conn: Any | None = None,
    session_dir: Path | None = None,
    as_of: datetime | None = None,
) -> MetricResult:
    """% of entities verified within applicable SLA."""
    metric_id = METRIC_FRESHNESS_COVERAGE
    now = as_of or datetime.now(UTC)
    freshness_hours = slas.default_freshness_hours()
    # For entity-level last_seen, use historical_consolidated window as a
    # more realistic default when daily open-opp SLA is too tight for legacy data.
    # Contract still exposes both: primary gate = open_opportunities_hours.
    limitations: list[str] = []

    if conn is not None:
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(DISTINCT e.id)
                FROM sc_public_entities e
                JOIN entity_coverage ec ON e.id = ec.entity_id
                WHERE e.is_active = TRUE
                  AND e.raio_200km = TRUE
                  AND ec.last_seen_at IS NOT NULL
                  AND ec.last_seen_at >= (NOW() - (%s || ' hours')::interval)
                """,
                (str(freshness_hours),),
            )
            row = cur.fetchone()
            num = int(row[0]) if row else 0
            cur.close()
            limitations.append(f"SLA window = open_opportunities_hours ({freshness_hours}h)")
            return _ready(
                metric_id,
                num,
                denominator,
                limitations=limitations,
                reason="entity_coverage.last_seen_at_within_sla",
            )
        except Exception as exc:
            limitations.append(f"db_error: {type(exc).__name__}: {exc}")

    sess = session_dir or _find_session_dir()
    if sess is not None:
        # Prefer freshness_manifest if present
        manifest = _load_json(sess / "freshness_manifest.json")
        if manifest:
            limitations.append(
                f"session freshness_manifest at {sess}; not entity-level SLA rollup"
            )
            # Manifest is source-level, not entity-level — mark PARTIAL/NOT_READY
            return _not_ready(
                metric_id,
                reason=(
                    "freshness_manifest.json is source-level, not entity-level. "
                    "Entity freshness requires entity_coverage.last_seen_at or "
                    "coverage_evidence.observed_at."
                ),
                denominator=denominator,
                limitations=limitations,
            )

        covered = _iter_jsonl(sess / "entities_covered.jsonl")
        if covered:
            cutoff = now - timedelta(hours=freshness_hours)
            fresh = 0
            for row in covered:
                ts = _parse_ts(row.get("last_seen") or row.get("last_seen_at"))
                if ts is not None and ts >= cutoff:
                    fresh += 1
            limitations.append(
                f"session entities_covered.jsonl last_seen within {freshness_hours}h; "
                "only covered entities inspected — uncovered treated as not fresh"
            )
            return _ready(
                metric_id,
                fresh,
                denominator,
                limitations=limitations,
                reason="session_entities_covered_last_seen",
            )

    if conn is None:
        return _not_ready(
            metric_id,
            reason=(
                "Database unavailable and no usable session freshness data. "
                "Fail closed: freshness_coverage is NOT_READY."
            ),
            denominator=denominator,
            limitations=limitations,
        )

    return _not_ready(
        metric_id,
        reason=f"freshness computation failed: {'; '.join(limitations) or 'unknown'}",
        denominator=denominator,
        limitations=limitations,
    )


def compute_opportunity_recall(
    denominator: int,
    *,
    benchmark_path: Path | str | None = None,
) -> MetricResult:
    """Recall from stratified benchmark sample — never from DB counts."""
    metric_id = METRIC_OPPORTUNITY_RECALL

    candidates: list[Path] = []
    if benchmark_path is not None:
        candidates.append(Path(benchmark_path))
    else:
        candidates.extend(
            [
            PROJECT_ROOT / "data" / "benchmarks" / "opportunity_recall_sample.json",
            PROJECT_ROOT / "data" / "benchmarks" / "opportunity_recall_sample.jsonl",
            PROJECT_ROOT / "docs" / "qa" / "recall-sample-2026-07-17.json",
            PROJECT_ROOT / "docs" / "ops" / "session-2026-07-17" / "opportunity_recall_sample.json",
            ]
        )

    path: Path | None = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return _not_ready(
            metric_id,
            reason=(
                "No stratified benchmark sample found. "
                "opportunity_recall MUST NOT be computed from database opportunity counts. "
                "Provide data/benchmarks/opportunity_recall_sample.json with fields: "
                "relevant (bool), retrieved (bool) per sample item."
            ),
            denominator=None,  # sample-based, not universe denominator
            limitations=["benchmark_sample_missing", "never_use_db_counts_for_recall"],
        )

    if path.suffix == ".jsonl":
        items = _iter_jsonl(path)
    else:
        raw = _load_json(path)
        if raw is None:
            return _not_ready(
                metric_id,
                reason=f"Failed to parse benchmark sample at {path}",
                denominator=None,
            )
        items_raw = (
            raw.get("items")
            or raw.get("portal_items")
            or raw.get("sample")
            or raw.get("records")
            or []
        )
        items = [i for i in items_raw if isinstance(i, dict)]
        if raw.get("portal_items") is not None:
            # Canonical recall-runner schema.
            unlabeled = [i for i in items if i.get("captured_by_system") is None]
            invalid_captured = [
                i
                for i in items
                if i.get("captured_by_system") is True and not i.get("capture_evidence")
            ]
            required_strata = set((raw.get("methodology") or {}).get("required_strata") or [])
            observed_strata = {s for i in items for s in (i.get("strata") or [])}
            missing_strata = sorted(required_strata - observed_strata)
            if unlabeled or invalid_captured or missing_strata:
                return _not_ready(
                    metric_id,
                    reason=(
                        "Recall sample is incomplete: "
                        f"unlabeled={len(unlabeled)}, "
                        f"captured_without_evidence={len(invalid_captured)}, "
                        f"missing_strata={missing_strata}"
                    ),
                    denominator=None,
                    limitations=[f"sample={path}", "stratified_sample_incomplete"],
                )
            items = [
                {
                    **i,
                    "relevant": True,
                    "retrieved": i.get("captured_by_system") is True,
                }
                for i in items
            ]

    relevant = [i for i in items if i.get("relevant") is True]
    if not relevant:
        return _not_ready(
            metric_id,
            reason=(
                f"Benchmark sample at {path} has no items with relevant=true. "
                "Cannot compute recall."
            ),
            denominator=None,
            limitations=[f"sample={path}"],
        )

    true_positives = sum(1 for i in relevant if i.get("retrieved") is True)
    return _ready(
        metric_id,
        true_positives,
        len(relevant),
        sample_size=len(items),
        reason=f"stratified_benchmark:{path.name}",
        limitations=[
            "computed_from_stratified_benchmark_sample",
            "not_from_database_counts",
            f"sample_path={path}",
        ],
    )


def compute_required_field_completeness(
    *,
    records: list[dict[str, Any]] | None = None,
    session_dir: Path | None = None,
) -> MetricResult:
    """Mean completeness of decision fields; absence is explicit."""
    metric_id = METRIC_REQUIRED_FIELD_COMPLETENESS

    rows = list(records or [])
    if not rows:
        sess = session_dir or _find_session_dir()
        if sess is not None:
            for name in (
                "radar_opportunities.jsonl",
                "entities_covered.jsonl",
            ):
                candidate = _iter_jsonl(sess / name)
                if candidate:
                    rows = candidate
                    break

    if not rows:
        return _not_ready(
            metric_id,
            reason=(
                "No opportunity/entity records available to score decision-field completeness"
            ),
            denominator=len(DECISION_FIELDS),
            limitations=["no_records"],
        )

    breakdown = compute_field_completeness(rows)
    mean_pct = breakdown["mean_completeness_pct"]
    # Represent as numerator = mean filled fields, denominator = field count
    # so report always has numerator/denominator/pct.
    mean_filled = (
        round(float(mean_pct) / 100.0 * len(DECISION_FIELDS), 4)
        if mean_pct is not None
        else 0.0
    )
    return _ready(
        metric_id,
        mean_filled,
        len(DECISION_FIELDS),
        field_breakdown=breakdown,
        sample_size=int(breakdown["records"]),
        reason="mean_decision_field_completeness",
        limitations=[
            "absence_is_explicit",
            f"decision_fields={len(DECISION_FIELDS)}",
            f"records_scored={breakdown['records']}",
        ],
    )


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def build_contract_report(
    *,
    conn: Any | None = None,
    as_of: date | datetime | None = None,
    session_dir: Path | str | None = None,
    registry_path: Path | str | None = None,
    sla_path: Path | str | None = None,
    benchmark_path: Path | str | None = None,
    commercial_entity_ids: set[int] | None = None,
    completeness_records: list[dict[str, Any]] | None = None,
    seed_path: Path | str | None = None,
    csv_path: Path | str | None = None,
) -> CoverageContractReport:
    """Build the full coverage contract report with all separate metrics."""
    if isinstance(as_of, datetime):
        as_of_dt = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)
        as_of_date = as_of_dt.date()
    elif isinstance(as_of, date):
        as_of_date = as_of
        as_of_dt = datetime(as_of.year, as_of.month, as_of.day, tzinfo=UTC)
    else:
        as_of_dt = datetime.now(UTC)
        as_of_date = as_of_dt.date()

    slas = load_sla_config(sla_path)
    denom = resolve_denominator(conn=conn, seed_path=seed_path, csv_path=csv_path)
    sess = _find_session_dir(session_dir)

    notes: list[str] = [
        "Commercial signal metric is NOT labeled coverage.",
        f"Headline metric: {HEADLINE_METRIC} (kind=commercial_signal).",
        f"Legacy alias: {LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY} → {HEADLINE_METRIC}.",
        "Denominator is never reduced to improve percentages.",
    ]
    if denom.notes:
        notes.append(f"Denominator notes: {denom.notes}")
    if sess is not None:
        notes.append(f"Session artifacts: {sess}")

    results = [
        compute_commercial_signal(
            denom.value,
            session_dir=sess,
            conn=conn,
            commercial_entity_ids=commercial_entity_ids,
        ),
        compute_source_mapping_coverage(denom.value, registry_path=registry_path),
        compute_operational_source_coverage(
            denom.value, slas, conn=conn, session_dir=sess, as_of=as_of_dt
        ),
        compute_freshness_coverage(
            denom.value, slas, conn=conn, session_dir=sess, as_of=as_of_dt
        ),
        compute_opportunity_recall(denom.value, benchmark_path=benchmark_path),
        compute_required_field_completeness(
            records=completeness_records, session_dir=sess
        ),
    ]

    metrics_map = {r.metric_id: r.to_dict() for r in results}

    # Expose legacy alias entry pointing at the commercial signal metric
    commercial = metrics_map[METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL]
    metrics_map[LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY] = {
        **commercial,
        "metric_id": LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY,
        "alias_of": METRIC_ENTITIES_WITH_RECENT_COMMERCIAL_SIGNAL,
        "kind": MetricKind.COMMERCIAL_SIGNAL.value,
        "is_coverage_metric": False,
        "label": "Legacy alias for entities_with_recent_commercial_signal (NOT coverage)",
        "notes": "Backward compatibility only. Do not call this coverage.",
    }

    return CoverageContractReport(
        generated_at=datetime.now(UTC).isoformat(),
        as_of=as_of_date.isoformat(),
        denominator=denom,
        slas=slas.to_dict(),
        metrics=metrics_map,
        headline_metric=HEADLINE_METRIC,
        headline_is_coverage=False,
        notes=notes,
    )


def format_report_table(report: CoverageContractReport | dict[str, Any]) -> str:
    """Human-readable table of all contract metrics."""
    data = report.to_dict() if isinstance(report, CoverageContractReport) else report
    lines: list[str] = []
    lines.append("Coverage Contract Report")
    lines.append("=" * 88)
    lines.append(f"as_of: {data.get('as_of')}  generated_at: {data.get('generated_at')}")
    denom = data.get("denominator") or {}
    lines.append(
        f"denominator: {denom.get('value')}  source={denom.get('source')}  "
        f"fixed_canonical={denom.get('fixed_canonical')}"
    )
    lines.append(
        f"headline_metric: {data.get('headline_metric')}  "
        f"headline_is_coverage={data.get('headline_is_coverage')}"
    )
    lines.append("")
    header = (
        f"{'metric_id':<42} {'kind':<18} {'status':<10} "
        f"{'num':>8} {'den':>8} {'pct':>8}  notes"
    )
    lines.append(header)
    lines.append("-" * len(header))

    metrics = data.get("metrics") or {}
    order = list(data.get("metric_order") or ALL_METRIC_IDS)
    # Include legacy alias at the end for visibility
    if LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY not in order:
        order.append(LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY)

    for mid in order:
        m = metrics.get(mid)
        if not m:
            continue
        num = m.get("numerator")
        den = m.get("denominator")
        pct = m.get("pct")
        num_s = "—" if num is None else str(num)
        den_s = "—" if den is None else str(den)
        pct_s = "—" if pct is None else f"{pct}%"
        note = m.get("reason") or ""
        if m.get("is_coverage_metric") is False and m.get("kind") == "commercial_signal":
            note = (note + " | NOT coverage").strip(" |")
        if mid == LEGACY_ALIAS_COMMERCIAL_OPPORTUNITY_ANY:
            note = "alias → entities_with_recent_commercial_signal | NOT coverage"
        lines.append(
            f"{mid:<42} {str(m.get('kind') or ''):<18} {str(m.get('status') or ''):<10} "
            f"{num_s:>8} {den_s:>8} {pct_s:>8}  {note[:60]}"
        )

    lines.append("")
    lines.append("Notes:")
    for n in data.get("notes") or []:
        lines.append(f"  - {n}")
    return "\n".join(lines) + "\n"


def try_connect() -> Any | None:
    """Best-effort DB connection; returns None if unavailable."""
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        env_path = PROJECT_ROOT / ".env"
        if env_path.is_file():
            for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == "DATABASE_URL":
                    dsn = v.strip().strip('"').strip("'")
                    break
    if not dsn:
        return None
    try:
        import psycopg2

        return psycopg2.connect(dsn, connect_timeout=10)
    except Exception:
        return None
