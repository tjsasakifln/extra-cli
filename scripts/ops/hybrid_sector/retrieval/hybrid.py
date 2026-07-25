"""Orchestrate 5+ independent retrieval channels then union-fuse."""
from __future__ import annotations

from typing import Any

from scripts.ops.hybrid_sector.models import CandidateRecord, RawOpportunity
from scripts.ops.hybrid_sector.retrieval.fusion import (
    ensure_full_universe_candidates,
    fuse_candidates,
)
from scripts.ops.hybrid_sector.retrieval.lexical import retrieve_lexical
from scripts.ops.hybrid_sector.retrieval.metadata import retrieve_metadata
from scripts.ops.hybrid_sector.retrieval.organ_history import retrieve_organ_history
from scripts.ops.hybrid_sector.retrieval.semantic import (
    EmbeddingProvider,
    retrieve_semantic,
)
from scripts.ops.hybrid_sector.retrieval.zero_match import retrieve_zero_match


def run_hybrid_retrieval(
    universe: list[RawOpportunity],
    *,
    classify_full_universe: bool = False,
    rrf_k: int = 60,
    lexical_max_terms: int | None = None,
    semantic_provider: EmbeddingProvider | None = None,
    semantic_top_k: int = 200,
    semantic_min_similarity: float = 0.12,
    short_text_max_chars: int = 40,
    high_value_threshold: float = 500_000.0,
    known_engineering_orgs: set[str] | None = None,
) -> tuple[list[CandidateRecord], dict[str, Any]]:
    """Run channels A–E independently, union-merge, optional full-universe fill."""
    lex_hits, lex_report = retrieve_lexical(universe, max_terms=lexical_max_terms)
    sem_hits, sem_report = retrieve_semantic(
        universe,
        provider=semantic_provider,
        top_k=semantic_top_k,
        min_similarity=semantic_min_similarity,
    )
    meta_hits = retrieve_metadata(universe)
    organ_hits = retrieve_organ_history(
        universe, known_engineering_orgs=known_engineering_orgs
    )
    zm_hits = retrieve_zero_match(
        universe,
        lexical_ids=set(lex_hits),
        semantic_hits=sem_hits,
        metadata_hits=meta_hits,
        organ_hits=organ_hits,
        short_text_max_chars=short_text_max_chars,
        high_value_threshold=high_value_threshold,
    )

    channel_hits = {
        "lexical": lex_hits,
        "semantic": sem_hits,
        "metadata": meta_hits,
        "organ_history": organ_hits,
        "zero_match": zm_hits,
    }
    candidates, analysis = fuse_candidates(universe, channel_hits, rrf_k=rrf_k)
    if classify_full_universe:
        candidates = ensure_full_universe_candidates(universe, candidates)
        analysis["full_universe_fill"] = True
        analysis["candidate_count"] = len(candidates)
    else:
        analysis["full_universe_fill"] = False

    report = {
        "channels": list(channel_hits.keys()),
        "channel_hit_counts": {k: len(v) for k, v in channel_hits.items()},
        "lexical_report": lex_report.to_dict(),
        "semantic_report": sem_report.to_dict(),
        "fusion_analysis": analysis,
        "rrf_k": rrf_k,
    }
    return candidates, report
