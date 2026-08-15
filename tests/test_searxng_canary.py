"""Tests for the DDGS vs SearXNG canary reporter (no live web)."""

from __future__ import annotations

from scripts.decision_unit_intelligence.search_http import SearchBackendUnavailableError
from scripts.decision_unit_intelligence.web_discovery import SearchHit
from scripts.ops.searxng_canary import build_report, compare_backend_hits, summarize_account


class _Term:
    value = "NO_ROUTE"


class _Ledger:
    def __init__(self) -> None:
        self.attempts = []
        self.duration_ms = 12
        self.cost_brl = 0.0
        self.bytes_touched = 40


class _Candidate:
    person_name = "João da Silva"


class _Account:
    def __init__(self) -> None:
        self.cnpj = "00820854000114"
        self.legal_name = "EMPRESA EXEMPLO"
        self.terminal = _Term()
        self.candidates = [_Candidate()]
        self.routes = []
        self.evidence = []
        self.ledger = _Ledger()


def test_compare_and_report_keep_failures_visible() -> None:
    left = [SearchHit(url="https://a.example/x", title="A", snippet="a", engine="ddgs")]
    comparison = compare_backend_hits(
        ddgs_hits=left,
        searxng_hits=[],
        ddgs_error=None,
        searxng_error="http_429",
        ddgs_ms=40.0,
        searxng_ms=12.0,
    )
    assert comparison["searxng"]["error"] == "http_429"
    assert comparison["ddgs"]["hit_count"] == 1

    account = _Account()
    summary = summarize_account(account)
    assert summary["useful_yield"] is True
    assert summary["person_email_pages"] == []

    report = build_report(
        cnpjs=["00820854000114"],
        ddgs_rows=[
            {
                "cnpj": "00820854000114",
                "useful_yield": True,
                "person_email_pages": ["https://a.example/x"],
                "latency_ms": 40,
                "failures": [],
                "blocked": False,
                "cost_brl": 0.0,
            }
        ],
        searxng_rows=[
            {
                "cnpj": "00820854000114",
                "useful_yield": False,
                "person_email_pages": [],
                "latency_ms": 12,
                "failures": [str(SearchBackendUnavailableError("http_429", status_code=429))],
                "blocked": True,
                "cost_brl": 0.0,
            }
        ],
        searxng_url="http://127.0.0.1:18888",
    )
    assert report["recommendation"]["primary"] == "ddgs"
    assert "silent" in report["recommendation"]["reason"]
    assert report["searxng"]["summary"]["blocked"] == 1
