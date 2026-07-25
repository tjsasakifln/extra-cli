"""Benchmark embedding channels on a corpus (real preferred; synthetic labeled Level B)."""
from __future__ import annotations

from typing import Any

from scripts.ops.hybrid_sector.raw_universe import build_raw_universe
from scripts.ops.hybrid_sector.retrieval.hybrid import run_hybrid_retrieval
from scripts.ops.hybrid_sector.retrieval.lexical import retrieve_lexical
from scripts.ops.hybrid_sector.retrieval.metadata import retrieve_metadata
from scripts.ops.hybrid_sector.retrieval.semantic import (
    EMBEDDING_CLASS_LEXICAL_FUZZY_HASH,
    HashEmbeddingProvider,
    build_embedding_provider,
    retrieve_semantic,
)


def _pos_ids(labels: dict[str, str]) -> set[str]:
    return {i for i, lab in labels.items() if lab == "POSITIVE"}


def _recall(pos: set[str], hit_ids: set[str]) -> float:
    return len(pos & hit_ids) / len(pos) if pos else 0.0


def _exclusive_rescues(pos: set[str], base: set[str], other: set[str]) -> int:
    return len((other - base) & pos)


def recall_vs_volume(
    ranked_ids: list[str],
    pos: set[str],
    volumes: list[int] | None = None,
) -> list[dict[str, Any]]:
    volumes = volumes or [10, 25, 50, 100, 200, 500, 1000, 5000]
    out = []
    for v in volumes:
        slice_ids = set(ranked_ids[:v])
        out.append(
            {
                "volume": v,
                "recall": _recall(pos, slice_ids),
                "n_pos_retrieved": len(pos & slice_ids),
                "n_pos": len(pos),
            }
        )
    return out


def benchmark_embedding_channels(
    records: list[dict[str, Any]],
    gold_labels: dict[str, str],
    *,
    real_provider_cfg: dict[str, Any] | None = None,
    try_real: bool = True,
) -> dict[str, Any]:
    """Benchmark: hash-ngram, real multi/PT (if available), lexical, lexical+emb,
    metadata, hybrid union — with incremental recall and exclusive rescues.
    """
    universe, _ = build_raw_universe(records, full_universe_threshold=10**9)
    pos = _pos_ids(gold_labels)
    if not pos:
        return {
            "passed": False,
            "status": "BLOCKED_EMBEDDING_OPERATIONAL_VALIDATION",
            "reason": "no positives in gold labels",
        }

    hash_provider = HashEmbeddingProvider()
    real_provider = None
    real_error = None
    if try_real and real_provider_cfg:
        try:
            real_provider = build_embedding_provider(real_provider_cfg)
            # smoke embed
            real_provider.embed(["pavimentação asfáltica teste"])
            if getattr(real_provider, "embedding_class", "") == EMBEDDING_CLASS_LEXICAL_FUZZY_HASH:
                real_provider = None
                real_error = "configured provider resolved to lexical_fuzzy_hash"
        except Exception as exc:  # noqa: BLE001
            real_error = str(exc)
            real_provider = None

    # 1) hash n-gram semantic
    hash_hits, hash_rep = retrieve_semantic(
        universe, provider=hash_provider, top_k=10**9, min_similarity=0.0
    )
    hash_ranked = [
        cid
        for cid, _ in sorted(
            ((h, hash_hits[h].score) for h in hash_hits),
            key=lambda x: (-x[1], x[0]),
        )
    ]
    hash_ids = set(hash_hits)

    # 2) real model (optional)
    real_ids: set[str] = set()
    real_ranked: list[str] = []
    real_rep = None
    if real_provider is not None:
        real_hits, real_rep = retrieve_semantic(
            universe, provider=real_provider, top_k=10**9, min_similarity=0.0
        )
        real_ids = set(real_hits)
        real_ranked = [
            cid
            for cid, _ in sorted(
                ((h, real_hits[h].score) for h in real_hits),
                key=lambda x: (-x[1], x[0]),
            )
        ]

    # 3) lexical
    lex_hits, _ = retrieve_lexical(universe)
    lex_ids = set(lex_hits)

    # 4) lexical + embedding (union hash)
    lex_emb_ids = lex_ids | hash_ids

    # 5) metadata
    meta_hits = retrieve_metadata(universe)
    meta_ids = set(meta_hits)

    # 6) hybrid union (full pipeline fusion)
    cands, hybrid_report = run_hybrid_retrieval(
        universe,
        classify_full_universe=False,
        semantic_provider=hash_provider,
        semantic_top_k=10**9,
        semantic_min_similarity=0.0,
    )
    # exclude residual-only from retrieval channel metrics
    hybrid_ids = {
        c.record.canonical_id
        for c in cands
        if not (set(c.retrieved_by) <= {"residual_audit", "full_universe"})
    }

    channels = {
        "hash_ngram": {
            "embedding_class": hash_provider.embedding_class,
            "operational_semantic": False,
            "recall": _recall(pos, hash_ids),
            "n_hits": len(hash_ids),
            "recall_vs_volume": recall_vs_volume(hash_ranked, pos),
            "exclusive_vs_lexical": _exclusive_rescues(pos, lex_ids, hash_ids),
        },
        "real_multilingual_or_pt": {
            "available": real_provider is not None,
            "error": real_error,
            "embedding_class": getattr(real_provider, "embedding_class", None),
            "model_id": getattr(real_provider, "model_id", None),
            "operational_semantic": bool(
                getattr(real_provider, "operational_semantic", False)
            ),
            "recall": _recall(pos, real_ids) if real_provider else None,
            "n_hits": len(real_ids),
            "recall_vs_volume": recall_vs_volume(real_ranked, pos) if real_ranked else [],
            "exclusive_vs_lexical": (
                _exclusive_rescues(pos, lex_ids, real_ids) if real_provider else None
            ),
            "exclusive_vs_hash": (
                _exclusive_rescues(pos, hash_ids, real_ids) if real_provider else None
            ),
        },
        "lexical": {
            "recall": _recall(pos, lex_ids),
            "n_hits": len(lex_ids),
        },
        "lexical_plus_embedding": {
            "recall": _recall(pos, lex_emb_ids),
            "n_hits": len(lex_emb_ids),
            "incremental_over_lexical": _recall(pos, lex_emb_ids) - _recall(pos, lex_ids),
            "exclusive_rescues_embedding": _exclusive_rescues(pos, lex_ids, hash_ids),
        },
        "metadata": {
            "recall": _recall(pos, meta_ids),
            "n_hits": len(meta_ids),
            "exclusive_vs_lexical": _exclusive_rescues(pos, lex_ids, meta_ids),
        },
        "hybrid_union": {
            "recall": _recall(pos, hybrid_ids),
            "n_hits": len(hybrid_ids),
            "report_channels": hybrid_report.get("channels"),
            "incremental_over_lexical": _recall(pos, hybrid_ids) - _recall(pos, lex_ids),
        },
    }

    # Real operational pass requires real provider benchmark on real corpus
    passed = real_provider is not None and real_ids is not None
    return {
        "passed": False,  # never auto-pass without explicit operational validation flag
        "status": (
            "BLOCKED_EMBEDDING_OPERATIONAL_VALIDATION"
            if not passed
            else "EMBEDDING_BENCHMARK_RAN_AWAITING_HUMAN"
        ),
        "provider_class": (
            getattr(real_provider, "embedding_class", None)
            if real_provider
            else EMBEDDING_CLASS_LEXICAL_FUZZY_HASH
        ),
        "hash_provider_class": hash_provider.embedding_class,
        "hash_is_operational_semantic": False,
        "n_positives": len(pos),
        "n_universe": len(universe),
        "channels": channels,
        "benchmark_summary": {
            "hash_recall": channels["hash_ngram"]["recall"],
            "lexical_recall": channels["lexical"]["recall"],
            "hybrid_recall": channels["hybrid_union"]["recall"],
            "real_available": real_provider is not None,
            "real_recall": channels["real_multilingual_or_pt"]["recall"],
        },
        "note": (
            "HashEmbeddingProvider is lexical_fuzzy_hash only. "
            "Operational semantic claims require real model benchmark + human review."
        ),
    }
