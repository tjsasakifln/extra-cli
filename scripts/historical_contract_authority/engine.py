"""Assemble a factual dossier. Absence stays UNKNOWN; replay is deterministic."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

from scripts.historical_contract_authority.acquire import attach_portal_locators, collect_documents
from scripts.historical_contract_authority.adapters import compare_via_415
from scripts.historical_contract_authority.extract import assemble_from_documents
from scripts.historical_contract_authority.gates import (
    admit,
    build_score,
    handoff_ready,
    quality_gates,
    score_dimensions,
)
from scripts.historical_contract_authority.models import (
    Calculation,
    Claim,
    Contradiction,
    Dossier,
    EditorialBrief,
    Maintenance,
    TimelineEvent,
)
from scripts.historical_contract_authority.schema import (
    METHOD_VERSION,
    SCHEMA,
    content_hash,
    dossier_id,
    producer_sha,
    sha256_text,
)

QUANT = Decimal("0.01")


def _dec(value: Any) -> Decimal | None:
    if value in {None, "", "UNKNOWN", "NOT_COMPUTABLE"}:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def replay_formula(
    formula: str, inputs: dict[str, str], *, unit: str, rounding: str = "ROUND_HALF_EVEN:0.01"
) -> tuple[bool, str, str]:
    if formula == "NOT_COMPUTABLE":
        return False, "NOT_COMPUTABLE", sha256_text("NOT_COMPUTABLE")
    if formula in {"delta_value", "percent_change"}:
        left = _dec(inputs.get("valor_atual"))
        right = _dec(inputs.get("valor_original"))
        if left is None or right is None:
            return False, "NOT_COMPUTABLE", sha256_text(f"{formula}|missing")
        if formula == "delta_value":
            result = (left - right).quantize(QUANT, rounding=ROUND_HALF_EVEN)
        else:
            if right == 0:
                return False, "NOT_COMPUTABLE", sha256_text("percent_change|zero_base")
            result = ((left - right) / right * Decimal("100")).quantize(QUANT, rounding=ROUND_HALF_EVEN)
        text = format(result, "f")
        digest = sha256_text(f"{formula}|{inputs}|{unit}|{rounding}|{text}")
        return True, text, digest
    if formula == "delta_days":
        start = _parse_date(inputs.get("start"))
        end = _parse_date(inputs.get("end"))
        if start is None or end is None:
            return False, "NOT_COMPUTABLE", sha256_text("delta_days|missing")
        text = str((end - start).days)
        return True, text, sha256_text(f"delta_days|{inputs}|{text}")
    return False, "NOT_COMPUTABLE", sha256_text(f"unknown_formula|{formula}")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _as_of_now(value: str | None) -> str:
    if value:
        return value
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_claims(raw_claims: list[dict[str, Any]]) -> tuple[Claim, ...]:
    parsed: list[Claim] = []
    for raw in raw_claims:
        klass = str(raw.get("class") or raw.get("klass") or "UNKNOWN")
        if klass not in {"FACT", "CALCULATION", "INFERENCE", "UNKNOWN"}:
            klass = "UNKNOWN"
        formula = raw.get("formula")
        inputs = {str(key): str(value) for key, value in (raw.get("inputs") or {}).items()}
        unit = raw.get("unit")
        replay = raw.get("replay_hash")
        result = raw.get("result")
        if klass == "CALCULATION" and formula:
            ok, computed, digest = replay_formula(formula, inputs, unit=str(unit or "UNKNOWN"))
            result = computed if ok else "NOT_COMPUTABLE"
            replay = digest
        parsed.append(
            Claim(
                claim_id=str(raw.get("claim_id")),
                klass=klass,  # type: ignore[arg-type]
                text=str(raw.get("text") or ""),
                source_refs=tuple(raw.get("source_refs") or ()),
                locators=tuple(raw.get("locators") or ()),
                confidence=float(raw.get("confidence") or 0.0),
                publication_fit=str(raw.get("publication_fit") or "internal"),
                conflict=raw.get("conflict"),
                superseded_by=raw.get("superseded_by"),
                formula=formula,
                inputs=inputs,
                unit=unit,
                result=result,
                rounding=raw.get("rounding"),
                replay_hash=replay,
                limitations=tuple(raw.get("limitations") or ()),
            )
        )
    return tuple(parsed)


def parse_events(raw_events: list[dict[str, Any]]) -> tuple[TimelineEvent, ...]:
    events = []
    for raw in raw_events:
        events.append(
            TimelineEvent(
                event_id=str(raw.get("event_id")),
                kind=str(raw.get("kind")),
                at=raw.get("at"),
                summary=str(raw.get("summary") or ""),
                source_refs=tuple(raw.get("source_refs") or ()),
                locators=tuple(raw.get("locators") or ()),
                delta_value=raw.get("delta_value"),
                delta_days=raw.get("delta_days"),
                superseded=bool(raw.get("superseded")),
            )
        )
    return tuple(sorted(events, key=lambda item: item.at or ""))


def parse_calculations(raw: list[dict[str, Any]], claims: tuple[Claim, ...]) -> tuple[Calculation, ...]:
    items: list[Calculation] = []
    seen = set()
    for source in list(raw) + [
        {
            "calc_id": item.claim_id,
            "formula": item.formula,
            "inputs": item.inputs,
            "unit": item.unit,
            "rounding": item.rounding or "ROUND_HALF_EVEN:0.01",
        }
        for item in claims
        if item.klass == "CALCULATION" and item.formula
    ]:
        calc_id = str(source.get("calc_id"))
        if calc_id in seen:
            continue
        seen.add(calc_id)
        formula = str(source.get("formula") or "NOT_COMPUTABLE")
        inputs = {str(key): str(value) for key, value in (source.get("inputs") or {}).items()}
        unit = str(source.get("unit") or "UNKNOWN")
        rounding = str(source.get("rounding") or "ROUND_HALF_EVEN:0.01")
        ok, result, digest = replay_formula(formula, inputs, unit=unit, rounding=rounding)
        items.append(
            Calculation(
                calc_id=calc_id,
                formula=formula,
                inputs=inputs,
                unit=unit,
                result=result,
                rounding=rounding,
                replay_hash=digest,
                limitations=tuple(source.get("limitations") or (("NOT_COMPUTABLE",) if not ok else ())),
                computable=ok,
            )
        )
    return tuple(items)


def parse_contradictions(raw: list[dict[str, Any]]) -> tuple[Contradiction, ...]:
    return tuple(
        Contradiction(
            contradiction_id=str(item.get("contradiction_id")),
            description=str(item.get("description") or ""),
            sources=tuple(item.get("sources") or ()),
            alternatives=tuple(item.get("alternatives") or ()),
            weakens=tuple(item.get("weakens") or ()),
            pending=tuple(item.get("pending") or ()),
            decision=str(item.get("decision") or "preserve_with_limitation"),
        )
        for item in raw
    )


def parse_brief(raw: dict[str, Any], question: str) -> EditorialBrief:
    theses = tuple((raw.get("theses") or [])[:3])
    return EditorialBrief(
        central_question=str(raw.get("central_question") or question or ""),
        theses=theses,
        why_singular=str(raw.get("why_singular") or ""),
        transferable_utility=str(raw.get("transferable_utility") or raw.get("utility") or ""),
        possible_implications=tuple(raw.get("possible_implications") or ()),
        reputational_risks=tuple(raw.get("reputational_risks") or ()),
        forbidden_terms=tuple(raw.get("forbidden_terms") or ("irregular", "fraude", "sobrepreço")),
        cannot_assert=tuple(raw.get("cannot_assert") or ()),
        plausible_intent=str(raw.get("plausible_intent") or ""),
        article_text=None,
    )


def parse_maintenance(raw: dict[str, Any], contract_id: str) -> Maintenance:
    return Maintenance(
        owner=str(raw.get("owner") or "historical-contract-authority"),
        refresh_triggers=tuple(raw.get("refresh_triggers") or ("new_official_document", "value_or_term_rectification")),
        invalidation_keys=tuple(raw.get("invalidation_keys") or (contract_id,)),
        expires_at=str(raw.get("expires_at") or "2026-11-15T00:00:00Z"),
        withdrawal_rule=str(raw.get("withdrawal_rule") or "withdraw_on_identity_conflict_or_supersession"),
        estimated_cost=str(raw.get("estimated_cost") or "low"),
    )


def replay_ok(calculations: tuple[Calculation, ...]) -> bool:
    for item in calculations:
        if not item.computable:
            continue
        ok, result, digest = replay_formula(item.formula, item.inputs, unit=item.unit, rounding=item.rounding)
        if not ok or result != item.result or digest != item.replay_hash:
            return False
    return True


def _identity_block(case: dict[str, Any], snapshot_hash: str, as_of: str) -> dict[str, Any]:
    identity = dict(case.get("identity") or {})
    identity["schema"] = SCHEMA
    identity["method_version"] = METHOD_VERSION
    identity["extractor_version"] = "historical-contract-authority-extract/1.0"
    identity["source_snapshot_hash"] = snapshot_hash
    identity["as_of"] = as_of
    return identity


def _should_fetch(case: dict[str, Any], fetch: bool | None) -> bool:
    if fetch is not None:
        return fetch
    mode = str(case.get("catalog_mode") or "fixture")
    return mode in {"official_projection", "official", "live_candidate"}


def build_dossier(
    case: dict[str, Any],
    *,
    as_of: str | None = None,
    snapshot_hash: str | None = None,
    fetch: bool | None = None,
    cache: dict[str, dict[str, Any]] | None = None,
    budget: dict[str, Any] | None = None,
) -> Dossier:
    stamp = _as_of_now(as_of or case.get("as_of"))
    working = attach_portal_locators(case)
    documents, _failed = collect_documents(working, fetch=_should_fetch(working, fetch), cache=cache, budget=budget)
    events = parse_events(list(working.get("events") or []))
    claims = parse_claims(list(working.get("claims") or []))
    assembled = assemble_from_documents(documents, working)
    if not claims:
        claims = assembled["claims"]  # type: ignore[assignment]
    if not events:
        events = assembled["events"]  # type: ignore[assignment]
    question = str(working.get("technical_question") or assembled.get("technical_question") or "")
    if not working.get("technical_question") and assembled.get("technical_question"):
        working = dict(working)
        working["technical_question"] = assembled["technical_question"]
        editorial = dict(working.get("editorial") or {})
        if not editorial.get("central_question"):
            editorial["central_question"] = assembled["technical_question"]
            working["editorial"] = editorial
    calculations = parse_calculations(list(working.get("calculations") or []), claims)
    contradictions = parse_contradictions(list(working.get("contradictions") or []))
    identity = working.get("identity") or {}
    contract_id = str(identity.get("contract_id") or "unknown")
    snap = snapshot_hash or str(
        working.get("source_snapshot_hash")
        or content_hash({"case_id": working.get("case_id"), "contract_id": contract_id})
    )
    brief = parse_brief(working.get("editorial") or {}, question)
    maintenance = parse_maintenance(case.get("maintenance") or {}, contract_id)
    admitted, admission_reasons = admit(working, documents, events)
    replay = replay_ok(calculations)
    gates = quality_gates(
        case=working,
        documents=documents,
        claims=claims,
        events=events,
        calculations=calculations,
        contradictions=contradictions,
        brief=brief,
        maintenance=maintenance,
        replay_ok=replay,
    )
    dimensions = score_dimensions(
        documents=documents,
        claims=claims,
        events=events,
        calculations=calculations,
        contradictions=contradictions,
        brief=brief,
        maintenance=maintenance,
        gates=gates,
    )
    score = build_score(dimensions, gates)
    comparability = compare_via_415(working, as_of=stamp)
    reasons = list(admission_reasons)
    if not admitted:
        reject_now = {
            "identity_swap",
            "value_or_date_conflict",
            "no_specific_technical_question",
            "reputational_block",
            "missing_identity",
        }
        hold_now = {
            "insufficient_documents",
            "missing_url_or_hash_or_locator",
            "value_without_semantics",
            "missing_official_instrument",
            "missing_reference_date",
            "missing_technical_question",
        }
        if reject_now.intersection(admission_reasons):
            state = "REJECT"
        elif hold_now.intersection(admission_reasons):
            state = "HOLD_FOR_DATA"
        else:
            state = "REJECT"
    elif handoff_ready(score):
        state = "HANDOFF_READY"
        reasons.append("quality_gates_passed")
    else:
        state = "HOLD_FOR_DATA"
        failed = [name for name, ok in gates.items() if not ok]
        if failed:
            reasons.append("quality_gate_failed")
            reasons.extend(failed[:6])
        if score.score < 88:
            reasons.append("score_below_88")
        if score.below_floor:
            reasons.append("dimension_below_75")
    limitations = tuple(working.get("limitations") or brief.cannot_assert)
    if any(item.result == "NOT_COMPUTABLE" for item in calculations):
        limitations = tuple(dict.fromkeys((*limitations, "NOT_COMPUTABLE")))
    dossier = Dossier(
        schema=SCHEMA,
        dossier_id=dossier_id(contract_id=contract_id, snapshot_hash=snap),
        state=state,  # type: ignore[arg-type]
        reason_codes=tuple(dict.fromkeys(reasons)),
        identity=_identity_block(working, snap, stamp),
        documents=documents,
        claims=claims,
        chronology=events,
        calculations=calculations,
        comparability=comparability,
        contradictions=contradictions,
        editorial=brief,
        maintenance=maintenance,
        score=score,
        as_of=stamp,
        freshness={
            "as_of": stamp,
            "max_age_hours": 48,
            "policy": "authority-freshness/1.0",
            "source_as_of": (working.get("dates") or {}).get("reference"),
        },
        source_snapshot_hash=snap,
        producer_sha=producer_sha(),
        catalog_mode=str(working.get("catalog_mode") or "fixture"),
        limitations=limitations,
        content_hash="",
    )
    return dossier


def dossier_dict(dossier: Dossier) -> dict[str, Any]:
    return dossier.as_dict()


def process_cases(
    cases: list[dict[str, Any]],
    *,
    as_of: str | None = None,
    snapshot_hash: str | None = None,
    fetch: bool | None = None,
    cache: dict[str, dict[str, Any]] | None = None,
    budget: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    stamp = _as_of_now(as_of)
    snap = snapshot_hash or content_hash({"cases": [item.get("case_id") for item in cases], "as_of": stamp})
    store = cache if cache is not None else {}
    spend = budget if budget is not None else {"requests": 0, "bytes": 0}
    return [
        dossier_dict(build_dossier(case, as_of=stamp, snapshot_hash=snap, fetch=fetch, cache=store, budget=spend))
        for case in cases
    ]
