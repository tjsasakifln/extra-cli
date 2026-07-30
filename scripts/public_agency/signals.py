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


# False-positive labor phrases that contain "OBRA" but are not engineering works.
_NON_ENGINEERING_OBRA_PHRASES: tuple[str, ...] = (
    "MAO DE OBRA",
    "MAO-DE-OBRA",
    "MAOS DE OBRA",
    "MAOS-DE-OBRA",
    "HORA HOMEM",
    "HORAS HOMEM",
)

# Strong engineering phrases (substring OK after folding).
_STRONG_ENGINEERING_PHRASES: tuple[str, ...] = (
    "OBRA DE ",
    "OBRAS DE ",
    "OBRA PUBLICA",
    "OBRAS PUBLICAS",
    "SERVICO DE ENGENHAR",
    "SERVICOS DE ENGENHAR",
    "SERVICOS TECNICOS DE ENGENHAR",
    "PROJETO BASICO",
    "PROJETO EXECUTIVO",
    "PAVIMENTACAO",
    "PAVIMENTAC",
    "TERRAPLENAGEM",
    "SANEAMENTO",
    "DRENAGEM",
    "FISCALIZACAO DE OBRA",
    "FISCALIZACAO DE OBRAS",
    "ACOMPANHAMENTO DE OBRA",
    "ORCAMENTO DE OBRA",
    "ORCAMENTO DE OBRAS",
    "MEMORIAL DESCRITIVO",
    "PLANILHA ORCAMENT",
    "ENGENHARIA CIVIL",
    "ENGENHARIA ELETRICA",
    "ENGENHARIA MECANICA",
    "INFRAESTRUTURA URBANA",
    "INFRAESTRUTURA VIARIA",
    "CONSTRUCAO CIVIL",
    "CONSTRUCAO DE ",
    "REFORMA DE EDIFIC",
    "REFORMA DE PREDIO",
    "REFORMA DE ESCOLA",
    "REFORMA DE UBS",
    "REFORMA DE UNIDADE",
    "EDIFICACAO",
    "EDIFICIO",
    "PONTE ",
    "VIADUTO",
    "BARRAGEM",
    "GALERIA DE AGUAS",
    "REDE DE ESGOTO",
    "REDE DE AGUA",
    "ESTACAO DE TRATAMENTO",
)

# Word-boundary tokens that alone are insufficient without context.
_WEAK_ENG_TOKENS_REQUIRING_CONTEXT: tuple[str, ...] = (
    "OBRA",
    "OBRAS",
    "REFORMA",
    "REFORMAS",
    "PROJETO",
    "PROJETOS",
    "CONSTRUCAO",
    "MANUTENCAO",
)


def _has_word(blob: str, token: str) -> bool:
    """Whole-word match for short tokens (avoids 'obra' inside other words wrongly)."""
    return re.search(rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])", blob) is not None


def is_engineering_object(obj: str | None, eng_keywords: list[str] | None = None) -> bool:
    """True only for objects that are works/engineering services — not 'mão de obra'.

    Rules (fail-closed toward NOT engineering):
    1. Empty → False
    2. If text is only labor/mão-de-obra (and no strong eng phrase) → False
    3. Strong engineering phrases → True
    4. Profile eng_keywords as whole-phrase/substring when length >= 5
    5. Bare token OBRA alone is NOT enough; 'OBRA DE X' / eng context required
    6. MATERIAIS DE CONSTRUCAO / fornecimento alone → False unless paired with obra/projeto
    """
    blob = _fold(obj)
    if not blob:
        return False

    # Strip pure labor phrasing for residual checks
    labor_only = any(p in blob for p in _NON_ENGINEERING_OBRA_PHRASES)
    strong_hit = any(p in blob for p in _STRONG_ENGINEERING_PHRASES)

    if strong_hit:
        return True

    # Explicit non-engineering commerce of materials without design/execution of works
    materials_only = any(
        p in blob
        for p in (
            "MATERIAIS DE CONSTRUCAO",
            "MATERIAL DE CONSTRUCAO",
            "FORNECIMENTO DE MATERIAIS",
            "AQUISICAO DE MATERIAIS",
            "COMPRA DE MATERIAIS",
            "MATERIAIS ELETRICOS",
            "MATERIAIS HIDRAULICOS",
        )
    )
    if materials_only and not strong_hit:
        # Allow only if clear execution of works is also stated
        if not re.search(r"\b(EXECUCAO DE OBRA|EXECUCAO DE OBRAS|CONSTRUCAO DE |REFORMA DE )\b", blob):
            return False

    # Hair/makeup/pageant etc. with incidental words
    if any(
        p in blob
        for p in (
            "CABELO",
            "MAQUIAGEM",
            "BELEZA",
            "ESTETICA",
            "CONCURSO DE BELEZA",
            "MISS ",
            "ALUGUEL DE",
            "LOCACAO DE VEICULO",
            "COMBUSTIVEL",
            "GENERO ALIMENTICIO",
            "MEDICAMENTO",
            "UNIFORME",
            "MATERIAL DE EXPEDIENTE",
            "PNEU",
            "PNEUS",
        )
    ) and not strong_hit:
        return False

    if labor_only and not strong_hit:
        # "Contratação de mão de obra temporária" without obra pública → not engineering
        if not re.search(r"\b(OBRA DE|OBRAS DE|OBRA PUBLICA|ENGENHAR)\b", blob):
            return False

    # Profile keywords (prefer longer phrases)
    for kw in eng_keywords or []:
        fk = _fold(kw)
        if not fk:
            continue
        if len(fk) >= 6 and fk in blob:
            # Skip if the only match is inside "MAO DE OBRA"
            if fk == "OBRA" or fk in _WEAK_ENG_TOKENS_REQUIRING_CONTEXT:
                continue
            if fk in ("OBRA",) or (fk == "OBRA" or "OBRA" == fk):
                continue
            # mão de obra contains obra as word — already handled
            if labor_only and fk in ("OBRA", "OBRAS", "REFORMA"):
                continue
            return True
        if len(fk) >= 8 and fk in blob:
            return True

    # Word-boundary engineering terms with required context
    if _has_word(blob, "ENGENHARIA") or "ENGENHAR" in blob:
        return True
    if any(
        _has_word(blob, t)
        for t in ("PAVIMENTACAO", "TERRAPLENAGEM", "SANEAMENTO", "DRENAGEM", "TERRAPLENAGEM")
    ):
        return True
    # "OBRA DE …" already in strong phrases; bare OBRA alone is False
    if re.search(r"\bOBRAS?\s+DE\s+\w", blob):
        return True
    if re.search(r"\bREFORMA\s+DE\s+\w", blob):
        return True
    if re.search(r"\bCONSTRUCAO\s+DE\s+\w", blob):
        return True

    return False


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
    eng_kws = eng_keywords or ["obra", "engenharia", "pavimentacao", "reforma", "saneamento"]
    hits: list[SignalHit] = []
    start = as_of - timedelta(days=window_days)

    eng_contracts = []
    for c in contracts:
        if _is_engineering_object(str(c.get("objeto_contrato") or ""), eng_kws):
            eng_contracts.append(c)

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
