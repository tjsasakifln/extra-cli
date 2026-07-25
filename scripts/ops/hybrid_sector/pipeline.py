"""End-to-end hybrid sector discovery pipeline (pure stages, injectable providers)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from scripts.ops.hybrid_sector import (
    ALLOWED_TERMINAL_STATES,
    FORBIDDEN_CLAIMS,
    FOUNDATION_PR_STATUS_READY,
    PIPELINE_VERSION,
    REQUIRED_HONEST_BLOCKERS,
)
from scripts.ops.hybrid_sector.classification.selective import classify_selective
from scripts.ops.hybrid_sector.config_runtime import (
    HybridSectorRuntimeConfig,
    load_runtime_config,
)
from scripts.ops.hybrid_sector.evaluation.embedding_benchmark import (
    benchmark_embedding_channels,
)
from scripts.ops.hybrid_sector.evaluation.gates import evaluate_gates
from scripts.ops.hybrid_sector.evaluation.gold_corpus import (
    adjudicated_match_ids,
    gold_index,
    load_gold_corpus,
    records_as_universe,
)
from scripts.ops.hybrid_sector.evaluation.llm_operational import (
    run_llm_operational_validation,
)
from scripts.ops.hybrid_sector.evaluation.metrics import (
    confusion_counts,
    decision_metrics,
    retrieval_metrics,
)
from scripts.ops.hybrid_sector.evaluation.no_match_audit import select_no_match_audit_sample
from scripts.ops.hybrid_sector.evaluation.real_corpus import (
    CORPUS_KIND_SYNTHETIC,
    audit_real_corpus,
    classify_corpus,
)
from scripts.ops.hybrid_sector.evaluation.review_analysis import analyze_review_queue
from scripts.ops.hybrid_sector.evaluation.shadow_replay import (
    multi_window_shadow,
)
from scripts.ops.hybrid_sector.llm.arbitration import arbitrate
from scripts.ops.hybrid_sector.llm.fake_provider import FakeLLMProvider
from scripts.ops.hybrid_sector.llm.protocol import (
    CircuitBreaker,
    CostGuard,
    LLMProvider,
    NullResponseCache,
    OpenAICompatibleProvider,
    ResponseCache,
)
from scripts.ops.hybrid_sector.models import CandidateRecord, DecisionLineage, RawOpportunity
from scripts.ops.hybrid_sector.policy.decision import map_to_commercial, split_deliverables
from scripts.ops.hybrid_sector.policy.review_queue import (
    ReviewCapacityConfig,
    prioritize_review_queue,
)
from scripts.ops.hybrid_sector.raw_universe import build_raw_universe
from scripts.ops.hybrid_sector.retrieval.hybrid import run_hybrid_retrieval
from scripts.ops.hybrid_sector.retrieval.semantic import build_embedding_provider

# Paid LLM default model (never commit secrets; key from .env / OPENAI_API_KEY)
DEFAULT_PAID_LLM_MODEL = "gpt-4o-mini"
DEFAULT_PAID_LLM_PROVIDER = "openai_compatible"

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = PROJECT_ROOT / "config/hybrid_sector/default.yaml"
_ENV_LOADED = False


def _parse_dotenv_file(path: Path) -> dict[str, str]:
    """Minimal .env parser (no dependency on python-dotenv)."""
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if not key:
            continue
        if len(val) >= 2 and val[0] == val[-1] and val[0] in {"'", '"'}:
            val = val[1:-1]
        out[key] = val
    return out


def load_project_env(*, override: bool = False) -> Path | None:
    """Load OPENAI_API_KEY and related vars from nearest .env (never commit secrets).

    Searches cwd and project root ancestors so worktrees pick up the main-repo `.env`.
    Does not override already-exported non-empty process env by default.
    Works without python-dotenv (manual parse fallback).
    """
    global _ENV_LOADED
    if _ENV_LOADED and not override:
        env_path = os.environ.get("HYBRID_SECTOR_ENV_FILE")
        return Path(env_path) if env_path else None

    candidates: list[Path] = []
    for start in (Path.cwd().resolve(), PROJECT_ROOT.resolve()):
        for base in (start, *start.parents):
            env_file = base / ".env"
            if env_file.is_file():
                candidates.append(env_file)
                break
    # Prefer the first found (cwd walk, then project root walk)
    chosen = candidates[0] if candidates else None
    if chosen is not None:
        parsed = _parse_dotenv_file(chosen)
        # Prefer python-dotenv when available (handles edge cases), then apply parse
        try:
            from dotenv import load_dotenv

            load_dotenv(chosen, override=override)
        except ImportError:
            pass
        for key, val in parsed.items():
            if override or not (os.environ.get(key) or "").strip():
                # Empty CI placeholders ("") must not block .env values when override
                if override or key not in os.environ or not str(os.environ.get(key) or "").strip():
                    os.environ[key] = val
        os.environ["HYBRID_SECTOR_ENV_FILE"] = str(chosen)
    _ENV_LOADED = True
    return chosen


def load_config(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_CONFIG
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def apply_paid_llm_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Enable real OpenAI path: gpt-4o-mini + OPENAI_API_KEY from .env.

    Default campaign remains offline; call this only for explicit paid runs
    (e.g. ``--allow-paid-llm``).
    """
    load_project_env()
    out: dict[str, Any] = dict(cfg or load_config())
    op = dict(out.get("operational") or {})
    op["enabled"] = True
    out["operational"] = op
    llm = dict(out.get("llm") or {})
    llm["provider"] = DEFAULT_PAID_LLM_PROVIDER
    # Force paid model: never keep offline-fake when real provider is active
    model = str(llm.get("model") or "").strip()
    if not model or model in {"offline-fake", "fake", "none"}:
        model = (
            os.environ.get("HYBRID_SECTOR_LLM_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or DEFAULT_PAID_LLM_MODEL
        )
    # Prefer gpt-4o-mini as project default for paid LLM
    if model == "offline-fake":
        model = DEFAULT_PAID_LLM_MODEL
    llm["model"] = model or DEFAULT_PAID_LLM_MODEL
    out["llm"] = llm
    return out


def build_provider(
    cfg: dict[str, Any] | HybridSectorRuntimeConfig,
    *,
    force_fake: bool = False,
) -> LLMProvider:
    """Construct LLM provider with every YAML/runtime field wired to runtime behavior."""
    if isinstance(cfg, HybridSectorRuntimeConfig):
        llm = {
            "provider": cfg.llm.provider,
            "model": cfg.llm.model,
            "base_url": cfg.llm.base_url,
            "timeout_seconds": cfg.llm.timeout_seconds,
            "max_retries": cfg.llm.max_retries,
            "max_cost_usd_per_cycle": cfg.llm.max_cost_usd_per_cycle,
            "circuit_breaker_failures": cfg.llm.circuit_breaker_failures,
            "cache_enabled": cfg.llm.cache_enabled,
            "temperature": cfg.llm.temperature,
            "prompt_version": cfg.llm.prompt_version,
            "max_concurrency": cfg.llm.max_concurrency,
        }
        operational_enabled = bool(cfg.operational.enabled)
    else:
        llm = dict(cfg.get("llm") or {})
        operational_enabled = bool((cfg.get("operational") or {}).get("enabled", False))
    # Offline defaults: force fake unless operational explicitly enabled AND not forced fake
    provider_name = "fake" if force_fake else str(llm.get("provider") or "fake")
    if not operational_enabled and not force_fake:
        # Safety: paid provider only when operational.enabled (set by apply_paid_llm_config)
        if provider_name == "openai_compatible":
            provider_name = "fake"
    if provider_name == "openai_compatible" and not force_fake:
        # Ensure .env is loaded so OPENAI_API_KEY is available
        load_project_env()
        cost = CostGuard(max_cost_usd=float(llm.get("max_cost_usd_per_cycle") or 5.0))
        breaker = CircuitBreaker(
            failure_threshold=int(llm.get("circuit_breaker_failures") or 5)
        )
        model = str(llm.get("model") or "").strip()
        if not model or model in {"offline-fake", "fake", "none"}:
            model = (
                os.environ.get("HYBRID_SECTOR_LLM_MODEL")
                or os.environ.get("OPENAI_MODEL")
                or DEFAULT_PAID_LLM_MODEL
            )
        temperature = float(llm.get("temperature") or 0.0)
        prompt_version = str(llm.get("prompt_version") or "sector-arbiter-v1")
        max_concurrency = int(llm.get("max_concurrency") or 1)
        if llm.get("cache_enabled", True):
            cache: ResponseCache | NullResponseCache = ResponseCache(
                model=str(model or DEFAULT_PAID_LLM_MODEL),
                prompt_version=prompt_version,
                temperature=temperature,
            )
        else:
            cache = NullResponseCache()
        return OpenAICompatibleProvider(
            model=model or DEFAULT_PAID_LLM_MODEL,
            base_url=llm.get("base_url"),
            timeout_seconds=float(llm.get("timeout_seconds") or 15),
            max_retries=int(llm.get("max_retries") or 2),
            cost_guard=cost,
            circuit_breaker=breaker,
            cache=cache,
            temperature=temperature,
            prompt_version=prompt_version,
            max_concurrency=max_concurrency,
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
    active_blockers: list[str] = field(default_factory=list)
    runtime_config: dict[str, Any] = field(default_factory=dict)
    observed_cost_usd: float = 0.0

    def to_summary(self) -> dict[str, Any]:
        n_universe = int(self.universe_metrics.get("raw_universe_count") or len(self.universe))
        decision_ids = {lin.canonical_id for lin in self.lineages}
        universe_ids = {r.canonical_id for r in self.universe}
        missing = sorted(universe_ids - decision_ids)
        return {
            "pipeline_version": PIPELINE_VERSION,
            "raw_universe_count": n_universe,
            "candidate_count": len(self.candidates),
            "lineage_count": len(self.lineages),
            "match_count": len(self.deliverables.get("deliverable_e_matches") or []),
            "review_count": len(self.deliverables.get("deliverable_e_review_queue") or []),
            "no_match_count": len(self.deliverables.get("deliverable_e_no_match_audit") or []),
            "review_status": self.review_status,
            "terminal_status": self.terminal_status,
            "active_blockers": list(self.active_blockers),
            "every_record_has_decision": (
                len(self.lineages) == n_universe and not missing
            ),
            "silent_drop_ids": missing,
            "observed_cost_usd": self.observed_cost_usd,
        }


def run_pipeline(
    records: list[dict[str, Any] | RawOpportunity],
    *,
    config: dict[str, Any] | None = None,
    runtime: HybridSectorRuntimeConfig | None = None,
    provider: LLMProvider | None = None,
    force_fake_llm: bool = True,
    gold_labels: dict[str, str] | None = None,
    gold_meta: dict[str, dict[str, Any]] | None = None,
    critical_positive_ids: set[str] | None = None,
    adjudicated_ids: set[str] | None = None,
    stratified_audit_ids: set[str] | None = None,
    corpus_kind: str = CORPUS_KIND_SYNTHETIC,
    corpus_audit: dict[str, Any] | None = None,
    llm_operational: dict[str, Any] | None = None,
    embedding_operational: dict[str, Any] | None = None,
    full_suite: dict[str, Any] | None = None,
    rc_v2_intact: bool | None = None,
    evaluation_level: str | None = None,
) -> PipelineResult:
    """Run full architecture. Every candidate gets a decision lineage (no silent drop)."""
    cfg = config if config is not None else load_config()
    rt = runtime or load_runtime_config()
    # Prefer runtime typed values; allow raw cfg override for tests
    ru_cfg = cfg.get("raw_universe") or {}
    ret_cfg = cfg.get("retrieval") or {}
    llm_cfg = cfg.get("llm") or {}
    mr_cfg = cfg.get("manual_review") or {}

    full_thr = int(ru_cfg.get("full_universe_threshold") or rt.full_universe_threshold)
    universe, umetrics = build_raw_universe(records, full_universe_threshold=full_thr)
    provider = provider or build_provider(cfg, force_fake=force_fake_llm)

    # Semantic provider from config (default lexical_fuzzy_hash)
    sem_cfg = ret_cfg.get("semantic") or {}
    if not sem_cfg.get("provider"):
        sem_cfg = {
            **sem_cfg,
            "provider": rt.semantic.provider,
            "model_id": rt.semantic.model_id,
            "model_version": rt.semantic.model_version,
            "top_k": rt.semantic.top_k,
            "min_similarity": rt.semantic.min_similarity,
            "base_url": rt.semantic.base_url,
            "timeout_seconds": rt.semantic.timeout_seconds,
            "max_retries": rt.semantic.max_retries,
            "cache_path": rt.semantic.cache_path,
        }
    embed_provider = build_embedding_provider({"semantic": sem_cfg})

    candidates, retrieval_report = run_hybrid_retrieval(
        universe,
        classify_full_universe=umetrics.classify_full_universe,
        rrf_k=int(ret_cfg.get("rrf_k") or rt.rrf_k),
        lexical_max_terms=(ret_cfg.get("lexical") or {}).get("max_terms"),
        semantic_provider=embed_provider,
        semantic_top_k=int(sem_cfg.get("top_k") or rt.semantic.top_k),
        semantic_min_similarity=float(
            sem_cfg.get("min_similarity") or rt.semantic.min_similarity
        ),
        short_text_max_chars=int(
            (ret_cfg.get("zero_match") or {}).get("short_text_max_chars")
            or rt.short_text_max_chars
        ),
        high_value_threshold=float(
            (ret_cfg.get("zero_match") or {}).get("high_value_threshold")
            or rt.high_value_threshold
        ),
    )
    retrieval_report["embedding_class"] = getattr(
        embed_provider, "embedding_class", "unknown"
    )
    retrieval_report["operational_semantic"] = bool(
        getattr(embed_provider, "operational_semantic", False)
    )

    stratified_audit_ids = stratified_audit_ids or set()
    lineages: list[DecisionLineage] = []
    cand_by_id: dict[str, CandidateRecord] = {}
    min_conf = int(llm_cfg.get("min_confidence") or rt.llm.min_confidence)
    hv_thr = float(
        (cfg.get("decision_policy") or {}).get("high_value_no_match_threshold")
        or rt.high_value_no_match_threshold
    )
    second_adj = float(
        llm_cfg.get("second_adjudication_value_threshold")
        or rt.llm.second_adjudication_value_threshold
    )
    max_concurrency = int(llm_cfg.get("max_concurrency") or rt.llm.max_concurrency or 1)
    # When operational.enabled=false, pipeline still runs offline campaign/eval paths
    # with force_fake; it never replaces commercial RC v2 Deliverable E outside campaign.
    operational_enabled = bool(
        (cfg.get("operational") or {}).get("enabled", rt.operational.enabled)
    )

    def _arbitrate_one(cand: CandidateRecord) -> DecisionLineage:
        det = classify_selective(cand)
        arb = arbitrate(
            cand,
            det,
            provider,
            min_confidence=min_conf,
            high_value_threshold=hv_thr,
            second_adjudication_value_threshold=second_adj,
            stratified_audit=cand.record.canonical_id in stratified_audit_ids,
        )
        return map_to_commercial(cand, det, arb)

    if max_concurrency <= 1 or len(candidates) <= 1:
        for cand in candidates:
            cand_by_id[cand.record.canonical_id] = cand
            lineages.append(_arbitrate_one(cand))
    else:
        # Limited concurrency with deterministic output order
        from concurrent.futures import ThreadPoolExecutor, as_completed

        for cand in candidates:
            cand_by_id[cand.record.canonical_id] = cand
        indexed = list(enumerate(candidates))
        results: dict[int, DecisionLineage] = {}
        workers = min(max_concurrency, len(candidates))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_arbitrate_one, cand): idx for idx, cand in indexed
            }
            for fut in as_completed(futures):
                idx = futures[fut]
                results[idx] = fut.result()
        lineages = [results[i] for i in range(len(candidates))]
    # Attach operational flag for artifact honesty
    _ = operational_enabled  # used in evaluation section below

    universe_ids = {r.canonical_id for r in universe}
    candidate_ids = {c.record.canonical_id for c in candidates}
    decision_ids = {lin.canonical_id for lin in lineages}
    assert len(lineages) == len(candidates), "lineage/candidate count mismatch"  # noqa: S101
    assert candidate_ids == universe_ids, (  # noqa: S101
        f"silent discard of raw-universe records: "
        f"{sorted(universe_ids - candidate_ids)[:20]}"
    )
    assert decision_ids == universe_ids, (  # noqa: S101
        f"raw-universe records without commercial decision: "
        f"{sorted(universe_ids - decision_ids)[:20]}"
    )

    reviews, review_status = prioritize_review_queue(
        lineages,
        cand_by_id,
        config=ReviewCapacityConfig(
            max_items_per_cycle=int(
                mr_cfg.get("max_items_per_cycle") or rt.max_items_per_cycle
            ),
            overflow_policy=str(
                mr_cfg.get("overflow_policy") or rt.overflow_policy
            ),
        ),
    )
    rev_pri = {r.canonical_id: r.review_priority for r in reviews}
    for lin in lineages:
        if lin.canonical_id in rev_pri:
            lin.review_priority = rev_pri[lin.canonical_id]

    records_by_id = {r.canonical_id: r for r in universe}
    deliverables = split_deliverables(lineages, records_by_id)

    # Observed cost (real) — not YAML copy
    observed_cost = 0.0
    if hasattr(provider, "cost_guard"):
        observed_cost = float(getattr(provider.cost_guard, "spent_usd", 0.0) or 0.0)
    if hasattr(embed_provider, "observed_cost_usd"):
        observed_cost += float(getattr(embed_provider, "observed_cost_usd", 0.0) or 0.0)

    evaluation: dict[str, Any] = {
        "retrieval_report": retrieval_report,
        "operational_enabled": operational_enabled,
    }
    level = evaluation_level or (
        "C"
        if corpus_kind == "REAL_OPERATIONAL_LOCKED_GOLD"
        else ("B" if corpus_kind == CORPUS_KIND_SYNTHETIC else "A")
    )
    corpus_audit = corpus_audit or {
        "corpus_kind": corpus_kind,
        "operational_gold_eligible": False,
        "n_records": len(universe),
        "blockers": ["BLOCKED_INVALID_EVALUATION_CORPUS"]
        if level != "C"
        else ["BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS"],
    }
    if "n_records" not in corpus_audit:
        corpus_audit = {**corpus_audit, "n_records": corpus_audit.get("n_records", len(universe))}
    llm_operational = llm_operational or {
        "passed": False,
        "status": "BLOCKED_LLM_OPERATIONAL_VALIDATION",
        "n_samples": 0,
        "min_required": 200,
        "human_review_complete": False,
    }
    embedding_operational = embedding_operational or {
        "passed": False,
        "status": "BLOCKED_EMBEDDING_OPERATIONAL_VALIDATION",
        "provider_class": getattr(embed_provider, "embedding_class", "unknown"),
    }
    full_suite = full_suite or {
        "passed": False,
        "status": "BLOCKED_FULL_SUITE_VALIDATION",
    }

    active_blockers: list[str] = []
    terminal = "BLOCKED_INSUFFICIENT_STATISTICAL_POWER"

    if gold_labels is not None:
        pos_ids = {i for i, lab in gold_labels.items() if lab == "POSITIVE"}
        retrieved_for_metrics = [
            c
            for c in candidates
            if not (set(c.retrieved_by) <= {"residual_audit", "full_universe"})
        ]
        ret_m = retrieval_metrics(
            pos_ids,
            retrieved_for_metrics if retrieved_for_metrics else candidates,
            gold_meta=gold_meta,
        )
        ret_m["positives_with_decision"] = len(pos_ids & decision_ids)
        ret_m["universe_decision_coverage"] = (
            len(decision_ids) / len(universe_ids) if universe_ids else 1.0
        )
        dec_m = decision_metrics(
            gold_labels,
            lineages,
            critical_positive_ids=critical_positive_ids,
            adjudicated_ids=adjudicated_ids,
        )
        llm_errors = [lin for lin in lineages if lin.llm_error]
        llm_err_review = sum(
            1 for lin in llm_errors if lin.commercial_decision == "REVIEW"
        )
        invented_accepted = sum(1 for lin in lineages if lin.invented_evidence_accepted)
        invented_seen = sum(1 for lin in lineages if lin.invented_evidence)
        silent_discards = len(universe_ids - decision_ids)
        audit = {
            "invented_evidence_accepted": invented_accepted,
            "invented_evidence_seen": invented_seen,
            "invented_evidence_rejected": max(0, invented_seen - invented_accepted),
            "llm_error_to_review_rate": (
                llm_err_review / len(llm_errors) if llm_errors else 1.0
            ),
            "lineage_coverage": (
                len(decision_ids) / len(universe_ids) if universe_ids else 1.0
            ),
            "silent_discards": silent_discards,
        }
        gate_res = evaluate_gates(
            ret_m,
            dec_m,
            audit=audit,
            thresholds=cfg.get("evaluation") or rt.evaluation,
            corpus_audit=corpus_audit,
            llm_operational=llm_operational,
            embedding_operational=embedding_operational,
            review_status=review_status,
            full_suite=full_suite,
            evaluation_level=level,
            rc_v2_intact=rc_v2_intact,
        )
        terminal = gate_res["terminal_status"]
        active_blockers = list(gate_res.get("active_blockers") or [])
        shadow = multi_window_shadow(
            universe,
            lineages,
            gold_labels,
            corpus_kind=corpus_kind,
        )
        no_match_lins = [lin for lin in lineages if lin.commercial_decision == "NO_MATCH"]
        nm_sample = select_no_match_audit_sample(no_match_lins, cand_by_id)
        review_analysis = analyze_review_queue(lineages, cand_by_id, gold_labels)
        evaluation.update(
            {
                "retrieval_metrics": ret_m,
                "decision_metrics": dec_m,
                "confusion": confusion_counts(gold_labels, lineages),
                "gates": gate_res,
                "shadow_replay": shadow,
                "review_analysis": review_analysis,
                "no_match_audit_sample_size": len(nm_sample),
                "no_match_audit_sample": nm_sample[:50],
                "evaluation_level": level,
                "corpus_kind": corpus_kind,
                "llm_operational": llm_operational,
                "embedding_operational": embedding_operational,
            }
        )
    else:
        terminal = "BLOCKED_INSUFFICIENT_STATISTICAL_POWER"
        active_blockers = sorted(
            set(REQUIRED_HONEST_BLOCKERS)
            | {
                "BLOCKED_INSUFFICIENT_STATISTICAL_POWER",
                "BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS",
            }
        )
        evaluation["gates"] = {
            "terminal_status": terminal,
            "active_blockers": active_blockers,
            "all_core_pass": False,
            "note": "no gold labels provided",
        }
        evaluation["evaluation_level"] = level
        evaluation["corpus_kind"] = corpus_kind
        evaluation["llm_operational"] = llm_operational
        evaluation["embedding_operational"] = embedding_operational

    if terminal not in ALLOWED_TERMINAL_STATES:
        terminal = "BLOCKED_INSUFFICIENT_RECALL"
    for claim in FORBIDDEN_CLAIMS:
        if claim in terminal:
            raise RuntimeError(f"forbidden claim in terminal: {claim}")

    # Ensure operational multi-blocker honesty when not READY
    # (do not force REVIEW_CAPACITY or INVALID on empty Level C)
    if terminal != "READY_FOR_RECALL_ASSURANCE_REVIEW":
        for b in REQUIRED_HONEST_BLOCKERS:
            if b in active_blockers:
                continue
            if b == "BLOCKED_LLM_OPERATIONAL_VALIDATION" and not (
                llm_operational or {}
            ).get("passed"):
                active_blockers.append(b)
            elif b == "BLOCKED_FULL_SUITE_VALIDATION" and not (
                full_suite or {}
            ).get("passed"):
                active_blockers.append(b)
        # Conditional: review capacity only when operationally blocked by volume
        if (
            review_status.get("operational_status")
            == "OPERATIONALLY_BLOCKED_REVIEW_VOLUME"
            and "BLOCKED_REVIEW_CAPACITY" not in active_blockers
        ):
            active_blockers.append("BLOCKED_REVIEW_CAPACITY")
        # Conditional: invalid evaluation only for non-C or explicit corpus blockers
        if level != "C" and "BLOCKED_INVALID_EVALUATION_CORPUS" not in active_blockers:
            active_blockers.append("BLOCKED_INVALID_EVALUATION_CORPUS")
        active_blockers = sorted(set(active_blockers))

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
        active_blockers=active_blockers,
        runtime_config=rt.to_dict(),
        observed_cost_usd=observed_cost,
    )


def run_from_gold_corpus(
    corpus_path: Path,
    *,
    split: str = "locked",
    config: dict[str, Any] | None = None,
    force_fake_llm: bool = True,
    include_distractors: bool = False,
    full_suite: dict[str, Any] | None = None,
    llm_operational: dict[str, Any] | None = None,
    embedding_operational: dict[str, Any] | None = None,
    rc_v2_intact: bool | None = None,
    run_embedding_benchmark: bool = False,
) -> PipelineResult:
    """Locked evaluation.

    Preferential: evaluate exclusively records with split=locked.
    If include_distractors=True, dev/calibration are added AND must keep labels
    (no unlabeled MATCH).
    """
    corpus = load_gold_corpus(corpus_path)
    kind = classify_corpus(corpus)
    audit = audit_real_corpus(corpus, cfg=(config or {}).get("evaluation"))
    labels, meta, critical = gold_index(corpus, split=split)
    adjudicated = adjudicated_match_ids(corpus, split=split)
    records = records_as_universe(corpus, split=split)

    if include_distractors and split == "locked":
        # Alternative: distractors must retain labels for evaluation
        for other in ("dev", "calibration"):
            other_labels, other_meta, other_crit = gold_index(corpus, split=other)
            labels.update(other_labels)
            meta.update(other_meta)
            critical |= other_crit
            records.extend(records_as_universe(corpus, split=other))
    # Preferred path: locked-only — do NOT add unlabeled distractors

    level = "C" if kind == "REAL_OPERATIONAL_LOCKED_GOLD" else (
        "B" if kind == CORPUS_KIND_SYNTHETIC else "A"
    )

    emb_op = embedding_operational
    if run_embedding_benchmark and emb_op is None:
        emb_op = benchmark_embedding_channels(
            records,
            labels,
            real_provider_cfg=(config or {}).get("retrieval"),
            try_real=True,
        )

    llm_op = llm_operational
    if llm_op is None:
        # Honest default: blocked until real stratified validation
        llm_op = run_llm_operational_validation(
            [meta[i] for i in labels if i in meta] or list(corpus.get("records") or []),
            provider=None if force_fake_llm else None,
            force_run=False,
        )

    return run_pipeline(
        records,
        config=config,
        force_fake_llm=force_fake_llm,
        gold_labels=labels,
        gold_meta=meta,
        critical_positive_ids=critical,
        adjudicated_ids=adjudicated,
        corpus_kind=kind,
        corpus_audit=audit,
        llm_operational=llm_op,
        embedding_operational=emb_op,
        full_suite=full_suite,
        rc_v2_intact=rc_v2_intact,
        evaluation_level=level,
    )


def write_campaign_artifacts(
    result: PipelineResult,
    out_dir: Path,
    *,
    corpus_manifest: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Write campaign deliverables with separated Level A/B/C claims."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    def w(name: str, obj: Any) -> Path:
        p = out_dir / name
        p.write_text(
            json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        paths[name] = p
        return p

    summary = result.to_summary()
    eval_ = result.evaluation
    gates = eval_.get("gates") or {}
    ret_m = eval_.get("retrieval_metrics") or {}
    dec_m = eval_.get("decision_metrics") or {}
    level = eval_.get("evaluation_level") or "B"
    corpus_kind = eval_.get("corpus_kind") or CORPUS_KIND_SYNTHETIC

    # Separated result sections — never blend synthetic + real rates
    synthetic_test_results = None
    real_operational_results = None
    if level == "B" or corpus_kind == CORPUS_KIND_SYNTHETIC:
        synthetic_test_results = {
            "evaluation_level": "B",
            "corpus_kind": CORPUS_KIND_SYNTHETIC,
            "retrieval_metrics": ret_m,
            "decision_metrics": dec_m,
            "note": "SYNTHETIC_ADVERSARIAL_FIXTURE — not operational gold",
            "headline_operational_recall": None,
            "headline_operational_precision": None,
        }
    if level == "C":
        real_operational_results = {
            "evaluation_level": "C",
            "corpus_kind": corpus_kind,
            "retrieval_metrics": ret_m,
            "decision_metrics": dec_m,
        }

    llm_op_raw = eval_.get("llm_operational") or {}
    paid_llm_validation = {
        "artifact_present": True,
        "passed": bool(llm_op_raw.get("passed")),
        "status": llm_op_raw.get("status") or "BLOCKED_LLM_OPERATIONAL_VALIDATION",
        "n_samples": llm_op_raw.get("n_samples") or 0,
        "min_required": llm_op_raw.get("min_required") or 200,
        "human_review_complete": bool(llm_op_raw.get("human_review_complete")),
    }
    suite_raw = (gates.get("gates") or {}).get("full_suite") or {}
    full_suite_status = {
        "artifact_present": True,
        "passed": bool(suite_raw.get("passed") or suite_raw.get("pass")),
        "status": suite_raw.get("status") or "BLOCKED_FULL_SUITE_VALIDATION",
        "details": suite_raw.get("details"),
    }
    real_eval_status = {
        "artifact_present": True,
        "passed": False,
        "status": (
            "BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS"
            if level == "C" and int(dec_m.get("n_positives") or 0) == 0
            else (
                result.terminal_status
                if result.terminal_status != "READY_FOR_RECALL_ASSURANCE_REVIEW"
                else "OK"
            )
        ),
        "n_positives": dec_m.get("n_positives"),
        "evaluation_level": level,
        "corpus_kind": corpus_kind,
    }
    # RC v2 check object — do not claim false when not checked
    rc_gate = (gates.get("gates") or {}).get("rc_v2_intact") or {
        "status": "NOT_CHECKED_IN_THIS_EXECUTION",
        "passed": None,
    }

    w(
        "manifest.json",
        {
            "campaign_id": "HYBRID-SECTOR-RECALL-LLM-ARBITER-01",
            "pipeline_version": PIPELINE_VERSION,
            "terminal_status": result.terminal_status,
            "active_blockers": result.active_blockers,
            "summary": summary,
            "forbidden_claims_absent": True,
            "pr_131_status": "CHANGES_REQUESTED_RECALL_ASSURANCE",
            "rc_v3_generated": False,
            "accepted": False,
            "merged": False,
            "evaluation_level": level,
            "corpus_kind": corpus_kind,
        },
    )
    w(
        "retrieval-evaluation.json",
        {
            "universe_metrics": result.universe_metrics,
            "retrieval_report": result.retrieval_report,
            "metrics": ret_m,
            "evaluation_level": level,
        },
    )
    w(
        "classification-evaluation.json",
        {
            "decision_metrics": dec_m,
            "confusion": eval_.get("confusion"),
            "lineage_count": len(result.lineages),
            "evaluation_level": level,
            "precision_variants": {
                "all_match_primary": dec_m.get("match_precision_all")
                or dec_m.get("match_precision"),
                "conservative_ambiguous_as_error": dec_m.get(
                    "match_precision_conservative"
                ),
                "hard_label_only_additional": dec_m.get("match_precision_hard_only"),
                "unlabeled_match_count": dec_m.get("unlabeled_match_count"),
                "all_match_count": dec_m.get("all_match_count"),
                "evaluated_match_count": dec_m.get("evaluated_match_count"),
            },
        },
    )
    w(
        "calibration.json",
        {
            "note": "probabilistic calibration deferred when scores are not probabilistic",
            "deterministic_confidence_hist": _conf_hist(result.lineages),
        },
    )
    n_pos_ci = int(dec_m.get("n_positives") or ret_m.get("n_gold_positives") or 0)
    ops_claim = bool(gates.get("operational_claim_allowed")) if isinstance(gates, dict) else False
    w(
        "confidence-intervals.json",
        {
            "evaluation_level": level,
            "operational_claims_allowed": ops_claim and level == "C" and n_pos_ci > 0,
            "retrieval_recall": {
                "point": ret_m.get("retrieval_recall") if n_pos_ci > 0 else None,
                "lower_95": ret_m.get("retrieval_recall_lower_95") if n_pos_ci > 0 else None,
            },
            "safe_recall": {
                "point": dec_m.get("safe_recall_match_plus_review") if n_pos_ci > 0 else None,
                "lower_95": dec_m.get("safe_recall_lower_95") if n_pos_ci > 0 else None,
            },
            "match_precision": {
                "point": dec_m.get("match_precision") if n_pos_ci > 0 else None,
                "lower_95": dec_m.get("match_precision_lower_95") if n_pos_ci > 0 else None,
            },
            "gates": gates,
            "note": (
                "Intervals from synthetic Level B must not be published as operational."
                if level != "C"
                else (
                    "No operational intervals: zero gold positives."
                    if n_pos_ci == 0
                    else "Level C operational intervals"
                )
            ),
        },
    )
    w("gold-corpus-manifest.json", corpus_manifest or {"status": "not_provided"})
    w("shadow-replay.json", eval_.get("shadow_replay") or {})
    w(
        "no-match-audit.json",
        {
            "sample_size": eval_.get("no_match_audit_sample_size"),
            "sample_preview": eval_.get("no_match_audit_sample"),
            "total_no_match": len(
                result.deliverables.get("deliverable_e_no_match_audit") or []
            ),
        },
    )
    w(
        "review-queue-analysis.json",
        {
            "status": result.review_status,
            "analysis": eval_.get("review_analysis"),
            "top": (result.deliverables.get("deliverable_e_review_queue") or [])[:20],
        },
    )
    # Cost: observed real, not YAML copy
    w(
        "llm-cost.json",
        {
            "provider_default": "fake",
            "paid_calls_in_default_ci": 0,
            "max_cost_usd_per_cycle": (
                (result.runtime_config.get("llm") or {}).get("max_cost_usd_per_cycle")
            ),
            "observed_cost_usd": result.observed_cost_usd,
            "cost_source": "runtime_observed",
            "not_yaml_copy": True,
        },
    )
    llm_failures = [
        {"canonical_id": lin.canonical_id, "error": lin.llm_error}
        for lin in result.lineages
        if lin.llm_error
    ]
    w("llm-failures.json", {"count": len(llm_failures), "failures": llm_failures})
    w(
        "prompt-injection-tests.json",
        {
            "note": "see tests/test_hybrid_sector_adversarial.py for executable suite",
            "policy": "source text is untrusted data; never modifies classifier rules",
        },
    )
    w(
        "drift-baseline.json",
        {
            "decision_distribution": _decision_dist(result.lineages),
            "review_rate": dec_m.get("review_rate"),
            "zero_match_rate": sum(
                1 for c in result.candidates if c.zero_match_rescue
            )
            / max(1, len(result.candidates)),
        },
    )
    # Separated claim artifacts
    w("synthetic_test_results.json", synthetic_test_results or {"status": "not_run"})
    w(
        "real_operational_results.json",
        real_operational_results
        or {
            "status": "not_run",
            "reason": "Level C real locked corpus required",
            "blockers": result.active_blockers,
        },
    )
    w("paid_llm_validation.json", paid_llm_validation)
    w("full_suite_status.json", full_suite_status)
    w(
        "embedding_benchmark.json",
        eval_.get("embedding_operational")
        or {"status": "BLOCKED_EMBEDDING_OPERATIONAL_VALIDATION"},
    )

    findings = []
    if result.terminal_status != "READY_FOR_RECALL_ASSURANCE_REVIEW":
        findings.append(
            {
                "severity": "HIGH",
                "finding": f"terminal={result.terminal_status}",
                "active_blockers": result.active_blockers,
                "action": "close real-corpus/LLM/capacity/full-suite gates before RC v3",
            }
        )
    if not statistical_power_note(dec_m):
        findings.append(
            {
                "severity": "HIGH",
                "finding": "insufficient statistical power for 99% CI claims",
                "action": "expand dual-reviewed real locked gold corpus",
            }
        )
    w("findings.json", {"findings": findings, "active_blockers": result.active_blockers})

    all_core = bool(gates.get("all_core_pass")) if isinstance(gates, dict) else False
    # Never publish all_core_pass=true when real gates not executed
    if level != "C":
        all_core = False

    honest_present = bool(
        gates.get("required_honest_blockers_present")
        if isinstance(gates, dict)
        else False
    )
    if not all_core:
        # Operational required blockers only (not vacuous REVIEW_CAPACITY)
        blockers = set(result.active_blockers)
        blockers |= set(REQUIRED_HONEST_BLOCKERS)
        result.active_blockers = sorted(blockers)
        honest_present = set(REQUIRED_HONEST_BLOCKERS) <= set(result.active_blockers)

    # Dual status: foundation PR vs operational pipeline (never conflate)
    operational_pipeline_status = result.terminal_status
    foundation_pr_status = FOUNDATION_PR_STATUS_READY  # candidate; CI/human gate final

    w(
        "result.json",
        {
            "terminal_status": result.terminal_status,
            "primary_terminal_status": (
                gates.get("primary_terminal_status")
                if isinstance(gates, dict)
                else result.terminal_status
            ),
            "foundation_pr_status": foundation_pr_status,
            "operational_pipeline_status": operational_pipeline_status,
            "active_blockers": result.active_blockers,
            "required_honest_blockers": sorted(REQUIRED_HONEST_BLOCKERS),
            "required_honest_blockers_present": honest_present,
            "allowed_states": sorted(ALLOWED_TERMINAL_STATES),
            "forbidden_claims": sorted(FORBIDDEN_CLAIMS),
            "summary": summary,
            "gates": gates,
            "evaluation_level": level,
            "corpus_kind": corpus_kind,
            "all_core_pass": all_core,
            "operational_claim_allowed": bool(
                gates.get("operational_claim_allowed")
            )
            if isinstance(gates, dict)
            else False,
            "separated_results": {
                "synthetic_test_results": {
                    "artifact_present": synthetic_test_results is not None,
                    "passed": False,
                    "status": (
                        "SYNTHETIC_ADVERSARIAL_ONLY"
                        if synthetic_test_results is not None
                        else "not_run"
                    ),
                },
                "real_operational_evaluation": real_eval_status,
                "paid_llm_validation": {
                    "artifact_present": paid_llm_validation["artifact_present"],
                    "passed": paid_llm_validation["passed"],
                    "status": paid_llm_validation["status"],
                },
                "full_suite": {
                    "artifact_present": full_suite_status["artifact_present"],
                    "passed": full_suite_status["passed"],
                    "status": full_suite_status["status"],
                },
            },
            "rc_v2_intact": rc_gate,
            "pr_131": "CHANGES_REQUESTED_RECALL_ASSURANCE",
            "claims": {
                "PROJECT_DONE": False,
                "ACCEPTED": False,
                "MERGED": False,
                "FULLY_GUARANTEED": False,
                "NO_FALSE_NEGATIVES_100": False,
            },
        },
    )
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
    for lin in lineages:
        if not lin.deterministic:
            continue
        c = lin.deterministic.confidence
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
    for lin in lineages:
        d[lin.commercial_decision] = d.get(lin.commercial_decision, 0) + 1
    return d


def _final_report_md(result: PipelineResult, findings: list[dict[str, Any]]) -> str:
    s = result.to_summary()
    level = result.evaluation.get("evaluation_level") or "?"
    lines = [
        "# HYBRID-SECTOR-RECALL-LLM-ARBITER-01 — Final Report",
        "",
        f"**Terminal status:** `{result.terminal_status}`",
        f"**Active blockers:** `{', '.join(result.active_blockers) or 'none'}`",
        f"**Evaluation level:** `{level}`",
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
        f"- Observed cost USD: {result.observed_cost_usd}",
        "",
        "## Architecture",
        "",
        "```",
        "RAW UNIVERSE → HYBRID RETRIEVAL (5 channels) → UNION+RRF rank",
        "→ DETERMINISTIC SELECTIVE → LLM ARBITER (eligible) → MATCH|REVIEW|NO_MATCH",
        "```",
        "",
        "## Evaluation levels (never blended)",
        "",
        "- A: unit fixtures",
        "- B: SYNTHETIC_ADVERSARIAL_FIXTURE (regression/attacks only)",
        "- C: real locked operational gold (only C sustains operational claims)",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("- No blocking findings beyond terminal status contract.")
    for f in findings:
        lines.append(f"- **{f['severity']}**: {f['finding']} — {f['action']}")
    lines.extend(
        [
            "",
            "## Non-claims",
            "",
            "- Not PROJECT_DONE",
            "- Not 100% NO FALSE NEGATIVES",
            "- Not FULLY GUARANTEED",
            "- Not ACCEPTED",
            "- Not MERGED",
            "",
        ]
    )
    return "\n".join(lines) + "\n"
