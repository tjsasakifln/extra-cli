"""Service fit router — evidence + moment, not fixed score templates."""

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
        # unknown/mixed → conservative ABM framing (independent review / focal diagnosis)
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


def _mature_no_reajuste(contracts: list[dict[str, Any]]) -> bool:
    """True only when vigência start is known and mature — publication-only
    dates must not invent a reajuste window (PNCP often has only pub date)."""
    for c in contracts:
        age = c.get("age_days")
        # Require explicit start_date (not publication_date-only inference).
        if not c.get("start_date"):
            continue
        if age is not None and age >= MATURE_DAYS and not c.get("has_reajuste") and not c.get("reajuste_evidence"):
            return True
    return False


def _insufficient(bag: dict[str, Any]) -> bool:
    contracts = bag.get("contracts") or []
    facts = [f for f in (bag.get("facts") or []) if f.get("text")]
    return len(contracts) == 0 and len(facts) == 0


def select_services(
    bag: dict[str, Any],
    *,
    structure: dict[str, Any],
    why: dict[str, Any],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    """Ordered rules: concrete pain > structure framing > discovery.

    Robust/ABM never gets "full outsource / no structure" framing.
    Lean may get operational/outsourced only with supporting evidence.
    """
    contracts = bag.get("contracts") or []
    sc = str(structure.get("structure_class") or "unknown")
    discovery = discovery_service_id(catalog)
    idx = service_index(catalog)

    primary_id: str
    secondary_id: str | None
    rationale_parts: list[str] = []

    if _insufficient(bag):
        primary_id = discovery
        secondary_id = "inteligencia_pncp_mercado" if "inteligencia_pncp_mercado" in idx else None
        rationale_parts.append(
            "Fatos insuficientes no input: melhor encaixe é diagnóstico/descoberta, sem fabricar especialidade."
        )
    elif why.get("trigger") == "addendum" or _has_addendum(contracts):
        primary_id = "aditivos_extracontratuais"
        secondary_id = "gestao_monitoramento_contratual"
        rationale_parts.append("Dor contratual concreta de aditivos/alterações supera sinal genérico de portfólio.")
    elif why.get("trigger") == "glosa_medicao" or _has_glosa_med(contracts):
        primary_id = "medicoes_glosas_memoria"
        secondary_id = "gestao_monitoramento_contratual"
        rationale_parts.append("Sinais de glosa/medição no material público apontam serviço de medições.")
    elif why.get("trigger") == "reequilibrio" or _has_reequilibrio(contracts):
        primary_id = "reequilibrio_economico_financeiro"
        secondary_id = "estruturacao_pleito_reajuste"
        rationale_parts.append("Menção a reequilíbrio no material ingerido define o encaixe primário.")
    elif why.get("trigger") == "mature_no_reajuste" or _mature_no_reajuste(contracts):
        primary_id = "estruturacao_pleito_reajuste"
        secondary_id = "diagnostico_contratual_b2g"
        rationale_parts.append(
            "Contrato maduro sem prova de reajuste no input: ângulo de estruturação de pleito "
            "(ausência de prova não afirma que reajuste nunca ocorreu)."
        )
    elif sc == "robust" and len(contracts) >= 5:
        # National structured without specific pain → independent audit / second opinion
        primary_id = "auditoria_orcamento_bdi"
        secondary_id = "diagnostico_contratual_b2g"
        rationale_parts.append(
            "Conta com sinais de estrutura robusta/ABM: oferecer revisão independente / "
            "segunda opinião / auditoria específica — jamais presumir ausência de estrutura."
        )
    elif sc == "lean" and len(contracts) > 0 and len(structure.get("lean_signals") or []) >= 2:
        # Lean with load evidence → operational reinforcement
        primary_id = "reforco_temporario_backoffice"
        secondary_id = "gestao_monitoramento_contratual"
        rationale_parts.append(
            "Hipótese de estrutura enxuta com carga contratual observada: reforço temporário "
            "de backoffice só porque evidências regionais/de volume sustentam — não por score fixo."
        )
    elif len(contracts) >= 3:
        primary_id = "gestao_monitoramento_contratual"
        secondary_id = discovery
        rationale_parts.append("Portfólio multi-contrato sem dor concreta dominante: monitoramento/gestão contratual.")
    else:
        primary_id = discovery
        secondary_id = "apoio_licitacoes_propostas"
        rationale_parts.append("Melhor ângulo atual é diagnóstico contratual B2G / discovery.")

    # Safety: never invent service outside catalog
    if primary_id not in idx:
        primary_id = discovery
        rationale_parts.append("Serviço primário ajustado para discovery (catálogo).")
    if secondary_id is not None and secondary_id not in idx:
        secondary_id = None

    # Robust accounts: rewrite approach if someone tried full outsource framing
    primary = _svc_ref(primary_id, sc, catalog)
    secondary = _svc_ref(secondary_id, sc, catalog) if secondary_id else None

    if sc == "robust" and primary_id == "reforco_temporario_backoffice":
        # Policy: robust never gets lean outsource as primary
        primary = _svc_ref("auditoria_orcamento_bdi", sc, catalog)
        secondary = _svc_ref(discovery, sc, catalog)
        rationale_parts.append("Override de política: conta robusta não recebe outsourcing pleno como primário.")

    if sc in {"robust", "mixed", "unknown"} and primary.get("approach_mode") == "outsourcing_operacional_temporario":
        primary = dict(primary)
        primary["approach_mode"] = "revisao_independente_segunda_opiniao"

    return {
        "primary_service": primary,
        "secondary_service": secondary,
        "service_fit_rationale": " ".join(rationale_parts),
    }
