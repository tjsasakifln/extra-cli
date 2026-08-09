"""Explicit ICP target-fit for CONFENGE automatic outreach.

Classes:
  TARGET_CONFIRMED         — material evidence of construction/engineering execution
  TARGET_PROBABLE_RESEARCH — possible adjacency; never EMAIL_SEND_READY
  TARGET_OUT_OF_SCOPE      — commerce/material/fleet/etc. without execution proof

Name alone never confirms. CNAE alone never confirms. A single weak keyword,
high contract value, or infrastructure agency alone never confirms.
Triangulation required for TARGET_CONFIRMED.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.commercial_leads.contract_relevance import (
    classify_contract_relevance,
    normalize_text,
)
from scripts.commercial_leads.sector_fit import (
    ACTIVITY_COMMERCE,
    ACTIVITY_CONSTRUCTION,
    ACTIVITY_ENGINEERING_SERVICE,
    ACTIVITY_EQUIPMENT,
    ACTIVITY_MATERIAL,
    ACTIVITY_TECHNICAL_DESIGN,
    CLASS_CONFIRMED,
    CLASS_OUT,
    CLASS_POSSIBLE,
    CLASS_STRONG,
    NAME_OUT_OF_SCOPE,
)

TARGET_FIT_VERSION = "confenge-target-fit-v1"

TARGET_CONFIRMED = "TARGET_CONFIRMED"
TARGET_PROBABLE_RESEARCH = "TARGET_PROBABLE_RESEARCH"
TARGET_OUT_OF_SCOPE = "TARGET_OUT_OF_SCOPE"

# Execution-heavy markers in objects (not mere supply/adjacency)
_EXECUTION_MARKERS: tuple[str, ...] = (
    "execucao de obra",
    "execucao de obras",
    "empreitada",
    "construcao civil",
    "pavimentacao",
    "terraplenagem",
    "saneamento",
    "obras de infraestrutura",
    "servicos de engenharia",
    "servico de engenharia",
    "projeto de engenharia",
    "projeto executivo de engenharia",
    "reforma predial",
    "manutencao predial",
    "manutencao civil",
    "recuperacao estrutural",
    "drenagem",
    "fundacao",
    "edificacao",
    "obra de arte especial",
    "reabilitacao de",
    "duplicacao de via",
    "pavimentacao asfaltica",
)

# Supply / adjacency objects that must not alone confirm ICP
_SUPPLY_ADJACENCY: tuple[str, ...] = (
    "aquisicao de",
    "fornecimento de materiais",
    "fornecimento de pecas",
    "fornecimento de pneus",
    "fornecimento de moveis",
    "conjuntos escolares",
    "cateter",
    "calibracao",
    "metrolog",
    "laudo tecnico de avaliacao imobiliaria",
    "avaliacao imobiliaria",
    "locacao de imoveis",
    "onibus",
    "veiculo",
    "frota",
    "revisao preventiva",
    "backdrop",
    "sinalizacao de eventos",
)

_NAME_HARD_OUT: tuple[str, ...] = NAME_OUT_OF_SCOPE + (
    "imoveis",
    "imobiliaria",
    "moveis",
    "mobiliario",
    "metrologica",
    "metrologia",
    "isomedical",
    "medico",
    "medical",
    "frotas",
    "manutencao de frotas",
    "importacao exportacao",
    "comercio importacao",
    "autopecas",
    "concessionaria",
    "dealer",
)


@dataclass
class TargetFitDecision:
    target_fit_class: str
    target_fit_confidence: float
    target_fit_evidence: list[dict[str, Any]] = field(default_factory=list)
    target_fit_reason_codes: list[str] = field(default_factory=list)
    target_fit_version: str = TARGET_FIT_VERSION
    sector_fit: str = ""
    activity_class: str = ""
    relevant_execution_contract_count: int = 0
    relevant_supply_only_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm_name(razao: str | None, fantasia: str | None) -> str:
    return normalize_text(f"{razao or ''} {fantasia or ''}")


def _name_hard_out(name_norm: str) -> list[str]:
    hits = [m for m in _NAME_HARD_OUT if m in name_norm]
    return hits


def _object_is_execution(obj: str) -> bool:
    n = normalize_text(obj)
    if not n:
        return False
    if any(a in n for a in _SUPPLY_ADJACENCY) and not any(e in n for e in _EXECUTION_MARKERS):
        return False
    rel = classify_contract_relevance(obj)
    if rel.status != "PASS":
        return False
    if any(e in n for e in _EXECUTION_MARKERS):
        return True
    # Strong layer-A hits that are not pure supply
    if rel.strong_hits and not any(a in n for a in _SUPPLY_ADJACENCY):
        return True
    return False


def _object_is_supply_only(obj: str) -> bool:
    n = normalize_text(obj)
    if not n:
        return False
    if any(e in n for e in _EXECUTION_MARKERS):
        return False
    return any(a in n for a in _SUPPLY_ADJACENCY)


def classify_target_fit(
    *,
    razao_social: str | None,
    nome_fantasia: str | None = None,
    contracts: list[dict[str, Any]] | None = None,
    cnae_principal: str | None = None,
    cnaes_secundarios: list[str] | None = None,
    sector_fit: str | None = None,
    activity_class: str | None = None,
    construction_evidence: dict[str, Any] | None = None,
) -> TargetFitDecision:
    """Triangulated target-fit for CONFENGE automatic outreach."""
    contracts = contracts or []
    ce = construction_evidence if isinstance(construction_evidence, dict) else {}
    sector = (sector_fit or ce.get("sector_fit") or "").strip().upper()
    activity = (activity_class or ce.get("activity_class") or "").strip().upper()
    reasons: list[str] = []
    evidence: list[dict[str, Any]] = []

    name_norm = _norm_name(razao_social, nome_fantasia)
    hard_name = _name_hard_out(name_norm)

    exec_contracts: list[dict[str, Any]] = []
    supply_only = 0
    for i, c in enumerate(contracts):
        if not isinstance(c, dict):
            continue
        obj = str(c.get("objeto_contrato") or c.get("objeto") or c.get("object") or "")
        if _object_is_execution(obj):
            exec_contracts.append(c)
            evidence.append(
                {
                    "id": str(c.get("contrato_id") or c.get("id") or f"ct-{i}"),
                    "type": "CONTRACT_EXECUTION",
                    "excerpt": obj[:240],
                    "agency": c.get("orgao_nome") or c.get("orgao") or c.get("agency"),
                    "value_brl": c.get("valor_total") or c.get("value_brl"),
                }
            )
        elif _object_is_supply_only(obj) or (
            classify_contract_relevance(obj).status != "PASS" and obj
        ):
            if _object_is_supply_only(obj):
                supply_only += 1

    n_exec = len(exec_contracts)
    # Official CNAE construction/engineering prefixes
    cnae_digits = "".join(ch for ch in str(cnae_principal or "") if ch.isdigit())
    cnae_eng = cnae_digits.startswith(("41", "42", "43", "7111", "7112", "7113", "7120"))

    # Hard out: OUT sector fit or activity commerce/material without execution
    if sector in {CLASS_OUT, "OUT_OF_SCOPE", "NOT_CONSTRUCTION"} and n_exec == 0:
        reasons.append("sector_fit_out_without_execution")
        return TargetFitDecision(
            target_fit_class=TARGET_OUT_OF_SCOPE,
            target_fit_confidence=0.9,
            target_fit_evidence=evidence,
            target_fit_reason_codes=reasons,
            sector_fit=sector,
            activity_class=activity,
            relevant_execution_contract_count=n_exec,
            relevant_supply_only_count=supply_only,
        )

    if hard_name and n_exec == 0:
        reasons.append("name_hard_out_without_execution")
        reasons.append(f"name_markers:{','.join(hard_name[:5])}")
        return TargetFitDecision(
            target_fit_class=TARGET_OUT_OF_SCOPE,
            target_fit_confidence=0.85,
            target_fit_evidence=evidence,
            target_fit_reason_codes=reasons,
            sector_fit=sector,
            activity_class=activity,
            relevant_execution_contract_count=0,
            relevant_supply_only_count=supply_only,
        )

    if activity in {ACTIVITY_COMMERCE, ACTIVITY_MATERIAL, ACTIVITY_EQUIPMENT} and n_exec == 0:
        reasons.append(f"activity_{activity}_without_execution")
        return TargetFitDecision(
            target_fit_class=TARGET_OUT_OF_SCOPE,
            target_fit_confidence=0.8,
            target_fit_evidence=evidence,
            target_fit_reason_codes=reasons,
            sector_fit=sector,
            activity_class=activity,
            relevant_execution_contract_count=0,
            relevant_supply_only_count=supply_only,
        )

    # TARGET_CONFIRMED: triangulation
    # Path A: sector CONFIRMED/STRONG + ≥1 execution contract
    # Path B: ≥3 execution contracts across history (even if sector POSSIBLE)
    # Path C: CNAE eng + ≥2 execution contracts
    if sector in {CLASS_CONFIRMED, CLASS_STRONG} and n_exec >= 1:
        reasons.append("sector_strong_plus_execution_contract")
        if cnae_eng:
            reasons.append("cnae_engineering_corroboration")
        return TargetFitDecision(
            target_fit_class=TARGET_CONFIRMED,
            target_fit_confidence=0.9 if sector == CLASS_CONFIRMED else 0.82,
            target_fit_evidence=evidence[:10],
            target_fit_reason_codes=reasons,
            sector_fit=sector,
            activity_class=activity,
            relevant_execution_contract_count=n_exec,
            relevant_supply_only_count=supply_only,
        )

    if n_exec >= 3:
        reasons.append("multi_execution_contracts_triangulation")
        if activity in {
            ACTIVITY_CONSTRUCTION,
            ACTIVITY_ENGINEERING_SERVICE,
            ACTIVITY_TECHNICAL_DESIGN,
        }:
            reasons.append("activity_class_engineering")
        return TargetFitDecision(
            target_fit_class=TARGET_CONFIRMED,
            target_fit_confidence=0.8,
            target_fit_evidence=evidence[:10],
            target_fit_reason_codes=reasons,
            sector_fit=sector,
            activity_class=activity,
            relevant_execution_contract_count=n_exec,
            relevant_supply_only_count=supply_only,
        )

    if cnae_eng and n_exec >= 2:
        reasons.append("cnae_plus_multi_execution")
        return TargetFitDecision(
            target_fit_class=TARGET_CONFIRMED,
            target_fit_confidence=0.78,
            target_fit_evidence=evidence[:10],
            target_fit_reason_codes=reasons,
            sector_fit=sector,
            activity_class=activity,
            relevant_execution_contract_count=n_exec,
            relevant_supply_only_count=supply_only,
        )

    # Sector CONFIRMED/STRONG without execution objects in the provided slice
    # → research (do not auto-send on name+CNAE alone)
    if sector in {CLASS_CONFIRMED, CLASS_STRONG} and n_exec == 0:
        # If construction_evidence already counted relevant contracts highly, allow research not out
        rel_count = int(ce.get("relevant_contract_count") or 0)
        if rel_count >= 3 and float(ce.get("relevant_ratio") or 0) >= 0.7:
            reasons.append("sector_strong_but_objects_not_in_slice_research")
            return TargetFitDecision(
                target_fit_class=TARGET_PROBABLE_RESEARCH,
                target_fit_confidence=0.55,
                target_fit_evidence=evidence,
                target_fit_reason_codes=reasons,
                sector_fit=sector,
                activity_class=activity,
                relevant_execution_contract_count=n_exec,
                relevant_supply_only_count=supply_only,
            )
        reasons.append("sector_strong_without_execution_objects")
        return TargetFitDecision(
            target_fit_class=TARGET_PROBABLE_RESEARCH,
            target_fit_confidence=0.5,
            target_fit_evidence=evidence,
            target_fit_reason_codes=reasons,
            sector_fit=sector,
            activity_class=activity,
            relevant_execution_contract_count=n_exec,
            relevant_supply_only_count=supply_only,
        )

    if n_exec == 1 or sector == CLASS_POSSIBLE or "POSSIBLE" in sector:
        reasons.append("possible_or_single_execution_needs_research")
        if hard_name and n_exec == 0:
            # already handled; keep research if some weak signal
            pass
        if n_exec == 0 and supply_only > 0:
            reasons.append("supply_adjacency_only")
            return TargetFitDecision(
                target_fit_class=TARGET_OUT_OF_SCOPE,
                target_fit_confidence=0.75,
                target_fit_evidence=evidence,
                target_fit_reason_codes=reasons,
                sector_fit=sector,
                activity_class=activity,
                relevant_execution_contract_count=0,
                relevant_supply_only_count=supply_only,
            )
        return TargetFitDecision(
            target_fit_class=TARGET_PROBABLE_RESEARCH,
            target_fit_confidence=0.45,
            target_fit_evidence=evidence,
            target_fit_reason_codes=reasons,
            sector_fit=sector,
            activity_class=activity,
            relevant_execution_contract_count=n_exec,
            relevant_supply_only_count=supply_only,
        )

    if n_exec == 0 and not sector:
        reasons.append("no_sector_no_execution")
        return TargetFitDecision(
            target_fit_class=TARGET_OUT_OF_SCOPE,
            target_fit_confidence=0.7,
            target_fit_evidence=evidence,
            target_fit_reason_codes=reasons,
            sector_fit=sector,
            activity_class=activity,
            relevant_execution_contract_count=0,
            relevant_supply_only_count=supply_only,
        )

    reasons.append("default_research")
    return TargetFitDecision(
        target_fit_class=TARGET_PROBABLE_RESEARCH,
        target_fit_confidence=0.4,
        target_fit_evidence=evidence,
        target_fit_reason_codes=reasons,
        sector_fit=sector,
        activity_class=activity,
        relevant_execution_contract_count=n_exec,
        relevant_supply_only_count=supply_only,
    )


def target_fit_from_universe_row(row: dict[str, Any]) -> TargetFitDecision:
    """Convenience: classify from a confenge-universe JSONL row."""
    ce = row.get("construction_evidence") if isinstance(row.get("construction_evidence"), dict) else {}
    port = row.get("portfolio") if isinstance(row.get("portfolio"), dict) else {}
    recent = port.get("recent_contracts") or []
    if not isinstance(recent, list):
        recent = []
    return classify_target_fit(
        razao_social=row.get("razao_social"),
        nome_fantasia=row.get("nome_fantasia"),
        contracts=recent,
        sector_fit=ce.get("sector_fit"),
        activity_class=ce.get("activity_class"),
        construction_evidence=ce,
    )
