"""Refs #270 — per-domain retry, Retry-After, circuit and partial windows."""

from __future__ import annotations

import pytest
import requests

from scripts.crawl.pncp_contract import PNCP_TAMANHO_PAGINA_MAX_CONTRATACOES
from scripts.crawl.resilience.http_policy import HttpResiliencePolicy
from scripts.factory_spine.contracts import (
    build_pncp_consulta_envelope,
    decide_resilience,
    window_is_complete,
)


@pytest.mark.parametrize(
    ("status", "error", "expected_action", "expected_terminal"),
    [
        (403, "HTTP 403", "block", "BLOCKED"),
        (401, "login required", "block", "BLOCKED"),
        (429, "HTTP 429", "retry", None),
        (504, "HTTP 504", "retry", None),
        (None, requests.Timeout("timeout"), "retry", None),
    ],
)
def test_issue_270_status_matrix(
    status: int | None,
    error: object,
    expected_action: str,
    expected_terminal: str | None,
) -> None:
    decision = decide_resilience(
        http_status=status,
        error=error,
        attempt=1,
        max_attempts=5,
        retry_after=12.0 if status == 429 else None,
        pages_fetched=1,
        pages_expected=4,
    )
    assert decision.action == expected_action
    assert decision.terminal == expected_terminal
    assert decision.window_complete is False
    if status == 429:
        assert decision.sleep_seconds == 12.0
        assert decision.transient is True


def test_issue_270_captcha_is_permanent_block() -> None:
    decision = decide_resilience(http_status=200, error="captcha required", attempt=1, max_attempts=8)
    assert decision.action == "block"
    assert decision.terminal == "BLOCKED"
    assert decision.transient is False


def test_issue_270_partial_fetch_never_closes_window() -> None:
    assert (
        window_is_complete(
            outcome="succeeded",
            pages_fetched=2,
            pages_expected=5,
            request_completed=True,
            scope_complete=False,
            pagination_reconciled=False,
        )
        is False
    )
    decision = decide_resilience(
        http_status=200,
        error=None,
        attempt=1,
        max_attempts=3,
        pages_fetched=2,
        pages_expected=5,
    )
    assert decision.action == "succeed"
    assert decision.window_complete is False


def test_issue_270_circuit_open_and_retry_after_policy() -> None:
    open_circuit = decide_resilience(
        http_status=504,
        error="HTTP 504",
        attempt=1,
        max_attempts=5,
        circuit_state="open",
    )
    assert open_circuit.action == "wait_circuit"
    assert open_circuit.window_complete is False
    policy = HttpResiliencePolicy(max_delay=30.0, retry_after_fallback=60.0)
    delayed = decide_resilience(
        http_status=429,
        error="HTTP 429",
        attempt=2,
        max_attempts=5,
        retry_after=45.0,
        policy=policy,
    )
    assert delayed.sleep_seconds == 30.0


def test_issue_270_pncp_envelope_rejects_invalid_tamanho_pagina() -> None:
    envelope = build_pncp_consulta_envelope(
        pagina=1,
        tamanho_pagina=PNCP_TAMANHO_PAGINA_MAX_CONTRATACOES,
        data_inicial="20260101",
        data_final="20260107",
    )
    assert envelope["tamanhoPagina"] == "50"
    assert "tamanhoPagina=50" in envelope["url"]
    with pytest.raises(ValueError, match="invalid PNCP tamanhoPagina"):
        build_pncp_consulta_envelope(
            pagina=1,
            tamanho_pagina=1,
            data_inicial="20260101",
            data_final="20260107",
        )
