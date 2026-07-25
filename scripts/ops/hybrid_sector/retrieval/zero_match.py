"""Canal E — zero-match rescue for records missed by lexical keywords.

Evaluates: no keyword match, short text, incomplete category, attachments,
organ history, value/modality compatible, semantic proximity.
"""
from __future__ import annotations

from typing import Iterable

from scripts.ops.hybrid_sector.models import RawOpportunity, RetrievalHit


def retrieve_zero_match(
    universe: Iterable[RawOpportunity],
    *,
    lexical_ids: set[str],
    semantic_hits: dict[str, RetrievalHit] | None = None,
    metadata_hits: dict[str, RetrievalHit] | None = None,
    organ_hits: dict[str, RetrievalHit] | None = None,
    short_text_max_chars: int = 40,
    high_value_threshold: float = 500_000.0,
) -> dict[str, RetrievalHit]:
    semantic_hits = semantic_hits or {}
    metadata_hits = metadata_hits or {}
    organ_hits = organ_hits or {}
    scored: list[tuple[str, float, str]] = []

    for rec in universe:
        cid = rec.canonical_id
        if cid in lexical_ids:
            continue  # not zero-match if lexical already hit

        score = 0.0
        reasons: list[str] = []
        text = rec.text_blob()

        # Short / incomplete text with docs
        if len(text) <= short_text_max_chars:
            score += 0.3
            reasons.append("short_text")
        if not rec.categories:
            score += 0.15
            reasons.append("incomplete_category")
        if rec.has_edital or rec.has_tr or rec.has_anexos:
            score += 0.25
            reasons.append("has_documents")
        if cid in organ_hits:
            score += 0.35
            reasons.append("organ_history_signal")
        if cid in metadata_hits:
            score += 0.3
            reasons.append("metadata_signal")
        if cid in semantic_hits:
            score += 0.4 + 0.2 * semantic_hits[cid].score
            reasons.append("semantic_proximity")
        if rec.valor_estimado is not None and rec.valor_estimado >= high_value_threshold:
            score += 0.2
            reasons.append("high_value")
        mod = (rec.modalidade or "").lower()
        if any(m in mod for m in ("concorrencia", "integrada", "rdc", "tomada")):
            score += 0.15
            reasons.append("compatible_modality")

        # Only rescue if there is at least one independent non-lexical signal
        if score >= 0.35 and reasons:
            scored.append((cid, score, ",".join(reasons)))

    scored.sort(key=lambda x: (-x[1], x[0]))
    hits: dict[str, RetrievalHit] = {}
    for rank, (cid, score, reason) in enumerate(scored, start=1):
        hits[cid] = RetrievalHit(
            channel="zero_match",
            score=score,
            rank=rank,
            reason=f"rescue:{reason}",
        )
    return hits
