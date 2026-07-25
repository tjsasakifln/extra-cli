"""Phase 7 — commercial decision policy: MATCH | REVIEW | NO_MATCH.

Client material shows only MATCH. REVIEW is internal. NO_MATCH is auditable.
"""
from __future__ import annotations

from typing import Any

from scripts.ops.hybrid_sector import (
    PIPELINE_VERSION,
    PROMPT_VERSION,
    RULE_STAMP,
    SCHEMA_VERSION,
)
from scripts.ops.hybrid_sector.llm.arbitration import ArbitrationOutcome
from scripts.ops.hybrid_sector.models import (
    CandidateRecord,
    DecisionLineage,
    DeterministicResult,
)


def map_to_commercial(
    candidate: CandidateRecord,
    det: DeterministicResult,
    arb: ArbitrationOutcome | None,
) -> DecisionLineage:
    """Map deterministic + optional LLM into final commercial decision with full lineage."""
    reasons: list[str] = []
    llm_decision = None
    llm_invoked = False
    llm_error = None
    second = None

    if arb and arb.invoked:
        llm_invoked = True
        llm_error = arb.error
        if arb.decision is not None:
            llm_decision = arb.decision.model_dump()
        if arb.second is not None:
            second = arb.second.model_dump()
        reasons.extend(arb.reasons or [])

    commercial: str
    review_question = None
    docs_needed: list[str] = []

    if det.decision == "CLEAR_POSITIVE" and not llm_invoked:
        commercial = "MATCH"
        reasons.append("deterministic_clear_positive")
    elif det.decision == "CLEAR_NEGATIVE" and not llm_invoked:
        commercial = "NO_MATCH"
        reasons.append("deterministic_clear_negative_no_llm")
    elif llm_invoked and llm_decision is not None:
        commercial = llm_decision["decision"]
        reasons.append(f"llm_decision:{commercial}")
        # LLM errors already mapped to REVIEW inside arbiter
        if llm_error:
            commercial = "REVIEW"
            reasons.append(f"llm_error_forced_review:{llm_error}")
        if commercial == "NO_MATCH" and det.has_execution_signal and det.positive_signals:
            # Safety: independent positive + NO_MATCH without second resolution → REVIEW
            if second is None and (candidate.record.valor_estimado or 0) >= 500_000:
                commercial = "REVIEW"
                reasons.append("high_value_no_match_with_positive_signal")
    else:
        # GRAY without LLM should not become commercial MATCH; keep REVIEW
        commercial = "REVIEW"
        reasons.append("gray_or_unresolved_default_review")

    # MATCH requirements
    if commercial == "MATCH":
        if not (det.positive_signals or (llm_decision and llm_decision.get("evidence"))):
            commercial = "REVIEW"
            reasons.append("match_requires_positive_evidence")
        if not candidate.record.source or not candidate.record.official_id:
            commercial = "REVIEW"
            reasons.append("match_requires_official_source")
        if det.decision == "CLEAR_NEGATIVE" and not llm_invoked:
            commercial = "NO_MATCH"
            reasons.append("blocker_clear_negative")

    if commercial == "REVIEW":
        review_question = _review_question(det, llm_decision)
        docs_needed = _docs_needed(candidate, det)

    lineage = DecisionLineage(
        canonical_id=candidate.record.canonical_id,
        commercial_decision=commercial,  # type: ignore[arg-type]
        deterministic=det,
        llm_decision=llm_decision,
        llm_invoked=llm_invoked,
        llm_error=llm_error,
        second_adjudication=second,
        retrieval=candidate.to_lineage_dict(),
        policy_reasons=reasons,
        review_question=review_question,
        documents_needed=docs_needed,
        pipeline_version=PIPELINE_VERSION,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        rule_stamp=RULE_STAMP,
    )
    return lineage


def _review_question(det: DeterministicResult, llm: dict[str, Any] | None) -> str:
    if det.mixed_scope:
        return "O escopo inclui execução/implantação de obra civil aderente ou apenas fornecimento?"
    if det.short_text:
        return "O objeto completo (TR/edital) confirma execução de engenharia?"
    if llm and llm.get("missing_information"):
        return "Preencher informações faltantes: " + ", ".join(llm["missing_information"][:5])
    return "Há evidência suficiente de aderência ao mercado de obras/engenharia da Extra?"


def _docs_needed(candidate: CandidateRecord, det: DeterministicResult) -> list[str]:
    docs: list[str] = []
    r = candidate.record
    if not r.has_edital:
        docs.append("edital")
    if not r.has_tr:
        docs.append("termo_de_referencia")
    if det.short_text or det.mixed_scope:
        docs.append("anexos_tecnicos")
    return docs


def split_deliverables(
    lineages: list[DecisionLineage],
    records_by_id: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Produce deliverable_e_matches / review_queue / no_match_audit lists."""
    matches: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    no_match: list[dict[str, Any]] = []

    for lin in lineages:
        rec = records_by_id.get(lin.canonical_id)
        base = {
            "canonical_id": lin.canonical_id,
            "objeto": getattr(rec, "objeto", "") if rec else "",
            "titulo": getattr(rec, "titulo", "") if rec else "",
            "orgao": getattr(rec, "orgao", "") if rec else "",
            "uf": getattr(rec, "uf", "") if rec else "",
            "valor_estimado": getattr(rec, "valor_estimado", None) if rec else None,
            "data_encerramento": getattr(rec, "data_encerramento", None) if rec else None,
            "source": getattr(rec, "source", "") if rec else "",
            "urls": getattr(rec, "urls", []) if rec else [],
            "lineage": lin.to_dict(),
        }
        if lin.commercial_decision == "MATCH":
            matches.append(base)
        elif lin.commercial_decision == "REVIEW":
            review.append(
                {
                    **base,
                    "review_question": lin.review_question,
                    "documents_needed": lin.documents_needed,
                    "priority": lin.review_priority,
                }
            )
        else:
            no_match.append(
                {
                    **base,
                    "reason": (lin.deterministic.reason if lin.deterministic else ""),
                    "rules_triggered": {
                        "positive": lin.deterministic.positive_signals if lin.deterministic else [],
                        "negative": lin.deterministic.negative_signals if lin.deterministic else [],
                    },
                    "retrieval_channels": lin.retrieval.get("retrieved_by", []),
                    "rule_version": lin.rule_stamp,
                    "llm_decision": lin.llm_decision,
                }
            )
    return {
        "deliverable_e_matches": matches,
        "deliverable_e_review_queue": review,
        "deliverable_e_no_match_audit": no_match,
    }
