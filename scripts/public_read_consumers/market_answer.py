"""Market Answer: typical integral-nominal value of paving contracts.

Grain is the full nominal instrument. Never cost/km. Fail closed to NEEDS_DATA
when typology, denominator or coverage fail. National claim requires #302 PASS.
"""

from __future__ import annotations

from typing import Any

from scripts.public_read_consumers.allowlist import project_allowed
from scripts.public_read_consumers.gates import (
    DATA_HOLD,
    DATA_READY,
    DATA_REJECT,
    NEEDS_DATA,
    REASON_COVERAGE,
    REASON_DENOMINATOR,
    REASON_EXTRA_1093,
    REASON_FIXTURE_AS_LIVE,
    REASON_NATIONAL_CLAIM,
    REASON_NEEDS_DATA,
    REASON_STALE,
    REASON_TYPOLOGY,
    coverage_ok,
    evaluate_claim_authorization,
    extra_1093_used,
    freshness_block,
    is_stale,
    refuse_fixture_as_live,
    unknown_remains_unknown,
)
from scripts.public_read_consumers.hashutil import assert_public_clean, attach_hash

SCHEMA = "public-read-market-answer-pavimentacao/1.0"
CONSUMER_ID = "web-cfg/market-answer/valor-tipico-contratos-pavimentacao"
QUESTION_ID = "valor-tipico-contratos-pavimentacao"
QUESTION = "Qual é o valor típico dos contratos públicos de pavimentação?"
TYPOLOGY_ID = "pavimentacao/1.0"
METHOD_ID = "integral-nominal-nearest-rank/1.0"
GRAIN = "integral_nominal_instrument"
GRAIN_NOT = ("cost_per_km", "unit_price", "price_per_m2", "custo_por_km")
MIN_N = 8


def _num(value: Any) -> float | None:
    cleaned = unknown_remains_unknown(value)
    if cleaned is None:
        return None
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    cleaned = unknown_remains_unknown(value)
    if cleaned is None:
        return None
    try:
        return int(cleaned)
    except (TypeError, ValueError):
        return None


def _typology_ok(raw: dict[str, Any]) -> bool:
    typology = raw.get("typology") if isinstance(raw.get("typology"), dict) else {}
    typology_id = str(raw.get("typology_id") or typology.get("id") or "")
    precision = typology.get("sample_precision_reviewed")
    if typology.get("failed") is True or raw.get("typology_failed") is True:
        return False
    if typology_id and typology_id != TYPOLOGY_ID:
        return False
    if precision is False:
        return False
    return bool(typology_id or raw.get("contracts") or raw.get("values"))


def project_market_answer(raw: dict[str, Any]) -> dict[str, Any]:
    generated_at = str(raw.get("generated_at") or "")
    if not generated_at:
        raise ValueError("generated_at is required")
    catalog_mode = str(raw.get("catalog_mode") or "fixture")
    claimed_live = bool(raw.get("claimed_live") or raw.get("official_live"))
    as_of = str(raw.get("as_of") or raw.get("source_as_of") or "")
    geography = raw.get("geography") if isinstance(raw.get("geography"), dict) else {}
    geo_code = str(geography.get("code") or raw.get("geography_code") or "")
    claim = evaluate_claim_authorization(raw.get("claim") or raw.get("claim_authorization"), geography=geo_code)
    stats_in = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
    values = raw.get("values") if isinstance(raw.get("values"), list) else None
    n = _int(stats_in.get("n") if "n" in stats_in else (len(values) if values is not None else raw.get("n")))
    median = _num(stats_in.get("median") if "median" in stats_in else raw.get("median"))
    p25 = _num(stats_in.get("p25") if "p25" in stats_in else raw.get("p25"))
    p75 = _num(stats_in.get("p75") if "p75" in stats_in else raw.get("p75"))
    coverage = dict(raw.get("coverage") or {})
    if n is not None:
        coverage.setdefault("n", n)
        coverage.setdefault("usable_n", n)
    if "status" not in coverage:
        coverage["status"] = "COMPLETE" if coverage_ok(coverage, min_n=MIN_N) else "INCOMPLETE"
    stale = is_stale(generated_at=generated_at, source_as_of=as_of)
    reasons: list[str] = []
    reasons.extend(refuse_fixture_as_live({"catalog_mode": catalog_mode, "claimed_live": claimed_live}))
    if extra_1093_used(raw) or extra_1093_used(raw.get("claim") or {}):
        reasons.append(REASON_EXTRA_1093)
    typology_ok = _typology_ok(raw)
    if not typology_ok:
        reasons.append(REASON_TYPOLOGY)
        reasons.append(REASON_NEEDS_DATA)
    if raw.get("denominator_failed") is True or (raw.get("denominator") or {}).get("ok") is False:
        reasons.append(REASON_DENOMINATOR)
        reasons.append(REASON_NEEDS_DATA)
    if not coverage_ok(coverage, min_n=MIN_N):
        reasons.append(REASON_COVERAGE)
        reasons.append(REASON_NEEDS_DATA)
    if stale:
        reasons.append(REASON_STALE)
    if geo_code.upper() in {"BR", "BRASIL", "NACIONAL"} and not claim["national_claim_allowed"]:
        reasons.append(REASON_NATIONAL_CLAIM)
    grain = str(raw.get("grain") or GRAIN)
    if grain in GRAIN_NOT or grain != GRAIN:
        reasons.append(REASON_TYPOLOGY)
        reasons.append(REASON_NEEDS_DATA)
        grain = GRAIN
    unique_reasons = list(dict.fromkeys(reasons + list(claim["reason_codes"])))
    if REASON_FIXTURE_AS_LIVE in unique_reasons:
        answer_state = DATA_REJECT
    elif (
        REASON_NEEDS_DATA in unique_reasons
        or REASON_TYPOLOGY in unique_reasons
        or REASON_COVERAGE in unique_reasons
        or REASON_DENOMINATOR in unique_reasons
    ):
        answer_state = NEEDS_DATA
    elif REASON_STALE in unique_reasons:
        answer_state = DATA_HOLD
    else:
        answer_state = DATA_READY
    publishable_stats = answer_state == DATA_READY
    payload = {
        "schema": SCHEMA,
        "schema_version": "v1.0.0",
        "consumer_id": CONSUMER_ID,
        "question_id": QUESTION_ID,
        "question": QUESTION,
        "typology_id": TYPOLOGY_ID,
        "method_id": METHOD_ID,
        "grain": GRAIN,
        "grain_not": list(GRAIN_NOT),
        "stats": {
            "median": median if publishable_stats else None,
            "p25": p25 if publishable_stats else None,
            "p75": p75 if publishable_stats else None,
            "n": n,
            "unit": GRAIN,
        },
        "period": raw.get("period") or {},
        "geography": {
            "code": None
            if geo_code.upper() in {"BR", "BRASIL", "NACIONAL"} and not claim["national_claim_allowed"]
            else (geo_code or None),
            "kind": geography.get("kind"),
            "label": geography.get("label"),
        },
        "currency": raw.get("currency") or "BRL",
        "base": raw.get("base") or "nominal",
        "distribution": list(raw.get("distribution") or []) if publishable_stats else [],
        "series": list(raw.get("series") or []) if publishable_stats else [],
        "contract_refs": list(raw.get("contract_refs") or []),
        "evidence_refs": list(raw.get("evidence_refs") or []),
        "peer_group": raw.get("peer_group") or {"status": "ABSENT", "ref": None, "issue": "#415"},
        "coverage": coverage,
        "freshness": freshness_block(
            generated_at=generated_at,
            source_as_of=as_of,
            stale=stale,
            invalidation_keys=("facts", "events", "coverage", "policy", "typology"),
        ),
        "missingness": raw.get("missingness") or {"unknown_values": 0 if publishable_stats else "UNKNOWN"},
        "suppression": raw.get("suppression") or {"applied": False, "reason_codes": []},
        "as_of": as_of,
        "limitations": list(raw.get("limitations") or ["ticket is integral nominal instrument, never cost per km"]),
        "unknown_fields": list(raw.get("unknown_fields") or []),
        "reason_codes": unique_reasons,
        "answer_state": answer_state,
        "data_state": answer_state if answer_state != NEEDS_DATA else DATA_HOLD,
        "claim_authorization": claim,
        "producer_status": "CONTRACT_FIXTURE" if catalog_mode == "fixture" else "OFFICIAL_LIVE",
        "official_live": bool(claimed_live)
        and catalog_mode == "official_live"
        and REASON_FIXTURE_AS_LIVE not in unique_reasons,
        "catalog_mode": catalog_mode,
        "claimed_live": claimed_live,
        "generated_at": generated_at,
    }
    if catalog_mode == "fixture":
        payload["official_live"] = False
        payload["producer_status"] = "CONTRACT_FIXTURE"
    payload = project_allowed(payload, consumer_id=CONSUMER_ID)
    assert_public_clean(payload)
    return attach_hash(payload)


def validate_market_answer(document: dict[str, Any]) -> None:
    if document.get("schema") != SCHEMA:
        raise ValueError(f"schema_validation_schema:{document.get('schema')}")
    if document.get("consumer_id") != CONSUMER_ID:
        raise ValueError("schema_validation_consumer")
    if document.get("grain") != GRAIN:
        raise ValueError("schema_validation_grain")
    if document.get("grain") in GRAIN_NOT:
        raise ValueError("grain_is_cost_per_km")
    if document.get("answer_state") not in {DATA_READY, DATA_HOLD, DATA_REJECT, NEEDS_DATA}:
        raise ValueError(f"schema_validation_answer_state:{document.get('answer_state')}")
    if document.get("catalog_mode") == "fixture" and document.get("official_live"):
        raise ValueError(REASON_FIXTURE_AS_LIVE)
    if document.get("claimed_live") and document.get("catalog_mode") == "fixture":
        if REASON_FIXTURE_AS_LIVE not in (document.get("reason_codes") or ()):
            raise ValueError(REASON_FIXTURE_AS_LIVE)
    claim = document.get("claim_authorization") or {}
    geo = (document.get("geography") or {}).get("code")
    if str(geo or "").upper() in {"BR", "BRASIL"} and not claim.get("national_claim_allowed"):
        raise ValueError(REASON_NATIONAL_CLAIM)
    assert_public_clean(document)
