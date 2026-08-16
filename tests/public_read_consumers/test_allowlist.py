"""Unauthorized fields and unnecessary PII stay out of public payloads."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.public_read_consumers.allowlist import scan_pii, unauthorized_fields
from scripts.public_read_consumers.export import build_contract_analysis_bundle, build_single_payload
from scripts.public_read_consumers.hashutil import scan_forbidden_tokens
from scripts.public_read_consumers.market_answer import CONSUMER_ID as MARKET_ID
from scripts.public_read_consumers.xray import CONSUMER_ID as XRAY_ID

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "public_read_consumers"


def test_contract_analysis_has_no_unauthorized_or_pii() -> None:
    raw = json.loads((FIXTURES / "contract_analysis" / "catalog.json").read_text(encoding="utf-8"))
    bundle = build_contract_analysis_bundle(raw)
    for item in bundle["analyses"]:
        assert unauthorized_fields(item, consumer_id="web-cfg/contract-analysis") == []
        assert scan_pii(item) == []
        assert scan_forbidden_tokens(item) == []


def test_market_and_xray_have_no_pii_or_brand() -> None:
    market_raw = json.loads((FIXTURES / "market_answer" / "ready.json").read_text(encoding="utf-8"))
    xray_raw = json.loads((FIXTURES / "xray" / "ready.json").read_text(encoding="utf-8"))
    market = build_single_payload(MARKET_ID, market_raw)
    xray = build_single_payload(XRAY_ID, xray_raw)
    assert unauthorized_fields(market, consumer_id=MARKET_ID) == []
    assert unauthorized_fields(xray, consumer_id=XRAY_ID) == []
    assert scan_pii(market) == []
    assert scan_pii(xray) == []
    assert scan_forbidden_tokens(market) == []
    assert scan_forbidden_tokens(xray) == []
