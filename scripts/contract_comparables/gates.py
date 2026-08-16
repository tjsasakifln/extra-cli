"""Fail-closed matching gates. No LLM, no embeddings, no reputation ranking."""

from __future__ import annotations

from scripts.contract_comparables.constants import (
    HARD_REFUSAL_REASONS,
    HOLD_REASONS,
    MAX_YEAR_DELTA_COMPARABLE,
    MAX_YEAR_DELTA_HOLD,
    MIN_COVERAGE_COMPARABLE,
    MIN_COVERAGE_HOLD,
    MIN_TYPOLOGY_CONFIDENCE,
    MIN_USABLE_N_COMPARABLE,
    MIN_USABLE_N_HOLD,
    REASON_AMBIGUOUS_TYPOLOGY,
    REASON_DISTINCT_SCOPE,
    REASON_DUPLICATE_OR_RECTIFICATION,
    REASON_EMBEDDING_NOT_AUTHORITY,
    REASON_FIELDS_UNAVAILABLE,
    REASON_GEOGRAPHY_NOT_COMPARABLE,
    REASON_INCOMPATIBLE_REGIME,
    REASON_INCOMPATIBLE_UNIT,
    REASON_INSUFFICIENT_COVERAGE,
    REASON_INSUFFICIENT_N,
    REASON_LIVE_COLUMNS,
    REASON_MISSING_VALUE,
    REASON_ORIGINAL_VS_UPDATED_MIX,
    REASON_PERIOD_NOT_COMPARABLE,
    REASON_PHYSICAL_UNIT,
    REASON_PORTE_NOT_COMPARABLE,
    REASON_TARGET_NOT_FOUND,
    REASON_TEXT_SIMILARITY_ONLY,
    REASON_TYPOLOGY_MISMATCH,
    REASON_UNIT_UNKNOWN,
    REASON_UNKNOWN_EXCLUDED,
    REASON_VALUE_SEMANTIC_MISMATCH,
    STATUS_COMPARABLE,
    STATUS_HOLD,
    STATUS_NOT,
    UNIT_CANONICAL,
    VALUE_SEMANTIC_CANONICAL,
)
from scripts.contract_comparables.models import Exclusion, PeerRequest, Recorte, SelectedPeer


def match_distance(focal: Recorte, peer: Recorte) -> float:
    distance = 0.0
    if focal.year is not None and peer.year is not None and focal.year != peer.year:
        distance += abs(focal.year - peer.year) * 0.25
    if (
        focal.contract.municipio
        and peer.contract.municipio
        and fold_eq(focal.contract.municipio, peer.contract.municipio) is False
    ):
        distance += 0.10
    if focal.porte != peer.porte and "unknown" not in {focal.porte, peer.porte}:
        distance += 0.15
    if focal.modalidade != peer.modalidade and "unknown" not in {focal.modalidade, peer.modalidade}:
        distance += 0.05
    return round(distance, 4)


def fold_eq(left: str, right: str) -> bool:
    from scripts.contract_comparables.normalize import fold_text

    return fold_text(left) == fold_text(right)


def quality_from_distance(distance: float) -> str:
    if distance == 0:
        return "exact_stratum"
    if distance <= 0.25:
        return "near_stratum"
    return "weak_stratum"


def peer_dimension_reasons(focal: Recorte, peer: Recorte) -> tuple[str, ...]:
    reasons: list[str] = []
    if peer.typology != "pavimentacao" or peer.typology_confidence < MIN_TYPOLOGY_CONFIDENCE:
        if peer.typology in {"ambiguo", "desconhecido"}:
            reasons.append(REASON_AMBIGUOUS_TYPOLOGY)
        else:
            reasons.append(REASON_TYPOLOGY_MISMATCH)
    if peer.scope == "mixed_paving_and_building" or (
        peer.scope != focal.scope and peer.typology == "pavimentacao" and peer.scope != "paving_works"
    ):
        reasons.append(REASON_DISTINCT_SCOPE)
    if peer.unit != UNIT_CANONICAL or focal.unit != UNIT_CANONICAL:
        if peer.unit == "unknown" or focal.unit == "unknown":
            reasons.append(REASON_UNIT_UNKNOWN)
        else:
            reasons.append(REASON_INCOMPATIBLE_UNIT)
    if peer.regime != focal.regime or peer.regime == "unknown" or focal.regime == "unknown":
        if peer.regime == "unknown" or focal.regime == "unknown":
            reasons.append(REASON_FIELDS_UNAVAILABLE)
        elif peer.regime != focal.regime:
            reasons.append(REASON_INCOMPATIBLE_REGIME)
    if focal.uf and peer.uf:
        if focal.uf != peer.uf:
            if focal.region and peer.region and focal.region == peer.region:
                reasons.append(REASON_GEOGRAPHY_NOT_COMPARABLE)
            else:
                reasons.append(REASON_GEOGRAPHY_NOT_COMPARABLE)
    elif not peer.uf or not focal.uf:
        reasons.append(REASON_GEOGRAPHY_NOT_COMPARABLE)
    if focal.year is None or peer.year is None:
        reasons.append(REASON_PERIOD_NOT_COMPARABLE)
    else:
        delta = abs(focal.year - peer.year)
        if delta > MAX_YEAR_DELTA_HOLD:
            reasons.append(REASON_PERIOD_NOT_COMPARABLE)
        elif delta > MAX_YEAR_DELTA_COMPARABLE:
            reasons.append(REASON_PERIOD_NOT_COMPARABLE)
    if peer.value_semantic != VALUE_SEMANTIC_CANONICAL or focal.value_semantic != VALUE_SEMANTIC_CANONICAL:
        reasons.append(REASON_VALUE_SEMANTIC_MISMATCH)
    if {focal.value_basis, peer.value_basis} == {"original", "atualizado"}:
        reasons.append(REASON_ORIGINAL_VS_UPDATED_MIX)
    if {focal.porte, peer.porte} == {"pequeno", "grande"}:
        reasons.append(REASON_PORTE_NOT_COMPARABLE)
    return tuple(dict.fromkeys(reasons))


def focal_gate_reasons(focal: Recorte, request: PeerRequest) -> tuple[str, ...]:
    reasons: list[str] = []
    if request.allow_text_similarity_authority:
        reasons.append(REASON_TEXT_SIMILARITY_ONLY)
    if request.allow_embeddings:
        reasons.append(REASON_EMBEDDING_NOT_AUTHORITY)
    if not request.live_semantic_columns_present:
        reasons.append(REASON_LIVE_COLUMNS)
        reasons.append(REASON_FIELDS_UNAVAILABLE)
    if request.allow_physical_unit_price:
        reasons.append(REASON_PHYSICAL_UNIT)
    if focal.typology != "pavimentacao":
        if focal.typology in {"ambiguo", "desconhecido"}:
            reasons.append(REASON_AMBIGUOUS_TYPOLOGY)
        else:
            reasons.append(REASON_TYPOLOGY_MISMATCH)
    elif focal.typology_confidence < MIN_TYPOLOGY_CONFIDENCE:
        reasons.append(REASON_AMBIGUOUS_TYPOLOGY)
    if focal.unit != UNIT_CANONICAL:
        reasons.append(REASON_INCOMPATIBLE_UNIT if focal.unit != "unknown" else REASON_UNIT_UNKNOWN)
    if focal.regime == "unknown":
        reasons.append(REASON_FIELDS_UNAVAILABLE)
    if focal.value_semantic != VALUE_SEMANTIC_CANONICAL:
        reasons.append(REASON_VALUE_SEMANTIC_MISMATCH)
    if focal.contract.valor_is_unknown or focal.contract.valor is None:
        reasons.append(REASON_MISSING_VALUE)
    if focal.uf is None or focal.year is None:
        reasons.append(REASON_FIELDS_UNAVAILABLE)
    return tuple(dict.fromkeys(reasons))


def decide_status(
    *,
    focal_reasons: tuple[str, ...],
    group_reasons: tuple[str, ...],
    usable_n: int,
    coverage: float,
    unresolved_duplicates: tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    reasons = list(focal_reasons)
    reasons.extend(group_reasons)
    if unresolved_duplicates:
        reasons.append(REASON_DUPLICATE_OR_RECTIFICATION)
    unique = tuple(dict.fromkeys(reasons))
    hard = tuple(code for code in unique if code in HARD_REFUSAL_REASONS)
    if hard:
        return STATUS_NOT, unique
    focal_holds = tuple(code for code in focal_reasons if code in HOLD_REASONS)
    if focal_holds:
        return STATUS_HOLD, unique
    if unique and all(code in HOLD_REASONS or code == REASON_INSUFFICIENT_N for code in unique) and usable_n == 0:
        if REASON_MISSING_VALUE in unique or REASON_LIVE_COLUMNS in unique or REASON_AMBIGUOUS_TYPOLOGY in unique:
            return STATUS_HOLD, unique
    if usable_n < MIN_USABLE_N_HOLD:
        extra = unique + ((REASON_INSUFFICIENT_N,) if REASON_INSUFFICIENT_N not in unique else ())
        if usable_n == 0 and (REASON_MISSING_VALUE in extra or REASON_UNKNOWN_EXCLUDED in extra):
            return STATUS_HOLD, tuple(dict.fromkeys(extra))
        return STATUS_NOT, tuple(dict.fromkeys(extra))
    if usable_n < MIN_USABLE_N_COMPARABLE or coverage < MIN_COVERAGE_COMPARABLE:
        extra = list(unique)
        if usable_n < MIN_USABLE_N_COMPARABLE:
            extra.append(REASON_INSUFFICIENT_N)
        if coverage < MIN_COVERAGE_COMPARABLE:
            extra.append(REASON_INSUFFICIENT_COVERAGE)
        return STATUS_HOLD, tuple(dict.fromkeys(extra))
    if coverage < MIN_COVERAGE_HOLD:
        extra = unique + ((REASON_INSUFFICIENT_COVERAGE,) if REASON_INSUFFICIENT_COVERAGE not in unique else ())
        return STATUS_HOLD, tuple(dict.fromkeys(extra))
    return STATUS_COMPARABLE, unique


def select_peers(
    focal: Recorte,
    candidates: tuple[Recorte, ...],
    request: PeerRequest,
) -> tuple[tuple[SelectedPeer, ...], tuple[Exclusion, ...], tuple[Recorte, ...]]:
    selected: list[SelectedPeer] = []
    exclusions: list[Exclusion] = []
    eligible: list[Recorte] = []
    for recorte in candidates:
        if recorte.contract.contract_id == focal.contract.contract_id:
            continue
        reasons = peer_dimension_reasons(focal, recorte)
        if reasons:
            exclusions.append(
                Exclusion(
                    contract_id=recorte.contract.contract_id,
                    reason_codes=reasons,
                    detail="dimension_gate",
                    match_distance=match_distance(focal, recorte),
                )
            )
            continue
        eligible.append(recorte)
        if recorte.contract.valor_is_unknown or recorte.contract.valor is None:
            exclusions.append(
                Exclusion(
                    contract_id=recorte.contract.contract_id,
                    reason_codes=(REASON_MISSING_VALUE, REASON_UNKNOWN_EXCLUDED),
                    detail="unknown_value_excluded_from_denominator",
                    match_distance=match_distance(focal, recorte),
                )
            )
            continue
        distance = match_distance(focal, recorte)
        selected.append(
            SelectedPeer(
                recorte=recorte,
                match_distance=distance,
                match_quality=quality_from_distance(distance),
            )
        )
    selected_sorted = tuple(
        sorted(selected, key=lambda item: (item.recorte.contract.contract_id, item.match_distance))
    )
    exclusions_sorted = tuple(sorted(exclusions, key=lambda item: item.contract_id))
    eligible_sorted = tuple(sorted(eligible, key=lambda item: item.contract.contract_id))
    _ = request
    return selected_sorted, exclusions_sorted, eligible_sorted


def missing_target(contract_id: str) -> tuple[str, tuple[str, ...]]:
    return STATUS_NOT, (REASON_TARGET_NOT_FOUND, contract_id)
