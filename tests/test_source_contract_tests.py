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


def test_pncp_live_probe_never_sends_page_size_below_minimum():
    from scripts.crawl.pncp_contract import PNCP_TAMANHO_PAGINA_MIN, legal_pncp_page_size
    from scripts.ops.source_contract_tests import (
        build_pncp_live_probe_url,
        parse_tamanho_pagina,
        pncp_live_page_size,
    )

    size = pncp_live_page_size()
    url = build_pncp_live_probe_url(data_inicial="20260801", data_final="20260803")
    parsed = parse_tamanho_pagina(url)
    assert size >= PNCP_TAMANHO_PAGINA_MIN
    assert parsed == size
    assert parsed is not None and parsed >= 10
    assert size == legal_pncp_page_size() or size >= PNCP_TAMANHO_PAGINA_MIN
    try:
        build_pncp_live_probe_url(data_inicial="20260801", data_final="20260803", tamanho_pagina=5)
        raise AssertionError("illegal page size must fail closed")
    except ValueError as exc:
        assert "INTERNAL_DEFECT" in str(exc)
        assert getattr(exc, "code", "INTERNAL_DEFECT") == "INTERNAL_DEFECT"


def test_invalid_pncp_page_size_config_fails_before_network(monkeypatch):
    from scripts.crawl.pncp_contract import (
        PNCPPageSizeError,
        require_legal_pncp_page_size,
    )
    from scripts.ops.source_contract_tests import (
        build_pncp_live_probe_url,
        http_probe,
        pncp_live_page_size,
        run_contract_suite,
    )

    monkeypatch.setenv("PNCP_PAGE_SIZE", "5")
    try:
        pncp_live_page_size()
        raise AssertionError("illegal PNCP_PAGE_SIZE must fail before URL build")
    except PNCPPageSizeError as exc:
        assert exc.code == "CONFIGURATION_ERROR"
        assert "CONFIGURATION_ERROR" in str(exc)

    try:
        require_legal_pncp_page_size()
        raise AssertionError("require_legal must not clamp illegal env onto the wire")
    except PNCPPageSizeError as exc:
        assert exc.code == "CONFIGURATION_ERROR"

    called: list[str] = []

    def _forbid_pncp_http(url: str, **_kwargs):
        if "pncp.gov.br" in url or "tamanhoPagina=" in url:
            called.append(url)
            raise AssertionError(f"http_probe must not run for illegal page size: {url}")
        return {
            "ok": False,
            "status": None,
            "url": url,
            "bytes": 0,
            "body_prefix": "",
            "error": "mocked-non-pncp",
            "kind": "network",
        }

    monkeypatch.setattr("scripts.ops.source_contract_tests.http_probe", _forbid_pncp_http)
    result = run_contract_suite(live=True)
    assert called == []
    live_size = result["checks"]["pncp_live_page_size"]
    assert live_size["ok"] is False
    assert live_size["class"] == "CONFIGURATION_ERROR"
    endpoint = result["checks"]["pncp_endpoint_live"]
    assert endpoint["ok"] is False
    assert endpoint["outcome"] == "CONFIGURATION_ERROR"
    assert endpoint.get("url") is None
    schema = result["checks"]["pncp_schema_live"]
    assert schema["ok"] is False
    # The shipped http_probe entry point still exists; we just never reached it.
    assert callable(http_probe)
    try:
        build_pncp_live_probe_url(data_inicial="20260801", data_final="20260803")
        raise AssertionError("builder must refuse illegal env")
    except PNCPPageSizeError as exc:
        assert exc.code == "CONFIGURATION_ERROR"


def test_illegal_explicit_page_size_never_calls_http_probe(monkeypatch):
    from scripts.crawl.pncp_contract import PNCPPageSizeError
    from scripts.ops.source_contract_tests import build_pncp_live_probe_url, http_probe

    called: list[str] = []

    def _forbid_http(url: str, **_kwargs):
        called.append(url)
        raise AssertionError(f"network reached with {url}")

    monkeypatch.setattr("scripts.ops.source_contract_tests.http_probe", _forbid_http)
    try:
        build_pncp_live_probe_url(data_inicial="20260801", data_final="20260803", tamanho_pagina=5)
        raise AssertionError("expected fail-closed")
    except PNCPPageSizeError as exc:
        assert exc.code == "INTERNAL_DEFECT"
    assert called == []
    assert callable(http_probe)


def test_invalid_pncp_page_size_400_is_internal_defect_not_transient():
    from scripts.ops.source_contract_tests import classify_http_outcome

    outcome = classify_http_outcome(
        400,
        "http_400",
        body='{"message":"must be greater than or equal to 10","status":"400"}',
        requested_page_size=5,
    )
    assert outcome == "INTERNAL_DEFECT"
    assert outcome != "EXTERNAL_TRANSIENT"
    assert outcome != "success_zero_records"
    # legal page size + unrelated 403 stays forbidden, not defect-from-page-size
    assert classify_http_outcome(403, "http_403", requested_page_size=10) == "http_403_forbidden"
    assert classify_http_outcome(429, "http_429", requested_page_size=10) == "http_429_rate_limited"
    assert classify_http_outcome(503, "http_5xx", requested_page_size=10) == "http_5xx_server_error"


def test_offline_suite_reports_legal_page_size_and_internal_defect_class():
    from scripts.crawl.pncp_contract import PNCP_TAMANHO_PAGINA_MIN
    from scripts.ops.source_contract_tests import parse_tamanho_pagina, run_contract_suite

    result = run_contract_suite(live=False)
    probe = result["checks"]["pncp_probe_page_size"]
    assert probe["ok"] is True
    assert probe["tamanhoPagina"] >= PNCP_TAMANHO_PAGINA_MIN
    assert probe["min"] == 10
    parsed = parse_tamanho_pagina(probe["url"])
    assert parsed == probe["tamanhoPagina"]
    assert parsed is not None and parsed >= 10
    assert "pncp_contract.require_legal_pncp_page_size" in probe["page_size_source"]
    invalid = result["checks"]["pncp_invalid_page_is_internal_defect"]
    assert invalid["ok"] is True
    assert invalid["outcome"] == "INTERNAL_DEFECT"


def test_empty_live_body_is_not_schema_proof(monkeypatch):
    from scripts.ops.source_contract_tests import run_contract_suite

    def _ok_empty(url: str, **_kwargs):
        return {
            "ok": True,
            "status": 200,
            "url": url,
            "bytes": 2,
            "body_prefix": "{}",
            "body": "{}",
            "error": None,
        }

    class _EmptyResp:
        def read(self) -> bytes:
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

    monkeypatch.setattr("scripts.ops.source_contract_tests.http_probe", _ok_empty)
    monkeypatch.setattr("scripts.ops.source_contract_tests.urlopen", lambda *_a, **_k: _EmptyResp())
    result = run_contract_suite(live=True)
    page = result["checks"]["pncp_live_page_size"]
    assert page["ok"] is True
    assert page["tamanhoPagina"] >= 10
    schema = result["checks"]["pncp_schema_live"]
    assert schema["ok"] is False
    assert "empty" in str(schema.get("error") or "").lower() or schema.get("empty_body_not_proof")


def test_contract_alerts():
    from scripts.ops.source_contract_tests import detect_contract_alerts

    alerts = detect_contract_alerts(payload={"data": []})
    codes = {a["code"] for a in alerts}
    assert "required_field_missing" in codes
    drop = detect_contract_alerts(
        payload={"data": [{"x": 1}], "totalRegistros": 1, "totalPaginas": 1, "numeroPagina": 1}, previous_volume=100
    )
    assert any(a["code"] == "abrupt_volume_drop" for a in drop)
