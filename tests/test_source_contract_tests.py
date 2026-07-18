"""Tests for scripts.ops.source_contract_tests (DoD §13.3)."""
from __future__ import annotations

from scripts.ops.source_contract_tests import (
    fixture_pncp_payload,
    run_contract_suite,
    validate_pncp_schema,
)


def test_pncp_fixture_schema_ok():
    v = validate_pncp_schema(fixture_pncp_payload())
    assert v["ok"] is True
    assert v["pagination_ok"] is True
    assert v["n_items"] == 1


def test_pncp_schema_missing_keys():
    v = validate_pncp_schema({"foo": 1})
    assert v["ok"] is False
    assert v["missing_envelope_keys"]


def test_offline_suite_passes():
    result = run_contract_suite(live=False)
    assert result["summary"]["all_ok"] is True
    assert result["checks"]["pncp_schema_fixture"]["ok"] is True
    assert result["checks"]["active_sources_endpoints"]["ok"] is True
    assert result["checks"]["pcp_endpoint_registry"]["ok"] is True
    assert result["checks"]["compras_gov_endpoint_registry"]["ok"] is True


def test_http_error_not_confused_with_zero():
    from scripts.ops.source_contract_tests import classify_http_outcome

    assert classify_http_outcome(403, "http_403") != "success_zero_records"
    assert classify_http_outcome(429, "http_429") != "success_zero_records"
    assert classify_http_outcome(500, "http_5xx") != "success_zero_records"
    assert classify_http_outcome(None, "timeout") != "success_zero_records"
    assert classify_http_outcome(200, None, 0) == "success_zero_records"


def test_contract_alerts():
    from scripts.ops.source_contract_tests import detect_contract_alerts

    alerts = detect_contract_alerts(payload={"data": []})
    codes = {a["code"] for a in alerts}
    assert "required_field_missing" in codes
    drop = detect_contract_alerts(payload={"data": [{"x": 1}], "totalRegistros": 1, "totalPaginas": 1, "numeroPagina": 1}, previous_volume=100)
    assert any(a["code"] == "abrupt_volume_drop" for a in drop)
