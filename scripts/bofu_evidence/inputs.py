"""Validate #435/#437 versioned public inputs. Copied fixtures are not live authority."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.bofu_evidence.gates import parse_iso
from scripts.bofu_evidence.models import (
    COMPARABLE_ACCEPTED_SCHEMAS,
    COMPARABLE_METRIC,
    COMPARABLE_UNIT,
    FORBIDDEN_NATIONAL_SOURCES,
    NATIONAL_CONTRACT_PATH,
    NATIONAL_SCHEMA,
    NATIONAL_VERDICTS,
    BofuInputError,
)

REPO = Path(__file__).resolve().parents[2]
COMPARABLE_CONTRACT_PATH = REPO / "docs" / "contracts" / "contract-comparables" / "comparable-contracts-v1.json"


def _load_national_contract() -> dict[str, Any]:
    return json.loads(NATIONAL_CONTRACT_PATH.read_text(encoding="utf-8"))


def _hash_ok(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text.lower())


def _walk_sources(payload: dict[str, Any]) -> list[str]:
    found: list[str] = []
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    universe = payload.get("universe") if isinstance(payload.get("universe"), dict) else {}
    consumer = payload.get("consumer") if isinstance(payload.get("consumer"), dict) else {}
    for raw in (
        payload.get("official_source"),
        payload.get("source"),
        universe.get("official_source"),
        provenance.get("official_source"),
        (consumer.get("provenance") or {}).get("official_source")
        if isinstance(consumer.get("provenance"), dict)
        else None,
    ):
        if raw:
            found.append(str(raw).strip().lower())
    return found


def validate_national_input(
    payload: dict[str, Any], *, synthetic: bool = False, now: str | None = None
) -> dict[str, Any]:
    """Refuse missing, expired, incompatible, extra_1093, or fixture-as-live coverage."""
    if not isinstance(payload, dict) or not payload:
        raise BofuInputError("missing_input:national_coverage")
    contract = _load_national_contract()
    schema = str(payload.get("schema_version") or payload.get("contract_version") or payload.get("schema") or "")
    verdict = str(payload.get("verdict") or "")
    if "national_claim_authorized" not in payload:
        raise BofuInputError("missing_field:national_claim_authorized")
    authorized = bool(payload.get("national_claim_authorized"))
    content = payload.get("content_hash") or payload.get("catalog_hash")
    if verdict not in set(contract.get("verdict_tokens") or NATIONAL_VERDICTS):
        raise BofuInputError(f"schema_version_mismatch:verdict:{verdict}")
    if not synthetic:
        if schema not in {NATIONAL_SCHEMA, contract.get("contract_version"), "national-coverage/1.0"}:
            raise BofuInputError(f"schema_version_mismatch:{schema or 'missing'}")
        if not _hash_ok(content):
            raise BofuInputError("missing_content_hash:national_coverage")
        catalog_mode = str(payload.get("catalog_mode") or payload.get("kind") or "").lower()
        if catalog_mode in {"fixture", "fixture_only"}:
            raise BofuInputError("fixture_treated_as_live:national_coverage")
    elif not content:
        raise BofuInputError("missing_content_hash:national_coverage")
    for source in _walk_sources(payload):
        if source in FORBIDDEN_NATIONAL_SOURCES:
            raise BofuInputError(f"forbidden_national_source:{source}")
    if authorized and verdict in {"PARTIAL", "BLOCKED", "NOT_MEASURED"}:
        raise BofuInputError(f"national_claim_incompatible:{verdict}")
    if authorized and not synthetic and verdict != "NATIONAL_CLAIM_AUTHORIZED":
        raise BofuInputError("national_claim_incompatible:unauthorized_verdict")
    expires = payload.get("expires_at") or payload.get("expires")
    if expires and now:
        if parse_iso(now) > parse_iso(str(expires)):
            raise BofuInputError("input_expired:national_coverage")
    expected = payload.get("expected")
    closed = payload.get("closed")
    if isinstance(expected, (int, float)) and expected < 0:
        raise BofuInputError("negative_count:expected")
    if isinstance(closed, (int, float)) and closed < 0:
        raise BofuInputError("negative_count:closed")
    return payload


def _metrics_block(payload: dict[str, Any]) -> dict[str, Any]:
    document = payload.get("document") if isinstance(payload.get("document"), dict) else payload
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    if not metrics and isinstance(document.get("metrics"), dict):
        metrics = document["metrics"]
    return metrics


def validate_comparable_input(
    payload: dict[str, Any], *, synthetic: bool = False, now: str | None = None
) -> dict[str, Any]:
    """Normalize #435 public comparable facts. Fixture copies are live only when synthetic."""
    if not isinstance(payload, dict) or not payload:
        raise BofuInputError("missing_input:comparable")
    document = payload.get("document") if isinstance(payload.get("document"), dict) else payload
    metrics = _metrics_block(payload)
    schema = str(payload.get("schema") or document.get("schema") or "")
    accepted = document.get("accepted_schemas") or payload.get("accepted_schemas") or []
    if not schema and accepted:
        schema = str(accepted[0])
    status = str(payload.get("status") or payload.get("state") or document.get("status") or "")
    content = payload.get("content_hash") or document.get("content_hash")
    catalog_mode = str(payload.get("catalog_mode") or document.get("catalog_mode") or "").lower()
    unit = str(payload.get("unit") or metrics.get("unit") or document.get("unit") or "")
    metric = str(
        payload.get("metric")
        or metrics.get("value_semantic")
        or payload.get("value_semantic")
        or document.get("value_semantic")
        or ""
    )
    n_used = payload.get("n_used")
    if n_used is None:
        n_used = payload.get("total_used", metrics.get("n", document.get("usable_n")))
    if isinstance(n_used, (int, float)) and n_used < 0:
        raise BofuInputError("negative_count:n_used")
    if not synthetic:
        accepted_set = {str(item) for item in accepted}
        if schema not in COMPARABLE_ACCEPTED_SCHEMAS and not (accepted_set & set(COMPARABLE_ACCEPTED_SCHEMAS)):
            raise BofuInputError(f"schema_version_mismatch:comparable:{schema or 'missing'}")
        if catalog_mode in {"fixture", "fixture_only"}:
            raise BofuInputError("fixture_treated_as_live:comparable")
        if not _hash_ok(content):
            raise BofuInputError("missing_content_hash:comparable")
        if not COMPARABLE_CONTRACT_PATH.is_file():
            raise BofuInputError("missing_input:comparable_contract")
    elif not content:
        raise BofuInputError("missing_content_hash:comparable")
    if unit and unit != COMPARABLE_UNIT:
        raise BofuInputError(f"unit_mismatch:{unit}")
    if metric and metric != COMPARABLE_METRIC:
        raise BofuInputError(f"metric_mismatch:{metric}")
    expires = payload.get("expires_at") or payload.get("expires") or document.get("expires_at")
    if expires and now:
        if parse_iso(now) > parse_iso(str(expires)):
            raise BofuInputError("input_expired:comparable")
    future = payload.get("as_of") or document.get("as_of")
    if future and now and str(future) > str(now) and "T" in str(future):
        # Future timestamp on a live comparable is incompatible.
        try:
            if parse_iso(str(future)) > parse_iso(str(now)):
                raise BofuInputError("future_timestamp:comparable")
        except ValueError:
            pass
    median = payload.get("median") or metrics.get("median")
    p25 = payload.get("p25") or metrics.get("p25")
    p75 = payload.get("p75") or metrics.get("p75")
    return {
        "pr": payload.get("pr", 435),
        "schema": schema or ("synthetic" if synthetic else ""),
        "state": status or "COMPARABLE",
        "status": status or "COMPARABLE",
        "paving_family": payload.get("paving_family") or document.get("typology") or "paralelepipedo",
        "target": payload.get("target") or payload.get("target_contract_id") or document.get("target_contract_id"),
        "n_used": n_used,
        "metric": metric or COMPARABLE_METRIC,
        "unit": unit or COMPARABLE_UNIT,
        "median": median,
        "p25": p25,
        "p75": p75,
        "content_hash": content,
        "catalog_mode": catalog_mode or ("fixture" if synthetic else "live_candidate"),
        "publication_authorization": False,
        "index_authorization": False,
        "national_claim_authorized": False,
        "source_ref": payload.get("source_ref") or "scripts.contract_comparables public contract",
    }
