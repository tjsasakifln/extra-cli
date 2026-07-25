"""Evaluation, statistical gates, gold corpus structure, campaign entry."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.ops.campaign_hybrid_sector_recall import main as campaign_main
from scripts.ops.hybrid_sector.config_runtime import (
    CONFIG_WIRING_MAP,
    get_runtime_attr,
    load_runtime_config,
)
from scripts.ops.hybrid_sector.evaluation.gates import (
    INSUFFICIENT_STATISTICAL_POWER,
    evaluate_gates,
)
from scripts.ops.hybrid_sector.evaluation.gold_corpus import (
    gold_index,
    load_gold_corpus,
    locked_test_adequacy,
)
from scripts.ops.hybrid_sector.evaluation.metrics import (
    binomial_ci_lower_one_sided,
    decision_metrics,
)
from scripts.ops.hybrid_sector.evaluation.real_corpus import (
    BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS,
    BLOCKED_INVALID_EVALUATION_CORPUS,
    CORPUS_KIND_SYNTHETIC,
    audit_real_corpus,
    classify_corpus,
)
from scripts.ops.hybrid_sector.models import DecisionLineage, DeterministicResult
from scripts.ops.hybrid_sector.pipeline import (
    run_pipeline,
    write_campaign_artifacts,
)
from scripts.ops.hybrid_sector.retrieval.semantic import (
    EMBEDDING_CLASS_LEXICAL_FUZZY_HASH,
    HashEmbeddingProvider,
    build_embedding_provider,
)

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = ROOT / "tests/fixtures/hybrid_sector/synthetic_adversarial_corpus.json"
REAL = ROOT / "tests/fixtures/hybrid_sector/real_operational_corpus.json"
CAMP = ROOT / "artifacts/campaigns/HYBRID-SECTOR-RECALL-LLM-ARBITER-01"


def _lin(cid: str, decision: str) -> DecisionLineage:
    return DecisionLineage(
        canonical_id=cid,
        commercial_decision=decision,  # type: ignore[arg-type]
        deterministic=DeterministicResult(
            decision="GRAY_ZONE",
            confidence=0.5,
            reason="test",
        ),
    )


def test_binomial_ci_all_success_large_n():
    low = binomial_ci_lower_one_sided(300, 300)
    assert low >= 0.99


def test_synthetic_corpus_reclassified_not_operational():
    assert SYNTHETIC.is_file(), "synthetic adversarial corpus missing"
    corpus = load_gold_corpus(SYNTHETIC)
    assert classify_corpus(corpus) == CORPUS_KIND_SYNTHETIC
    assert corpus.get("corpus_kind") == CORPUS_KIND_SYNTHETIC
    assert corpus.get("operational_gold") is False
    audit = audit_real_corpus(corpus)
    assert audit["operational_gold_eligible"] is False
    assert BLOCKED_INVALID_EVALUATION_CORPUS in audit["blockers"]
    adq = locked_test_adequacy(corpus)
    # numeric quotas may pass on synthetic but not operational gold
    assert adq["numeric_quotas_only"] is True
    assert BLOCKED_INVALID_EVALUATION_CORPUS in adq["blockers"]


def test_real_corpus_scaffold_insufficient():
    assert REAL.is_file()
    corpus = load_gold_corpus(REAL)
    audit = audit_real_corpus(corpus)
    assert audit["operational_gold_eligible"] is False
    assert BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS in audit["blockers"]
    assert len(corpus.get("records") or []) == 0


def test_annotation_artifacts_exist():
    base = ROOT / "tests/fixtures/hybrid_sector"
    for name in (
        "annotation-provenance.json",
        "annotation-agreement.json",
        "annotation-adjudications.json",
    ):
        assert (base / name).is_file(), name


def test_gates_insufficient_power_honest():
    retrieval = {
        "retrieval_recall": 1.0,
        "retrieval_recall_lower_95": 0.5,
        "n_gold_positives": 10,
    }
    decision = {
        "safe_recall_match_plus_review": 1.0,
        "safe_recall_lower_95": 0.5,
        "critical_false_negatives": 0,
        "n_positives": 10,
        "match_precision": 1.0,
        "match_precision_lower_95": 0.5,
        "match_false_positives_hard": 0,
        "unlabeled_match_count": 0,
        "all_match_count": 0,
        "evaluated_match_count": 0,
    }
    res = evaluate_gates(
        retrieval,
        decision,
        audit={
            "invented_evidence_accepted": 0,
            "llm_error_to_review_rate": 1.0,
            "lineage_coverage": 1.0,
            "silent_discards": 0,
        },
        evaluation_level="B",
    )
    assert res["gates"]["statistical_power"]["status"] == INSUFFICIENT_STATISTICAL_POWER
    assert res["terminal_status"] != "READY_FOR_RECALL_ASSURANCE_REVIEW"
    assert "BLOCKED_INVALID_EVALUATION_CORPUS" in res["active_blockers"]
    assert "BLOCKED_LLM_OPERATIONAL_VALIDATION" in res["active_blockers"]
    assert "BLOCKED_FULL_SUITE_VALIDATION" in res["active_blockers"]


def test_gates_ready_requires_all_real_evidence():
    """READY only when Level C + all operational gates pass — synthetic metrics alone insufficient."""
    retrieval = {
        "retrieval_recall": 1.0,
        "retrieval_recall_lower_95": 0.995,
        "n_gold_positives": 300,
    }
    decision = {
        "safe_recall_match_plus_review": 1.0,
        "safe_recall_lower_95": 0.995,
        "critical_false_negatives": 0,
        "n_positives": 300,
        "match_precision": 1.0,
        "match_precision_all": 1.0,
        "match_precision_lower_95": 0.95,
        "match_false_positives_hard": 0,
        "unlabeled_match_count": 0,
        "all_match_count": 10,
        "evaluated_match_count": 10,
        "review_rate": 0.1,
        "ambiguous_match_commercial_risk": 0,
    }
    # Level B with perfect metrics still not READY
    res_b = evaluate_gates(
        retrieval,
        decision,
        audit={
            "invented_evidence_accepted": 0,
            "llm_error_to_review_rate": 1.0,
            "lineage_coverage": 1.0,
            "silent_discards": 0,
        },
        evaluation_level="B",
        review_status={"operational_status": "WITHIN_CAPACITY"},
    )
    assert res_b["terminal_status"] != "READY_FOR_RECALL_ASSURANCE_REVIEW"
    assert res_b["all_core_pass"] is False

    # Level C with all evidence
    res_c = evaluate_gates(
        retrieval,
        decision,
        audit={
            "invented_evidence_accepted": 0,
            "llm_error_to_review_rate": 1.0,
            "lineage_coverage": 1.0,
            "silent_discards": 0,
        },
        corpus_audit={
            "operational_gold_eligible": True,
            "blockers": [],
            "dual_review": {"ok": True},
            "quotas": {"ok": True},
        },
        llm_operational={
            "passed": True,
            "n_samples": 200,
            "min_required": 200,
            "human_review_complete": True,
        },
        embedding_operational={"passed": True, "provider_class": "sentence_transformer"},
        review_status={"operational_status": "WITHIN_CAPACITY"},
        full_suite={"passed": True, "status": "FULL_SUITE_GREEN"},
        evaluation_level="C",
        rc_v2_intact=True,
    )
    assert res_c["terminal_status"] == "READY_FOR_RECALL_ASSURANCE_REVIEW"
    assert res_c["all_core_pass"] is True


def test_unlabeled_match_gate_fails():
    """Force unlabeled MATCH → integrity gate failure."""
    gold = {"a": "POSITIVE", "b": "NEGATIVE"}
    lineages = [
        _lin("a", "MATCH"),
        _lin("b", "MATCH"),
        _lin("unlabeled-x", "MATCH"),  # no gold label
    ]
    m = decision_metrics(gold, lineages)
    assert m["unlabeled_match_count"] == 1
    assert m["unlabeled_match_gate_ok"] is False
    assert m["all_match_count"] == 3
    assert m["evaluated_match_count"] == 3
    assert m["all_match_count_equals_evaluated"] is True
    # primary precision over ALL matches (not hard-only subset)
    assert m["match_precision_all"] == pytest.approx(1 / 3)
    assert m["match_precision_hard_only_is_primary"] is False

    res = evaluate_gates(
        {"retrieval_recall": 1.0, "retrieval_recall_lower_95": 0.995, "n_gold_positives": 300},
        {
            **m,
            "n_positives": 300,
            "safe_recall_match_plus_review": 1.0,
            "safe_recall_lower_95": 0.995,
            "critical_false_negatives": 0,
        },
        audit={
            "invented_evidence_accepted": 0,
            "llm_error_to_review_rate": 1.0,
            "lineage_coverage": 1.0,
            "silent_discards": 0,
        },
        evaluation_level="C",
        corpus_audit={"operational_gold_eligible": True, "blockers": [], "quotas": {"ok": True}},
    )
    assert res["gates"]["unlabeled_match"]["pass"] is False
    assert "BLOCKED_UNLABELED_MATCH" in res["active_blockers"]


def test_precision_variants_all_conservative_hard():
    gold = {
        "p1": "POSITIVE",
        "n1": "NEGATIVE",
        "a1": "AMBIGUOUS",
    }
    lineages = [
        _lin("p1", "MATCH"),
        _lin("n1", "MATCH"),
        _lin("a1", "MATCH"),
    ]
    m = decision_metrics(gold, lineages, adjudicated_ids=set())
    assert m["all_match_count"] == 3
    assert m["match_true_positives"] == 1
    assert m["match_false_positives_hard"] == 1
    assert m["match_ambiguous"] == 1
    assert m["ambiguous_match_unadjudicated_as_error"] == 1
    assert m["match_precision_all"] == pytest.approx(1 / 3)
    # hard-only excludes ambiguous
    assert m["match_precision_hard_only"] == pytest.approx(0.5)
    assert m["match_precision_hard_only_is_primary"] is False


def test_locked_only_no_unlabeled_distractors():
    """Preferred path: locked-only universe — no unlabeled MATCH from dev/calibration."""
    if not SYNTHETIC.is_file():
        pytest.skip("synthetic corpus missing")
    # Small subset via pipeline on synthetic locked — may be slow; sample via gold_index
    corpus = load_gold_corpus(SYNTHETIC)
    labels, meta, critical = gold_index(corpus, split="locked")
    # Only first 30 locked for speed
    sample_ids = list(labels.keys())[:30]
    labels_s = {i: labels[i] for i in sample_ids}
    meta_s = {i: meta[i] for i in sample_ids}
    records = [
        {
            "source": meta_s[i].get("source") or "gold",
            "official_id": meta_s[i].get("official_id") or i.split("::")[-1],
            "objeto": meta_s[i].get("objeto") or "",
            "orgao": meta_s[i].get("orgao") or "",
            "uf": meta_s[i].get("uf") or "SC",
            "valor_estimado": meta_s[i].get("valor_estimado"),
            "categories": meta_s[i].get("categories") or [],
            "items": meta_s[i].get("items") or [],
            "has_tr": bool(meta_s[i].get("has_tr")),
        }
        for i in sample_ids
    ]
    result = run_pipeline(
        records,
        force_fake_llm=True,
        gold_labels=labels_s,
        gold_meta=meta_s,
        critical_positive_ids={i for i in critical if i in labels_s},
        corpus_kind=CORPUS_KIND_SYNTHETIC,
        evaluation_level="B",
    )
    dec = result.evaluation.get("decision_metrics") or {}
    assert dec.get("unlabeled_match_count", 0) == 0
    assert dec.get("all_match_count") == dec.get("evaluated_match_count")


def test_hash_provider_is_lexical_fuzzy_hash():
    p = HashEmbeddingProvider()
    assert p.embedding_class == EMBEDDING_CLASS_LEXICAL_FUZZY_HASH
    assert p.operational_semantic is False
    built = build_embedding_provider({"semantic": {"provider": "lexical_fuzzy_hash"}})
    assert built.embedding_class == EMBEDDING_CLASS_LEXICAL_FUZZY_HASH


def test_config_wiring_each_yaml_key_reaches_runtime(tmp_path):
    """Mutate each wired YAML key and confirm runtime object field updates."""
    base = yaml.safe_load(
        (ROOT / "config/hybrid_sector/default.yaml").read_text(encoding="utf-8")
    )
    mutations = {
        "llm.model": "mutated-model-xyz",
        "llm.base_url": "https://example.test/v1",
        "llm.timeout_seconds": 42.0,
        "llm.max_retries": 7,
        "llm.max_concurrency": 9,
        "llm.max_cost_usd_per_cycle": 12.5,
        "llm.circuit_breaker_failures": 3,
        "llm.min_confidence": 77,
        "llm.second_adjudication_value_threshold": 2_000_000.0,
        "llm.cache_enabled": False,
        "llm.provider": "openai_compatible",
        "retrieval.semantic.provider": "sentence_transformer",
        "retrieval.semantic.model_id": "mutated-embed-model",
        "retrieval.semantic.base_url": "https://embed.test/v1",
        "retrieval.semantic.timeout_seconds": 33.0,
        "retrieval.semantic.max_retries": 4,
        "retrieval.semantic.cache_path": str(tmp_path / "emb.cache"),
        "manual_review.max_items_per_cycle": 55,
        "raw_universe.full_universe_threshold": 123,
        "retrieval.rrf_k": 17,
    }

    def set_dotted(d: dict, path: str, value):
        parts = path.split(".")
        cur = d
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = value

    for yaml_path, value in mutations.items():
        data = json.loads(json.dumps(base))  # deep copy via json
        set_dotted(data, yaml_path, value)
        cfg_path = tmp_path / f"cfg-{yaml_path.replace('.', '_')}.yaml"
        cfg_path.write_text(yaml.dump(data), encoding="utf-8")
        rt = load_runtime_config(cfg_path)
        runtime_path = CONFIG_WIRING_MAP[yaml_path]
        got = get_runtime_attr(rt, runtime_path)
        assert got == value, f"{yaml_path} → {runtime_path}: expected {value!r} got {got!r}"


def test_campaign_entry_fixtures_twice(tmp_path):
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    assert campaign_main(["--fixtures", "--out", str(out1)]) == 0
    assert campaign_main(["--fixtures", "--out", str(out2)]) == 0
    for out in (out1, out2):
        result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        assert result["terminal_status"] != "READY_FOR_RECALL_ASSURANCE_REVIEW" or result.get(
            "all_core_pass"
        )
        assert result["claims"]["ACCEPTED"] is False
        assert result["claims"]["MERGED"] is False
        assert (out / "deliverable_e_matches.json").is_file()
        assert (out / "synthetic_test_results.json").is_file() or (
            out / "real_operational_results.json"
        ).is_file()
        # multi-blocker honesty when not ready
        if result["terminal_status"] != "READY_FOR_RECALL_ASSURANCE_REVIEW":
            blockers = set(result.get("active_blockers") or [])
            assert blockers != {"BLOCKED_REVIEW_CAPACITY"}


def test_require_ready_exits_nonzero(tmp_path):
    out = tmp_path / "req"
    code = campaign_main(["--fixtures", "--out", str(out), "--require-ready"])
    assert code != 0


def test_locked_real_corpus_campaign(tmp_path):
    """Locked evaluation without --fixtures on real scaffold."""
    out = tmp_path / "locked"
    code = campaign_main(
        [
            "--corpus",
            str(REAL),
            "--split",
            "locked",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert result["terminal_status"] != "READY_FOR_RECALL_ASSURANCE_REVIEW"
    blockers = set(result.get("active_blockers") or [])
    # multi-blocker: not only review capacity
    assert "BLOCKED_LLM_OPERATIONAL_VALIDATION" in blockers or result[
        "terminal_status"
    ] == "BLOCKED_LLM_OPERATIONAL_VALIDATION"
    assert result.get("all_core_pass") is False
    # separated artifacts
    assert (out / "paid_llm_validation.json").is_file()
    assert (out / "full_suite_status.json").is_file()
    assert (out / "real_operational_results.json").is_file()
    assert (out / "annotation-provenance.json").is_file()


def test_write_artifacts_contract(tmp_path):
    records = [
        {
            "source": "pncp",
            "official_id": "1",
            "objeto": "Execução de pavimentação asfáltica em vias",
            "orgao": "Secretaria de Obras",
        },
        {
            "source": "pncp",
            "official_id": "2",
            "objeto": "Aquisição de notebook para secretaria",
        },
    ]
    gold = {"pncp::1": "POSITIVE", "pncp::2": "NEGATIVE"}
    result = run_pipeline(
        records,
        force_fake_llm=True,
        gold_labels=gold,
        corpus_kind=CORPUS_KIND_SYNTHETIC,
        evaluation_level="B",
    )
    write_campaign_artifacts(result, tmp_path, corpus_manifest={"n": 2})
    required = [
        "manifest.json",
        "retrieval-evaluation.json",
        "classification-evaluation.json",
        "calibration.json",
        "confidence-intervals.json",
        "gold-corpus-manifest.json",
        "shadow-replay.json",
        "no-match-audit.json",
        "review-queue-analysis.json",
        "llm-cost.json",
        "llm-failures.json",
        "prompt-injection-tests.json",
        "drift-baseline.json",
        "findings.json",
        "result.json",
        "final-report.md",
        "deliverable_e_matches.json",
        "deliverable_e_review_queue.json",
        "deliverable_e_no_match_audit.json",
        "synthetic_test_results.json",
        "real_operational_results.json",
        "paid_llm_validation.json",
        "full_suite_status.json",
    ]
    for name in required:
        assert (tmp_path / name).is_file(), name
    result_json = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result_json["claims"]["ACCEPTED"] is False
    assert result_json.get("all_core_pass") is False
    cost = json.loads((tmp_path / "llm-cost.json").read_text(encoding="utf-8"))
    assert cost.get("not_yaml_copy") is True
    assert "observed_cost_usd" in cost


def test_promotion_eligible_false_on_synthetic():
    if not SYNTHETIC.is_file():
        pytest.skip("missing synthetic")
    # tiny run
    records = [
        {
            "source": "pncp",
            "official_id": "1",
            "objeto": "Execução de pavimentação asfáltica",
            "orgao": "Secretaria de Obras",
            "captured_at": "2026-01-01",
        },
        {
            "source": "portal_sc",
            "official_id": "2",
            "objeto": "Aquisição de canetas",
            "captured_at": "2026-02-01",
        },
    ]
    gold = {"pncp::1": "POSITIVE", "portal_sc::2": "NEGATIVE"}
    result = run_pipeline(
        records,
        force_fake_llm=True,
        gold_labels=gold,
        corpus_kind=CORPUS_KIND_SYNTHETIC,
        evaluation_level="B",
    )
    shadow = result.evaluation.get("shadow_replay") or {}
    overall = shadow.get("overall") or shadow
    assert overall.get("promotion_eligible") is False
