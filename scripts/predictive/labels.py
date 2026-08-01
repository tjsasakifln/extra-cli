"""Formal label definitions for predictive targets.

Labels use only events observable after as_of. Invalid negatives (absence
without coverage evidence) are rejected, never coerced to 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

LabelQuality = Literal["ok", "rejected_invalid_negative", "ambiguous", "data_blocked"]


@dataclass(frozen=True)
class LabelDefinition:
    target_name: str
    description: str
    unit: str
    positive_rule: str
    negative_rule: str
    requires_coverage_for_negative: bool
    horizon_days: int | None = None


LABEL_DEFINITIONS: dict[str, LabelDefinition] = {
    "demand_30d": LabelDefinition(
        target_name="demand_30d",
        description="Probability ente publishes AEC-relevant contracting within 30d",
        unit="ente × categoria_aec × horizonte × as_of_date",
        positive_rule=(
            "At least one AEC-classified contract/edital for the ente with "
            "event_at in (as_of, as_of+30d]"
        ),
        negative_rule=(
            "No AEC event in window AND coverage evidence that the source was "
            "queried for that ente/period (coverage flag or successful crawl window)"
        ),
        requires_coverage_for_negative=True,
        horizon_days=30,
    ),
    "demand_60d": LabelDefinition(
        target_name="demand_60d",
        description="Probability ente publishes AEC-relevant contracting within 60d",
        unit="ente × categoria_aec × horizonte × as_of_date",
        positive_rule="AEC event in (as_of, as_of+60d]",
        negative_rule="No AEC event + coverage evidence",
        requires_coverage_for_negative=True,
        horizon_days=60,
    ),
    "demand_90d": LabelDefinition(
        target_name="demand_90d",
        description="Probability ente publishes AEC-relevant contracting within 90d",
        unit="ente × categoria_aec × horizonte × as_of_date",
        positive_rule="AEC event in (as_of, as_of+90d]",
        negative_rule="No AEC event + coverage evidence",
        requires_coverage_for_negative=True,
        horizon_days=90,
    ),
    "competitive_winner_p2a": LabelDefinition(
        target_name="competitive_winner_p2a",
        description="Probability supplier is winner/adjudicatee among candidates",
        unit="procurement_outcome × supplier_candidate × as_of_before_result",
        positive_rule="Supplier is the observed winner/adjudicatee of the process",
        negative_rule=(
            "Supplier was in the pre-result candidate set and is not the winner. "
            "Suppliers absent from the candidate set are NOT negatives."
        ),
        requires_coverage_for_negative=False,
        horizon_days=None,
    ),
    "competitive_participation_p2b": LabelDefinition(
        target_name="competitive_participation_p2b",
        description="Probability supplier participates (requires participant lists)",
        unit="process × supplier × as_of_before_session",
        positive_rule="Supplier appears on real participant list (proposals/ata/homologação)",
        negative_rule=(
            "Process has complete participant documentation AND supplier not listed. "
            "Non-win alone is NOT non-participation."
        ),
        requires_coverage_for_negative=True,
        horizon_days=None,
    ),
    "winning_discount_p3": LabelDefinition(
        target_name="winning_discount_p3",
        description="Winning discount quantiles (requires estimated+outcome value join)",
        unit="process/item with auditável estimated→outcome value link",
        positive_rule="N/A (regression target)",
        negative_rule="N/A",
        requires_coverage_for_negative=False,
        horizon_days=None,
    ),
    "extra_win_probability_p4": LabelDefinition(
        target_name="extra_win_probability_p4",
        description="Conditional win probability for Extra given participation",
        unit="participant × opportunity",
        positive_rule="Participant is winner/adjudicatee",
        negative_rule="Participant observed and not winner (never universe negatives)",
        requires_coverage_for_negative=False,
        horizon_days=None,
    ),
}


# AEC keyword heuristic for civil engineering relevance (object text)
AEC_POSITIVE_TERMS = (
    "obra",
    "constru",
    "paviment",
    "edific",
    "reforma",
    "ampliacao",
    "ampliação",
    "drenagem",
    "terraplen",
    "saneamento",
    "urbaniz",
    "infraestrutura",
    "manutencao predial",
    "manutenção predial",
    "recuperacao estrutural",
    "recuperação estrutural",
    "engenharia civil",
    "alvenaria",
    "concreto",
    "asfalt",
    "galeria pluvial",
    "rede coletora",
)

AEC_NEGATIVE_TERMS = (
    "software",
    "licenca de uso",
    "licença de uso",
    "medicamento",
    "material de escritorio",
    "material de escritório",
    "combustivel",
    "combustível",
    "locacao de veiculos",
    "locação de veículos",
)


def is_aec_object(objeto: str | None) -> bool:
    if not objeto:
        return False
    text = objeto.casefold()
    if any(n in text for n in AEC_NEGATIVE_TERMS):
        # Still allow if strong positive construction terms dominate
        if not any(p in text for p in ("obra", "constru", "paviment", "edific")):
            return False
    return any(p in text for p in AEC_POSITIVE_TERMS)


def aec_category(objeto: str | None) -> str:
    if not objeto:
        return "outros_aec"
    t = objeto.casefold()
    mapping = [
        ("paviment", "pavimentacao"),
        ("drenagem", "drenagem"),
        ("terraplen", "terraplenagem"),
        ("saneamento", "saneamento"),
        ("esgoto", "saneamento"),
        ("reforma", "reformas"),
        ("amplia", "ampliacoes"),
        ("manuten", "manutencao_predial"),
        ("edific", "obras_edificacoes"),
        ("constru", "obras_edificacoes"),
        ("urbaniz", "infraestrutura_urbana"),
        ("infraestrutura", "infraestrutura_urbana"),
    ]
    for needle, cat in mapping:
        if needle in t:
            return cat
    return "outros_aec" if is_aec_object(objeto) else "non_aec"


@dataclass
class LabelResult:
    label_value: float | None
    label_quality: LabelQuality
    label_source: str
    reason: str


def demand_label(
    *,
    as_of: datetime,
    horizon_days: int,
    future_aec_events: list[datetime],
    coverage_ok: bool,
) -> LabelResult:
    """Build demand label for one ente×category×as_of."""
    window_end = as_of + timedelta(days=horizon_days)
    positives = [e for e in future_aec_events if as_of < e <= window_end]
    if positives:
        return LabelResult(
            label_value=1.0,
            label_quality="ok",
            label_source="observed_aec_event",
            reason=f"{len(positives)} AEC event(s) in ({as_of.isoformat()}, {window_end.isoformat()}]",
        )
    if not coverage_ok:
        return LabelResult(
            label_value=None,
            label_quality="rejected_invalid_negative",
            label_source="insufficient_coverage",
            reason="No event and no coverage evidence — cannot label as negative",
        )
    return LabelResult(
        label_value=0.0,
        label_quality="ok",
        label_source="coverage_confirmed_absence",
        reason=f"Coverage OK and no AEC event through {window_end.isoformat()}",
    )


def winner_label(
    *,
    supplier_id: str,
    winner_id: str,
    in_candidate_set: bool,
) -> LabelResult:
    if not in_candidate_set:
        return LabelResult(
            label_value=None,
            label_quality="rejected_invalid_negative",
            label_source="not_in_candidate_set",
            reason="Supplier not in pre-result candidate set — not a negative",
        )
    if supplier_id == winner_id:
        return LabelResult(
            label_value=1.0,
            label_quality="ok",
            label_source="observed_winner",
            reason="Supplier is winner",
        )
    return LabelResult(
        label_value=0.0,
        label_quality="ok",
        label_source="candidate_non_winner",
        reason="Candidate not winner",
    )


def participation_label(
    *,
    supplier_id: str,
    participant_ids: set[str] | None,
    documentation_complete: bool,
) -> LabelResult:
    if not documentation_complete or participant_ids is None:
        return LabelResult(
            label_value=None,
            label_quality="data_blocked",
            label_source="no_participant_list",
            reason="P2B requires real participant documentation",
        )
    if supplier_id in participant_ids:
        return LabelResult(
            label_value=1.0,
            label_quality="ok",
            label_source="participant_list",
            reason="On participant list",
        )
    return LabelResult(
        label_value=0.0,
        label_quality="ok",
        label_source="complete_list_absence",
        reason="Complete list and supplier not present",
    )


def winning_discount(
    *,
    estimated_value: float | None,
    outcome_value: float | None,
    estimated_value_semantics: str | None,
    outcome_value_semantics: str | None,
    same_process: bool,
) -> tuple[float | None, dict[str, Any]]:
    """Return discount fraction (estimated-outcome)/estimated or None if invalid."""
    meta: dict[str, Any] = {
        "estimated_value_semantics": estimated_value_semantics,
        "outcome_value_semantics": outcome_value_semantics,
        "same_process": same_process,
    }
    allowed_est = {"estimated", "valor_estimado", "budget_estimate"}
    allowed_out = {"adjudicated", "homologated", "contracted_initial", "valor_homologado"}
    forbidden_out = {"paid", "valor_pago", "executed", "additive"}

    if not same_process:
        meta["block"] = "process_mismatch"
        return None, meta
    if estimated_value is None or outcome_value is None:
        meta["block"] = "missing_value"
        return None, meta
    if estimated_value <= 0 or outcome_value <= 0:
        meta["block"] = "non_positive_value"
        return None, meta
    if (estimated_value_semantics or "") not in allowed_est:
        meta["block"] = "bad_estimated_semantics"
        return None, meta
    if (outcome_value_semantics or "") in forbidden_out:
        meta["block"] = "paid_value_forbidden"
        return None, meta
    if (outcome_value_semantics or "") not in allowed_out:
        meta["block"] = "bad_outcome_semantics"
        return None, meta
    discount = (estimated_value - outcome_value) / estimated_value
    # Sanity: discounts outside [-0.5, 0.8] are suspicious
    if discount < -0.5 or discount > 0.8:
        meta["block"] = "discount_out_of_range"
        meta["raw_discount"] = discount
        return None, meta
    meta["discount"] = discount
    return discount, meta
