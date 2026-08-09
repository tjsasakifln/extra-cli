"""Prior reajuste / apostila history classification."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.commercial.reajuste_14133 import (
    ADJUSTMENT_HISTORY_CONFLICT,
    ADJUSTMENT_HISTORY_UNAVAILABLE,
    NO_PRIOR_ADJUSTMENT_LOCATED,
    PARTIAL_ADJUSTMENT_CONFIRMED,
    PRIOR_ADJUSTMENT_CONFIRMED,
)


@dataclass
class AdjustmentHistoryResult:
    status: str
    evidences: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Absence of apostila is NOT proof reajuste was never granted
    absence_is_not_proof: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_adjustment_history(
    *,
    apostila_mentions: int = 0,
    reajuste_concedido_mentions: int = 0,
    partial_mentions: int = 0,
    conflict_mentions: int = 0,
    searched_sources: bool = False,
    document_texts: list[str] | None = None,
) -> AdjustmentHistoryResult:
    """Classify adjustment history from real search signals (fail-closed honesty)."""
    import re

    texts = document_texts or []
    blob = "\n".join(texts).lower()
    if re.search(r"reajuste\s+parcial|parcialmente\s+reajust", blob):
        partial_mentions = max(partial_mentions, 1)
    if re.search(r"j[aá]\s+reajust|reajuste\s+concedido|apostilado\s+o\s+reajuste", blob):
        reajuste_concedido_mentions = max(reajuste_concedido_mentions, 1)
    if re.search(r"apostila", blob):
        apostila_mentions = max(apostila_mentions, 1)
    if re.search(r"diverg[eê]ncia.*reajuste|reajuste.*cancelad", blob):
        conflict_mentions = max(conflict_mentions, 1)

    notes = [
        "NO_PRIOR_ADJUSTMENT_LOCATED não prova que nenhum reajuste foi concedido.",
        "Ausência de apostila no PNCP não autoriza classificação como apto para outreach.",
    ]

    if conflict_mentions > 0 and (reajuste_concedido_mentions > 0 or apostila_mentions > 0):
        return AdjustmentHistoryResult(
            status=ADJUSTMENT_HISTORY_CONFLICT,
            evidences=["conflict_signals_in_documents"],
            notes=notes,
        )

    if reajuste_concedido_mentions > 0 and partial_mentions == 0:
        return AdjustmentHistoryResult(
            status=PRIOR_ADJUSTMENT_CONFIRMED,
            evidences=["reajuste_concedido_or_apostilado"],
            notes=notes,
        )

    if partial_mentions > 0:
        return AdjustmentHistoryResult(
            status=PARTIAL_ADJUSTMENT_CONFIRMED,
            evidences=["partial_reajuste_signals"],
            notes=notes,
        )

    if apostila_mentions > 0 and reajuste_concedido_mentions == 0:
        # Apostila may be non-reajuste (e.g. deadline) — not full confirmation
        return AdjustmentHistoryResult(
            status=NO_PRIOR_ADJUSTMENT_LOCATED,
            evidences=["apostila_mentioned_effect_unclear"],
            notes=notes + ["Apostila localizada sem confirmação de efeito de reajuste."],
        )

    if not searched_sources:
        return AdjustmentHistoryResult(
            status=ADJUSTMENT_HISTORY_UNAVAILABLE,
            evidences=[],
            notes=notes + ["Fontes de apostilas/atos não foram consultadas de forma completa."],
        )

    return AdjustmentHistoryResult(
        status=NO_PRIOR_ADJUSTMENT_LOCATED,
        evidences=["search_without_reajuste_hit"],
        notes=notes,
    )
