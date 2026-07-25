"""YAML → runtime config object. Every key must reach a real runtime field."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SemanticRuntimeConfig:
    provider: str = "lexical_fuzzy_hash"
    model_id: str = "offline-hash-embedding-pt-v1"
    model_version: str = "1.0.0"
    base_url: str | None = None
    top_k: int = 200
    min_similarity: float = 0.12
    batch_size: int = 32
    timeout_seconds: float = 60.0
    max_retries: int = 2
    normalize: bool = True
    dim: int | None = None
    cache_path: str | None = None
    cost_per_1k_tokens: float = 0.00002


@dataclass
class LLMRuntimeConfig:
    enabled: bool = True
    provider: str = "fake"
    model: str = "offline-fake"
    base_url: str | None = None
    prompt_version: str = "sector-arbiter-v1"
    timeout_seconds: float = 15.0
    max_retries: int = 2
    max_cost_usd_per_cycle: float = 5.0
    max_concurrency: int = 4
    circuit_breaker_failures: int = 5
    min_confidence: int = 60
    second_adjudication_value_threshold: float = 1_000_000.0
    cache_enabled: bool = True
    temperature: float = 0.0


@dataclass
class OperationalRuntimeConfig:
    """Disabled-by-default operational challenger switch."""

    enabled: bool = False


@dataclass
class HybridSectorRuntimeConfig:
    """Typed runtime mirror of config/hybrid_sector/default.yaml."""

    pipeline_version: str = "hybrid-sector-recall-llm-arbiter/1.1.0"
    full_universe_threshold: int = 500
    max_items_per_cycle: int = 100
    overflow_policy: str = "preserve_and_flag"
    rrf_k: int = 60
    lexical_max_terms: int | None = None
    semantic: SemanticRuntimeConfig = field(default_factory=SemanticRuntimeConfig)
    llm: LLMRuntimeConfig = field(default_factory=LLMRuntimeConfig)
    operational: OperationalRuntimeConfig = field(
        default_factory=OperationalRuntimeConfig
    )
    high_value_no_match_threshold: float = 500_000.0
    short_text_max_chars: int = 40
    high_value_threshold: float = 500_000.0
    evaluation: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def load_runtime_config(path: Path | None = None) -> HybridSectorRuntimeConfig:
    if path is None:
        path = (
            Path(__file__).resolve().parents[3] / "config/hybrid_sector/default.yaml"
        )
    raw: dict[str, Any] = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            raw = loaded

    ru = raw.get("raw_universe") or {}
    mr = raw.get("manual_review") or {}
    ret = raw.get("retrieval") or {}
    sem = ret.get("semantic") or {}
    zm = ret.get("zero_match") or {}
    llm = raw.get("llm") or {}
    op = raw.get("operational") or {}
    dp = raw.get("decision_policy") or {}
    ev = raw.get("evaluation") or {}

    return HybridSectorRuntimeConfig(
        pipeline_version=str(
            raw.get("pipeline_version") or "hybrid-sector-recall-llm-arbiter/1.1.0"
        ),
        full_universe_threshold=int(ru.get("full_universe_threshold") or 500),
        max_items_per_cycle=int(mr.get("max_items_per_cycle") or 100),
        overflow_policy=str(mr.get("overflow_policy") or "preserve_and_flag"),
        rrf_k=int(ret.get("rrf_k") or 60),
        lexical_max_terms=(ret.get("lexical") or {}).get("max_terms"),
        semantic=SemanticRuntimeConfig(
            provider=str(sem.get("provider") or "lexical_fuzzy_hash"),
            model_id=str(sem.get("model_id") or "offline-hash-embedding-pt-v1"),
            model_version=str(sem.get("model_version") or "1.0.0"),
            base_url=sem.get("base_url"),
            top_k=int(sem.get("top_k") or 200),
            min_similarity=float(sem.get("min_similarity") or 0.12),
            batch_size=int(sem.get("batch_size") or 32),
            timeout_seconds=float(sem.get("timeout_seconds") or 60),
            max_retries=int(sem.get("max_retries") or 2),
            normalize=bool(sem.get("normalize", True)),
            dim=sem.get("dim"),
            cache_path=sem.get("cache_path"),
            cost_per_1k_tokens=float(sem.get("cost_per_1k_tokens") or 0.00002),
        ),
        llm=LLMRuntimeConfig(
            enabled=bool(llm.get("enabled", True)),
            provider=str(llm.get("provider") or "fake"),
            model=str(llm.get("model") or "offline-fake"),
            base_url=llm.get("base_url"),
            prompt_version=str(llm.get("prompt_version") or "sector-arbiter-v1"),
            timeout_seconds=float(llm.get("timeout_seconds") or 15),
            max_retries=int(llm.get("max_retries") or 2),
            max_cost_usd_per_cycle=float(llm.get("max_cost_usd_per_cycle") or 5.0),
            max_concurrency=int(llm.get("max_concurrency") or 4),
            circuit_breaker_failures=int(llm.get("circuit_breaker_failures") or 5),
            min_confidence=int(llm.get("min_confidence") or 60),
            second_adjudication_value_threshold=float(
                llm.get("second_adjudication_value_threshold") or 1_000_000.0
            ),
            cache_enabled=bool(llm.get("cache_enabled", True)),
            temperature=float(llm.get("temperature") or 0.0),
        ),
        # Default: disabled foundation — commercial path untouched
        operational=OperationalRuntimeConfig(
            enabled=bool(op.get("enabled", False)),
        ),
        high_value_no_match_threshold=float(
            dp.get("high_value_no_match_threshold") or 500_000.0
        ),
        short_text_max_chars=int(zm.get("short_text_max_chars") or 40),
        high_value_threshold=float(zm.get("high_value_threshold") or 500_000.0),
        evaluation={k: float(v) if isinstance(v, (int, float)) else v for k, v in ev.items()},
        raw=raw,
    )


# Mapping for config-wiring tests: yaml dotted path → runtime attribute path
CONFIG_WIRING_MAP: dict[str, str] = {
    "llm.model": "llm.model",
    "llm.base_url": "llm.base_url",
    "llm.timeout_seconds": "llm.timeout_seconds",
    "llm.max_retries": "llm.max_retries",
    "llm.max_concurrency": "llm.max_concurrency",
    "llm.max_cost_usd_per_cycle": "llm.max_cost_usd_per_cycle",
    "llm.circuit_breaker_failures": "llm.circuit_breaker_failures",
    "llm.min_confidence": "llm.min_confidence",
    "llm.second_adjudication_value_threshold": "llm.second_adjudication_value_threshold",
    "llm.cache_enabled": "llm.cache_enabled",
    "llm.provider": "llm.provider",
    "llm.temperature": "llm.temperature",
    "llm.prompt_version": "llm.prompt_version",
    "operational.enabled": "operational.enabled",
    "retrieval.semantic.provider": "semantic.provider",
    "retrieval.semantic.model_id": "semantic.model_id",
    "retrieval.semantic.base_url": "semantic.base_url",
    "retrieval.semantic.timeout_seconds": "semantic.timeout_seconds",
    "retrieval.semantic.max_retries": "semantic.max_retries",
    "retrieval.semantic.cache_path": "semantic.cache_path",
    "manual_review.max_items_per_cycle": "max_items_per_cycle",
    "raw_universe.full_universe_threshold": "full_universe_threshold",
    "retrieval.rrf_k": "rrf_k",
}


def get_runtime_attr(cfg: HybridSectorRuntimeConfig, dotted: str) -> Any:
    cur: Any = cfg
    for part in dotted.split("."):
        cur = getattr(cur, part)
    return cur
