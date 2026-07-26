"""Deterministic supplier sector-fit classification for CONFENGE (gold standard).

Architecture rules (non-negotiable):
- Concentration uses FULL supplier contract history, never prefilter-only.
- Single relevant contract without official evidence → max POSSIBLE.
- Name alone never publishable.
- STRONG without CNAE requires multi-agency, time span, diversity, high ratio.
- Material suppliers are a distinct activity class, not auto-engineering.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

from scripts.commercial_leads.contract_relevance import (
    classify_contract_relevance,
    normalize_text,
)

RULE_VERSION = "supplier-sector-fit-v2.2-gold"
# v2.2 restores STRONG_MIN_TIME_SPAN_DAYS=180 (objective non-negotiable).
# Short observation windows (~160d campaign snapshots) cannot mint STRONG
# without CNAE: CONFIRMED via official CNAE is the publishable path.

# Classes required by goal
CLASS_CONFIRMED = "CONFIRMED_ENGINEERING"
CLASS_STRONG = "STRONG_ENGINEERING_FIT"
CLASS_POSSIBLE = "POSSIBLE_ENGINEERING_FIT"
CLASS_OUT = "OUT_OF_SCOPE"
CLASS_UNKNOWN = "UNKNOWN"
CLASS_CONFLICTING = "CONFLICTING"

PUBLISHABLE = frozenset({CLASS_CONFIRMED, CLASS_STRONG})

# Activity classes (commercial profile declares which are eligible)
ACTIVITY_ENGINEERING_SERVICE = "ENGINEERING_SERVICE_PROVIDER"
ACTIVITY_CONSTRUCTION = "CONSTRUCTION_CONTRACTOR"
ACTIVITY_TECHNICAL_DESIGN = "TECHNICAL_DESIGN_PROVIDER"
ACTIVITY_MATERIAL = "ENGINEERING_MATERIAL_SUPPLIER"
ACTIVITY_EQUIPMENT = "EQUIPMENT_RENTAL"
ACTIVITY_COMMERCE = "GENERAL_COMMERCE"
ACTIVITY_OTHER = "OTHER"

# Name markers — positive (auxiliary only; never sole basis for publishable)
NAME_ENGINEERING: tuple[str, ...] = (
    "engenharia",
    "engenheir",
    "construtora",
    "construcoes",
    "construcao",
    "empreiteira",
    "paviment",
    "terraplenagem",
    "saneamento",
    "estruturas",
    "geotecnia",
    "topografia",
    "arquitetura e engenharia",
    "projetos de engenharia",
    "consultoria e projetos",
    "obras publicas",
    "infraestrutura",
    "empreendimentos",
    "projetos",
)

# Name markers — strong out of scope
NAME_OUT_OF_SCOPE: tuple[str, ...] = (
    "autopeca",
    "auto peca",
    "autopecas",
    "pecas e servicos",
    "comercio de pneus",
    "pneus",
    "tratorpeca",
    "tratorpecas",
    "auto eletrica",
    "autoeletrica",
    "churrascaria",
    "pizzaria",
    "restaurante",
    "padaria",
    "supermercado",
    "farmacia",
    "drogaria",
    "terceirizacao",
    "terceirizacoes",
    "limpeza",
    "conservacao e limpeza",
    "vigilancia",
    "seguranca patrimonial",
    "locacoes de equipamentos",
    "locacao de equipamentos",
    "locadora",
    "transportes",
    "logistica",
    "frete",
    "materiais p construcao",
    "materiais de construcao",
    "comercio de materiais",
    "comercio varejista",
    "comercio de",
    "comercio e",
    " distribuidora",
    "patrometal",
    "pinturas",
    "tintas",
    "posto de combustivel",
    "combustiveis",
    "informatica",
    "tecnologia da informacao",
    "software",
    "contabilidade",
    "contabil",
    "advocacia",
    "advogados",
    "imobiliario",
    "imobiliarios",
    "artefatos de cimento",
    "artefatos de concreto",
    "pre moldados",
    "premoldados",
    "concreto usinado",
    "concreteira",
)

CNAE_ENGINEERING_PREFIXES: tuple[str, ...] = (
    "41",  # construção de edifícios
    "42",  # obras de infraestrutura
    "43",  # serviços especializados para construção
    "7111",  # serviços de arquitetura
    "7112",  # serviços de engenharia
    "7113",  # testes e análises técnicas
    "7120",
)

CNAE_OUT_PREFIXES: tuple[str, ...] = (
    "45",  # comércio e reparação de veículos
    "46",  # comércio por atacado
    "47",  # comércio varejista
    "49",  # transporte terrestre
    "56",  # alimentação
    "62",  # TI
    "63",
    "81",  # serviços para edifícios e paisagismo (limpeza etc.)
    "78",  # seleção e agenciamento de mão de obra
    "80",  # segurança/vigilância
)

# Manufacturing / materials (not engineering service providers)
CNAE_MATERIAL_PREFIXES: tuple[str, ...] = (
    "23",  # produtos de minerais não-metálicos (cimento, pré-moldados, cerâmica)
    "24",  # metalurgia
    "25",  # produtos de metal (exceto máquinas)
)

# Gold-standard STRONG thresholds (without CNAE principal)
STRONG_MIN_RELEVANT = 3
STRONG_MIN_RATIO = 0.70
STRONG_MIN_AGENCIES = 2
STRONG_MIN_TIME_SPAN_DAYS = 180  # objective non-negotiable (v2.2)
STRONG_MIN_OBJECT_DIVERSITY = 2

# Material / supply markers
SUPPLY_ONLY_MARKERS: tuple[str, ...] = (
    "aquisicao de materiais",
    "fornecimento de materiais",
    "materiais de construcao",
    "materiais para construcao",
    "fornecimento de cimento",
    "pre moldado",
    "pre-moldado",
    "agregados",
    "artefatos de cimento",
    "tubos de",
    "pecas e componentes",
)

ENG_SERVICE_MARKERS: tuple[str, ...] = (
    "execucao de obra",
    "servicos de engenharia",
    "pavimentacao",
    "construcao civil",
    "empreitada",
    "fiscalizacao de obra",
    "projeto de engenharia",
    "terraplenagem",
    "drenagem",
    "saneamento",
)


@dataclass
class SectorFitDecision:
    classification: str
    confidence: float
    rule_version: str = RULE_VERSION
    evidence: list[dict[str, Any]] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    conflicting_evidence: list[dict[str, Any]] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)
    run_id: str | None = None
    relevant_contract_ratio: float = 0.0
    relevant_contract_count: int = 0
    irrelevant_contract_count: int = 0
    review_contract_count: int = 0
    total_contract_count: int = 0
    total_contract_count_full_history: int = 0
    relevant_contract_ratio_full_history: float = 0.0
    agency_count_relevant: int = 0
    object_diversity: int = 0
    time_span_days: int | None = None
    contract_category_distribution: dict[str, int] = field(default_factory=dict)
    activity_class: str = ACTIVITY_OTHER
    name_hits_positive: list[str] = field(default_factory=list)
    name_hits_negative: list[str] = field(default_factory=list)
    cnae_principal: str | None = None
    cnae_secondary: list[str] = field(default_factory=list)
    history_source: str = "full_history_required"
    denominator_invariant_ok: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def publishable(self) -> bool:
        return self.classification in PUBLISHABLE


def _norm_name(name: str | None) -> str:
    return normalize_text(name)


def _hits(norm: str, patterns: tuple[str, ...]) -> list[str]:
    return [p for p in patterns if p in norm]


def _cnae_digits(cnae: str | None) -> str:
    if not cnae:
        return ""
    return re.sub(r"\D", "", str(cnae))


def _cnae_matches(cnae: str | None, prefixes: tuple[str, ...]) -> bool:
    d = _cnae_digits(cnae)
    if not d:
        return False
    return any(d.startswith(p) for p in prefixes)


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _row_object(row: Any, object_field: str) -> str | None:
    if isinstance(row, dict):
        return row.get(object_field) or row.get("objeto") or row.get("objeto_contrato")
    return getattr(row, "objeto", None) or getattr(row, "objeto_contrato", None)


def _row_agency(row: Any) -> str | None:
    if isinstance(row, dict):
        return (
            row.get("orgao_cnpj")
            or row.get("orgao_nome")
            or row.get("agency_id")
            or row.get("agency")
        )
    return (
        getattr(row, "orgao_cnpj", None)
        or getattr(row, "orgao_nome", None)
        or getattr(row, "agency_id", None)
    )


def _row_pub_date(row: Any) -> date | None:
    if isinstance(row, dict):
        return _parse_date(
            row.get("data_publicacao") or row.get("data_inicio") or row.get("publication_date")
        )
    return _parse_date(
        getattr(row, "data_publicacao", None) or getattr(row, "data_inicio", None)
    )


def compute_contract_history_stats(
    contracts: list[Any],
    *,
    object_field: str = "objeto_contrato",
) -> dict[str, Any]:
    """Compute full-history concentration stats (denominator must include all contracts)."""
    relevant = 0
    irrelevant = 0
    review = 0
    total = 0
    object_labels: list[str] = []
    relevant_agencies: set[str] = set()
    relevant_objects: set[str] = set()
    dates: list[date] = []
    category_dist: Counter[str] = Counter()
    evidence_relevant: list[dict[str, Any]] = []
    conflicting_contracts: list[dict[str, Any]] = []
    supply_hits = 0
    eng_service_hits = 0

    for row in contracts:
        total += 1
        obj = _row_object(row, object_field)
        rel = classify_contract_relevance(obj)
        object_labels.append(rel.status)
        category_dist[rel.status] += 1
        obj_norm = normalize_text(obj)
        if any(m in obj_norm for m in SUPPLY_ONLY_MARKERS):
            supply_hits += 1
        if any(m in obj_norm for m in ENG_SERVICE_MARKERS):
            eng_service_hits += 1

        if rel.status == "PASS":
            relevant += 1
            agency = _row_agency(row)
            if agency:
                relevant_agencies.add(str(agency).strip().lower())
            if obj_norm:
                # coarse diversity: first 40 chars of normalized object
                relevant_objects.add(obj_norm[:40])
            d = _row_pub_date(row)
            if d:
                dates.append(d)
            evidence_relevant.append(
                {
                    "type": "relevant_contract",
                    "objeto": (str(obj)[:160] if obj else None),
                    "reason_codes": rel.reason_codes,
                    "strong_hits": rel.strong_hits[:5],
                    "agency": agency,
                }
            )
        elif rel.status == "REVIEW":
            review += 1
        else:
            irrelevant += 1
            if rel.negative_context:
                conflicting_contracts.append(
                    {
                        "type": "out_of_scope_contract",
                        "objeto": (str(obj)[:160] if obj else None),
                        "negative": rel.negative_context[:5],
                    }
                )

    ratio = (relevant / total) if total else 0.0
    time_span = None
    if len(dates) >= 2:
        time_span = (max(dates) - min(dates)).days
    elif len(dates) == 1:
        time_span = 0

    invariant_ok = (relevant + irrelevant + review) == total
    return {
        "relevant_contract_count": relevant,
        "irrelevant_contract_count": irrelevant,
        "review_contract_count": review,
        "total_contract_count_full_history": total,
        "relevant_contract_ratio_full_history": round(ratio, 4),
        "agency_count_relevant": len(relevant_agencies),
        "object_diversity": len(relevant_objects),
        "time_span_days": time_span,
        "contract_category_distribution": dict(category_dist),
        "evidence_relevant": evidence_relevant,
        "conflicting_contracts": conflicting_contracts,
        "supply_hits": supply_hits,
        "eng_service_hits": eng_service_hits,
        "denominator_invariant_ok": invariant_ok,
        "object_labels": object_labels,
    }


def infer_activity_class(
    *,
    stats: dict[str, Any],
    pos_name: list[str],
    neg_name: list[str],
    cnae_eng: bool,
    cnae_out: bool,
) -> str:
    """Infer coarse activity class for commercial eligibility filtering."""
    supply = int(stats.get("supply_hits") or 0)
    eng = int(stats.get("eng_service_hits") or 0)
    relevant = int(stats.get("relevant_contract_count") or 0)
    ratio = float(stats.get("relevant_contract_ratio_full_history") or 0.0)

    if supply > 0 and eng == 0 and not cnae_eng:
        return ACTIVITY_MATERIAL
    name_join = " ".join(pos_name + neg_name)
    if "locac" in name_join or "locadora" in name_join:
        return ACTIVITY_EQUIPMENT
    if cnae_out and not cnae_eng:
        return ACTIVITY_COMMERCE
    if eng > 0 and ratio >= 0.5:
        if any(x in name_join for x in ("construtora", "construcao", "empreiteira")):
            return ACTIVITY_CONSTRUCTION
        if any(x in name_join for x in ("projeto", "arquitet", "consultoria")):
            return ACTIVITY_TECHNICAL_DESIGN
        return ACTIVITY_ENGINEERING_SERVICE
    if cnae_eng:
        return ACTIVITY_ENGINEERING_SERVICE
    if relevant > 0:
        return ACTIVITY_OTHER
    return ACTIVITY_COMMERCE if neg_name else ACTIVITY_OTHER


def classify_supplier_sector_fit(
    *,
    razao_social: str | None,
    nome_fantasia: str | None = None,
    contracts: list[dict[str, Any]] | None = None,
    cnae_principal: str | None = None,
    cnaes_secundarios: list[str] | None = None,
    object_field: str = "objeto_contrato",
    run_id: str | None = None,
    history_is_full: bool = True,
) -> SectorFitDecision:
    """Classify supplier sector fit with full provenance on full contract history.

    history_is_full must be True for production paths. If False, classification
    is capped at POSSIBLE/UNKNOWN and never STRONG/CONFIRMED from contracts alone.
    """
    contracts = contracts or []
    cnaes_secundarios = cnaes_secundarios or []
    name_norm = f"{_norm_name(razao_social)} {_norm_name(nome_fantasia)}".strip()
    pos_name = _hits(name_norm, NAME_ENGINEERING)
    neg_name = _hits(name_norm, NAME_OUT_OF_SCOPE)

    evidence: list[dict[str, Any]] = []
    conflicting: list[dict[str, Any]] = []
    sources: list[str] = ["razao_social"]
    reasons: list[str] = []

    if pos_name:
        evidence.append({"type": "legal_name_positive", "hits": pos_name})
        reasons.append("name_engineering_marker")
    if neg_name:
        conflicting.append({"type": "legal_name_negative", "hits": neg_name})
        reasons.append("name_out_of_scope_marker")

    stats = compute_contract_history_stats(contracts, object_field=object_field)
    relevant = int(stats["relevant_contract_count"])
    total = int(stats["total_contract_count_full_history"])
    ratio = float(stats["relevant_contract_ratio_full_history"])
    agencies = int(stats["agency_count_relevant"])
    diversity = int(stats["object_diversity"])
    time_span = stats["time_span_days"]
    supply_hits = int(stats["supply_hits"])
    eng_service_hits = int(stats["eng_service_hits"])

    if total:
        sources.append("contract_objects_full_history")
        evidence.append(
            {
                "type": "contract_concentration_full_history",
                "relevant": relevant,
                "irrelevant": stats["irrelevant_contract_count"],
                "review": stats["review_contract_count"],
                "total": total,
                "ratio": ratio,
                "agencies_relevant": agencies,
                "object_diversity": diversity,
                "time_span_days": time_span,
                "history_is_full": history_is_full,
            }
        )
        evidence.extend(stats["evidence_relevant"][:30])
        conflicting.extend(stats["conflicting_contracts"][:20])

    if not stats["denominator_invariant_ok"]:
        reasons.append("FAIL_denominator_invariant")

    cnae_eng = _cnae_matches(cnae_principal, CNAE_ENGINEERING_PREFIXES)
    cnae_out = _cnae_matches(cnae_principal, CNAE_OUT_PREFIXES)
    cnae_material = _cnae_matches(cnae_principal, CNAE_MATERIAL_PREFIXES)
    sec_eng = any(_cnae_matches(c, CNAE_ENGINEERING_PREFIXES) for c in cnaes_secundarios)
    if cnae_principal:
        sources.append("cnae_principal")
        evidence.append(
            {
                "type": "cnae_principal",
                "value": cnae_principal,
                "engineering": cnae_eng,
                "out": cnae_out,
            }
        )
    if cnaes_secundarios:
        sources.append("cnae_secondary")

    activity = infer_activity_class(
        stats=stats,
        pos_name=pos_name,
        neg_name=neg_name,
        cnae_eng=cnae_eng,
        cnae_out=cnae_out or cnae_material,
    )
    if cnae_material and not cnae_eng:
        activity = ACTIVITY_MATERIAL

    classification = CLASS_UNKNOWN
    confidence = 0.2

    # --- Decision tree (gold standard) ---

    # Materials manufacturer (CNAE 23/24/25) is not an engineering service firm
    if cnae_material and not cnae_eng:
        classification = CLASS_OUT if ratio < 0.85 else CLASS_CONFLICTING
        confidence = 0.86
        reasons.append("cnae_material_manufacturer")
        activity = ACTIVITY_MATERIAL
    # Name engineering + CNAE retail + commercial history → CONFLICTING
    elif pos_name and cnae_out and not cnae_eng and ratio < STRONG_MIN_RATIO:
        classification = CLASS_CONFLICTING
        confidence = 0.7
        reasons.append("name_engineering_cnae_out_conflicting")
    # Hard OUT: name negative without engineering evidence
    elif neg_name and not pos_name and not cnae_eng and ratio < 0.5:
        classification = CLASS_OUT
        confidence = 0.9
        reasons.append("name_out_dominates")
    elif neg_name and not pos_name and eng_service_hits == 0 and not cnae_eng:
        classification = CLASS_OUT
        confidence = 0.88
        reasons.append("name_out_no_engineering_services")
    elif activity == ACTIVITY_MATERIAL and eng_service_hits == 0 and not cnae_eng:
        classification = CLASS_OUT
        confidence = 0.82
        reasons.append("materials_supply_only")
        reasons.append("activity_class_material_supplier")
    elif cnae_out and not cnae_eng and ratio < STRONG_MIN_RATIO:
        classification = CLASS_OUT
        confidence = 0.85
        reasons.append("cnae_out_of_scope")
    # CONFIRMED: requires official CNAE (or equivalent official) evidence
    elif cnae_eng and not neg_name:
        classification = CLASS_CONFIRMED
        confidence = 0.95 if ratio >= 0.4 else 0.88
        reasons.append("cnae_principal_engineering")
        if ratio >= 0.4:
            reasons.append("contracts_support_cnae")
        if pos_name:
            reasons.append("name_supports")
    elif cnae_eng and neg_name:
        classification = CLASS_CONFLICTING
        confidence = 0.6
        reasons.append("cnae_engineering_name_conflict")
    elif sec_eng and ratio >= 0.75 and relevant >= STRONG_MIN_RELEVANT and not neg_name and history_is_full:
        # Secondary CNAE alone is weaker; still can confirm with dominant contracts
        classification = CLASS_CONFIRMED
        confidence = 0.84
        reasons.append("secondary_cnae_plus_dominant_full_history")
    # STRONG without CNAE: cumulative multi-evidence on FULL history
    elif (
        history_is_full
        and relevant >= STRONG_MIN_RELEVANT
        and ratio >= STRONG_MIN_RATIO
        and agencies >= STRONG_MIN_AGENCIES
        and (time_span is not None and time_span >= STRONG_MIN_TIME_SPAN_DAYS)
        and diversity >= STRONG_MIN_OBJECT_DIVERSITY
        and not neg_name
        and not cnae_out
        and eng_service_hits >= 1
        and supply_hits < relevant  # not materials-dominant
    ):
        classification = CLASS_STRONG
        confidence = 0.78 if pos_name else 0.72
        reasons.append("strong_full_history_concentration")
        reasons.append(
            f"thresholds_v2:relevant>={STRONG_MIN_RELEVANT},ratio>={STRONG_MIN_RATIO},"
            f"agencies>={STRONG_MIN_AGENCIES},span>={STRONG_MIN_TIME_SPAN_DAYS}d,"
            f"diversity>={STRONG_MIN_OBJECT_DIVERSITY}"
        )
        if pos_name:
            reasons.append("name_supports")
    # Single relevant contract rule: max POSSIBLE without official evidence
    elif relevant == 1 and not cnae_eng:
        classification = CLASS_POSSIBLE if not neg_name else CLASS_CONFLICTING
        confidence = 0.45
        reasons.append("single_relevant_contract_cap_possible")
        if pos_name:
            reasons.append("name_auxiliary_only")
    # Name alone never publishable
    elif pos_name and total == 0 and not cnae_eng:
        classification = CLASS_POSSIBLE
        confidence = 0.4
        reasons.append("name_only_no_contracts_not_publishable")
    elif pos_name and neg_name:
        classification = CLASS_CONFLICTING
        confidence = 0.55
        reasons.append("name_conflict")
    elif neg_name and ratio >= STRONG_MIN_RATIO and relevant >= 2:
        classification = CLASS_CONFLICTING
        confidence = 0.5
        reasons.append("name_out_but_contracts_engineering")
    elif relevant >= 1 and ratio >= 0.35 and not neg_name:
        classification = CLASS_POSSIBLE
        confidence = 0.55
        reasons.append("some_relevant_contracts_not_strong")
        if not history_is_full:
            reasons.append("history_not_full_capped")
        if relevant < STRONG_MIN_RELEVANT:
            reasons.append("below_strong_min_relevant")
        if ratio < STRONG_MIN_RATIO:
            reasons.append("below_strong_min_ratio")
        if agencies < STRONG_MIN_AGENCIES:
            reasons.append("below_strong_min_agencies")
        if time_span is None or time_span < STRONG_MIN_TIME_SPAN_DAYS:
            reasons.append("below_strong_min_time_span")
        if diversity < STRONG_MIN_OBJECT_DIVERSITY:
            reasons.append("below_strong_min_diversity")
    elif total == 0 and not pos_name and not cnae_principal:
        classification = CLASS_UNKNOWN
        confidence = 0.15
        reasons.append("no_evidence")
    elif ratio == 0 and total > 0 and not pos_name:
        classification = CLASS_OUT if neg_name else CLASS_UNKNOWN
        confidence = 0.8 if neg_name else 0.3
        reasons.append("contracts_not_engineering" if neg_name else "no_relevant_contracts")
    else:
        classification = CLASS_POSSIBLE if relevant else CLASS_UNKNOWN
        confidence = 0.4 if relevant else 0.25
        reasons.append("default_low_evidence")

    # Multiservice / mixed: relevant minority with strong out markers
    if total >= 3 and 0 < ratio < 0.35 and neg_name:
        classification = CLASS_OUT
        confidence = max(confidence, 0.75)
        reasons.append("multiservice_out_dominant")

    # Absolute safety: never publishable from incomplete history
    if not history_is_full and classification in (CLASS_STRONG, CLASS_CONFIRMED) and not cnae_eng:
        classification = CLASS_POSSIBLE
        confidence = min(confidence, 0.5)
        reasons.append("incomplete_history_demoted_from_publishable")

    # Absolute: single relevant without CNAE cannot be STRONG/CONFIRMED
    if relevant <= 1 and not cnae_eng and classification in (CLASS_STRONG, CLASS_CONFIRMED):
        classification = CLASS_POSSIBLE
        confidence = min(confidence, 0.5)
        reasons.append("single_contract_forced_possible")

    return SectorFitDecision(
        classification=classification,
        confidence=round(confidence, 4),
        evidence=evidence[:40],
        reason_codes=reasons,
        conflicting_evidence=conflicting[:20],
        data_sources=sources,
        run_id=run_id,
        relevant_contract_ratio=round(ratio, 4),
        relevant_contract_count=relevant,
        irrelevant_contract_count=int(stats["irrelevant_contract_count"]),
        review_contract_count=int(stats["review_contract_count"]),
        total_contract_count=total,
        total_contract_count_full_history=total,
        relevant_contract_ratio_full_history=round(ratio, 4),
        agency_count_relevant=agencies,
        object_diversity=diversity,
        time_span_days=time_span,
        contract_category_distribution=dict(stats["contract_category_distribution"]),
        activity_class=activity,
        name_hits_positive=pos_name,
        name_hits_negative=neg_name,
        cnae_principal=cnae_principal,
        cnae_secondary=list(cnaes_secundarios),
        history_source="full_history" if history_is_full else "prefilter_only_incomplete",
        denominator_invariant_ok=bool(stats["denominator_invariant_ok"]),
    )


def sector_fit_histogram(decisions: list[SectorFitDecision]) -> dict[str, int]:
    c: Counter[str] = Counter(d.classification for d in decisions)
    return dict(c)


def assert_denominator_invariant(decision: SectorFitDecision) -> None:
    """Raise if concentration counts do not reconcile."""
    total = (
        decision.relevant_contract_count
        + decision.irrelevant_contract_count
        + decision.review_contract_count
    )
    if total != decision.total_contract_count_full_history:
        raise AssertionError(
            f"denominator invariant FAIL: {decision.relevant_contract_count}+"
            f"{decision.irrelevant_contract_count}+{decision.review_contract_count} "
            f"!= {decision.total_contract_count_full_history}"
        )
    if not decision.denominator_invariant_ok:
        raise AssertionError("denominator_invariant_ok is False")
