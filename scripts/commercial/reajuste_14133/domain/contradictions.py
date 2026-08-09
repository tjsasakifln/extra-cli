"""Detect material contradictions across signals (no fixed False)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ContradictionResult:
    material_contradiction: bool
    items: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_material_contradictions(
    *,
    regime_labels: list[str] | None = None,
    is_construction: bool = False,
    object_text: str | None = None,
    value_status: str | None = None,
    already_adjusted: bool = False,
    claiming_no_adjustment: bool = False,
    data_base_confirmed: bool = False,
    data_base_proxy_only: bool = False,
    index_in_clause: bool = False,
    index_outside_clause_only: bool = False,
    legal_regime_conflict: bool = False,
) -> ContradictionResult:
    """Compute real contradictions from available signals."""
    items: list[str] = []
    regimes = [r for r in (regime_labels or []) if r]
    uniq = set(regimes)
    if legal_regime_conflict or len(uniq) > 1:
        if legal_regime_conflict or (
            "LEI_14133_2021" in uniq and ("LEI_8666_1993" in uniq or "RDC" in uniq)
        ):
            items.append("regime_legal_contraditorio")

    if already_adjusted and claiming_no_adjustment:
        items.append("reajuste_ja_concedido_vs_claim_aberto")

    if index_outside_clause_only and not index_in_clause:
        items.append("indice_mencionado_fora_da_clausula_de_reajuste")

    if data_base_confirmed and data_base_proxy_only:
        items.append("data_base_confirmada_e_proxy_simultaneos")

    if value_status in {"VALUE_CONFLICT"}:
        items.append("valor_contratual_em_conflito")

    obj = (object_text or "").lower()
    if is_construction and any(
        k in obj for k in ("fornecimento de materiais", "licenca de software", "software de gestao")
    ):
        items.append("objeto_misto_construcao_vs_fornecimento_ou_software")

    return ContradictionResult(material_contradiction=bool(items), items=items)
