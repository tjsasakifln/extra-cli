"""LLM arbitration policy: when to call, fail→REVIEW, evidence validation, second adjudicate."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.ops.hybrid_sector.llm.evidence import validate_evidence_list
from scripts.ops.hybrid_sector.llm.protocol import LLMError, LLMProvider
from scripts.ops.hybrid_sector.llm.schema import (
    PROMPT_VERSION,
    SectorArbitrationRequest,
    SectorLLMDecision,
)
from scripts.ops.hybrid_sector.models import (
    CandidateRecord,
    DeterministicResult,
)


@dataclass
class ArbitrationOutcome:
    decision: SectorLLMDecision | None
    invoked: bool
    error: str | None = None
    invented_evidence: list[str] | None = None
    second: SectorLLMDecision | None = None
    second_error: str | None = None
    reasons: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.model_dump() if self.decision else None,
            "invoked": self.invoked,
            "error": self.error,
            "invented_evidence": self.invented_evidence,
            "second": self.second.model_dump() if self.second else None,
            "second_error": self.second_error,
            "reasons": list(self.reasons or []),
            "prompt_version": PROMPT_VERSION,
        }


def should_invoke_llm(
    det: DeterministicResult,
    candidate: CandidateRecord,
    *,
    high_value_threshold: float = 500_000.0,
    stratified_audit: bool = False,
) -> tuple[bool, list[str]]:
    """Phase 6 — selective LLM trigger policy."""
    reasons: list[str] = []
    if det.decision == "GRAY_ZONE":
        reasons.append("gray_zone")
    if det.mixed_scope:
        reasons.append("mixed_scope")
    if det.short_text:
        reasons.append("short_text")
    if det.margin < 0.15 and det.positive_signals and det.negative_signals:
        reasons.append("low_margin")
    retrieved = set(candidate.retrieved_by)
    if "semantic" in retrieved and "lexical" not in retrieved:
        reasons.append("semantic_without_keyword")
    if candidate.zero_match_rescue:
        reasons.append("zero_match_audit")
    if det.has_execution_signal and det.decision != "CLEAR_POSITIVE":
        reasons.append("execution_signal_non_clear")
    valor = candidate.record.valor_estimado
    if (
        det.decision == "CLEAR_NEGATIVE"
        and valor is not None
        and valor >= high_value_threshold
    ):
        reasons.append("high_value_pending_no_match")
    if stratified_audit and det.decision == "CLEAR_NEGATIVE":
        reasons.append("stratified_discard_sample")
    # Category relevant + weak text
    if det.decision != "CLEAR_POSITIVE" and any(
        any(k in (c or "").lower() for k in ("obra", "engenharia", "infra", "saneamento"))
        for c in candidate.record.categories
    ) and det.short_text:
        reasons.append("category_insufficient_text")
    return (len(reasons) > 0), reasons


def _safe_review(reason: str, *, missing: list[str] | None = None) -> SectorLLMDecision:
    return SectorLLMDecision(
        decision="REVIEW",
        confidence=0,
        evidence=[],
        reasoning=reason,
        missing_information=missing or [],
        needs_more_data=True,
    )


def arbitrate(
    candidate: CandidateRecord,
    det: DeterministicResult,
    provider: LLMProvider,
    *,
    min_confidence: int = 60,
    high_value_threshold: float = 500_000.0,
    second_adjudication_value_threshold: float = 1_000_000.0,
    stratified_audit: bool = False,
    force_invoke: bool = False,
) -> ArbitrationOutcome:
    """Invoke LLM when eligible; map all failures to REVIEW never NO_MATCH."""
    invoke, reasons = should_invoke_llm(
        det,
        candidate,
        high_value_threshold=high_value_threshold,
        stratified_audit=stratified_audit,
    )
    if force_invoke:
        invoke = True
        reasons = reasons or ["force_invoke"]
    if not invoke:
        return ArbitrationOutcome(decision=None, invoked=False, reasons=[])

    raw = candidate.record
    req = SectorArbitrationRequest(
        canonical_id=raw.canonical_id,
        objeto=raw.objeto,
        titulo=raw.titulo,
        items=list(raw.items),
        categories=list(raw.categories),
        orgao=raw.orgao,
        valor_estimado=raw.valor_estimado,
        modality=raw.modalidade,
        deterministic_decision=det.decision,
        deterministic_reason=det.reason,
        retrieval_channels=list(candidate.retrieved_by),
        source_text=raw.text_blob(),
        prompt_variant="primary",
    )

    try:
        decision = provider.classify(req)
    except LLMError as exc:
        return ArbitrationOutcome(
            decision=_safe_review(f"llm_error:{exc.kind}:{exc}"),
            invoked=True,
            error=str(exc),
            reasons=reasons,
        )
    except Exception as exc:  # noqa: BLE001
        return ArbitrationOutcome(
            decision=_safe_review(f"llm_unexpected:{exc}"),
            invoked=True,
            error=str(exc),
            reasons=reasons,
        )

    # Validate evidence — invented → REVIEW
    source = req.trusted_source_blob()
    valid, invented = validate_evidence_list(decision.evidence, source)
    if invented:
        return ArbitrationOutcome(
            decision=_safe_review(
                "invented_evidence_invalidates_decision",
                missing=["literal_evidence"],
            ),
            invoked=True,
            invented_evidence=invented,
            reasons=reasons,
        )
    decision = decision.model_copy(update={"evidence": valid})

    if decision.confidence < min_confidence:
        decision = _safe_review(
            f"low_confidence:{decision.confidence}<{min_confidence}",
            missing=list(decision.missing_information),
        )
        return ArbitrationOutcome(
            decision=decision, invoked=True, reasons=reasons + ["low_confidence"]
        )

    if decision.needs_more_data and decision.decision != "REVIEW":
        decision = decision.model_copy(update={"decision": "REVIEW"})

    # Second adjudication for high value/critical when NO_MATCH + independent positive
    second = None
    second_err = None
    valor = raw.valor_estimado or 0.0
    if (
        decision.decision == "NO_MATCH"
        and (det.positive_signals or det.has_execution_signal or "semantic" in candidate.retrieved_by)
        and valor >= second_adjudication_value_threshold
    ):
        req2 = req.model_copy(
            update={
                "prompt_variant": "second_adjudication",
                "deterministic_decision": "",
                "deterministic_reason": "",
            }
        )
        try:
            second = provider.classify(req2)
            v2, inv2 = validate_evidence_list(second.evidence, source)
            if inv2 or second.confidence < min_confidence:
                decision = _safe_review("second_adjudication_invalid_or_low_conf")
            elif second.decision != decision.decision:
                decision = _safe_review(
                    f"second_adjudication_divergence:{decision.decision}!={second.decision}"
                )
            else:
                second = second.model_copy(update={"evidence": v2})
        except Exception as exc:  # noqa: BLE001
            second_err = str(exc)
            decision = _safe_review(f"second_adjudication_error:{exc}")

    return ArbitrationOutcome(
        decision=decision,
        invoked=True,
        second=second,
        second_error=second_err,
        reasons=reasons,
    )
