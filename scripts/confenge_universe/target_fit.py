"""Explicit ICP target-fit for CONFENGE automatic outreach.

Classes:
  TARGET_CONFIRMED              — material evidence of construction/engineering execution
  TARGET_PROBABLE_RESEARCH      — POSITIVE ICP adjacency evidence; never EMAIL_SEND_READY
  TARGET_INSUFFICIENT_EVIDENCE  — no positive construction/engineering evidence yet
  TARGET_OUT_OF_SCOPE           — commerce/material/fleet/etc. without execution proof

Name alone never confirms. CNAE alone never confirms. A single weak keyword,
high contract value, or infrastructure agency alone never confirms.
Triangulation required for TARGET_CONFIRMED.

PROBABLE is NOT a synonym for "unknown". Absence of evidence is
TARGET_INSUFFICIENT_EVIDENCE (or OUT when hard negatives apply).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.commercial_leads.contract_relevance import (
    FOUNDATION_ENGINEERING_PHRASES,
    classify_contract_relevance,
    neutralize_evidence,
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
from scripts.confenge_contract_identity import public_contract_id
from scripts.confenge_universe.parafiscal import (
    PARAFISCAL_HARD_OUT_REASON,
    match_parafiscal_in_names,
)

# v2: PROBABLE requires positive ICP evidence; unknown → INSUFFICIENT_EVIDENCE
# v3: entity-name / event-presence evidence neutralization; bare "fundacao" no
# longer counts as structural-foundation execution evidence.
TARGET_FIT_VERSION = "confenge-target-fit-v3"

TARGET_CONFIRMED = "TARGET_CONFIRMED"
TARGET_PROBABLE_RESEARCH = "TARGET_PROBABLE_RESEARCH"
TARGET_INSUFFICIENT_EVIDENCE = "TARGET_INSUFFICIENT_EVIDENCE"
TARGET_OUT_OF_SCOPE = "TARGET_OUT_OF_SCOPE"

# Positive ICP construction/engineering activity classes (not mere supplier)
_POSITIVE_ICP_ACTIVITIES = frozenset(
    {
        ACTIVITY_CONSTRUCTION,
        ACTIVITY_ENGINEERING_SERVICE,
        ACTIVITY_TECHNICAL_DESIGN,
    }
)

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
    "edificacao",
    "obra de arte especial",
    "reabilitacao de",
    "duplicacao de via",
    "pavimentacao asfaltica",
    # Structural foundation phraseology. The former bare "fundacao de" /
    # "fundacoes de" entries matched legal-person names ("Fundação de Apoio ...")
    # and are replaced by the unambiguous engineering phrases below.
    *FOUNDATION_ENGINEERING_PHRASES,
)

# Supply / adjacency objects that must not alone confirm ICP
_SUPPLY_ADJACENCY: tuple[str, ...] = (
    "aquisicao de",
    "aquisicao de medicamento",
    "aquisicao de medicamentos",
    "aquisicao de insumos",
    "fornecimento de materiais",
    "fornecimento de pecas",
    "fornecimento de pneus",
    "fornecimento de moveis",
    "fornecimento de medicamento",
    "fornecimento de medicamentos",
    "medicamento",
    "medicamentos",
    "farmaceutic",
    "insumos hospital",
    "insumos medic",
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
    "farmaceutic",
    "farmacia",
    "quimico-farmaceutica",
    "quimico farmaceutica",
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


def _parafiscal_name_surface(
    razao_social: str | None,
    nome_fantasia: str | None,
    contracts: list[dict[str, Any]],
) -> list[str]:
    """Full name surface evaluated by the parafiscal gate (design C4).

    `razao_social` alone is NOT enough: `loader._load_contracts` picks it as the
    first non-null `fornecedor_nome` of a query without ORDER BY, so it is
    non-deterministic between runs. Measured in production: the 4 Sistema S roots
    have 235 distinct supplier-name variants, 15 of which match no marker
    ("SESCRS", "SEBRAEMG", truncated and mojibake variants). Scanning every
    distinct supplier name makes the gate deterministic regardless of which
    variant the loader happens to pick.
    """
    surface: list[str] = []
    seen: set[str] = set()
    for candidate in (razao_social, nome_fantasia):
        if isinstance(candidate, str) and candidate.strip() and candidate not in seen:
            seen.add(candidate)
            surface.append(candidate)
    for c in contracts:
        if not isinstance(c, dict):
            continue
        nome = c.get("fornecedor_nome") or c.get("nome_fornecedor")
        if isinstance(nome, str) and nome.strip() and nome not in seen:
            seen.add(nome)
            surface.append(nome)
    return surface


def _object_is_execution(obj: str) -> bool:
    # Strip entity-name / event-presence evidence BEFORE any evaluation. The
    # `rel.strong_hits and not supply_adjacency` fallback below would otherwise
    # keep a hit via "construcao civil" coming from the event theme alone.
    stripped = neutralize_evidence(obj)
    if stripped != normalize_text(obj):
        obj = stripped

    n = normalize_text(obj)
    if not n:
        return False
    # Pure supply / medication acquisition never counts as construction execution,
    # even if agency names contain foundation-like tokens (fundacao saude).
    if any(a in n for a in _SUPPLY_ADJACENCY):
        # Allow only if a true construction execution marker also appears
        # (e.g. "aquisicao de servicos de execucao de obra" is rare but possible).
        if not any(e in n for e in _EXECUTION_MARKERS):
            return False
        # If both, require explicit obra/engenharia execution tokens (not fundacao alone)
        strong_exec = (
            "execucao de obra",
            "execucao de obras",
            "empreitada",
            "pavimentacao",
            "construcao civil",
            "servicos de engenharia",
            "servico de engenharia",
        )
        if not any(e in n for e in strong_exec):
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
    strong_exec = (
        "execucao de obra",
        "execucao de obras",
        "empreitada",
        "pavimentacao",
        "construcao civil",
        "servicos de engenharia",
        "servico de engenharia",
    )
    if any(e in n for e in strong_exec):
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
                    "id": public_contract_id(c) or f"ct-{i}",
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

    # ------------------------------------------------------------------
    # Parafiscal / Sistema S institutional gate (AC 21, 22 — design C3/C4).
    #
    # UNCONDITIONAL: no `n_exec == 0` clause. Sistema S does refurbish its own
    # buildings, so it does accumulate real execution contracts (measured: 6/3/3
    # for SESC-RS / SENAC / SENAI) — and is still never a CONFENGE client. This
    # is an ICP policy decision, not a text-precision one.
    #
    # Placed AFTER the contract loop on purpose: `relevant_execution_contract_count`
    # stays truthful and auditable in the suppressed result, so a reviewer can see
    # "a root with 6 real execution contracts was suppressed" and contest it.
    #
    # This is the PRIMARY defence of the outbound path (reconcile → compute →
    # confenge_target_fit_shadow → continuous feed). `resolve_identity`'s
    # PARAFISCAL_INSTITUTIONAL exclusion is defence in depth for the universe
    # builder path only — `classify_target_fit` never calls it.
    # ------------------------------------------------------------------
    parafiscal_hit = match_parafiscal_in_names(
        _parafiscal_name_surface(razao_social, nome_fantasia, contracts)
    )
    if parafiscal_hit:
        matched_name, marker = parafiscal_hit
        reasons.append(PARAFISCAL_HARD_OUT_REASON)
        reasons.append(f"parafiscal_marker:{marker}")
        # Which name variant fired the gate — audit trail for the C4 surface,
        # since it is frequently NOT `razao_social`.
        evidence = [
            *evidence[:10],
            {
                "id": "parafiscal-name-match",
                "type": "PARAFISCAL_NAME",
                "excerpt": matched_name[:240],
                "marker": marker,
            },
        ]
        return TargetFitDecision(
            target_fit_class=TARGET_OUT_OF_SCOPE,
            # Above the 0.9 of `sector_fit_out_without_execution`: entity-type
            # evidence, not object-text evidence.
            target_fit_confidence=0.95,
            target_fit_evidence=evidence,
            target_fit_reason_codes=reasons,
            sector_fit=sector,
            activity_class=activity,
            relevant_execution_contract_count=n_exec,
            relevant_supply_only_count=supply_only,
        )

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

    # Pure supply/adjacency contracts without any execution → OUT (not PROBABLE)
    if n_exec == 0 and supply_only > 0 and not cnae_eng:
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

    # Positive ICP evidence flags (at least one required for PROBABLE)
    positive_cnae = bool(cnae_eng)
    positive_activity = activity in _POSITIVE_ICP_ACTIVITIES
    positive_sector = sector in {
        CLASS_CONFIRMED,
        CLASS_STRONG,
        CLASS_POSSIBLE,
    } or "POSSIBLE" in sector or "ENGINEERING" in sector or "CONSTRUCTION" in sector
    positive_exec = n_exec >= 1
    rel_count = int(ce.get("relevant_contract_count") or 0)
    positive_ce_count = rel_count >= 1 and float(ce.get("relevant_ratio") or 0) >= 0.3
    has_positive_icp = (
        positive_exec
        or positive_cnae
        or positive_activity
        or (positive_sector and sector in {CLASS_CONFIRMED, CLASS_STRONG, CLASS_POSSIBLE})
        or positive_ce_count
    )

    # Sector CONFIRMED/STRONG without execution objects in the provided slice
    # → research only when other positive ICP signals exist
    if sector in {CLASS_CONFIRMED, CLASS_STRONG} and n_exec == 0:
        if rel_count >= 3 and float(ce.get("relevant_ratio") or 0) >= 0.7:
            reasons.append("sector_strong_but_objects_not_in_slice_research")
            evidence.append(
                {
                    "id": "ce-relevant",
                    "type": "CONSTRUCTION_EVIDENCE_COUNT",
                    "excerpt": f"relevant_contract_count={rel_count}",
                }
            )
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
        if positive_cnae or positive_activity or positive_ce_count:
            reasons.append("sector_strong_without_execution_objects")
            if positive_cnae:
                reasons.append("positive_cnae_engineering")
                evidence.append(
                    {
                        "id": "cnae",
                        "type": "CNAE_ENGINEERING",
                        "excerpt": str(cnae_principal or cnae_digits),
                    }
                )
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
        reasons.append("sector_label_without_positive_icp_evidence")
        return TargetFitDecision(
            target_fit_class=TARGET_INSUFFICIENT_EVIDENCE,
            target_fit_confidence=0.35,
            target_fit_evidence=evidence,
            target_fit_reason_codes=reasons,
            sector_fit=sector,
            activity_class=activity,
            relevant_execution_contract_count=n_exec,
            relevant_supply_only_count=supply_only,
        )

    if n_exec == 1 or sector == CLASS_POSSIBLE or "POSSIBLE" in sector:
        reasons.append("possible_or_single_execution_needs_research")
        if n_exec == 0 and supply_only > 0 and not (positive_cnae or positive_activity):
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
        if has_positive_icp:
            if positive_exec:
                reasons.append("single_execution_contract_positive")
            if positive_cnae:
                reasons.append("positive_cnae_engineering")
                evidence.append(
                    {
                        "id": "cnae",
                        "type": "CNAE_ENGINEERING",
                        "excerpt": str(cnae_principal or cnae_digits),
                    }
                )
            if positive_activity:
                reasons.append(f"positive_activity:{activity}")
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
        reasons.append("possible_label_without_positive_icp_evidence")
        return TargetFitDecision(
            target_fit_class=TARGET_INSUFFICIENT_EVIDENCE,
            target_fit_confidence=0.3,
            target_fit_evidence=evidence,
            target_fit_reason_codes=reasons,
            sector_fit=sector,
            activity_class=activity,
            relevant_execution_contract_count=n_exec,
            relevant_supply_only_count=supply_only,
        )

    if n_exec == 0 and not sector:
        reasons.append("no_sector_no_execution")
        if positive_cnae or positive_activity:
            if positive_cnae:
                reasons.append("positive_cnae_engineering")
                evidence.append(
                    {
                        "id": "cnae",
                        "type": "CNAE_ENGINEERING",
                        "excerpt": str(cnae_principal or cnae_digits),
                    }
                )
            return TargetFitDecision(
                target_fit_class=TARGET_PROBABLE_RESEARCH,
                target_fit_confidence=0.4,
                target_fit_evidence=evidence,
                target_fit_reason_codes=reasons,
                sector_fit=sector,
                activity_class=activity,
                relevant_execution_contract_count=0,
                relevant_supply_only_count=supply_only,
            )
        return TargetFitDecision(
            target_fit_class=TARGET_INSUFFICIENT_EVIDENCE,
            target_fit_confidence=0.25,
            target_fit_evidence=evidence,
            target_fit_reason_codes=reasons + ["insufficient_positive_icp_evidence"],
            sector_fit=sector,
            activity_class=activity,
            relevant_execution_contract_count=0,
            relevant_supply_only_count=supply_only,
        )

    # Default: never inflate PROBABLE without positive ICP evidence
    if has_positive_icp:
        reasons.append("positive_icp_needs_research")
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

    reasons.append("insufficient_positive_icp_evidence")
    return TargetFitDecision(
        target_fit_class=TARGET_INSUFFICIENT_EVIDENCE,
        target_fit_confidence=0.25,
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
