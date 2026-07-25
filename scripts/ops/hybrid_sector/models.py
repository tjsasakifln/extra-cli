"""Shared record contracts for hybrid sector discovery."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

CommercialDecision = Literal["MATCH", "REVIEW", "NO_MATCH"]
DeterministicDecision = Literal["CLEAR_POSITIVE", "GRAY_ZONE", "CLEAR_NEGATIVE"]


@dataclass
class RawOpportunity:
    """Raw open-edital universe record (recall denominator source)."""

    source: str
    official_id: str
    objeto: str = ""
    titulo: str = ""
    items: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    orgao: str = ""
    municipio: str = ""
    uf: str = ""
    modalidade: str = ""
    valor_estimado: float | None = None
    data_abertura: str | None = None
    data_encerramento: str | None = None
    urls: list[str] = field(default_factory=list)
    has_edital: bool = False
    has_tr: bool = False
    has_etp: bool = False
    has_anexos: bool = False
    captured_at: str = ""
    source_coverage_status: str = "unknown"
    source_freshness_status: str = "unknown"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def canonical_id(self) -> str:
        return f"{self.source}::{self.official_id}"

    def text_blob(self) -> str:
        parts = [self.objeto, self.titulo, " ".join(self.items), " ".join(self.categories)]
        return " | ".join(p for p in parts if p).strip()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["canonical_id"] = self.canonical_id
        return d


@dataclass
class RetrievalHit:
    """Per-channel retrieval result for one record."""

    channel: str
    score: float
    rank: int
    reason: str = ""


@dataclass
class CandidateRecord:
    """Union-merge candidate with full retrieval lineage (never silently dropped)."""

    record: RawOpportunity
    retrieved_by: list[str] = field(default_factory=list)
    retrieval_scores: dict[str, float] = field(default_factory=dict)
    retrieval_rank_by_channel: dict[str, int] = field(default_factory=dict)
    retrieval_reason: list[str] = field(default_factory=list)
    zero_match_rescue: bool = False
    fused_score: float = 0.0
    fused_rank: int | None = None
    exclusive_rescue_channel: str | None = None
    inclusion_reason: str = ""

    def to_lineage_dict(self) -> dict[str, Any]:
        return {
            "canonical_id": self.record.canonical_id,
            "retrieved_by": list(self.retrieved_by),
            "retrieval_scores": dict(self.retrieval_scores),
            "retrieval_rank_by_channel": dict(self.retrieval_rank_by_channel),
            "retrieval_reason": list(self.retrieval_reason),
            "zero_match_rescue": self.zero_match_rescue,
            "fused_score": self.fused_score,
            "fused_rank": self.fused_rank,
            "exclusive_rescue_channel": self.exclusive_rescue_channel,
            "inclusion_reason": self.inclusion_reason,
            "channel_count": len(self.retrieved_by),
        }


@dataclass
class DeterministicResult:
    decision: DeterministicDecision
    confidence: float
    positive_signals: list[str] = field(default_factory=list)
    negative_signals: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    reason: str = ""
    rule_version: str = ""
    margin: float = 0.0
    has_execution_signal: bool = False
    short_text: bool = False
    champion_label: str = ""
    mixed_scope: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionLineage:
    """End-to-end audit trail for one record — silent discard is a bug."""

    canonical_id: str
    commercial_decision: CommercialDecision
    deterministic: DeterministicResult | None = None
    llm_decision: dict[str, Any] | None = None
    llm_invoked: bool = False
    llm_error: str | None = None
    second_adjudication: dict[str, Any] | None = None
    retrieval: dict[str, Any] = field(default_factory=dict)
    policy_reasons: list[str] = field(default_factory=list)
    review_priority: float | None = None
    review_question: str | None = None
    documents_needed: list[str] = field(default_factory=list)
    pipeline_version: str = ""
    prompt_version: str = ""
    schema_version: str = ""
    rule_stamp: str = ""
    invented_evidence: list[str] = field(default_factory=list)
    invented_evidence_accepted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "commercial_decision": self.commercial_decision,
            "deterministic": self.deterministic.to_dict() if self.deterministic else None,
            "llm_decision": self.llm_decision,
            "llm_invoked": self.llm_invoked,
            "llm_error": self.llm_error,
            "second_adjudication": self.second_adjudication,
            "retrieval": self.retrieval,
            "policy_reasons": list(self.policy_reasons),
            "review_priority": self.review_priority,
            "review_question": self.review_question,
            "documents_needed": list(self.documents_needed),
            "pipeline_version": self.pipeline_version,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "rule_stamp": self.rule_stamp,
            "invented_evidence": list(self.invented_evidence),
            "invented_evidence_accepted": self.invented_evidence_accepted,
        }
