"""Service fit router — evidence + moment, not fixed score templates.

Ordering principle:
  concrete pain/event >
  documentary event >
  operational need >
  reajuste verification window >
  diagnóstico genérico

`reajuste` is NEVER the default.
`diagnóstico` is the commercial fallback when no specialty is sustained.
"""

from __future__ import annotations

from typing import Any

from scripts.confenge_account_intelligence.catalog import (
    catalog_version,
    discovery_service_id,
    service_index,
)
from scripts.confenge_account_intelligence.facts import MATURE_DAYS


def _svc_ref(service_id: str, structure_class: str, catalog: dict[str, Any]) -> dict[str, Any]:
    idx = service_index(catalog)
    svc = idx.get(service_id) or {}
    modes = svc.get("approach_modes") or {}
    if structure_class == "robust":
        mode = modes.get("robust") or "revisao_independente_segunda_opiniao"
    elif structure_class == "lean":
        mode = modes.get("lean") or modes.get("robust") or "apoio_operacional"
    else:
        mode = modes.get("robust") or modes.get("lean") or "diagnostico_focal"
    return {
        "service_id": service_id,
        "label": str(svc.get("label") or service_id),
        "family": str(svc.get("family") or "unknown"),
        "approach_mode": str(mode),
        "catalog_version": catalog_version(catalog),
    }


def _has_addendum(contracts: list[dict[str, Any]]) -> bool:
    return any(c.get("has_addendum") or (c.get("addendum_count") or 0) > 0 for c in contracts)


def _has_glosa_med(contracts: list[dict[str, Any]]) -> bool:
    return any(c.get("glosa_signals") or c.get("measurement_issues") for c in contracts)


def _has_reequilibrio(contracts: list[dict[str, Any]]) -> bool:
    return any(c.get("reequilibrio_mention") for c in contracts)


def _has_budget_bdi(contracts: list[dict[str, Any]], bag: dict[str, Any]) -> bool:
    if bag.get("signals", {}).get("budget_audit_need") or bag.get("signals", {}).get("bdi_signal"):
        return True
    for c in contracts:
        if c.get("budget_or_bdi_signal") or c.get("planilha_signal"):
            return True
        obj = str(c.get("object") or c.get("objeto") or "").lower()
        if any(tok in obj for tok in ("bdi", "planilha orcament", "planilha orçament", "composicao de custo")):
            return True
    return False


def _has_tender_signal(contracts: list[dict[str, Any]], bag: dict[str, Any]) -> bool:
    if bag.get("signals", {}).get("recent_tender_activity") or bag.get("signals", {}).get("proposal_window"):
        return True
    for c in contracts:
        if c.get("tender_or_proposal_signal"):
            return True
        obj = str(c.get("object") or "").lower()
        if any(tok in obj for tok in ("edital", "proposta comercial", "licitacao", "licitação")):
            return True
    return False


def _mature_no_reajuste(contracts: list[dict[str, Any]]) -> bool:
    """True only when vigência start is known and mature — publication-only
    dates must not invent a reajuste window (PNCP often has only pub date).

    This is a VERIFICATION window hypothesis, not proof of economic right.
    It must not defeat stronger concrete pain signals (caller order enforces).
    """
    for c in contracts:
        age = c.get("age_days")
        if not c.get("start_date"):
            continue
        if age is not None and age >= MATURE_DAYS and not c.get("has_reajuste") and not c.get("reajuste_evidence"):
            return True
    return False


def _insufficient(bag: dict[str, Any]) -> bool:
    contracts = bag.get("contracts") or []
    facts = [f for f in (bag.get("facts") or []) if f.get("text")]
    return len(contracts) == 0 and len(facts) == 0


def _candidate(
    service_id: str,
    *,
    score: float,
    factual_basis: str,
    temporal_relevance: str,
    confidence: float,
    supporting_signal_ids: list[str],
    evidence_ids: list[str],
    why_this: str,
    why_not_others: str,
    contraindications: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "service_id": service_id,
        "score": score,
        "supporting_signal_ids": supporting_signal_ids,
        "evidence_ids": evidence_ids,
        "factual_basis": factual_basis,
        "temporal_relevance": temporal_relevance,
        "confidence": confidence,
        "contraindications": list(contraindications or []),
        "why_this_service": why_this,
        "why_not_other_services": why_not_others,
    }


def build_service_candidates(
    bag: dict[str, Any],
    *,
    structure: dict[str, Any],
    why: dict[str, Any],
    catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    """Rank service candidates from evidence. Higher score = better fit."""
    contracts = bag.get("contracts") or []
    sc = str(structure.get("structure_class") or "unknown")
    discovery = discovery_service_id(catalog)
    idx = service_index(catalog)
    trigger = str(why.get("trigger") or "")
    candidates: list[dict[str, Any]] = []

    # Evidence IDs from contracts
    ev_ids = [str(c.get("id")) for c in contracts if c.get("id")][:10]

    if _insufficient(bag):
        candidates.append(
            _candidate(
                discovery,
                score=100,
                factual_basis="no_contracts_no_facts",
                temporal_relevance="none",
                confidence=0.9,
                supporting_signal_ids=["insufficient_facts"],
                evidence_ids=[],
                why_this="Fatos insuficientes: diagnóstico/descoberta sem fabricar especialidade.",
                why_not_others="Sem dor concreta sustentada, reajuste/aditivo/glosa seriam invenção.",
            )
        )
        if "inteligencia_pncp_mercado" in idx:
            candidates.append(
                _candidate(
                    "inteligencia_pncp_mercado",
                    score=40,
                    factual_basis="empty_portfolio_market_scan",
                    temporal_relevance="low",
                    confidence=0.4,
                    supporting_signal_ids=["insufficient_facts"],
                    evidence_ids=[],
                    why_this="Secundário de inteligência de mercado na ausência de dossiê.",
                    why_not_others="Primário permanece diagnóstico.",
                )
            )
        return candidates

    # Concrete pain — highest priority
    if trigger == "addendum" or _has_addendum(contracts):
        candidates.append(
            _candidate(
                "aditivos_extracontratuais",
                score=95,
                factual_basis="addendum_signal_in_public_record",
                temporal_relevance="high",
                confidence=0.85,
                supporting_signal_ids=["addendum"],
                evidence_ids=ev_ids,
                why_this="Dor contratual concreta de aditivos/alterações.",
                why_not_others="Supera reajuste genérico e portfólio sem evento.",
            )
        )
    if trigger == "glosa_medicao" or _has_glosa_med(contracts):
        candidates.append(
            _candidate(
                "medicoes_glosas_memoria",
                score=94,
                factual_basis="glosa_or_measurement_signal",
                temporal_relevance="high",
                confidence=0.85,
                supporting_signal_ids=["glosa_medicao"],
                evidence_ids=ev_ids,
                why_this="Sinais de glosa/medição no material público.",
                why_not_others="Evento documental específico supera janela de reajuste.",
            )
        )
    if trigger == "reequilibrio" or _has_reequilibrio(contracts):
        candidates.append(
            _candidate(
                "reequilibrio_economico_financeiro",
                score=93,
                factual_basis="reequilibrio_mention",
                temporal_relevance="high",
                confidence=0.8,
                supporting_signal_ids=["reequilibrio"],
                evidence_ids=ev_ids,
                why_this="Menção a reequilíbrio no material ingerido.",
                why_not_others="Não reduzir a reajuste ordinário sem nexo.",
            )
        )
    if _has_budget_bdi(contracts, bag):
        candidates.append(
            _candidate(
                "auditoria_orcamento_bdi",
                score=80,
                factual_basis="budget_bdi_planilha_signal",
                temporal_relevance="medium",
                confidence=0.7,
                supporting_signal_ids=["budget_bdi"],
                evidence_ids=ev_ids,
                why_this="Sinais de orçamento/BDI/planilha no material.",
                why_not_others="Especialidade documental de planilha, não reajuste default.",
            )
        )
    if _has_tender_signal(contracts, bag):
        candidates.append(
            _candidate(
                "apoio_licitacoes_propostas",
                score=78,
                factual_basis="tender_or_proposal_signal",
                temporal_relevance="medium",
                confidence=0.65,
                supporting_signal_ids=["tender_proposal"],
                evidence_ids=ev_ids,
                why_this="Atividade de licitação/proposta observada.",
                why_not_others="Janela competitiva, não reajuste.",
            )
        )

    # Operational / structure-based (FASE7).
    # Structure proxies open ONLY gestão or diagnóstico — never invent specialty
    # (auditoria/BDI/planilha) without specialty signals (_has_budget_bdi above).
    # Lean backoffice: operational only with multi-contract load (≥3).
    if (
        sc == "lean"
        and len(contracts) >= 3
        and len(structure.get("lean_signals") or []) >= 2
    ):
        candidates.append(
            _candidate(
                "reforco_temporario_backoffice",
                score=62,
                factual_basis="lean_structure_with_load",
                temporal_relevance="medium",
                confidence=0.5,
                supporting_signal_ids=["structure_lean", "multi_contract"],
                evidence_ids=ev_ids,
                why_this="Hipótese de estrutura enxuta com carga multi-contrato sustentada.",
                why_not_others="Não inferir 'sem estrutura' por ausência de dados públicos.",
            )
        )
    if len(contracts) >= 3:
        # Lean multi-contract: backoffice (62) is the operational primary; gestão secondary.
        # Robust multi (≥5) elevates gestão (72) above mature reajuste verify (48) without
        # inventing BDI specialty.
        if sc == "lean":
            gestao_score = 55.0
            gestao_signals = ["multi_contract"]
        elif sc == "robust" and len(contracts) >= 5:
            gestao_score = 72.0
            gestao_signals = ["structure_robust", "multi_contract"]
        else:
            gestao_score = 65.0
            gestao_signals = ["multi_contract"]
        candidates.append(
            _candidate(
                "gestao_monitoramento_contratual",
                score=gestao_score,
                factual_basis="multi_contract_portfolio",
                temporal_relevance="medium",
                confidence=0.6,
                supporting_signal_ids=gestao_signals,
                evidence_ids=ev_ids,
                why_this=(
                    "Portfólio multi-contrato sem dor concreta dominante "
                    "(gestão/monitoramento — especialidade só com sinais específicos)."
                ),
                why_not_others=(
                    "Monitoramento/gestão supera janela de verificação de reajuste; "
                    "não inventar orçamento/BDI sem sinal de planilha."
                ),
            )
        )

    # Reajuste verification window (FASE7):
    # concrete pain > documentary > operational (multi-contract) > reajuste verify > discovery
    # Multi-contract (≥3): 48 < gestão 65 / robust 72 / lean-backoffice 62
    # Thin mature book (1–2): 60 so verification beats discovery; not competing with gestão
    if trigger == "mature_no_reajuste" or _mature_no_reajuste(contracts):
        mature_score = 48.0 if len(contracts) >= 3 else 60.0
        candidates.append(
            _candidate(
                "estruturacao_pleito_reajuste",
                score=mature_score,
                factual_basis="mature_contract_without_reajuste_proof",
                temporal_relevance="medium",
                confidence=0.55,
                supporting_signal_ids=["mature_no_reajuste"],
                evidence_ids=ev_ids,
                why_this=(
                    "Contrato maduro com start_date conhecido sem prova de reajuste no input: "
                    "janela de VERIFICAÇÃO (ausência de prova ≠ evento econômico)."
                ),
                why_not_others=(
                    "Em carteira multi-contrato, gestão/orçamento operacional vencem; "
                    "em livro fino maduro, a verificação de reajuste supera discovery."
                ),
                contraindications=[
                    "publication_date_only_must_not_invent_window",
                    "must_not_defeat_multi_contract_operational_need",
                ],
            )
        )

    # Always keep diagnóstico as low-score fallback candidate
    candidates.append(
        _candidate(
            discovery,
            score=20,
            factual_basis="fallback_diagnosis",
            temporal_relevance="none",
            confidence=0.5,
            supporting_signal_ids=["fallback"],
            evidence_ids=ev_ids[:3],
            why_this="Fallback comercial correto quando especialidade não é sustentada.",
            why_not_others="Reajuste jamais é default.",
        )
    )

    # Drop unknown catalog ids
    candidates = [c for c in candidates if c["service_id"] in idx]
    candidates.sort(key=lambda c: (-float(c["score"]), c["service_id"]))
    return candidates


def select_services(
    bag: dict[str, Any],
    *,
    structure: dict[str, Any],
    why: dict[str, Any],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    """Select primary/secondary from ranked candidates. Reajuste never default."""
    sc = str(structure.get("structure_class") or "unknown")
    discovery = discovery_service_id(catalog)
    idx = service_index(catalog)

    candidates = build_service_candidates(bag, structure=structure, why=why, catalog=catalog)
    if not candidates:
        primary_id = discovery
        secondary_id = None
        rationale_parts = ["Sem candidatos: diagnóstico."]
    else:
        primary_id = str(candidates[0]["service_id"])
        secondary_id = str(candidates[1]["service_id"]) if len(candidates) > 1 else None
        if secondary_id == primary_id:
            secondary_id = str(candidates[2]["service_id"]) if len(candidates) > 2 else None
        rationale_parts = [str(candidates[0].get("why_this_service") or "")]
        if candidates[0].get("why_not_other_services"):
            rationale_parts.append(str(candidates[0]["why_not_other_services"]))

    # Safety: never invent service outside catalog
    if primary_id not in idx:
        primary_id = discovery
        rationale_parts.append("Serviço primário ajustado para discovery (catálogo).")
    if secondary_id is not None and secondary_id not in idx:
        secondary_id = None

    primary = _svc_ref(primary_id, sc, catalog)
    secondary = _svc_ref(secondary_id, sc, catalog) if secondary_id else None

    # Robust never gets full-outsource backoffice as primary — demote to gestão
    # (not invented BDI specialty without budget signals).
    if sc == "robust" and primary_id == "reforco_temporario_backoffice":
        primary_id = "gestao_monitoramento_contratual"
        primary = _svc_ref(primary_id, sc, catalog)
        secondary = _svc_ref(discovery, sc, catalog)
        rationale_parts.append(
            "Override de política: conta robusta não recebe outsourcing pleno como primário "
            "(gestão/monitoramento; especialidade BDI só com sinal de planilha)."
        )

    if sc in {"robust", "mixed", "unknown"} and primary.get("approach_mode") == "outsourcing_operacional_temporario":
        primary = dict(primary)
        primary["approach_mode"] = "revisao_independente_segunda_opiniao"

    # Propagate router evidence onto primary for SERVICE_FIT_SUPPORTED consumers.
    primary = dict(primary)
    win = next((c for c in candidates if c.get("service_id") == primary.get("service_id")), None)
    if win:
        primary["supporting_signal_ids"] = list(win.get("supporting_signal_ids") or [])
        primary["evidence_ids"] = list(win.get("evidence_ids") or [])
        primary["factual_basis"] = win.get("factual_basis")
        primary["confidence"] = win.get("confidence")
    else:
        primary.setdefault("supporting_signal_ids", ["fallback"] if primary_id == discovery else [])
        primary.setdefault("evidence_ids", [])

    if secondary:
        secondary = dict(secondary)
        sec = next((c for c in candidates if c.get("service_id") == secondary.get("service_id")), None)
        if sec:
            secondary["supporting_signal_ids"] = list(sec.get("supporting_signal_ids") or [])
            secondary["evidence_ids"] = list(sec.get("evidence_ids") or [])

    return {
        "primary_service": primary,
        "secondary_service": secondary,
        "service_fit_rationale": " ".join(p for p in rationale_parts if p),
        "service_candidates": candidates,
    }
