"""B2G X-Ray facts only; denied tokens and invalid CNPJ."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.public_read_consumers.allowlist import scan_xray_denied
from scripts.public_read_consumers.hashutil import content_hash
from scripts.public_read_consumers.xray import NEEDS_DATA, normalize_cnpj, project_xray

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "public_read_consumers" / "xray"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_normalizes_cnpj_and_returns_observed_facts() -> None:
    payload = project_xray(_load("ready.json"))
    assert payload["input"]["cnpj_normalized"] == "83102277000152"
    assert payload["answer_state"] == "DATA_READY"
    assert payload["observed_portfolio"]["contract_count"] == 2
    assert payload["second_read_candidates"][0]["kind"] == "candidate_ref"
    assert payload["official_live"] is False
    assert scan_xray_denied(payload) == []


def test_unknown_cnpj_needs_data() -> None:
    payload = project_xray(_load("unknown_cnpj.json"))
    assert payload["input"]["cnpj_normalized"] is None
    assert payload["answer_state"] == NEEDS_DATA
    assert "input_unknown" in payload["reason_codes"]
    assert payload["contracts"] == []


def test_rejects_risk_credit_pain_tokens() -> None:
    raw = _load("ready.json")
    raw["limitations"] = ["score de risco e irregularidade"]
    with pytest.raises(ValueError, match="xray_denied_field"):
        project_xray(raw)


def test_strips_total_share_without_denominator() -> None:
    raw = _load("ready.json")
    raw["concentration"]["market_share_total"] = 0.4
    del raw["concentration"]["denominator"]
    payload = project_xray(raw)
    assert "market_share_total" not in payload["concentration"]
    assert "share_without_denominator" in payload["reason_codes"]


def test_normalize_cnpj_rejects_short_and_zero() -> None:
    assert normalize_cnpj("12.345") is None
    assert normalize_cnpj("00.000.000/0000-00") is None
    assert normalize_cnpj("83.102.277/0001-52") == "83102277000152"


def test_determinism() -> None:
    raw = _load("ready.json")
    first = project_xray(raw)
    second = project_xray(raw)
    assert first["content_hash"] == second["content_hash"]
    body = {key: value for key, value in first.items() if key != "content_hash"}
    assert first["content_hash"] == content_hash(body)
