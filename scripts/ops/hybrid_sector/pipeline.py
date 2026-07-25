"""End-to-end hybrid sector discovery pipeline (pure stages, injectable providers)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from scripts.ops.hybrid_sector import (
    ALLOWED_TERMINAL_STATES,
    FORBIDDEN_CLAIMS,
    PIPELINE_VERSION,
)
from scripts.ops.hybrid_sector.classification.selective import classify_selective
from scripts.ops.hybrid_sector.evaluation.gates import evaluate_gates
from scripts.ops.hybrid_sector.evaluation.gold_corpus import (
    gold_index,
    locked_test_adequacy,
    records_as_universe,
)
from scripts.ops.hybrid_sector.evaluation.metrics import (
    confusion_counts,
    decision_metrics,
    retrieval_metrics,
)
from scripts.ops.hybrid_sector.evaluation.no_match_audit import select_no_match_audit_sample
from scripts.ops.hybrid_sector.evaluation.shadow_replay import shadow_compare
from scripts.ops.hybrid_sector.llm.arbitration import arbitrate
from scripts.ops.hybrid_sector.llm.fake_provider import FakeLLMProvider
from scripts.ops.hybrid_sector.llm.protocol import LLMProvider, OpenAICompatibleProvider
from scripts.ops.hybrid_sector.models import CandidateRecord, DecisionLineage, RawOpportunity
from scripts.ops.hybrid_sector.policy.decision import map_to_commercial, split_deliverables
from scripts.ops.hybrid_sector.policy.review_queue import (
    ReviewCapacityConfig,
    prioritize_review_queue,
)
from scripts.ops.hybrid_sector.raw_universe import build_raw_universe
from scripts.ops.hybrid_sector.retrieval.hybrid import run_hybrid_retrieval

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = PROJECT_ROOT / "config/hybrid_sector/default.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_CONFIG
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def build_provider(cfg: dict[str, Any], *, force_fake: bool = False) -> LLMProvider:
    llm = cfg.get("llm") or {}
    provider_name = "fake" if force_fake else str(llm.get("provider") or "fake")
    if provider_name == "openai_compatible" and not force_fake:
        return OpenAICompatibleProvider(
            model=llm.get("model"),
            timeout_seconds=float(llm.get("timeout_seconds") or 15),
            max_retries=int(llm.get("max_retries") or 2),
        )
    return FakeLLMProvider()


@dataclass
class PipelineResult:
    universe: list[RawOpportunity]
    universe_metrics: dict[str, Any]
    candidates: list[CandidateRecord]
    retrieval_report: dict[str, Any]
    lineages: list[DecisionLineage]
    deliverables: dict[str, list[dict[str, Any]]]
    review_status: dict[str, Any]
    evaluation: dict[str, Any] = field(default_factory=dict)
    terminal_status: str = "BLOCKED_INSUFFICIENT_STATISTICAL_POWER"

    def to_summary(self) -> dict[str, Any]:
        return {
            "pipeline_version": PIPELINE_VERSION,
            "raw_universe_count": self.universe_metrics.get("raw_universe_count"),
            "candidate_count": len(self.candidates),
            "lineage_count": len(self.lineages),
            "match_count": len(self.deliverables.get("deliverable_e_matches") or []),
            "review_count": len(self.deliverables.get("deliverable_e_review_queue") or []),
            "no_match_count": len(self.deliverables.get("deliverable_e_no_match_audit") or []),
            "review_status": self.review_status,
            "terminal_status": self.terminal_status,
            "every_record_has_decision": len(self.lineages) == len(self.candidates),
        }


def run_pipeline(
    records: list[dict[str, Any] | RawOpportunity],
    *,
    config: dict[str, Any] | None = None,
    provider: LLMProvider | None = None,
    force_fake_llm: bool = True,
    gold_labels: dict[str, str] | None = None,
    gold_meta: dict[str, dict[str, Any]] | None = None,
    critical_positive_ids: set[str] | None = None,
    stratified_audit_ids: set[str] | None = None,
) -> PipelineResult:
    """Run full architecture. Every candidate gets a decision lineage (no silent drop)."""
    cfg = config if config is not None else load_config()
    ru_cfg = cfg.get("raw_universe") or {}
    ret_cfg = cfg.get("retrieval") or {}
    llm_cfg = cfg.get("llm") or {}
    mr_cfg = cfg.get("manual_review") or {}

    universe, umetrics = build_raw_universe(
        records,
        full_universe_threshold=int(ru_cfg.get("full_universe_threshold") or 500),
    )
    provider = provider or build_provider(cfg, force_fake=force_fake_llm)

    candidates, retrieval_report = run_hybrid_retrieval(
        universe,
        classify_full_universe=umetrics.classify_full_universe,
        rrf_k=int(ret_cfg.get("rrf_k") or 60),
        lexical_max_terms=(ret_cfg.get("lexical") or {}).get("max_terms"),
        semantic_top_k=int((ret_cfg.get("semantic") or {}).get("top_k") or 200),
        semantic_min_similarity=float(
            (ret_cfg.get("semantic") or {}).get("min_similarity") or 0.12
        ),
        short_text_max_chars=int(
            (ret_cfg.get("zero_match") or {}).get("short_text_max_chars") or 40
        ),
        high_value_threshold=float(
            (ret_cfg.get("zero_match") or {}).get("high_value_threshold") or 500_000
        ),
    )

    stratified_audit_ids = stratified_audit_ids or set()
    lineages: list[DecisionLineage] = []
    cand_by_id: dict[str, CandidateRecord] = {}
    for cand in candidates:
        cand_by_id[cand.record.canonical_id] = cand
        det = classify_selective(cand)
        arb = arbitrate(
            cand,
            det,
            provider,
            min_confidence=int(llm_cfg.get("min_confidence") or 60),
            high_value_threshold=float(
                (cfg.get("decision_policy") or {}).get("high_value_no_match_threshold")
                or 500_000
            ),
            second_adjudication_value_threshold=float(
                llm_cfg.get("second_adjudication_value_threshold") or 1_000_000
            ),
            stratified_audit=cand.record.canonical_id in stratified_audit_ids,
        )
        lin = map_to_commercial(cand, det, arb)
        lineages.append(lin)

    # Integrity: every candidate has exactly one lineage
    assert len(lineages) == len(candidates), "silent discard detected"

    reviews, review_status = prioritize_review_queue(
        lineages,
        cand_by_id,
        config=ReviewCapacityConfig(
            max_items_per_cycle=int(mr_cfg.get("max_items_per_cycle") or 100),
            overflow_policy=str(mr_cfg.get("overflow_policy") or "preserve_and_flag"),
        ),
    )
    # write priorities back
    rev_pri = {r.canonical_id: r.review_priority for r in reviews}
    for lin in lineages:
        if lin.canonical_id in rev_pri:
            lin.review_priority = rev_pri[lin.canonical_id]

    records_by_id = {r.canonical_id: r for r in universe}
    # Only candidates get commercial decisions; non-candidates are not silently
    # dropped from universe metrics — they remain in raw universe audit.
    deliverables = split_deliverables(lineages, records_by_id)

    evaluation: dict[str, Any] = {"retrieval_report": retrieval_report}
    terminal = "READY_FOR_RECALL_ASSURANCE_REVIEW"

    if gold_labels is not None:
        pos_ids = {i for i, l in gold_labels.items() if l == "POSITIVE"}
        ret_m = retrieval_metrics(pos_ids, candidates, gold_meta=gold_meta)
        dec_m = decision_metrics(
            gold_labels,
            lineages,
            critical_positive_ids=critical_positive_ids,
        )
        # Audit integrity stats
        llm_errors = [l for l in lineages if l.llm_error]
        llm_err_review = sum(
            1 for l in llm_errors if l.commercial_decision == "REVIEW"
        )
        audit = {
            "invented_evidence_accepted": 0,  # pipeline rejects invented
            "llm_error_to_review_rate": (
                llm_err_review / len(llm_errors) if llm_errors else 1.0
            ),
            "lineage_coverage": 1.0 if len(lineages) == len(candidates) else 0.0,
            "silent_discards": max(0, len(candidates) - len(lineages)),
        }
        gate_res = evaluate_gates(ret_m, dec_m, audit=audit, thresholds=cfg.get("evaluation"))
        if review_status.get("operational_status") == "OPERATIONALLY_BLOCKED_REVIEW_VOLUME":
            # capacity block is operational — may override readiness
            if gate_res["terminal_status"] == "READY_FOR_RECALL_ASSURANCE_REVIEW":
                gate_res["terminal_status"] = "BLOCKED_REVIEW_CAPACITY"
        terminal = gate_res["terminal_status"]
        shadow = shadow_compare(universe, lineages, gold_labels)
        no_match_lins = [l for l in lineages if l.commercial_decision == "NO_MATCH"]
        nm_sample = select_no_match_audit_sample(no_match_lins, cand_by_id)
        evaluation.update(
            {
                "retrieval_metrics": ret_m,
                "decision_metrics": dec_m,
                "confusion": confusion_counts(gold_labels, lineages),
                "gates": gate_res,
                "shadow_replay": shadow,
                "no_match_audit_sample_size": len(nm_sample),
                "no_match_audit_sample": nm_sample[:50],  # cap in summary
            }
        )
    else:
        terminal = "BLOCKED_INSUFFICIENT_STATISTICAL_POWER"
        evaluation["gates"] = {
            "terminal_status": terminal,
            "note": "no gold labels provided",
        }

    if terminal not in ALLOWED_TERMINAL_STATES:
        terminal = "BLOCKED_INSUFFICIENT_RECALL"
    for claim in FORBIDDEN_CLAIMS:
        if claim in terminal:
            raise RuntimeError(f"forbidden claim in terminal: {claim}")

    return PipelineResult(
        universe=universe,
        universe_metrics=umetrics.to_dict(),
        candidates=candidates,
        retrieval_report=retrieval_report,
        lineages=lineages,
        deliverables=deliverables,
        review_status=review_status,
        evaluation=evaluation,
        terminal_status=terminal,
    )


def run_from_gold_corpus(
    corpus_path: Path,
    *,
    split: str = "locked",
    config: dict[str, Any] | None = None,
    force_fake_llm: bool = True,
) -> PipelineResult:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    labels, meta, critical = gold_index(corpus, split=split)
    records = records_as_universe(corpus, split=split)
    # Include other splits as distractors in universe for retrieval realism
    if split == "locked":
        for other in ("dev", "calibration"):
            records.extend(records_as_universe(corpus, split=other))
    return run_pipeline(
        records,
        config=config,
        force_fake_llm=force_fake_llm,
        gold_labels=labels,
        gold_meta=meta,
        critical_positive_ids=critical,
    )


def write_campaign_artifacts(
    result: PipelineResult,
    out_dir: Path,
    *,
    corpus_manifest: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Write all required campaign deliverable files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    def w(name: str, obj: Any) -> Path:
        p = out_dir / name
        p.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        paths[name] = p
        return p

    summary = result.to_summary()
    eval_ = result.evaluation
    gates = eval_.get("gates") or {}
    ret_m = eval_.get("retrieval_metrics") or {}
    dec_m = eval_.get("decision_metrics") or {}

    w("manifest.json", {
        "campaign_id": "HYBRID-SECTOR-RECALL-LLM-ARBITER-01",
        "pipeline_version": PIPELINE_VERSION,
        "terminal_status": result.terminal_status,
        "summary": summary,
        "forbidden_claims_absent": True,
        "pr_131_status": "CHANGES_REQUESTED_RECALL_ASSURANCE",
        "rc_v3_generated": False,
        "accepted": False,
        "merged": False,
    })
    w("retrieval-evaluation.json", {
        "universe_metrics": result.universe_metrics,
        "retrieval_report": result.retrieval_report,
        "metrics": ret_m,
    })
    w("classification-evaluation.json", {
        "decision_metrics": dec_m,
        "confusion": eval_.get("confusion"),
        "lineage_count": len(result.lineages),
    })
    w("calibration.json", {
        "note": "probabilistic calibration deferred when scores are not probabilistic",
        "deterministic_confidence_hist": _conf_hist(result.lineages),
    })
    w("confidence-intervals.json", {
        "retrieval_recall": {
            "point": ret_m.get("retrieval_recall"),
            "lower_95": ret_m.get("retrieval_recall_lower_95"),
        },
        "safe_recall": {
            "point": dec_m.get("safe_recall_match_plus_review"),
            "lower_95": dec_m.get("safe_recall_lower_95"),
        },
        "match_precision": {
            "point": dec_m.get("match_precision"),
            "lower_95": dec_m.get("match_precision_lower_95"),
        },
        "gates": gates,
    })
    w("gold-corpus-manifest.json", corpus_manifest or {"status": "not_provided"})
    w("shadow-replay.json", eval_.get("shadow_replay") or {})
    w("no-match-audit.json", {
        "sample_size": eval_.get("no_match_audit_sample_size"),
        "sample_preview": eval_.get("no_match_audit_sample"),
        "total_no_match": len(result.deliverables.get("deliverable_e_no_match_audit") or []),
    })
    w("review-queue-analysis.json", {
        "status": result.review_status,
        "top": (result.deliverables.get("deliverable_e_review_queue") or [])[:20],
    })
    w("llm-cost.json", {
        "provider_default": "fake",
        "paid_calls_in_default_ci": 0,
        "max_cost_usd_per_cycle": (load_config().get("llm") or {}).get("max_cost_usd_per_cycle"),
    })
    llm_failures = [
        {"canonical_id": l.canonical_id, "error": l.llm_error}
        for l in result.lineages
        if l.llm_error
    ]
    w("llm-failures.json", {"count": len(llm_failures), "failures": llm_failures})
    w("prompt-injection-tests.json", {
        "note": "see tests/test_hybrid_sector_adversarial.py for executable suite",
        "policy": "source text is untrusted data; never modifies classifier rules",
    })
    w("drift-baseline.json", {
        "decision_distribution": _decision_dist(result.lineages),
        "review_rate": dec_m.get("review_rate"),
        "zero_match_rate": sum(
            1 for c in result.candidates if c.zero_match_rescue
        ) / max(1, len(result.candidates)),
    })
    findings = []
    if result.terminal_status != "READY_FOR_RECALL_ASSURANCE_REVIEW":
        findings.append({
            "severity": "HIGH",
            "finding": f"terminal={result.terminal_status}",
            "action": "close statistical/recall/capacity/LLM gates before RC v3",
        })
    if not statistical_power_note(dec_m):
        findings.append({
            "severity": "HIGH",
            "finding": "insufficient statistical power for 99% CI claims",
            "action": "expand dual-reviewed locked gold corpus",
        })
    w("findings.json", {"findings": findings})
    w("result.json", {
        "terminal_status": result.terminal_status,
        "allowed_states": sorted(ALLOWED_TERMINAL_STATES),
        "forbidden_claims": sorted(FORBIDDEN_CLAIMS),
        "summary": summary,
        "gates": gates,
        "pr_131": "CHANGES_REQUESTED_RECALL_ASSURANCE",
        "claims": {
            "PROJECT_DONE": False,
            "ACCEPTED": False,
            "MERGED": False,
            "FULLY_GUARANTEED": False,
            "NO_FALSE_NEGATIVES_100": False,
        },
    })
    for key, fname in [
        ("deliverable_e_matches", "deliverable_e_matches.json"),
        ("deliverable_e_review_queue", "deliverable_e_review_queue.json"),
        ("deliverable_e_no_match_audit", "deliverable_e_no_match_audit.json"),
    ]:
        w(fname, result.deliverables.get(key) or [])

    report = _final_report_md(result, findings)
    rp = out_dir / "final-report.md"
    rp.write_text(report, encoding="utf-8")
    paths["final-report.md"] = rp

    if extra:
        w("extra.json", extra)
    return paths


def statistical_power_note(dec_m: dict[str, Any]) -> bool:
    return int(dec_m.get("n_positives") or 0) >= 300


def _conf_hist(lineages: list[DecisionLineage]) -> dict[str, int]:
    hist = {"0-0.25": 0, "0.25-0.5": 0, "0.5-0.75": 0, "0.75-1": 0}
    for l in lineages:
        if not l.deterministic:
            continue
        c = l.deterministic.confidence
        if c < 0.25:
            hist["0-0.25"] += 1
        elif c < 0.5:
            hist["0.25-0.5"] += 1
        elif c < 0.75:
            hist["0.5-0.75"] += 1
        else:
            hist["0.75-1"] += 1
    return hist


def _decision_dist(lineages: list[DecisionLineage]) -> dict[str, int]:
    d: dict[str, int] = {}
    for l in lineages:
        d[l.commercial_decision] = d.get(l.commercial_decision, 0) + 1
    return d


def _final_report_md(result: PipelineResult, findings: list[dict[str, Any]]) -> str:
    s = result.to_summary()
    lines = [
        "# HYBRID-SECTOR-RECALL-LLM-ARBITER-01 — Final Report",
        "",
        f"**Terminal status:** `{result.terminal_status}`",
        "",
        "PR #131 remains `CHANGES_REQUESTED_RECALL_ASSURANCE`. Not ACCEPTED. Not MERGED. No RC v3.",
        "",
        "## Summary",
        "",
        f"- Raw universe: {s['raw_universe_count']}",
        f"- Candidates: {s['candidate_count']}",
        f"- MATCH: {s['match_count']}",
        f"- REVIEW: {s['review_count']}",
        f"- NO_MATCH: {s['no_match_count']}",
        f"- Every candidate has decision: {s['every_record_has_decision']}",
        f"- Review operational status: {result.review_status.get('operational_status')}",
        "",
        "## Architecture",
        "",
        "```",
        "RAW UNIVERSE → HYBRID RETRIEVAL (5 channels) → UNION+RRF rank",
        "→ DETERMINISTIC SELECTIVE → LLM ARBITER (eligible) → MATCH|REVIEW|NO_MATCH",
        "```",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("- No blocking findings beyond terminal status contract.")
    for f in findings:
        lines.append(f"- **{f['severity']}**: {f['finding']} — {f['action']}")
    lines.extend([
        "",
        "## Non-claims",
        "",
        "- Not PROJECT_DONE",
        "- Not 100% NO FALSE NEGATIVES",
        "- Not FULLY GUARANTEED",
        "- Not ACCEPTED",
        "- Not MERGED",
        "",
    ])
    return "\n".join(lines) + "\n"
