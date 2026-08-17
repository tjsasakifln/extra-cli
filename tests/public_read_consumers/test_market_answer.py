"""Market Answer grain, NEEDS_DATA and #302 fail-closed."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.public_read_consumers.hashutil import content_hash
from scripts.public_read_consumers.market_answer import (
    GRAIN,
    GRAIN_NOT,
    NEEDS_DATA,
    SCHEMA,
    project_market_answer,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "public_read_consumers" / "market_answer"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_ready_answer_keeps_integral_nominal_grain() -> None:
    payload = project_market_answer(_load("ready.json"))
    assert payload["schema"] == SCHEMA
    assert payload["grain"] == GRAIN
    assert payload["grain"] not in GRAIN_NOT
    assert payload["answer_state"] == "DATA_READY"
    assert payload["stats"]["median"] == 740874.59
    assert payload["stats"]["n"] == 12
    assert payload["official_live"] is False
    assert payload["producer_status"] == "CONTRACT_FIXTURE"
    assert "cost_per_km" not in json.dumps(payload["stats"])
    assert payload["claim_authorization"]["national_claim_allowed"] is False


def test_typology_or_coverage_failure_is_needs_data() -> None:
    payload = project_market_answer(_load("needs_data.json"))
    assert payload["answer_state"] == NEEDS_DATA
    assert "NEEDS_DATA" in payload["reason_codes"]
    assert payload["stats"]["median"] is None
    assert payload["stats"]["n"] == 3


def test_national_claim_blocked_without_302_pass() -> None:
    payload = project_market_answer(_load("national_without_302.json"))
    assert payload["claim_authorization"]["national_claim_allowed"] is False
    assert "national_claim_blocked" in payload["reason_codes"]
    assert payload["geography"]["code"] is None
    assert payload["answer_state"] == NEEDS_DATA
    assert payload["stats"]["median"] is None
    assert payload["stats"]["p25"] is None
    assert payload["stats"]["p75"] is None
    assert payload["distribution"] == []
    assert payload["series"] == []


def test_commercial_universe_never_national_denominator() -> None:
    payload = project_market_answer(_load("extra_1093.json"))
    assert payload["claim_authorization"]["national_claim_allowed"] is False
    assert payload["claim_authorization"]["commercial_universe_used_as_denominator"] is True
    assert "inconsistent_denominator_commercial_universe" in payload["reason_codes"]
    assert "denominator_failed" in payload["reason_codes"]
    assert payload["answer_state"] == NEEDS_DATA
    assert payload["stats"]["median"] is None
    assert payload["stats"]["p25"] is None
    assert payload["stats"]["p75"] is None
    dumped = json.dumps(payload)
    assert "extra_1093" not in dumped
    assert "Extra 1093" not in dumped


def test_cost_per_km_grain_is_refused() -> None:
    raw = _load("ready.json")
    raw["grain"] = "cost_per_km"
    payload = project_market_answer(raw)
    assert payload["answer_state"] == NEEDS_DATA
    assert payload["grain"] == GRAIN
    assert "typology_failed" in payload["reason_codes"]


def test_determinism() -> None:
    raw = _load("ready.json")
    first = project_market_answer(raw)
    second = project_market_answer(raw)
    assert first["content_hash"] == second["content_hash"]
    body = {key: value for key, value in first.items() if key != "content_hash"}
    assert first["content_hash"] == content_hash(body)
