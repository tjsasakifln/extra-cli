"""Object classification for art. 75 I vs II — never assume engineering by profession."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from scripts.public_agency import OBJECT_ENGINEERING, OBJECT_HUMAN, OBJECT_OTHER

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PROFILE = _ROOT / "config/commercial/public_agency_profile.yaml"


def _fold(text: str | None) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.upper()).strip()


@dataclass
class ObjectClassification:
    suggested_class: str
    confidence: float
    evidences: list[str] = field(default_factory=list)
    justification: str = ""
    favorable_elements: list[str] = field(default_factory=list)
    contrary_elements: list[str] = field(default_factory=list)
    pending_questions: list[str] = field(default_factory=list)
    art_potentially_required: bool = False
    human_validation_required: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_keywords(profile_path: Path | None = None) -> tuple[list[str], list[str]]:
    p = profile_path or _DEFAULT_PROFILE
    if not p.exists():
        eng = ["OBRA", "ENGENHARIA", "PAVIMENTACAO", "CONSTRUCAO", "REFORMA"]
        other = ["CAPACITACAO", "TREINAMENTO", "CURSO", "SOFTWARE"]
        return eng, other
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    eng = [_fold(x) for x in (data.get("engineering_object_keywords") or [])]
    other = [_fold(x) for x in (data.get("other_service_keywords") or [])]
    return eng, other


def classify_object(
    object_text: str | None,
    *,
    profile_path: Path | None = None,
    min_confidence_auto: float = 0.65,
) -> ObjectClassification:
    blob = _fold(object_text)
    eng_kws, other_kws = _load_keywords(profile_path)

    if not blob:
        return ObjectClassification(
            suggested_class=OBJECT_HUMAN,
            confidence=0.0,
            evidences=[],
            justification="Objeto ausente ou vazio; classificação automática impossível.",
            pending_questions=["Qual é o objeto concreto da contratação?"],
            art_potentially_required=False,
            human_validation_required=True,
        )

    eng_hits = [k for k in eng_kws if k and k in blob]
    other_hits = [k for k in other_kws if k and k in blob]

    favorable: list[str] = []
    contrary: list[str] = []
    evidences: list[str] = []

    if eng_hits:
        favorable.extend(f"termo_engenharia:{h}" for h in eng_hits[:8])
        evidences.extend(eng_hits[:8])
    if other_hits:
        contrary.extend(f"termo_outro_servico:{h}" for h in other_hits[:8]) if eng_hits else favorable.extend(
            f"termo_outro_servico:{h}" for h in other_hits[:8]
        )
        evidences.extend(other_hits[:8])

    # Ambiguous: both sides fire
    if eng_hits and other_hits:
        return ObjectClassification(
            suggested_class=OBJECT_HUMAN,
            confidence=0.4,
            evidences=evidences,
            justification=(
                "Objeto apresenta elementos de serviço de engenharia e de outro serviço; "
                "exige classificação jurídica humana."
            ),
            favorable_elements=favorable,
            contrary_elements=contrary,
            pending_questions=[
                "O núcleo do objeto é obra/serviço de engenharia ou consultoria/capacitação administrativa?"
            ],
            art_potentially_required=True,
            human_validation_required=True,
        )

    if eng_hits and not other_hits:
        conf = min(0.55 + 0.08 * len(eng_hits), 0.92)
        human = conf < min_confidence_auto
        return ObjectClassification(
            suggested_class=OBJECT_ENGINEERING,
            confidence=round(conf, 3),
            evidences=evidences,
            justification=(
                "Termos do objeto são tecnicamente enquadráveis como obra ou serviço de engenharia "
                f"(art. 75, I potencialmente aplicável se demais requisitos legais forem atendidos)."
            ),
            favorable_elements=favorable,
            contrary_elements=contrary,
            pending_questions=[] if not human else ["Validar enquadramento técnico formal do objeto."],
            art_potentially_required=True,
            human_validation_required=human,
        )

    if other_hits and not eng_hits:
        conf = min(0.55 + 0.08 * len(other_hits), 0.9)
        human = conf < min_confidence_auto
        return ObjectClassification(
            suggested_class=OBJECT_OTHER,
            confidence=round(conf, 3),
            evidences=evidences,
            justification=(
                "Termos do objeto apontam para serviço/compra não classificável como "
                "serviço de engenharia (art. 75, II potencialmente aplicável)."
            ),
            favorable_elements=favorable or [f"termo_outro_servico:{h}" for h in other_hits[:8]],
            contrary_elements=contrary,
            pending_questions=[] if not human else ["Confirmar que não há componente de engenharia no objeto."],
            art_potentially_required=False,
            human_validation_required=human,
        )

    return ObjectClassification(
        suggested_class=OBJECT_HUMAN,
        confidence=0.25,
        evidences=[],
        justification=(
            "Elementos insuficientes para classificar automaticamente o objeto "
            "como serviço de engenharia ou outro serviço."
        ),
        favorable_elements=[],
        contrary_elements=[],
        pending_questions=["Descrever o objeto com verbetes técnicos suficientes."],
        art_potentially_required=False,
        human_validation_required=True,
    )


def may_allege_dispensa_ceiling(classification: ObjectClassification) -> bool:
    """Commercial allegation about ceiling only when classification is non-ambiguous."""
    if classification.suggested_class == OBJECT_HUMAN:
        return False
    if classification.human_validation_required and classification.confidence < 0.65:
        return False
    return True
