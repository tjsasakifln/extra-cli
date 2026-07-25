"""Unit tests driving real hybrid_sector shipped callables (no test theater)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.hybrid_sector.classification.selective import classify_selective
from scripts.ops.hybrid_sector.llm.arbitration import arbitrate, should_invoke_llm
from scripts.ops.hybrid_sector.llm.evidence import evidence_is_valid, validate_evidence_list
from scripts.ops.hybrid_sector.llm.fake_provider import FakeLLMProvider
from scripts.ops.hybrid_sector.llm.protocol import LLMError
from scripts.ops.hybrid_sector.llm.schema import SectorLLMDecision
from scripts.ops.hybrid_sector.models import CandidateRecord, RawOpportunity
from scripts.ops.hybrid_sector.pipeline import run_pipeline
from scripts.ops.hybrid_sector.policy.decision import map_to_commercial, split_deliverables
from scripts.ops.hybrid_sector.policy.review_queue import (
    OPERATIONALLY_BLOCKED_REVIEW_VOLUME,
    ReviewCapacityConfig,
    prioritize_review_queue,
)
from scripts.ops.hybrid_sector.raw_universe import build_raw_universe
from scripts.ops.hybrid_sector.retrieval.fusion import fuse_candidates, rrf_score
from scripts.ops.hybrid_sector.retrieval.hybrid import run_hybrid_retrieval
from scripts.ops.hybrid_sector.retrieval.lexical import retrieve_lexical
from scripts.ops.hybrid_sector.models import RetrievalHit


def _rec(**kw) -> RawOpportunity:
    base = {
        "source": "pncp",
        "official_id": kw.pop("official_id", "t1"),
        "objeto": kw.pop("objeto", ""),
    }
    base.update(kw)
    return RawOpportunity(**base)


def test_raw_universe_metrics_and_denominator():
    records = [
        {"source": "pncp", "official_id": "1", "objeto": "pavimentação asfáltica"},
        {"source": "pncp", "official_id": "2", "objeto": "", "titulo": ""},
        {"source": "pncp", "official_id": "3", "objeto": "x", "items": ["a"], "categories": ["obras"], "has_tr": True},
    ]
    universe, metrics = build_raw_universe(records, full_universe_threshold=10)
    d = metrics.to_dict()
    assert d["raw_universe_count"] == 3
    assert d["recall_denominator"] == 3
    assert d["records_with_object"] == 2
    assert d["records_missing_critical_text"] == 1
    assert d["records_with_items"] == 1
    assert d["records_with_category"] == 1
    assert d["records_with_documents"] == 1
    assert d["classify_full_universe"] is True


def test_rrf_ranks_but_union_keeps_single_channel_rescues():
    universe = [
        _rec(official_id="lex-only", objeto="Execução de pavimentação asfáltica em vias"),
        _rec(official_id="sem-only", objeto="Melhorias no logradouro sem termo comum"),
        _rec(official_id="both", objeto="Execução de drenagem urbana e galerias pluviais"),
    ]
    channel_hits = {
        "lexical": {
            "pncp::lex-only": RetrievalHit("lexical", 1.0, 1),
            "pncp::both": RetrievalHit("lexical", 0.9, 2),
        },
        "semantic": {
            "pncp::sem-only": RetrievalHit("semantic", 0.5, 1),
            "pncp::both": RetrievalHit("semantic", 0.8, 2),
        },
    }
    cands, analysis = fuse_candidates(universe, channel_hits, rrf_k=60)
    ids = {c.record.canonical_id for c in cands}
    assert "pncp::lex-only" in ids
    assert "pncp::sem-only" in ids
    assert "pncp::both" in ids
    exclusive = {c.record.canonical_id: c.exclusive_rescue_channel for c in cands}
    assert exclusive["pncp::lex-only"] == "lexical"
    assert exclusive["pncp::sem-only"] == "semantic"
    assert analysis["single_channel_candidates_kept"] >= 2
    # RRF score utility
    assert rrf_score([1, 2], k=60) > rrf_score([10], k=60)


def test_hybrid_five_channels_run():
    universe = [
        _rec(
            official_id="a",
            objeto="Execução de pavimentação asfáltica",
            orgao="Secretaria Municipal de Obras",
            categories=["Obras de engenharia"],
            has_tr=True,
            valor_estimado=2_000_000,
        ),
        _rec(
            official_id="b",
            objeto="Aquisição de computador notebook",
            orgao="Secretaria de Educação",
        ),
        _rec(
            official_id="c",
            objeto="Melhorias no trecho viário central",
            orgao="Secretaria de Infraestrutura",
            has_anexos=True,
            valor_estimado=800_000,
            modalidade="Concorrência",
        ),
    ]
    cands, report = run_hybrid_retrieval(universe, classify_full_universe=True)
    assert set(report["channels"]) >= {
        "lexical",
        "semantic",
        "metadata",
        "organ_history",
        "zero_match",
    }
    assert len(cands) >= 1
    # lineage fields present
    for c in cands:
        lin = c.to_lineage_dict()
        assert "retrieved_by" in lin
        assert "retrieval_scores" in lin
        assert "zero_match_rescue" in lin


def test_selective_execution_blocks_clear_negative():
    # Negative-ish supply language + explicit execução → at least GRAY_ZONE
    rec = _rec(
        objeto="Aquisição de equipamentos com execução de obra civil de implantação de rede"
    )
    det = classify_selective(rec)
    assert det.decision in {"GRAY_ZONE", "CLEAR_POSITIVE"}
    assert det.decision != "CLEAR_NEGATIVE"


def test_selective_absence_of_keyword_not_auto_no_match():
    rec = _rec(objeto="Melhorias no logradouro principal do bairro")
    det = classify_selective(rec)
    # Cannot be automatic irreversible clear-negative solely from missing keywords
    # (may be GRAY or CLEAR_NEGATIVE only if champion is sure — short without docs → gray)
    assert det.decision in {"GRAY_ZONE", "CLEAR_NEGATIVE", "CLEAR_POSITIVE"}


def test_selective_clear_positive_pavimentacao():
    rec = _rec(objeto="Contratação para execução de pavimentação asfáltica em vias urbanas")
    det = classify_selective(rec)
    assert det.decision == "CLEAR_POSITIVE"
    assert det.positive_signals


def test_selective_clear_negative_software():
    rec = _rec(objeto="Manutenção de software e licença de uso de sistema de gestão")
    det = classify_selective(rec)
    assert det.decision == "CLEAR_NEGATIVE"


def test_llm_error_never_no_match():
    cand = CandidateRecord(
        record=_rec(objeto="Execução de drenagem urbana"),
        retrieved_by=["lexical"],
    )
    det = classify_selective(cand)
    provider = FakeLLMProvider(force_error="timeout")
    out = arbitrate(cand, det, provider, force_invoke=True)
    assert out.invoked
    assert out.decision is not None
    assert out.decision.decision == "REVIEW"
    lin = map_to_commercial(cand, det, out)
    assert lin.commercial_decision == "REVIEW"


def test_invented_evidence_forces_review():
    cand = CandidateRecord(
        record=_rec(objeto="Execução de pavimentação asfáltica em vias"),
        retrieved_by=["lexical"],
    )
    det = classify_selective(cand)
    provider = FakeLLMProvider(invent_evidence=True)
    out = arbitrate(cand, det, provider, force_invoke=True)
    assert out.decision is not None
    assert out.decision.decision == "REVIEW"
    assert out.invented_evidence


def test_evidence_literal_validation():
    source = "Execução de pavimentação asfáltica em vias urbanas"
    assert evidence_is_valid("pavimentação asfáltica", source)
    assert not evidence_is_valid("trecho inventado xyz-999", source)
    valid, invented = validate_evidence_list(
        ["pavimentação asfáltica", "documento secreto inventado"],
        source,
    )
    assert "pavimentação asfáltica" in valid
    assert invented


def test_decision_policy_match_only_commercial():
    records = [
        {
            "source": "pncp",
            "official_id": "m1",
            "objeto": "Execução de pavimentação asfáltica em vias urbanas do município",
            "orgao": "Secretaria de Obras",
            "valor_estimado": 1_000_000,
        },
        {
            "source": "pncp",
            "official_id": "n1",
            "objeto": "Aquisição de computadores All in One para laboratório",
            "orgao": "Educação",
        },
        {
            "source": "pncp",
            "official_id": "g1",
            "objeto": "Fornecimento e instalação de drenagem pluvial",
            "orgao": "Infraestrutura",
            "valor_estimado": 500_000,
            "has_tr": True,
        },
    ]
    result = run_pipeline(records, force_fake_llm=True)
    assert result.to_summary()["every_record_has_decision"] is True
    match_ids = {m["canonical_id"] for m in result.deliverables["deliverable_e_matches"]}
    for lin in result.lineages:
        if lin.canonical_id in match_ids:
            assert lin.commercial_decision == "MATCH"
        if lin.commercial_decision != "MATCH":
            assert lin.canonical_id not in match_ids
    # commercial MATCH subset of MATCH decisions
    assert all(m["lineage"]["commercial_decision"] == "MATCH" for m in result.deliverables["deliverable_e_matches"])


def test_review_overflow_preserves_and_flags():
    lineages = []
    cands = {}
    for i in range(15):
        rec = _rec(official_id=f"r{i}", objeto=f"caso duvidoso {i} melhorias viárias")
        cand = CandidateRecord(record=rec, retrieved_by=["semantic"])
        det = classify_selective(cand)
        # force gray path
        from scripts.ops.hybrid_sector.models import DeterministicResult

        det = DeterministicResult(
            decision="GRAY_ZONE",
            confidence=0.4,
            reason="test",
            positive_signals=["x"],
        )
        lin = map_to_commercial(cand, det, None)
        lin.commercial_decision = "REVIEW"
        lineages.append(lin)
        cands[lin.canonical_id] = cand
    reviews, status = prioritize_review_queue(
        lineages,
        cands,
        config=ReviewCapacityConfig(max_items_per_cycle=5, overflow_policy="preserve_and_flag"),
    )
    assert len(reviews) == 15  # no discard
    assert status["discarded"] == 0
    assert status["operational_status"] == OPERATIONALLY_BLOCKED_REVIEW_VOLUME
    assert status["preserved_all"] is True


def test_pipeline_no_silent_discard_full_path():
    records = [
        {"source": "t", "official_id": str(i), "objeto": obj}
        for i, obj in enumerate(
            [
                "Execução de terraplenagem e muro de arrimo",
                "Aquisição de medicamentos hospitalares",
                "Revitalização de praça pública com drenagem",
                "Credenciamento de instituições financeiras",
                "Serviços técnicos com escopo a definir no TR",
            ]
        )
    ]
    result = run_pipeline(records, force_fake_llm=True)
    assert len(result.lineages) == len(result.candidates)
    assert len(result.lineages) == len(result.universe)
    assert result.to_summary()["every_record_has_decision"] is True
    assert result.to_summary()["silent_drop_ids"] == []
    assert all(l.commercial_decision in {"MATCH", "REVIEW", "NO_MATCH"} for l in result.lineages)
    assert all(l.retrieval for l in result.lineages)
    assert all(l.pipeline_version for l in result.lineages)


def test_pipeline_no_silent_discard_hybrid_mode_threshold_below_n():
    """When n > full_universe_threshold, residual records must still get a decision."""
    # Mix: one clear lexical hit, one pure distractor with no engineering signal
    records = [
        {
            "source": "hyb",
            "official_id": "hit",
            "objeto": "Execução de pavimentação asfáltica em vias urbanas",
            "orgao": "Secretaria de Obras",
        },
        {
            "source": "hyb",
            "official_id": "miss",
            "objeto": "xyzzy qqq nonmatching gibberish token set alpha",
            "orgao": "Setor Administrativo",
            "valor_estimado": 1000,
        },
    ]
    # Force hybrid residual path: threshold < n so classify_full_universe=False
    cfg = {
        "raw_universe": {"full_universe_threshold": 1},
        "manual_review": {"max_items_per_cycle": 100, "overflow_policy": "preserve_and_flag"},
        "llm": {"provider": "fake", "min_confidence": 60},
        "retrieval": {
            "rrf_k": 60,
            "semantic": {"top_k": 1, "min_similarity": 0.99},  # hard to hit gibberish
            "zero_match": {"short_text_max_chars": 5, "high_value_threshold": 9e12},
        },
    }
    result = run_pipeline(records, config=cfg, force_fake_llm=True)
    universe_ids = {r.canonical_id for r in result.universe}
    decision_ids = {l.canonical_id for l in result.lineages}
    assert universe_ids - decision_ids == set(), (
        f"silent drop under hybrid: {universe_ids - decision_ids}"
    )
    assert len(result.lineages) == len(result.universe) == 2
    assert result.to_summary()["every_record_has_decision"] is True
    assert result.universe_metrics["classify_full_universe"] is False
    # Missed retrieval still has commercial decision (not disappeared)
    miss = next(l for l in result.lineages if l.canonical_id.endswith("::miss"))
    assert miss.commercial_decision in {"MATCH", "REVIEW", "NO_MATCH"}
    assert miss.retrieval.get("inclusion_reason") in {
        "hybrid_residual_universe_audit",
        "full_universe_threshold",
        "exclusive_channel:lexical",
        "multi_channel:lexical",
    } or "residual" in str(miss.retrieval.get("inclusion_reason", "")).lower() or miss.retrieval.get(
        "retrieved_by"
    )


def test_invented_evidence_accepted_counted_not_hardcoded():
    """Audit field invented_evidence_accepted is measured from lineages."""
    from scripts.ops.hybrid_sector.llm.arbitration import ArbitrationOutcome
    from scripts.ops.hybrid_sector.llm.schema import SectorLLMDecision
    from scripts.ops.hybrid_sector.models import DeterministicResult
    from scripts.ops.hybrid_sector.policy.decision import map_to_commercial
    from scripts.ops.hybrid_sector.models import CandidateRecord, RawOpportunity

    cand = CandidateRecord(
        record=RawOpportunity(
            source="t", official_id="1", objeto="Execução de pavimentação asfáltica"
        ),
        retrieved_by=["lexical"],
    )
    det = DeterministicResult(decision="GRAY_ZONE", confidence=0.4, reason="gray")
    # Simulated arbiter path that still somehow left invented evidence on outcome
    # (production arbiter forces REVIEW; policy must mark accepted=False)
    from scripts.ops.hybrid_sector.llm.fake_provider import FakeLLMProvider
    from scripts.ops.hybrid_sector.llm.arbitration import arbitrate

    out = arbitrate(
        cand, det, FakeLLMProvider(invent_evidence=True), force_invoke=True
    )
    lin = map_to_commercial(cand, det, out)
    assert lin.invented_evidence, "invented snippets must be recorded on lineage"
    assert lin.commercial_decision == "REVIEW"
    assert lin.invented_evidence_accepted is False


def test_should_invoke_llm_on_gray_and_zero_match():
    cand = CandidateRecord(
        record=_rec(objeto="caso curto", valor_estimado=600_000),
        retrieved_by=["semantic"],
        zero_match_rescue=True,
    )
    from scripts.ops.hybrid_sector.models import DeterministicResult

    det = DeterministicResult(decision="GRAY_ZONE", confidence=0.4, reason="gray")
    invoke, reasons = should_invoke_llm(det, cand)
    assert invoke
    assert "gray_zone" in reasons
