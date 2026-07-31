"""Explainable need/risk signals for public-agency prospecting."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

SIGNAL_VERSION = "public-agency-signals-v1"

NEED_SIGNAL_IDS = (
    "small_municipality",
    "recurring_engineering_procurements",
    "high_engineering_spend_relative_to_population",
    "failed_or_deserted_engineering_procurements",
    "cancelled_engineering_procurements",
    "low_bidder_competition",
    "repeated_deadline_extensions",
    "recurrent_contract_amendments",
    "recurrent_value_amendments",
    "contract_rescission",
    "contract_sanctions",
    "works_or_services_with_long_execution",
    "recent_engineering_transfer_or_grant",
    "upcoming_procurement_plan_item",
    "active_direct_contracting_notice",
    "recent_publication_of_engineering_demand",
    "repeated_document_inconsistency",
    "contract_execution_distress",
    "procurement_pipeline_without_observed_contract",
    "seasonal_procurement_window",
    "institutional_contact_available",
)

RISK_SIGNAL_IDS = (
    "possible_expense_fragmentation",
    "same_nature_annual_sum_unknown",
    "same_nature_annual_sum_above_threshold",
    "legal_classification_ambiguous",
    "conflict_of_interest_risk",
    "insufficient_public_evidence",
    "stale_data",
    "missing_official_identity",
    "restricted_or_nonpublic_contact_only",
    "service_outside_confenge_capacity",
    "required_technical_credential_missing",
)


def _fold(text: str | None) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.upper()).strip()


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if type(value) is date:
        return value
    if hasattr(value, "date") and callable(value.date):
        try:
            return value.date()  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001
            return None
    s = str(value)[:10]
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return None


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Multi-tier engineering object verdict (fail-closed).
# Order: EMPTY → HARD_NEGATIVE → STRONG_WORKS → WEAK_NOUN_ONLY → KEYWORD_ONLY → NONE
# Profile keywords NEVER alone force is_engineering=True.
# ---------------------------------------------------------------------------

TIER_NONE = "NONE"
TIER_HARD_NEGATIVE = "HARD_NEGATIVE"
TIER_STRONG_WORKS = "STRONG_WORKS"
TIER_WEAK_NOUN_ONLY = "WEAK_NOUN_ONLY"
TIER_KEYWORD_ONLY = "KEYWORD_ONLY"


@dataclass(frozen=True)
class EngineeringObjectVerdict:
    is_engineering: bool
    tier: str
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_engineering": self.is_engineering,
            "tier": self.tier,
            "reasons": list(self.reasons),
        }


# HARD_NEGATIVE always wins (checked first after empty).
_HARD_NEGATIVE_PHRASES: tuple[tuple[str, str], ...] = (
    ("labor_mao_de_obra", "MAO DE OBRA"),
    ("labor_mao_de_obra", "MAO-DE-OBRA"),
    ("labor_mao_de_obra", "MAOS DE OBRA"),
    ("labor_hora_homem", "HORA HOMEM"),
    ("pageant_cabelo", "CABELO"),
    ("pageant_maquiagem", "MAQUIAGEM"),
    ("pageant_beleza", "BELEZA"),
    ("pageant_estetica", "ESTETICA"),
    ("pageant_concurso", "CONCURSO DE BELEZA"),
    ("rental_aluguel", "ALUGUEL DE"),
    ("rental_locacao_veiculo", "LOCACAO DE VEICULO"),
    ("fuel", "COMBUSTIVEL"),
    ("food", "GENERO ALIMENTICIO"),
    ("medicine", "MEDICAMENTO"),
    ("uniform", "UNIFORME"),
    ("office_supplies", "MATERIAL DE EXPEDIENTE"),
    ("office_supplies", "MATERIAIS DE EXPEDIENTE"),
    ("tires", "PNEU"),
    ("tires", "PNEUS"),
    ("kitchen", "UTENSILIOS DE COZINHA"),
    ("hygiene_paper", "PAPEIS PARA HIGIENE"),
    ("disposable", "MATERIAIS DESCARTAVEIS"),
    ("furniture", "MOVEIS PARA ESCRITORIO"),
    ("notebooks", "NOTEBOOKS"),
    ("occupancy_concessao", "CONCESSAO DE USO"),
    ("occupancy_concessao", "CONCESSAO DE USO DE"),
    ("occupancy_cessao", "CESSAO DE IMOVEL"),
    ("occupancy_cessao", "CESSAO DE USO"),
    ("occupancy_permissao", "PERMISSAO DE USO"),
    ("occupancy_comodato", "COMODATO"),
    ("sports_event", "EVENTOS ESPORTIVOS"),
    ("school_transport", "TRANSPORTE ESCOLAR"),
)

# Supply-only patterns: acquisition without works-execution verbs → HARD_NEGATIVE
_SUPPLY_ONLY_RE = re.compile(
    r"\b(AQUISICAO|COMPRA|FORNECIMENTO|AQUISICAO DE|COMPRA DE|FORNECIMENTO DE)\b.{0,80}\b("
    r"MATERIAIS?|MATERIAL|ROMPEDOR|EQUIPAMENTO|EQUIPAMENTOS|FERRAMENTA|FERRAMENTAS|"
    r"MAQUINA|MAQUINAS|VEICULO|VEICULOS|MOVEIS|MOBILIARIO|PNEU|PNEUS|"
    r"COMBUSTIVEL|MEDICAMENTO|UNIFORME|NOTEBOOK|TABLET"
    r")\b"
)

# Works-execution verbs that can rescue an otherwise supply-looking object
_WORKS_EXECUTION_RE = re.compile(
    r"\b("
    r"EXECUCAO DE OBRA|EXECUCAO DE OBRAS|EXECUCAO DAS OBRAS|"
    r"OBRA DE |OBRAS DE |OBRA PUBLICA|OBRAS PUBLICAS|"
    r"CONSTRUCAO DE |REFORMA DE |"
    r"PAVIMENTACAO|TERRAPLENAGEM|"
    r"PROJETO BASICO|PROJETO EXECUTIVO|"
    r"SERVICOS? DE ENGENHAR|FISCALIZACAO DE OBRA"
    r")\b"
)

# STRONG_WORKS only — multi-word works / engineering services (never bare nouns).
_STRONG_WORKS_PATTERNS: tuple[tuple[str, str], ...] = (
    ("obra_de", r"\bOBRAS?\s+DE\s+\w"),
    ("obra_publica", r"\bOBRAS?\s+PUBLICAS?\b"),
    ("execucao_obra", r"\bEXECUCAO\s+(DE\s+)?(DAS\s+)?OBRAS?\b"),
    ("construcao_de", r"\bCONSTRUCAO\s+DE\s+\w"),
    ("construcao_civil", r"\bCONSTRUCAO\s+CIVIL\b"),
    ("reforma_de_building", r"\bREFORMA\s+DE\s+(ESCOLA|PREDIO|EDIFIC|UBS|UNIDADE|CRECHE|HOSPITAL|PONTE|PRACA|CALCADA)"),
    ("pavimentacao", r"\bPAVIMENTAC"),
    ("terraplenagem", r"\bTERRAPLENAGEM\b"),
    ("drenagem_works", r"\bDRENAGEM\s+(URBANA|PLUVIAL|DE\s+)"),
    ("saneamento_works", r"\b(OBRAS?\s+DE\s+)?SANEAMENTO\b"),
    ("rede_esgoto", r"\bREDE\s+DE\s+ESGOTO\b"),
    ("rede_agua", r"\bREDE\s+DE\s+AGUA\b"),
    ("estacao_tratamento", r"\bESTACAO\s+DE\s+TRATAMENTO\b"),
    ("projeto_basico", r"\bPROJETO\s+BASICO\b"),
    ("projeto_executivo", r"\bPROJETO\s+EXECUTIVO\b"),
    ("servicos_engenharia", r"\bSERVICOS?\s+(TECNICOS\s+DE\s+)?ENGENHAR"),
    ("engenharia_discipline", r"\bENGENHARIA\s+(CIVIL|ELETRICA|MECANICA|AMBIENTAL)\b"),
    ("fiscalizacao_obra", r"\bFISCALIZACAO\s+DE\s+OBRAS?\b"),
    ("acompanhamento_obra", r"\bACOMPANHAMENTO\s+DE\s+OBRAS?\b"),
    ("orcamento_obra", r"\bORCAMENTO\s+DE\s+OBRAS?\b"),
    ("memorial_descritivo", r"\bMEMORIAL\s+DESCRITIVO\b"),
    ("planilha_orcament", r"\bPLANILHA\s+ORCAMENT"),
    ("infraestrutura_urbana", r"\bINFRAESTRUTURA\s+(URBANA|VIARIA)\b"),
    ("ponte_works", r"\b(CONSTRUCAO|REFORMA|OBRA)\s+.{0,20}\bPONTE\b"),
    ("viaduto", r"\bVIADUTO\b"),
    ("barragem", r"\bBARRAGEM\b"),
    ("galeria_aguas", r"\bGALERIA\s+DE\s+AGUAS\b"),
)

# WEAK nouns alone never True (even if profile keyword matches).
_WEAK_NOUN_RE = re.compile(
    r"\b("
    r"EDIFICACAO|EDIFICACOES|EDIFICIO|EDIFICIOS|"
    r"CONSTRUCAO|CONSTRUCOES|"
    r"REFORMA|REFORMAS|"
    r"OBRA|OBRAS|"
    r"PROJETO|PROJETOS|"
    r"INFRAESTRUTURA|MANUTENCAO"
    r")\b"
)


def classify_engineering_object(
    obj: str | None,
    eng_keywords: list[str] | None = None,
) -> EngineeringObjectVerdict:
    """Multi-tier engineering object classification (fail-closed).

    Profile eng_keywords never alone force True — only annotate KEYWORD_ONLY
    when STRONG_WORKS already matched, or stand alone as non-engineering.
    """
    blob = _fold(obj)
    if not blob:
        return EngineeringObjectVerdict(False, TIER_NONE, ("empty",))

    # 1) HARD_NEGATIVE
    neg_reasons: list[str] = []
    for rid, phrase in _HARD_NEGATIVE_PHRASES:
        if phrase in blob:
            neg_reasons.append(rid)

    supply_match = _SUPPLY_ONLY_RE.search(blob)
    has_works_exec = bool(_WORKS_EXECUTION_RE.search(blob))
    if supply_match and not has_works_exec:
        neg_reasons.append("supply_only_acquisition")

    # Secretariat / organ names containing INFRAESTRUTURA alone (not works context)
    if re.search(r"\bSECRETARIA\b.{0,40}\bINFRAESTRUTURA\b", blob) and not has_works_exec:
        if not any(
            p in blob
            for p in (
                "OBRA DE ",
                "OBRAS DE ",
                "PAVIMENT",
                "EXECUCAO DE OBRA",
                "PROJETO BASICO",
            )
        ):
            # Only count as negative if no strong works pattern will match later —
            # still record; hard negative if no strong works
            pass

    if neg_reasons and not has_works_exec:
        # concession / labor / supply without works execution → hard negative
        return EngineeringObjectVerdict(False, TIER_HARD_NEGATIVE, tuple(dict.fromkeys(neg_reasons)))

    # If hard negatives co-exist WITH works execution verbs (rare), still allow
    # strong works evaluation below — but pure concession stays negative:
    if any(r.startswith("occupancy_") for r in neg_reasons) and not has_works_exec:
        return EngineeringObjectVerdict(False, TIER_HARD_NEGATIVE, tuple(dict.fromkeys(neg_reasons)))
    if any(r.startswith("pageant_") or r.startswith("labor_") for r in neg_reasons) and not has_works_exec:
        return EngineeringObjectVerdict(False, TIER_HARD_NEGATIVE, tuple(dict.fromkeys(neg_reasons)))
    if "supply_only_acquisition" in neg_reasons:
        return EngineeringObjectVerdict(False, TIER_HARD_NEGATIVE, tuple(dict.fromkeys(neg_reasons)))

    # 2) STRONG_WORKS
    strong_reasons: list[str] = []
    for rid, pattern in _STRONG_WORKS_PATTERNS:
        if re.search(pattern, blob):
            strong_reasons.append(rid)

    # SANEAMENTO / DRENAGEM only as works (not bare word in unrelated context)
    if re.search(r"\bSANEAMENTO\b", blob) and re.search(
        r"\b(OBRA|OBRAS|EXECUCAO|REDE|SISTEMA|SERVICOS?\s+DE)\b", blob
    ):
        strong_reasons.append("saneamento_works_context")
    if re.search(r"\bDRENAGEM\b", blob) and re.search(
        r"\b(OBRA|OBRAS|EXECUCAO|PLUVIAL|URBANA|SISTEMA)\b", blob
    ):
        strong_reasons.append("drenagem_works_context")

    if strong_reasons:
        # Profile keywords may annotate but never gate
        kw_hits = []
        for kw in eng_keywords or []:
            fk = _fold(kw)
            if fk and len(fk) >= 4 and fk in blob:
                kw_hits.append(f"keyword:{fk[:40]}")
        reasons = tuple(dict.fromkeys(strong_reasons + kw_hits[:5]))
        return EngineeringObjectVerdict(True, TIER_STRONG_WORKS, reasons)

    # 3) WEAK_NOUN_ONLY — False
    if _WEAK_NOUN_RE.search(blob):
        return EngineeringObjectVerdict(
            False,
            TIER_WEAK_NOUN_ONLY,
            ("weak_noun_without_works_execution",),
        )

    # 4) Profile keywords alone — False (KEYWORD_ONLY)
    kw_only: list[str] = []
    for kw in eng_keywords or []:
        fk = _fold(kw)
        if fk and len(fk) >= 4 and fk in blob:
            kw_only.append(f"keyword:{fk[:40]}")
    if kw_only:
        return EngineeringObjectVerdict(False, TIER_KEYWORD_ONLY, tuple(kw_only[:8]))

    return EngineeringObjectVerdict(False, TIER_NONE, ("no_match",))


def is_engineering_object(obj: str | None, eng_keywords: list[str] | None = None) -> bool:
    """True only for STRONG_WORKS tier. eng_keywords never force True alone."""
    return classify_engineering_object(obj, eng_keywords).is_engineering


def is_strong_works_object(obj: str | None, eng_keywords: list[str] | None = None) -> bool:
    """Alias used by pipeline publishability seals."""
    return classify_engineering_object(obj, eng_keywords).tier == TIER_STRONG_WORKS


def _is_engineering_object(obj: str | None, eng_keywords: list[str]) -> bool:
    """Backward-compatible alias."""
    return is_engineering_object(obj, eng_keywords)


@dataclass
class SignalHit:
    signal_id: str
    status: str  # FIRED | NOT_FIRED | NOT_COMPUTABLE
    confidence: float
    weight: float
    evidence: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    definition: str = ""
    version: str = SIGNAL_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_agency_signals(
    *,
    contracts: list[dict[str, Any]],
    population: int | None,
    as_of: date,
    eng_keywords: list[str] | None = None,
    has_institutional_contact: bool = False,
    object_class_ambiguous: bool = False,
    fragmentation_indicators: list[str] | None = None,
    conflict_state: str | None = None,
    annual_sum_state: str | None = None,
    window_days: int = 730,
) -> list[SignalHit]:
    """Compute versioned signals from buyer-side contracts + context."""
    # Profile keywords never force eng classification (see classify_engineering_object).
    eng_kws = eng_keywords or []
    hits: list[SignalHit] = []
    start = as_of - timedelta(days=window_days)

    # Only STRONG_WORKS tier counts as engineering for need signals.
    eng_contracts = []
    for c in contracts:
        verdict = classify_engineering_object(str(c.get("objeto_contrato") or ""), eng_kws)
        if verdict.tier == TIER_STRONG_WORKS:
            row = dict(c)
            row["_eng_verdict"] = verdict.as_dict()
            eng_contracts.append(row)

    # small_municipality
    if population is None:
        hits.append(
            SignalHit(
                signal_id="small_municipality",
                status="NOT_COMPUTABLE",
                confidence=0.0,
                weight=0.05,
                limitations=["population unknown"],
                definition="Município com população até 50 mil (contextual, não prova necessidade).",
            )
        )
    else:
        fired = population <= 50000
        hits.append(
            SignalHit(
                signal_id="small_municipality",
                status="FIRED" if fired else "NOT_FIRED",
                confidence=0.9 if fired else 0.9,
                weight=0.05,
                evidence=[{"population": population, "threshold": 50000}],
                definition="Município com população até 50 mil (contextual).",
            )
        )

    # recurring_engineering_procurements
    if not eng_contracts:
        hits.append(
            SignalHit(
                signal_id="recurring_engineering_procurements",
                status="NOT_FIRED" if contracts else "NOT_COMPUTABLE",
                confidence=0.7 if contracts else 0.0,
                weight=0.15,
                evidence=[{"engineering_contracts": 0}],
                definition="Múltiplos contratos de engenharia no período de observação.",
                limitations=[] if contracts else ["no contracts loaded"],
            )
        )
    else:
        dates = [_parse_date(c.get("data_publicacao") or c.get("data_inicio")) for c in eng_contracts]
        dates_ok = [d for d in dates if d and d >= start]
        fired = len(dates_ok) >= 3 or len(eng_contracts) >= 3
        hits.append(
            SignalHit(
                signal_id="recurring_engineering_procurements",
                status="FIRED" if fired else "NOT_FIRED",
                confidence=0.75,
                weight=0.15,
                evidence=[
                    {
                        "engineering_contracts": len(eng_contracts),
                        "in_window": len(dates_ok),
                        "window_days": window_days,
                    }
                ],
                definition="Múltiplos contratos de engenharia no período de observação.",
            )
        )

    # high_engineering_spend_relative_to_population
    eng_value = sum(_num(c.get("valor_total")) or 0.0 for c in eng_contracts)
    if population and population > 0 and eng_contracts:
        per_capita = eng_value / population
        fired = per_capita >= 50.0  # heuristic BRL/hab
        hits.append(
            SignalHit(
                signal_id="high_engineering_spend_relative_to_population",
                status="FIRED" if fired else "NOT_FIRED",
                confidence=0.6,
                weight=0.1,
                evidence=[{"eng_value": eng_value, "population": population, "per_capita": round(per_capita, 2)}],
                definition="Gasto de engenharia elevado relativo à população (heurística).",
                limitations=["heurística local; não é indicador de capacidade técnica isolado"],
            )
        )
    else:
        hits.append(
            SignalHit(
                signal_id="high_engineering_spend_relative_to_population",
                status="NOT_COMPUTABLE",
                confidence=0.0,
                weight=0.1,
                limitations=["population or engineering spend missing"],
                definition="Gasto de engenharia elevado relativo à população.",
            )
        )

    # works_or_services_with_long_execution
    long_exec = 0
    for c in eng_contracts:
        di = _parse_date(c.get("data_inicio"))
        df = _parse_date(c.get("data_fim"))
        if di and df and (df - di).days >= 180:
            long_exec += 1
    hits.append(
        SignalHit(
            signal_id="works_or_services_with_long_execution",
            status="FIRED" if long_exec else ("NOT_FIRED" if eng_contracts else "NOT_COMPUTABLE"),
            confidence=0.7 if eng_contracts else 0.0,
            weight=0.08,
            evidence=[{"long_execution_count": long_exec}],
            definition="Contratos de engenharia com execução >= 180 dias.",
        )
    )

    # recent_publication_of_engineering_demand
    recent = 0
    for c in eng_contracts:
        d = _parse_date(c.get("data_publicacao") or c.get("data_inicio"))
        if d and d >= as_of - timedelta(days=180):
            recent += 1
    hits.append(
        SignalHit(
            signal_id="recent_publication_of_engineering_demand",
            status="FIRED" if recent else ("NOT_FIRED" if contracts else "NOT_COMPUTABLE"),
            confidence=0.7 if contracts else 0.0,
            weight=0.12,
            evidence=[{"recent_eng_publications_180d": recent}],
            definition="Publicação recente de demanda/contrato de engenharia.",
        )
    )

    # contract_execution_distress — proxy via is_active long contracts without end
    distress = 0
    for c in eng_contracts:
        di = _parse_date(c.get("data_inicio"))
        df = _parse_date(c.get("data_fim"))
        active = c.get("is_active") in (True, "t", "true", "1", 1)
        if active and di and (as_of - di).days > 365 and (df is None or df < as_of):
            distress += 1
    hits.append(
        SignalHit(
            signal_id="contract_execution_distress",
            status="FIRED" if distress else ("NOT_FIRED" if eng_contracts else "NOT_COMPUTABLE"),
            confidence=0.55 if eng_contracts else 0.0,
            weight=0.12,
            evidence=[{"distress_proxy_count": distress}],
            definition="Proxy de sofrimento executivo (contrato longo ativo/vencido).",
            limitations=["proxy; não prova atraso oficial sem aditivos/atas"],
        )
    )

    # institutional_contact_available
    hits.append(
        SignalHit(
            signal_id="institutional_contact_available",
            status="FIRED" if has_institutional_contact else "NOT_FIRED",
            confidence=0.8,
            weight=0.05,
            evidence=[{"institutional_contact": has_institutional_contact}],
            definition="Contato institucional público disponível.",
        )
    )

    # Risk signals
    hits.append(
        SignalHit(
            signal_id="same_nature_annual_sum_unknown",
            status="FIRED"
            if (annual_sum_state in (None, "DIRECT_CONTRACTING_SUM_UNKNOWN") or annual_sum_state == "DIRECT_CONTRACTING_SUM_UNKNOWN")
            else "NOT_FIRED",
            confidence=0.9,
            weight=-0.05,
            evidence=[{"annual_sum_state": annual_sum_state}],
            definition="Somatório anual da mesma natureza desconhecido.",
        )
    )
    if annual_sum_state == "SAME_NATURE_ANNUAL_SUM_ABOVE_THRESHOLD":
        hits.append(
            SignalHit(
                signal_id="same_nature_annual_sum_above_threshold",
                status="FIRED",
                confidence=0.85,
                weight=-0.2,
                evidence=[{"annual_sum_state": annual_sum_state}],
                definition="Somatório anual da mesma natureza acima do teto.",
            )
        )

    frag = fragmentation_indicators or []
    hits.append(
        SignalHit(
            signal_id="possible_expense_fragmentation",
            status="FIRED" if frag else "NOT_FIRED",
            confidence=0.7 if frag else 0.6,
            weight=-0.15 if frag else 0.0,
            evidence=[{"indicators": frag}],
            definition="Indícios de fracionamento de despesa.",
        )
    )

    hits.append(
        SignalHit(
            signal_id="legal_classification_ambiguous",
            status="FIRED" if object_class_ambiguous else "NOT_FIRED",
            confidence=0.9,
            weight=-0.1 if object_class_ambiguous else 0.0,
            definition="Classificação jurídica do objeto ambígua.",
        )
    )

    coi_risk = conflict_state in {
        "CONFLICT_BLOCKED",
        "CONFLICT_REVIEW_REQUIRED",
        "CONFLICT_CHECK_PENDING",
    }
    hits.append(
        SignalHit(
            signal_id="conflict_of_interest_risk",
            status="FIRED" if coi_risk else "NOT_FIRED",
            confidence=0.8,
            weight=-0.25 if conflict_state == "CONFLICT_BLOCKED" else (-0.05 if coi_risk else 0.0),
            evidence=[{"conflict_state": conflict_state}],
            definition="Risco de conflito de interesses (pendente/bloqueado).",
        )
    )

    # missing identity
    # (caller may add; we check via contracts orgao fields)
    has_id = any(c.get("orgao_cnpj") or c.get("orgao_nome") for c in contracts)
    hits.append(
        SignalHit(
            signal_id="missing_official_identity",
            status="FIRED" if not has_id else "NOT_FIRED",
            confidence=0.9,
            weight=-0.3 if not has_id else 0.0,
            definition="Identidade oficial do órgão ausente.",
        )
    )

    # insufficient public evidence
    hits.append(
        SignalHit(
            signal_id="insufficient_public_evidence",
            status="FIRED" if len(contracts) == 0 else "NOT_FIRED",
            confidence=0.85,
            weight=-0.2 if not contracts else 0.0,
            evidence=[{"contract_count": len(contracts)}],
            definition="Sem evidência pública mínima de contratos.",
        )
    )

    # stale_data
    latest = None
    for c in contracts:
        d = _parse_date(c.get("data_publicacao") or c.get("data_inicio"))
        if d and (latest is None or d > latest):
            latest = d
    if latest is None:
        hits.append(
            SignalHit(
                signal_id="stale_data",
                status="NOT_COMPUTABLE",
                confidence=0.0,
                weight=-0.05,
                limitations=["no dated contracts"],
                definition="Dados obsoletos (>365 dias sem publicação).",
            )
        )
    else:
        stale = (as_of - latest).days > 365
        hits.append(
            SignalHit(
                signal_id="stale_data",
                status="FIRED" if stale else "NOT_FIRED",
                confidence=0.75,
                weight=-0.08 if stale else 0.0,
                evidence=[{"latest_date": latest.isoformat(), "age_days": (as_of - latest).days}],
                definition="Dados obsoletos (>365 dias sem publicação).",
            )
        )

    return hits


def material_need_signals(hits: list[SignalHit]) -> list[SignalHit]:
    """Signals that count as material need (not merely small municipality)."""
    material_ids = {
        "recurring_engineering_procurements",
        "high_engineering_spend_relative_to_population",
        "works_or_services_with_long_execution",
        "recent_publication_of_engineering_demand",
        "contract_execution_distress",
        "active_direct_contracting_notice",
        "failed_or_deserted_engineering_procurements",
        "cancelled_engineering_procurements",
        "recurrent_contract_amendments",
    }
    return [h for h in hits if h.signal_id in material_ids and h.status == "FIRED"]
