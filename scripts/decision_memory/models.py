"""Closed typed contracts for Decision & Outcome Memory v1."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class HumanDecision(str, Enum):
    GO = "GO"
    REVIEW = "REVIEW"
    NO_GO = "NO_GO"


class LegacyDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    DEFER = "DEFER"
    UNKNOWN = "UNKNOWN"
    NOT_PROVIDED = "NOT_PROVIDED"


class SystemRecommendation(str, Enum):
    GO = "GO"
    REVIEW = "REVIEW"
    NO_GO = "NO_GO"
    UNKNOWN = "UNKNOWN"
    NOT_PROVIDED = "NOT_PROVIDED"


class TemporalIntegrity(str, Enum):
    PROSPECTIVE = "PROSPECTIVE"
    HISTORICAL_UNVERIFIED = "HISTORICAL_UNVERIFIED"
    OUTCOME_WITHOUT_PRIOR_DECISION = "OUTCOME_WITHOUT_PRIOR_DECISION"
    TEMPORAL_ORDER_UNKNOWN = "TEMPORAL_ORDER_UNKNOWN"


class EventOrigin(str, Enum):
    CLI = "cli"
    REVIEW = "review"
    IMPORT = "import"
    API = "api"
    SYSTEM = "system"
    SUPERSESSION = "supersession"


class CorrectionType(str, Enum):
    CORRECTION = "CORRECTION"
    SUPERSESSION = "SUPERSESSION"
    CLARIFICATION = "CLARIFICATION"
    VOID = "VOID"


class ActionStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"
    OVERDUE = "OVERDUE"


class ActionCriticality(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class OutcomeType(str, Enum):
    UNKNOWN = "UNKNOWN"
    NO_PARTICIPATION = "NO_PARTICIPATION"
    PROPOSAL_SUBMITTED = "PROPOSAL_SUBMITTED"
    INELIGIBLE = "INELIGIBLE"
    DISQUALIFIED = "DISQUALIFIED"
    LOSS = "LOSS"
    WIN = "WIN"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"
    ANNULLED = "ANNULLED"
    HOMOLOGATED = "HOMOLOGATED"
    AWARDED = "AWARDED"
    CONTRACTED = "CONTRACTED"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    INCIDENT = "INCIDENT"
    ADDENDUM = "ADDENDUM"
    CONTRACT_CLOSED = "CONTRACT_CLOSED"
    MARGIN_DECLARED = "MARGIN_DECLARED"


class ConfirmationDegree(str, Enum):
    DECLARED = "DECLARED"
    DOCUMENTED = "DOCUMENTED"
    OFFICIAL = "OFFICIAL"
    UNVERIFIED = "UNVERIFIED"


class DecisionRecordInput(StrictModel):
    client_id: str = Field(min_length=1)
    opportunity_key: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    justification: str = Field(min_length=1)
    human_decision: HumanDecision
    legacy_decision: LegacyDecision | None = None
    system_recommendation: SystemRecommendation = SystemRecommendation.NOT_PROVIDED
    source_identifiers: dict[str, str] = Field(default_factory=dict)
    cycle_id: str | None = None
    run_id: str | None = None
    decided_at: datetime | None = None
    session_deadline_at: datetime | None = None
    premises: list[str] = Field(default_factory=list)
    constraints_known: list[str] = Field(default_factory=list)
    data_limitations: list[str] = Field(default_factory=list)
    profile_id: str | None = None
    profile_version: str | None = None
    profile_hash: str | None = None
    evidence_hash: str | None = None
    evidence_locators: list[str] = Field(default_factory=list)
    engine_version: str | None = None
    prediction_ref: dict[str, Any] | None = None
    temporal_integrity: TemporalIntegrity = TemporalIntegrity.PROSPECTIVE
    origin: EventOrigin = EventOrigin.CLI
    idempotency_key: str | None = None
    supersedes_event_id: UUID | None = None
    correction_reason: str | None = None
    correction_type: CorrectionType | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("client_id", "opportunity_key", "actor", "justification")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("must be non-empty")
        return str(v).strip()


class ActionRecordInput(StrictModel):
    client_id: str = Field(min_length=1)
    decision_event_id: UUID
    opportunity_key: str = Field(min_length=1)
    description: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    owner: str | None = None
    owner_absent_reason: str | None = None
    due_at: datetime | None = None
    due_absent_reason: str | None = None
    criticality: ActionCriticality = ActionCriticality.NORMAL
    status: ActionStatus = ActionStatus.OPEN
    temporal_integrity: TemporalIntegrity = TemporalIntegrity.PROSPECTIVE
    origin: EventOrigin = EventOrigin.CLI
    idempotency_key: str | None = None
    supersedes_event_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _owner_due_policy(self) -> ActionRecordInput:
        if not self.owner and not self.owner_absent_reason:
            raise ValueError("owner required or owner_absent_reason must justify absence")
        if self.owner and self.owner_absent_reason:
            raise ValueError("provide owner OR owner_absent_reason, not both")
        if self.due_at is None and not self.due_absent_reason:
            raise ValueError("due_at required or due_absent_reason must justify absence")
        if self.due_at is not None and self.due_absent_reason:
            raise ValueError("provide due_at OR due_absent_reason, not both")
        return self


class ActionCompleteInput(StrictModel):
    client_id: str = Field(min_length=1)
    action_event_id: UUID
    actor: str = Field(min_length=1)
    evidence_hash: str = Field(min_length=1)
    evidence_locators: list[str] = Field(default_factory=list)
    completed_at: datetime | None = None
    notes: str | None = None
    idempotency_key: str | None = None


class OutcomeRecordInput(StrictModel):
    client_id: str = Field(min_length=1)
    opportunity_key: str = Field(min_length=1)
    outcome_type: OutcomeType
    observed_at: datetime
    source: str = Field(min_length=1)
    evidence_hash: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    decision_event_id: UUID | None = None
    effective_at: datetime | None = None
    locator: str | None = None
    confirmation_degree: ConfirmationDegree = ConfirmationDegree.DECLARED
    structured_facts: dict[str, Any] = Field(default_factory=dict)
    observations: str | None = None
    limitations: list[str] = Field(default_factory=list)
    expected_margin: float | None = None
    realized_margin: float | None = None
    temporal_integrity: TemporalIntegrity | None = None
    origin: EventOrigin = EventOrigin.CLI
    idempotency_key: str | None = None
    supersedes_event_id: UUID | None = None
    correction_reason: str | None = None
    correction_type: CorrectionType | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source", "evidence_hash", "actor", "client_id", "opportunity_key")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("must be non-empty")
        return str(v).strip()


class MetricCell(StrictModel):
    name: str
    numerator: int | float
    denominator: int | float | None
    unknown_count: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    exclusions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    value: float | None = None


class CliResult(StrictModel):
    ok: bool
    status: str
    client_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    schema_version: str = "decision-memory/1.0"
