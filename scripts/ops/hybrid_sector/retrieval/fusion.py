"""Phase 3 — union merge of channels + RRF prioritization only (never exclusion)."""
from __future__ import annotations

from typing import Any

from scripts.ops.hybrid_sector.models import CandidateRecord, RawOpportunity, RetrievalHit


def rrf_score(ranks: list[int], *, k: int = 60) -> float:
    """Reciprocal Rank Fusion score from 1-based ranks."""
    return sum(1.0 / (k + r) for r in ranks if r is not None and r > 0)


def fuse_candidates(
    universe: list[RawOpportunity],
    channel_hits: dict[str, dict[str, RetrievalHit]],
    *,
    rrf_k: int = 60,
) -> tuple[list[CandidateRecord], dict[str, Any]]:
    """Build candidate set as UNION of all channel hits.

    RRF ranks only — single-channel rescues are NEVER dropped before classification.
    When classify_full_universe is desired, caller may pass all records as a
    synthetic 'universe' channel; this function still only unions provided hits.
    """
    by_id: dict[str, RawOpportunity] = {r.canonical_id: r for r in universe}
    # Collect all ids that appeared in any channel
    all_ids: set[str] = set()
    for hits in channel_hits.values():
        all_ids.update(hits.keys())

    candidates: list[CandidateRecord] = []
    for cid in sorted(all_ids):
        rec = by_id.get(cid)
        if rec is None:
            continue
        cand = CandidateRecord(record=rec)
        for ch_name, hits in channel_hits.items():
            hit = hits.get(cid)
            if hit is None:
                continue
            cand.retrieved_by.append(ch_name)
            cand.retrieval_scores[ch_name] = hit.score
            cand.retrieval_rank_by_channel[ch_name] = hit.rank
            if hit.reason:
                cand.retrieval_reason.append(f"{ch_name}:{hit.reason}")
        if "zero_match" in cand.retrieved_by:
            cand.zero_match_rescue = True
        ranks = list(cand.retrieval_rank_by_channel.values())
        cand.fused_score = rrf_score(ranks, k=rrf_k)
        if len(cand.retrieved_by) == 1:
            cand.exclusive_rescue_channel = cand.retrieved_by[0]
            cand.inclusion_reason = f"exclusive_channel:{cand.retrieved_by[0]}"
        else:
            cand.inclusion_reason = f"multi_channel:{','.join(cand.retrieved_by)}"
        candidates.append(cand)

    # Sort by fused score for prioritization only
    candidates.sort(key=lambda c: (-c.fused_score, c.record.canonical_id))
    for i, c in enumerate(candidates, start=1):
        c.fused_rank = i

    analysis = _rescue_analysis(candidates, channel_hits)
    return candidates, analysis


def _rescue_analysis(
    candidates: list[CandidateRecord],
    channel_hits: dict[str, dict[str, RetrievalHit]],
) -> dict[str, Any]:
    lexical_ids = set(channel_hits.get("lexical", {}))
    unique_rescues: dict[str, int] = {}
    for ch in channel_hits:
        if ch == "lexical":
            continue
        only = set(channel_hits[ch]) - lexical_ids
        unique_rescues[ch] = len(only)

    single_channel = sum(1 for c in candidates if len(c.retrieved_by) == 1)
    return {
        "candidate_count": len(candidates),
        "lexical_only_count": len(lexical_ids),
        "would_lose_without_non_lexical": sum(unique_rescues.values()),
        "unique_rescues_by_channel": unique_rescues,
        "single_channel_candidates_kept": single_channel,
        "zero_match_rescues": sum(1 for c in candidates if c.zero_match_rescue),
        "note": "RRF used only for ranking; no pre-classification exclusion by RRF score",
    }


def ensure_full_universe_candidates(
    universe: list[RawOpportunity],
    candidates: list[CandidateRecord],
    *,
    mode: str = "full_universe",
) -> list[CandidateRecord]:
    """Include every raw-universe record not yet a candidate (no silent drop).

    Modes:
      - full_universe: volume ≤ threshold; classify entire universe
      - residual_audit: hybrid retrieval active; non-hits still get a decision
        (auditable NO_MATCH/REVIEW/MATCH), never disappear

    RRF ranking still only prioritizes retrieved hits; residuals rank last.
    """
    channel = "full_universe" if mode == "full_universe" else "residual_audit"
    reason = (
        "full_universe:classify_all"
        if mode == "full_universe"
        else "residual_not_retrieved:must_classify_no_silent_drop"
    )
    inclusion = (
        "full_universe_threshold"
        if mode == "full_universe"
        else "hybrid_residual_universe_audit"
    )
    have = {c.record.canonical_id for c in candidates}
    extra: list[CandidateRecord] = []
    for rec in universe:
        if rec.canonical_id in have:
            continue
        extra.append(
            CandidateRecord(
                record=rec,
                retrieved_by=[channel],
                retrieval_scores={channel: 0.0},
                retrieval_rank_by_channel={channel: 0},
                retrieval_reason=[reason],
                inclusion_reason=inclusion,
                fused_score=0.0,
            )
        )
    if not extra:
        return candidates
    merged = list(candidates) + extra
    for i, c in enumerate(merged, start=1):
        if c.fused_rank is None:
            c.fused_rank = i
    return merged
