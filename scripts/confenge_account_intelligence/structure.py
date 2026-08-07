"""Internal structure hypothesis — never asserted as fact without source."""

from __future__ import annotations

from typing import Any


def build_structure_hypothesis(bag: dict[str, Any]) -> dict[str, Any]:
    """Classify robust / lean / mixed / unknown from public signals only.

    Rules:
    - Absence of robust signals is NOT proof of lean structure.
    - assertion_as_fact is always False.
    """
    signals = bag.get("signals") or {}
    contracts = bag.get("contracts") or []
    ufs = {str(c.get("uf")).upper() for c in contracts if c.get("uf")}

    robust_signals: list[str] = []
    lean_signals: list[str] = []

    if signals.get("national_operation"):
        robust_signals.append("national_operation_signal")
    if len(ufs) >= 3:
        robust_signals.append(f"multi_uf_portfolio:{len(ufs)}_ufs")
    if signals.get("consortium_participation"):
        robust_signals.append("consortium_participation_signal")
    if signals.get("legal_claims_compliance_unit"):
        robust_signals.append("legal_claims_compliance_unit_signal")
    if signals.get("large_team_public_signal"):
        robust_signals.append("large_team_public_signal")
    if signals.get("high_recurrence") or len(contracts) >= 8:
        robust_signals.append("high_recurrence_or_large_portfolio")

    if signals.get("regional_only"):
        lean_signals.append("regional_only_signal")
    elif len(ufs) == 1 and len(contracts) > 0:
        lean_signals.append("single_uf_in_observed_portfolio")
    if signals.get("rapid_growth"):
        lean_signals.append("rapid_growth_signal")
    if signals.get("concentrated_functions"):
        lean_signals.append("concentrated_functions_signal")
    if signals.get("low_public_formalization"):
        lean_signals.append("low_public_formalization_signal")
    if 0 < len(contracts) <= 3 and len(ufs) <= 1:
        lean_signals.append("few_contracts_regional_footprint")

    n_rob = len(robust_signals)
    n_lean = len(lean_signals)

    if n_rob == 0 and n_lean == 0:
        structure_class = "unknown"
        confidence = 0.15
        notes = (
            "Sem sinais públicos suficientes para classificar estrutura interna. "
            "Ausência de informação não prova estrutura enxuta nem robusta."
        )
    elif n_rob >= 2 and n_rob > n_lean:
        structure_class = "robust"
        confidence = min(0.85, 0.45 + 0.1 * n_rob)
        notes = (
            "Hipótese de estrutura robusta a partir de sinais públicos (ABM). "
            "Não afirmar organograma ou capacidade interna como fato."
        )
    elif n_lean >= 2 and n_lean > n_rob and n_rob == 0:
        # Only lean when multiple lean signals AND zero robust — still low confidence
        structure_class = "lean"
        confidence = min(0.55, 0.25 + 0.08 * n_lean)
        notes = (
            "Hipótese de estrutura enxuta com base em sinais fracos/regionais. "
            "Nunca usar ausência de dado como prova de ausência de estrutura."
        )
    elif n_rob > 0 and n_lean > 0:
        structure_class = "mixed"
        confidence = 0.4
        notes = "Sinais mistos de robustez e enxutez; tratar como ABM conservador."
    elif n_rob > 0:
        structure_class = "robust"
        confidence = min(0.7, 0.4 + 0.1 * n_rob)
        notes = "Poucos sinais robustos públicos; hipótese provisória de conta estruturada."
    else:
        structure_class = "lean"
        confidence = 0.3
        notes = (
            "Sinais leves de operação regional/enxuta. "
            "Oferta outsourced só se evidência de carga sustentar."
        )

    return {
        "structure_class": structure_class,
        "confidence": round(confidence, 3),
        "robust_signals": robust_signals,
        "lean_signals": lean_signals,
        "assertion_as_fact": False,
        "notes": notes,
    }
