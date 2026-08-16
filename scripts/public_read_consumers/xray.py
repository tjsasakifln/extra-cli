"""B2G X-Ray: observed public portfolio for a visitor CNPJ or entity id.

Facts only. No risk, credit, pain, irregularity, capacity, consent or total
market share without a denominator.
"""

from __future__ import annotations

import re
from typing import Any

from scripts.public_read_consumers.allowlist import project_allowed, scan_xray_denied
from scripts.public_read_consumers.gates import (
    DATA_HOLD,
    DATA_READY,
    DATA_REJECT,
    NEEDS_DATA,
    REASON_COVERAGE,
    REASON_FIXTURE_AS_LIVE,
    REASON_STALE,
    REASON_UNKNOWN_INPUT,
    coverage_ok,
    freshness_block,
    is_stale,
    refuse_fixture_as_live,
    unknown_remains_unknown,
)
from scripts.public_read_consumers.hashutil import assert_public_clean, attach_hash

SCHEMA = "public-read-b2g-xray/1.0"
CONSUMER_ID = "web-cfg/b2g-xray"
CNPJ_DIGITS = re.compile(r"\D+")


def normalize_cnpj(value: str | None) -> str | None:
    if value is None:
        return None
    digits = CNPJ_DIGITS.sub("", str(value))
    if len(digits) != 14:
        return None
    if digits == "0" * 14:
        return None
    return digits


def _input_identity(raw: dict[str, Any]) -> dict[str, Any]:
    incoming = raw.get("input") if isinstance(raw.get("input"), dict) else {}
    cnpj = normalize_cnpj(incoming.get("cnpj") or incoming.get("cnpj_normalized") or raw.get("cnpj"))
    entity_id = unknown_remains_unknown(incoming.get("canonical_entity_id") or raw.get("canonical_entity_id"))
    return {
        "cnpj_normalized": cnpj,
        "canonical_entity_id": str(entity_id) if entity_id else None,
    }


def project_xray(raw: dict[str, Any]) -> dict[str, Any]:
    generated_at = str(raw.get("generated_at") or "")
    if not generated_at:
        raise ValueError("generated_at is required")
    catalog_mode = str(raw.get("catalog_mode") or "fixture")
    claimed_live = bool(raw.get("claimed_live") or raw.get("official_live"))
    as_of = str(raw.get("as_of") or raw.get("source_as_of") or "")
    identity = _input_identity(raw)
    reasons: list[str] = []
    reasons.extend(refuse_fixture_as_live({"catalog_mode": catalog_mode, "claimed_live": claimed_live}))
    if not identity["cnpj_normalized"] and not identity["canonical_entity_id"]:
        reasons.append(REASON_UNKNOWN_INPUT)
    coverage = dict(raw.get("coverage") or {})
    contracts = list(raw.get("contracts") or [])
    coverage.setdefault("n", len(contracts))
    coverage.setdefault("usable_n", len(contracts))
    if "status" not in coverage:
        coverage["status"] = "COMPLETE" if contracts else "INCOMPLETE"
    stale = is_stale(generated_at=generated_at, source_as_of=as_of)
    if stale:
        reasons.append(REASON_STALE)
    if not coverage_ok(coverage, min_n=1) and REASON_UNKNOWN_INPUT not in reasons:
        reasons.append(REASON_COVERAGE)
    incoming_share = raw.get("market_share")
    if incoming_share is not None and not (isinstance(incoming_share, dict) and incoming_share.get("denominator")):
        reasons.append("share_without_denominator")
    concentration = raw.get("concentration") if isinstance(raw.get("concentration"), dict) else {}
    if concentration.get("market_share_total") is not None and not concentration.get("denominator"):
        concentration = {key: value for key, value in concentration.items() if key != "market_share_total"}
        reasons.append("share_without_denominator")
    comparables = raw.get("comparables") if isinstance(raw.get("comparables"), dict) else None
    if comparables and comparables.get("status") not in {"COMPARABLE", "PEER_VALID", "HOLD_FOR_DATA", "PEER_WEAK"}:
        comparables = {
            "status": comparables.get("status") or "NOT_COMPARABLE",
            "position": None,
            "reason_codes": list(comparables.get("reason_codes") or ["NOT_COMPARABLE"]),
        }
    unique_reasons = list(dict.fromkeys(reasons))
    if REASON_FIXTURE_AS_LIVE in unique_reasons:
        state = DATA_REJECT
    elif REASON_UNKNOWN_INPUT in unique_reasons:
        state = NEEDS_DATA
    elif REASON_COVERAGE in unique_reasons:
        state = NEEDS_DATA
    elif REASON_STALE in unique_reasons:
        state = DATA_HOLD
    else:
        state = DATA_READY
    payload = {
        "schema": SCHEMA,
        "schema_version": "v1.0.0",
        "consumer_id": CONSUMER_ID,
        "input": identity,
        "observed_portfolio": raw.get("observed_portfolio")
        or {
            "contract_count": len(contracts) if state == DATA_READY else None,
            "value_sum_nominal_brl": unknown_remains_unknown(
                (raw.get("observed_portfolio") or {}).get("value_sum_nominal_brl")
            )
            if isinstance(raw.get("observed_portfolio"), dict)
            else None,
        },
        "contracts": contracts if state in {DATA_READY, DATA_HOLD} else [],
        "organs": list(raw.get("organs") or []) if state in {DATA_READY, DATA_HOLD} else [],
        "ufs": list(raw.get("ufs") or []) if state in {DATA_READY, DATA_HOLD} else [],
        "typologies": list(raw.get("typologies") or []) if state in {DATA_READY, DATA_HOLD} else [],
        "concentration": concentration if state in {DATA_READY, DATA_HOLD} else {},
        "events": list(raw.get("events") or []) if state in {DATA_READY, DATA_HOLD} else [],
        "comparables": comparables,
        "related_analyses": list(raw.get("related_analyses") or []),
        "second_read_candidates": list(raw.get("second_read_candidates") or raw.get("candidate_refs") or []),
        "as_of": as_of,
        "coverage": coverage,
        "freshness": freshness_block(
            generated_at=generated_at,
            source_as_of=as_of,
            stale=stale,
            invalidation_keys=("facts", "events", "coverage", "policy", "entity"),
        ),
        "limitations": list(
            raw.get("limitations") or ["observed public portfolio only; no scoring or lending product"]
        ),
        "unknown_fields": list(raw.get("unknown_fields") or []),
        "reason_codes": unique_reasons,
        "data_state": state if state != NEEDS_DATA else DATA_HOLD,
        "answer_state": state,
        "producer_status": "CONTRACT_FIXTURE" if catalog_mode == "fixture" else "OFFICIAL_LIVE",
        "official_live": bool(claimed_live) and catalog_mode == "official_live",
        "catalog_mode": catalog_mode,
        "claimed_live": claimed_live,
        "generated_at": generated_at,
    }
    if catalog_mode == "fixture":
        payload["official_live"] = False
        payload["producer_status"] = "CONTRACT_FIXTURE"
    payload = project_allowed(payload, consumer_id=CONSUMER_ID)
    denied = scan_xray_denied(payload)
    if denied:
        raise ValueError(f"xray_denied_field:{denied[0]}")
    assert_public_clean(payload)
    return attach_hash(payload)


def validate_xray(document: dict[str, Any]) -> None:
    if document.get("schema") != SCHEMA:
        raise ValueError(f"schema_validation_schema:{document.get('schema')}")
    if document.get("consumer_id") != CONSUMER_ID:
        raise ValueError("schema_validation_consumer")
    if document.get("catalog_mode") == "fixture" and document.get("official_live"):
        raise ValueError(REASON_FIXTURE_AS_LIVE)
    denied = scan_xray_denied(document)
    if denied:
        raise ValueError(f"xray_denied_field:{denied[0]}")
    assert_public_clean(document)
