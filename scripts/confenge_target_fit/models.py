"""Dataclasses for continuous target-fit materialization."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CompanyInput:
    """Semantically relevant inputs for fingerprint + classification."""

    company_key: str
    cnpj_raiz: str
    razao_social: str | None = None
    nome_fantasia: str | None = None
    cnae_principal: str | None = None
    cnaes_secundarios: list[str] = field(default_factory=list)
    contracts: list[dict[str, Any]] = field(default_factory=list)
    sector_fit: str | None = None
    activity_class: str | None = None
    construction_evidence: dict[str, Any] = field(default_factory=dict)
    is_consortium_member: bool = False
    consortium_notes: list[str] = field(default_factory=list)
    source_max_updated_at: datetime | None = None
    source_watermark: str = ""
    # Filial lineage: contract → cnpj14 → raiz
    branch_cnpjs: list[str] = field(default_factory=list)


@dataclass
class MaterializedTargetFit:
    company_key: str
    cnpj_raiz: str
    target_fit_class: str
    target_fit_confidence: float
    target_fit_version: str
    target_fit_reason_codes: list[str]
    target_fit_evidence: list[dict[str, Any]]
    computed_at: datetime
    source_watermark: str
    source_max_updated_at: datetime | None
    input_fingerprint: str
    classifier_sha: str
    schema_version: str
    operational_status: str = "ok"
    sector_fit: str = ""
    activity_class: str = ""
    relevant_execution_contract_count: int = 0
    relevant_supply_only_count: int = 0
    materialization_mode: str = "ACTIVE"
    previous_class: str | None = None
    previous_confidence: float | None = None
    transition_event: str | None = None

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.computed_at is not None:
            d["computed_at"] = self.computed_at.isoformat()
        if self.source_max_updated_at is not None:
            d["source_max_updated_at"] = self.source_max_updated_at.isoformat()
        return d


@dataclass
class TransitionEvent:
    event_type: str
    company_key: str
    cnpj_raiz: str
    old_class: str | None
    new_class: str | None
    old_confidence: float | None
    new_confidence: float | None
    reason_codes: list[str]
    changed_evidence_ids: list[str]
    source_watermark: str
    computed_at: datetime
    target_fit_version: str
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["computed_at"] = self.computed_at.isoformat()
        return d


@dataclass
class DirtyItem:
    id: int | None
    company_key: str
    cnpj_raiz: str
    reason: str
    source_entity: str
    source_id: str | None
    source_updated_at: datetime | None
    source_watermark: str
    priority: int
    status: str
    attempt_count: int
    next_retry_at: datetime | None
    last_error: str | None
    idempotency_key: str
    input_fingerprint: str | None = None


@dataclass
class CycleStats:
    cycle_id: str
    cycle_kind: str
    mode: str
    target_fit_version: str
    source_watermark: str = ""
    dirty_enqueued: int = 0
    claimed: int = 0
    processed: int = 0
    skipped_same_fingerprint: int = 0
    upgrades: int = 0
    downgrades: int = 0
    unchanged: int = 0
    failures: int = 0
    retries: int = 0
    dead_letter: int = 0
    transitions: dict[str, int] = field(default_factory=dict)
    processing_latency_ms_total: float = 0.0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FreshnessDecision:
    company_key: str
    target_fit_fresh: bool
    target_fit_age_seconds: float | None
    target_fit_computed_at: datetime | None
    target_fit_source_watermark: str
    datalake_watermark: str
    reason: str
    blocks_send: bool

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.target_fit_computed_at is not None:
            d["target_fit_computed_at"] = self.target_fit_computed_at.isoformat()
        return d


@dataclass
class HealthReport:
    status: str
    datalake_watermark: str
    target_fit_watermark: str
    lag_seconds: float | None
    dirty: int
    processing: int
    retry: int
    dead: int
    current_version: str
    confirmed: int
    probable: int
    out: int
    last_success: str | None
    async_mode: str
    auto_paused: bool
    insufficient: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format_human(self) -> str:
        lag = "n/a" if self.lag_seconds is None else f"{self.lag_seconds:.0f}s"
        cov = (self.details or {}).get("coverage") or {}
        ratio = cov.get("coverage_ratio")
        ratio_s = "n/a" if ratio is None else f"{float(ratio) * 100:.2f}%"
        lines = [
            f"STATUS: {self.status}",
            f"DATALAKE WATERMARK: {self.datalake_watermark or '(none)'}",
            f"TARGET-FIT WATERMARK: {self.target_fit_watermark or '(none)'}",
            f"LAG: {lag}",
            f"DIRTY: {self.dirty}",
            f"PROCESSING: {self.processing}",
            f"RETRY: {self.retry}",
            f"DEAD: {self.dead}",
            f"CURRENT VERSION: {self.current_version}",
            f"CONFIRMED: {self.confirmed}",
            f"PROBABLE: {self.probable}",
            f"OUT: {self.out}",
            f"INSUFFICIENT_EVIDENCE: {self.insufficient}",
            f"MATERIALIZED: {self.confirmed + self.probable + self.out + self.insufficient}",
            f"COVERAGE_MODE: {cov.get('coverage_mode') or 'BOOTSTRAPPING'}",
            f"COVERAGE_RATIO: {ratio_s}",
            f"CANONICAL_ROOTS: {cov.get('canonical_company_count') or 0}",
            f"FULL_NATIONAL_READY: {cov.get('FULL_NATIONAL_READY', False)}",
            f"LAST_FULL_RECONCILE: {cov.get('last_full_reconcile_completed_at') or '(never)'}",
            f"UNEXPLAINED_MISSING: {cov.get('last_full_reconcile_unexplained_missing', 'n/a')}",
            f"LAST SUCCESS: {self.last_success or '(never)'}",
            f"ASYNC MODE: {self.async_mode}",
            f"AUTO PAUSED: {self.auto_paused}",
        ]
        return "\n".join(lines)
