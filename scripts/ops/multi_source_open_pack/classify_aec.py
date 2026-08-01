"""Classificação hierárquica AEC — substitui engenharia_hint como autoridade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.ops.sector_classifier import SectorClassification, classify_object

TAXONOMY_VERSION = "aec-hierarchy/1.0.0"

# Hierarchical commercial categories for Extra
HIERARCHY = {
    "obra": "obra",
    "servico_comum_engenharia": "serviço comum de engenharia",
    "manutencao_predial": "manutenção predial",
    "infraestrutura_urbana": "infraestrutura urbana",
    "saneamento": "saneamento",
    "pavimentacao": "pavimentação",
    "edificacoes": "edificações",
    "reforma_ampliacao": "reforma/ampliação",
    "projeto_consultoria_engenharia": "projeto/consultoria de engenharia",
    "fornecimento_com_instalacao": "fornecimento com instalação relevante",
    "fornecimento_puro": "fornecimento puro",
    "locacao": "locação",
    "servico_nao_relacionado": "serviço não relacionado",
    "aquisicao_nao_relacionada": "aquisição não relacionada",
    "evento_sem_disputa": "evento sem disputa ativa",
}

_SUB_TO_HIER = {
    "pavimentacao": "pavimentacao",
    "drenagem": "infraestrutura_urbana",
    "terraplenagem": "infraestrutura_urbana",
    "saneamento": "saneamento",
    "infraestrutura_urbana": "infraestrutura_urbana",
    "edificacoes": "edificacoes",
    "reformas": "reforma_ampliacao",
    "manutencao_predial": "manutencao_predial",
    "obras_civis": "obra",
    "projetos": "projeto_consultoria_engenharia",
}


@dataclass
class AecClassification:
    category: str
    category_label: str
    sector_label: str
    confidence: float
    reason: str
    is_aec: bool
    is_profile_adherent: bool
    taxonomy_version: str = TAXONOMY_VERSION
    sector_raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "category_label": self.category_label,
            "sector_label": self.sector_label,
            "confidence": self.confidence,
            "reason": self.reason,
            "is_aec": self.is_aec,
            "is_profile_adherent": self.is_profile_adherent,
            "taxonomy_version": self.taxonomy_version,
        }


def _map_sector(sec: SectorClassification, *, is_active_dispute: bool) -> AecClassification:
    if not is_active_dispute:
        return AecClassification(
            category="evento_sem_disputa",
            category_label=HIERARCHY["evento_sem_disputa"],
            sector_label=sec.label,
            confidence=max(sec.confidence, 0.9),
            reason=sec.reason or "sem disputa ativa",
            is_aec=False,
            is_profile_adherent=False,
            sector_raw=sec.to_dict(),
        )

    if sec.label == "EXCLUDED_CATEGORY":
        cat = "aquisicao_nao_relacionada"
        return AecClassification(
            category=cat,
            category_label=HIERARCHY[cat],
            sector_label=sec.label,
            confidence=sec.confidence,
            reason=sec.reason,
            is_aec=False,
            is_profile_adherent=False,
            sector_raw=sec.to_dict(),
        )

    if sec.label == "NON_ENGINEERING":
        # Try to refine hierarchy for audit
        neg = " ".join(sec.negative_terms + sec.excluded_terms)
        if "locac" in neg or "locacao" in (sec.reason or ""):
            cat = "locacao"
        elif "fornec" in (sec.reason or "") or "aquisicao" in (sec.reason or ""):
            cat = "fornecimento_puro"
        else:
            cat = "servico_nao_relacionado"
        return AecClassification(
            category=cat,
            category_label=HIERARCHY[cat],
            sector_label=sec.label,
            confidence=sec.confidence,
            reason=sec.reason,
            is_aec=False,
            is_profile_adherent=False,
            sector_raw=sec.to_dict(),
        )

    if sec.label in {"ENGINEERING_HIGH_CONFIDENCE", "ENGINEERING_REVIEW"}:
        hier = _SUB_TO_HIER.get(sec.subcategory or "", "obra")
        adherent = sec.label == "ENGINEERING_HIGH_CONFIDENCE" or (
            sec.label == "ENGINEERING_REVIEW" and sec.confidence >= 0.45
        )
        return AecClassification(
            category=hier,
            category_label=HIERARCHY.get(hier, hier),
            sector_label=sec.label,
            confidence=sec.confidence,
            reason=sec.reason,
            is_aec=True,
            is_profile_adherent=adherent and sec.sector_match,
            sector_raw=sec.to_dict(),
        )

    # AMBIGUOUS
    return AecClassification(
        category="servico_nao_relacionado",
        category_label=HIERARCHY["servico_nao_relacionado"],
        sector_label=sec.label,
        confidence=sec.confidence,
        reason=sec.reason or "classificação ambígua",
        is_aec=False,
        is_profile_adherent=False,
        sector_raw=sec.to_dict(),
    )


def classify_aec(
    objeto: str,
    *,
    is_active_dispute: bool = True,
    modalidade: str = "",
    profile: dict[str, Any] | None = None,
) -> AecClassification:
    """Classificação hierárquica auditável. NÃO usa engenharia_hint."""
    text = objeto or ""
    if modalidade:
        text = f"{text} | {modalidade}"
    sec = classify_object(objeto=text, profile=profile)
    return _map_sector(sec, is_active_dispute=is_active_dispute)
