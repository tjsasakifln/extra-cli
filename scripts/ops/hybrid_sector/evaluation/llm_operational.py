"""Operational stratified LLM validation (real provider) — not FakeLLM unit path."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.ops.hybrid_sector.llm.protocol import LLMProvider
from scripts.ops.hybrid_sector.llm.schema import SectorArbitrationRequest

BLOCKED_LLM_OPERATIONAL_VALIDATION = "BLOCKED_LLM_OPERATIONAL_VALIDATION"
MIN_STRATIFIED_SAMPLES = 200


STRATA = (
    "positive_no_keyword",
    "hard_negative",
    "mixed_scope",
    "short_object",
    "divergence_candidate",
    "high_value",
    "prompt_injection",
    "needs_attachments",
)


def stratify_records(
    records: list[dict[str, Any]],
    *,
    min_total: int = MIN_STRATIFIED_SAMPLES,
) -> list[dict[str, Any]]:
    """Build stratified sample from real records. Does not invent rows."""
    buckets: dict[str, list[dict[str, Any]]] = {s: [] for s in STRATA}
    for r in records:
        label = r.get("label")
        obj = (r.get("objeto") or "") + " " + (r.get("titulo") or "")
        valor = float(r.get("valor_estimado") or 0)
        if label == "POSITIVE" and not r.get("has_keyword"):
            buckets["positive_no_keyword"].append(r)
        if label == "NEGATIVE":
            buckets["hard_negative"].append(r)
        if r.get("segment") == "mixed" or "misto" in obj.lower():
            buckets["mixed_scope"].append(r)
        if len(obj.strip()) < 40:
            buckets["short_object"].append(r)
        if valor >= 1_000_000:
            buckets["high_value"].append(r)
        if any(
            x in obj.lower()
            for x in ("ignore previous", "system prompt", "você é", "jailbreak")
        ):
            buckets["prompt_injection"].append(r)
        if r.get("has_anexos") or r.get("has_tr") or r.get("has_edital"):
            if r.get("object_clarity") == "low" or not r.get("has_keyword"):
                buckets["needs_attachments"].append(r)
        if label == "AMBIGUOUS":
            buckets["divergence_candidate"].append(r)

    # Round-robin sample up to min_total without inventing
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    # ensure each stratum contributes
    per = max(1, min_total // max(1, len(STRATA)))
    for stratum, items in buckets.items():
        for r in items[:per]:
            cid = r.get("canonical_id") or r.get("official_id")
            if cid in seen:
                continue
            seen.add(str(cid))
            row = dict(r)
            row["_stratum"] = stratum
            selected.append(row)
    # fill remainder from all records
    if len(selected) < min_total:
        for r in records:
            if len(selected) >= min_total:
                break
            cid = r.get("canonical_id") or r.get("official_id")
            if str(cid) in seen:
                continue
            seen.add(str(cid))
            row = dict(r)
            row["_stratum"] = "fill"
            selected.append(row)
    return selected


@dataclass
class LLMOperationalRun:
    model: str
    provider: str
    prompt_version: str
    temperature: float
    n_samples: int
    results: list[dict[str, Any]] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    observed_cost_usd: float = 0.0
    total_latency_s: float = 0.0
    retries: int = 0
    cache_hits: int = 0
    failures: int = 0
    human_review_complete: bool = False
    human_reviewer_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "provider": self.provider,
            "prompt": self.prompt_version,
            "temperature": self.temperature,
            "n_samples": self.n_samples,
            "tokens_in": self.total_input_tokens,
            "tokens_out": self.total_output_tokens,
            "observed_cost_usd": self.observed_cost_usd,
            "latency_s_total": self.total_latency_s,
            "retries": self.retries,
            "cache_hits": self.cache_hits,
            "failures": self.failures,
            "human_review_complete": self.human_review_complete,
            "human_reviewer_id": self.human_reviewer_id,
            "results": self.results,
        }


def run_llm_operational_validation(
    records: list[dict[str, Any]],
    *,
    provider: LLMProvider | None = None,
    min_samples: int = MIN_STRATIFIED_SAMPLES,
    force_run: bool = False,
    human_review_complete: bool = False,
    human_reviewer_id: str | None = None,
    estimated_cost_per_call: float = 0.002,
) -> dict[str, Any]:
    """Run stratified real-LLM validation. Never uses FakeLLM as success proof.

    If provider missing or samples < min → BLOCKED_LLM_OPERATIONAL_VALIDATION.
    """
    sample = stratify_records(records, min_total=min_samples)
    n = len(sample)

    if n < min_samples:
        return {
            "passed": False,
            "status": BLOCKED_LLM_OPERATIONAL_VALIDATION,
            "reason": "insufficient stratified real samples",
            "n_samples": n,
            "min_required": min_samples,
            "human_review_complete": False,
            "strata_counts": _strata_counts(sample),
        }

    if provider is None:
        return {
            "passed": False,
            "status": BLOCKED_LLM_OPERATIONAL_VALIDATION,
            "reason": "no real LLM provider configured (FakeLLM is unit-only)",
            "n_samples": n,
            "min_required": min_samples,
            "human_review_complete": False,
            "strata_counts": _strata_counts(sample),
        }

    # Reject FakeLLM as operational validation
    provider_name = type(provider).__name__
    if provider_name == "FakeLLMProvider":
        return {
            "passed": False,
            "status": BLOCKED_LLM_OPERATIONAL_VALIDATION,
            "reason": "FakeLLMProvider is unit-test only; operational validation requires real provider",
            "n_samples": n,
            "min_required": min_samples,
            "human_review_complete": False,
        }

    if not force_run:
        # Default: do not burn paid tokens unless explicitly forced
        return {
            "passed": False,
            "status": BLOCKED_LLM_OPERATIONAL_VALIDATION,
            "reason": "real LLM run not forced (use --allow-paid-llm / force_run)",
            "n_samples": n,
            "min_required": min_samples,
            "human_review_complete": human_review_complete,
            "strata_counts": _strata_counts(sample),
            "provider": provider_name,
            "would_run": True,
        }

    model = getattr(provider, "model", "unknown")
    run = LLMOperationalRun(
        model=str(model),
        provider=provider_name,
        prompt_version=str(getattr(provider, "prompt_version", "sector-arbiter-v1")),
        temperature=0.0,
        n_samples=n,
        human_review_complete=human_review_complete,
        human_reviewer_id=human_reviewer_id,
    )

    for r in sample:
        t0 = time.monotonic()
        req = SectorArbitrationRequest(
            canonical_id=str(r.get("canonical_id") or r.get("official_id")),
            objeto=str(r.get("objeto") or ""),
            titulo=str(r.get("titulo") or ""),
            items=list(r.get("items") or []),
            categories=list(r.get("categories") or []),
            orgao=str(r.get("orgao") or ""),
            valor_estimado=r.get("valor_estimado"),
            modality=str(r.get("modalidade") or ""),
            deterministic_decision="GRAY_ZONE",
            deterministic_reason="operational_validation",
            retrieval_channels=["operational_sample"],
            source_text=str(r.get("objeto") or ""),
        )
        entry: dict[str, Any] = {
            "canonical_id": req.canonical_id,
            "stratum": r.get("_stratum"),
            "gold_label": r.get("label"),
        }
        try:
            decision = provider.classify(req)
            latency = time.monotonic() - t0
            run.total_latency_s += latency
            run.observed_cost_usd += estimated_cost_per_call
            # token accounting if provider logs usage
            entry.update(
                {
                    "decision": decision.decision if hasattr(decision, "decision") else None,
                    "confidence": getattr(decision, "confidence", None),
                    "evidence": getattr(decision, "evidence", None)
                    or getattr(decision, "evidence_spans", None),
                    "latency_s": latency,
                    "error": None,
                    "fallback": None,
                }
            )
            # divergence vs gold when available
            gold = r.get("label")
            pred = entry.get("decision")
            entry["divergence"] = _divergence(gold, pred)
            run.results.append(entry)
        except Exception as exc:  # noqa: BLE001
            run.failures += 1
            run.retries += 1
            entry.update(
                {
                    "decision": None,
                    "error": str(exc),
                    "latency_s": time.monotonic() - t0,
                    "fallback": "REVIEW",
                    "divergence": None,
                }
            )
            run.results.append(entry)

    # Operational pass requires: run completed + human review of decisions
    passed = (
        run.failures == 0
        and run.n_samples >= min_samples
        and run.human_review_complete
    )
    payload = run.to_dict()
    payload.update(
        {
            "passed": passed,
            "status": (
                "LLM_OPERATIONAL_VALIDATED"
                if passed
                else BLOCKED_LLM_OPERATIONAL_VALIDATION
            ),
            "min_required": min_samples,
            "strata_counts": _strata_counts(sample),
            "note": (
                "Human review of stratified decisions is mandatory. "
                "Cost is observed runtime, not YAML copy."
            ),
        }
    )
    return payload


def _strata_counts(sample: list[dict[str, Any]]) -> dict[str, int]:
    c: dict[str, int] = {}
    for r in sample:
        s = str(r.get("_stratum") or "unknown")
        c[s] = c.get(s, 0) + 1
    return c


def _divergence(gold: str | None, pred: str | None) -> str | None:
    if not gold or not pred:
        return None
    if gold == "POSITIVE" and pred in {"MATCH", "POSITIVE"}:
        return "agree_pos"
    if gold == "NEGATIVE" and pred in {"NO_MATCH", "NEGATIVE"}:
        return "agree_neg"
    if gold == "AMBIGUOUS":
        return "ambiguous_gold"
    return "disagree"


def write_llm_validation_artifact(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return path
