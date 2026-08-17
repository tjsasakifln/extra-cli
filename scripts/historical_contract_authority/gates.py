"""Admission gates, quality hard gates and DOSSIER_AUTHORITY_SCORE."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from scripts.historical_contract_authority.models import (
    Calculation,
    Claim,
    Contradiction,
    DocumentRecord,
    EditorialBrief,
    Maintenance,
    ScoreBreakdown,
    TimelineEvent,
)
from scripts.historical_contract_authority.schema import (
    FORBIDDEN_CONCLUSION,
    GENERIC_FICHA_QUESTIONS,
    HANDOFF_MIN_DIMENSION,
    HANDOFF_MIN_SCORE,
    MIN_EVIDENCE_FAMILIES,
    MIN_MATERIAL_CLAIMS,
    SCORE_WEIGHTS,
    is_sha256,
)

GENERIC_THESES = frozenset(
    {
        "contrato publico de grande valor",
        "contrato público de grande valor",
        "obra importante no municipio",
        "obra importante no município",
        "empresa conhecida venceu licitacao",
        "empresa conhecida venceu licitação",
    }
)


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def identity_swap(identity: dict[str, Any], documents: Iterable[DocumentRecord]) -> bool:
    if identity.get("identity_swap"):
        return True
    expected_orgao = _digits(identity.get("orgao_cnpj"))
    expected_mun = str(identity.get("municipio") or "").casefold().strip()
    alt_orgao = _digits(identity.get("alt_orgao_cnpj"))
    alt_mun = str(identity.get("alt_municipio") or "").casefold().strip()
    if (
        expected_orgao
        and alt_orgao
        and expected_orgao != alt_orgao
        and expected_mun
        and alt_mun
        and expected_mun != alt_mun
    ):
        return True
    for doc in documents:
        blob = f"{doc.title} {doc.text}".casefold()
        other = _digits(identity.get("conflicting_cnpj"))
        if other and expected_orgao and other != expected_orgao and other in _digits(blob):
            if expected_mun and identity.get("conflicting_municipio"):
                return True
    return False


def hidden_value_or_date_conflict(case: dict[str, Any]) -> bool:
    dates = case.get("dates") or {}
    if dates.get("conflict_hidden"):
        return True
    conflicts = list(dates.get("conflicts") or [])
    if conflicts and not dates.get("conflict_disclosed"):
        return True
    values = case.get("values") or {}
    if values.get("conflict_hidden"):
        return True
    return False


def official_primary(documents: tuple[DocumentRecord, ...]) -> bool:
    return any(item.klass in {"instrument", "registry", "contract"} and item.url for item in documents)


def distinct_official_events(documents: tuple[DocumentRecord, ...], events: tuple[TimelineEvent, ...]) -> int:
    families = {item.family for item in documents if item.url and item.binary_sha256}
    kinds = {item.kind for item in events if item.source_refs}
    return max(len(families), len(kinds))


def hashed_located(documents: tuple[DocumentRecord, ...]) -> bool:
    if not documents:
        return False
    return all(
        item.url
        and is_sha256(item.binary_sha256)
        and item.locator.as_text() != "UNSPECIFIED"
        and (item.bytes_len > 0 or bool(item.text.strip()))
        for item in documents
    )


def admit(
    case: dict[str, Any], documents: tuple[DocumentRecord, ...], events: tuple[TimelineEvent, ...]
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    identity = case.get("identity") or {}
    if not identity.get("contract_id"):
        reasons.append("missing_identity")
    if identity_swap(identity, documents):
        reasons.append("identity_swap")
    if hidden_value_or_date_conflict(case):
        reasons.append("value_or_date_conflict")
    if not official_primary(documents):
        reasons.append("missing_official_instrument")
    distinct = distinct_official_events(documents, events)
    exceptional = bool(case.get("extraordinary_single_source"))
    if distinct < 2 and not exceptional:
        reasons.append("insufficient_documents")
    if exceptional and distinct < 2:
        reasons.append("extraordinary_single_source_recorded")
    if not hashed_located(documents):
        reasons.append("missing_url_or_hash_or_locator")
    if not (case.get("dates") or {}).get("reference"):
        reasons.append("missing_reference_date")
    question = str(case.get("technical_question") or "").strip()
    if not question:
        reasons.append("missing_technical_question")
    elif question.lower() in GENERIC_FICHA_QUESTIONS:
        reasons.append("no_specific_technical_question")
    if case.get("reputational_block"):
        reasons.append("reputational_block")
    if (case.get("values") or {}).get("valor_semantic") in {None, "", "unknown"} and case.get("require_value_semantic"):
        reasons.append("value_without_semantics")
    blocking = tuple(
        code
        for code in reasons
        if code
        not in {
            "extraordinary_single_source_recorded",
        }
    )
    critical = {
        "missing_identity",
        "identity_swap",
        "value_or_date_conflict",
        "missing_official_instrument",
        "insufficient_documents",
        "missing_url_or_hash_or_locator",
        "missing_reference_date",
        "missing_technical_question",
        "no_specific_technical_question",
        "reputational_block",
    }
    failed = tuple(code for code in blocking if code in critical or code == "value_without_semantics")
    return (len(failed) == 0), tuple(dict.fromkeys(reasons))


def fact_without_locator(claims: tuple[Claim, ...]) -> bool:
    return any(item.klass == "FACT" and (not item.source_refs or not item.locators) for item in claims)


def calc_incomplete(claims: tuple[Claim, ...], calculations: tuple[Calculation, ...]) -> bool:
    for item in claims:
        if item.klass != "CALCULATION":
            continue
        if not item.formula or not item.inputs or not item.unit or not item.replay_hash:
            return True
    return any(
        not item.computable or not item.replay_hash or not item.formula for item in calculations if item.computable
    )


def inference_mislabeled(claims: tuple[Claim, ...]) -> bool:
    for item in claims:
        blob = item.text.casefold()
        if any(term in blob for term in FORBIDDEN_CONCLUSION) and item.klass == "FACT":
            return True
        if item.klass == "INFERENCE" and item.publication_fit == "as_fact":
            return True
    return False


def unknown_erased(claims: tuple[Claim, ...], documents: tuple[DocumentRecord, ...]) -> bool:
    weak_ocr = any(
        item.ocr_used and item.ocr_confidence is not None and item.ocr_confidence < 0.50 for item in documents
    )
    if weak_ocr and not any(item.klass == "UNKNOWN" for item in claims):
        return True
    return any(item.klass == "FACT" and "UNKNOWN" in item.text for item in claims)


def chronology_useful(events: tuple[TimelineEvent, ...]) -> bool:
    kinds = {item.kind for item in events}
    material = kinds & {
        "amendment_term",
        "amendment_value",
        "scope_change",
        "suspension",
        "resumption",
        "rescission",
        "apostille",
        "rectification",
    }
    dated = [item for item in events if item.at and item.source_refs]
    return bool(material) and len(dated) >= 3


def singular_thesis(brief: EditorialBrief) -> bool:
    if not brief.theses or not brief.central_question or not brief.why_singular:
        return False
    folded = {item.casefold().strip() for item in brief.theses}
    if folded & GENERIC_THESES:
        return False
    if "grande valor" in brief.why_singular.casefold() and "aditiv" not in brief.why_singular.casefold():
        return False
    return len(brief.central_question) >= 40


def quality_gates(
    *,
    case: dict[str, Any],
    documents: tuple[DocumentRecord, ...],
    claims: tuple[Claim, ...],
    events: tuple[TimelineEvent, ...],
    calculations: tuple[Calculation, ...],
    contradictions: tuple[Contradiction, ...],
    brief: EditorialBrief,
    maintenance: Maintenance,
    replay_ok: bool,
) -> dict[str, bool]:
    families = {item.family for item in documents}
    exceptional = bool(case.get("extraordinary_single_source"))
    material = tuple(item for item in claims if item.klass in {"FACT", "CALCULATION"} and item.source_refs)
    return {
        "facts_sourced_located": not fact_without_locator(claims),
        "calculations_replayable": not calc_incomplete(claims, calculations)
        and (not any(item.klass == "CALCULATION" for item in claims) or bool(calculations)),
        "inferences_labeled": not inference_mislabeled(claims),
        "unknown_preserved": not unknown_erased(claims, documents),
        "identity_stable": not identity_swap(case.get("identity") or {}, documents),
        "no_hidden_value_date_conflict": not hidden_value_or_date_conflict(case),
        "min_material_claims": len(material) >= MIN_MATERIAL_CLAIMS,
        "min_evidence_families": len(families) >= MIN_EVIDENCE_FAMILIES or exceptional,
        "useful_chronology": chronology_useful(events),
        "singular_thesis": singular_thesis(brief),
        "utility_beyond_source": bool(brief.transferable_utility) and len(brief.transferable_utility) >= 40,
        "counter_evidence_examined": bool(contradictions),
        "limitations_explicit": bool(brief.cannot_assert) and bool(case.get("limitations") or brief.cannot_assert),
        "reputational_risk_acceptable": not case.get("reputational_block")
        and "accusation" not in " ".join(brief.reputational_risks).casefold(),
        "deterministic_replay": replay_ok,
        "freshness_maintenance_defined": bool(
            maintenance.expires_at and maintenance.refresh_triggers and maintenance.owner
        ),
    }


def _clip(value: int) -> int:
    return max(0, min(100, value))


def score_dimensions(
    *,
    documents: tuple[DocumentRecord, ...],
    claims: tuple[Claim, ...],
    events: tuple[TimelineEvent, ...],
    calculations: tuple[Calculation, ...],
    contradictions: tuple[Contradiction, ...],
    brief: EditorialBrief,
    maintenance: Maintenance,
    gates: dict[str, bool],
) -> dict[str, int]:
    families = {item.family for item in documents}
    hashed = sum(1 for item in documents if item.binary_sha256 and item.url)
    documentary = 70 if len(families) >= 3 else 48 if len(families) == 2 else 20 if families else 0
    documentary += 20 if hashed >= 4 else 10 if hashed >= 2 else 0
    documentary += 10 if documents and all(item.locator.as_text() != "UNSPECIFIED" for item in documents) else 0
    epistemic = 0
    epistemic += 25 if gates["facts_sourced_located"] else 0
    epistemic += 25 if gates["calculations_replayable"] else 8
    epistemic += 25 if gates["inferences_labeled"] else 0
    epistemic += 25 if gates["unknown_preserved"] else 0
    singularity = 50 if gates["singular_thesis"] else 10
    singularity += 30 if brief.why_singular and "aditiv" in brief.why_singular.casefold() else 8
    singularity += 20 if 1 <= len(brief.theses) <= 3 else 0
    calc_ch = 40 if gates["useful_chronology"] else 10
    calc_ch += 35 if calculations and all(item.replay_hash for item in calculations) else 8
    calc_ch += 25 if any(item.kind in {"amendment_term", "amendment_value", "scope_change"} for item in events) else 0
    utility = 50 if gates["utility_beyond_source"] else 15
    utility += (
        30
        if "b2g" in brief.transferable_utility.casefold() or "construtor" in brief.transferable_utility.casefold()
        else 8
    )
    utility += 20 if gates["counter_evidence_examined"] else 0
    citability = 40 if hashed >= 2 else 10
    citability += 40 if documents and all(item.url.startswith("http") for item in documents) else 0
    citability += 20 if all(item.locators for item in claims if item.klass == "FACT") else 0
    maint = 40 if gates["freshness_maintenance_defined"] else 10
    maint += 30 if maintenance.invalidation_keys else 0
    maint += 30 if maintenance.withdrawal_rule else 0
    return {
        "documentary_depth": _clip(documentary),
        "epistemic_integrity": _clip(epistemic),
        "analytical_singularity": _clip(singularity),
        "calc_chronology_rigor": _clip(calc_ch),
        "decision_utility": _clip(utility),
        "citability": _clip(citability),
        "maintenance": _clip(maint),
    }


def build_score(dimensions: dict[str, int], gates: dict[str, bool]) -> ScoreBreakdown:
    total = 0
    for name, weight in SCORE_WEIGHTS.items():
        total += int(dimensions[name]) * weight
    score = total / 100.0
    below = tuple(name for name, value in dimensions.items() if value < HANDOFF_MIN_DIMENSION)
    return ScoreBreakdown(
        dimensions=dimensions,
        weights=dict(SCORE_WEIGHTS),
        weighted_total_x100=total,
        score=score,
        hard_gates=gates,
        below_floor=below,
    )


def handoff_ready(score: ScoreBreakdown) -> bool:
    if not all(score.hard_gates.values()):
        return False
    if score.below_floor:
        return False
    if score.score < HANDOFF_MIN_SCORE:
        return False
    return True
