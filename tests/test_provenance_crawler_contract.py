"""Crawler regressions for the keyword-only provenance terminal contract (#342)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from scripts.crawl import (
    ciga_ckan_crawler as ciga,
)
from scripts.crawl import (
    doe_sc_crawler as doe,
)
from scripts.crawl import (
    dom_sc_crawler as dom,
)
from scripts.crawl import (
    pcp_crawler as pcp,
)
from scripts.crawl import (
    provenance_sync,
)
from scripts.crawl import (
    tce_sc_crawler as tce,
)


class ProvenanceRecorder:
    def __init__(self, *, complete_error: Exception | None = None) -> None:
        self.complete_error = complete_error
        self.started: list[dict[str, Any]] = []
        self.completed: list[dict[str, Any]] = []
        self.failed: list[dict[str, Any]] = []

    def start(self, *, source: str, mode: str = "full", params=None) -> str:
        call = {"source": source, "mode": mode, "params": params}
        self.started.append(call)
        return f"persisted-{source}-run"

    def complete(self, *, run_id: str, source: str, **counts: Any) -> None:
        self.completed.append({"run_id": run_id, "source": source, **counts})
        if self.complete_error is not None:
            raise self.complete_error

    def fail(self, *, run_id: str, source: str, error_message: str, **counts: Any) -> None:
        self.failed.append({"run_id": run_id, "source": source, "error_message": error_message, **counts})


def _install_recorder(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    recorder: ProvenanceRecorder,
) -> None:
    targets = [module]
    if module is ciga:
        targets.append(provenance_sync)
    for target in targets:
        monkeypatch.setattr(target, "provenance_start", recorder.start, raising=False)
        monkeypatch.setattr(target, "provenance_complete", recorder.complete, raising=False)
        monkeypatch.setattr(target, "provenance_fail", recorder.fail, raising=False)


def _configure_pcp(monkeypatch: pytest.MonkeyPatch) -> Callable[[], list[dict]]:
    monkeypatch.setattr(pcp, "INGESTION_UFS", ["SC"])
    monkeypatch.setattr(pcp, "_PCP_UF_CODE", {"SC": "42"})
    monkeypatch.setattr(
        pcp,
        "_fetch_page",
        lambda *_args: ([{"unidadeCompradora": {"uf": "SC"}}], False),
    )
    return lambda: pcp.crawl(mode="incremental")


def _configure_doe(monkeypatch: pytest.MonkeyPatch) -> Callable[[], list[dict]]:
    monkeypatch.setattr(doe, "DOE_SC_ENABLED", True)
    monkeypatch.setattr(doe, "_load_categories", lambda: None)
    monkeypatch.setattr(doe, "_fetch_materias", lambda *_args: [{"id": 1}, {"id": 2}])
    return lambda: doe.crawl(mode="incremental")


def _configure_dom(monkeypatch: pytest.MonkeyPatch) -> Callable[[], list[dict]]:
    monkeypatch.setattr(dom, "DOM_SC_ENABLED", True)
    monkeypatch.setattr(dom, "DOM_SC_CPF", "123")
    monkeypatch.setattr(dom, "DOM_SC_CNPJ", "456")
    monkeypatch.setattr(dom, "DOM_SC_API_KEY", "key")
    monkeypatch.setattr(dom, "_fetch_publications", lambda *_args: [{"id": 1}])
    return lambda: dom.crawl(mode="incremental")


def _configure_tce(monkeypatch: pytest.MonkeyPatch) -> Callable[[], list[dict]]:
    monkeypatch.setattr(tce, "TCE_SC_ENABLED", True)
    monkeypatch.setattr(tce, "_fetch_licitacoes", lambda **_kwargs: [{"id": 1}])
    monkeypatch.setattr(tce, "_fetch_contratos", lambda **_kwargs: [{"id": 2}])
    monkeypatch.setattr(tce.time, "sleep", lambda _seconds: None)
    return lambda: tce.crawl(mode="incremental")


def _configure_ciga(monkeypatch: pytest.MonkeyPatch) -> Callable[[], list[dict]]:
    monkeypatch.setattr(ciga, "list_domsc_months", lambda: ["domsc-janeiro-2026"])
    monkeypatch.setattr(ciga, "download_month", lambda _month: [{"id": 1}, {"id": 2}, {"id": 3}])
    return lambda: ciga.crawl(mode="incremental")


CRAWLERS = [
    ("pcp", pcp, _configure_pcp, 1),
    ("doe_sc", doe, _configure_doe, 2),
    ("dom_sc", dom, _configure_dom, 1),
    ("tce_sc", tce, _configure_tce, 2),
    ("ciga_ckan", ciga, _configure_ciga, 3),
]


@pytest.mark.parametrize(("source", "module", "configure", "expected_fetched"), CRAWLERS)
def test_crawler_reuses_persisted_run_identity_and_named_counts(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    module: Any,
    configure: Callable[[pytest.MonkeyPatch], Callable[[], list[dict]]],
    expected_fetched: int,
) -> None:
    recorder = ProvenanceRecorder()
    _install_recorder(monkeypatch, module, recorder)
    crawl = configure(monkeypatch)

    crawl()

    assert recorder.started and recorder.started[0]["source"] == source
    assert recorder.completed == [
        {
            "run_id": f"persisted-{source}-run",
            "source": source,
            "records_fetched": expected_fetched,
            "duration_ms": recorder.completed[0]["duration_ms"],
        }
    ]
    assert isinstance(recorder.completed[0]["duration_ms"], int)
    assert recorder.failed == []


@pytest.mark.parametrize(("source", "module", "configure", "_expected_fetched"), CRAWLERS)
def test_crawler_does_not_convert_terminal_persistence_failure_to_success(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    module: Any,
    configure: Callable[[pytest.MonkeyPatch], Callable[[], list[dict]]],
    _expected_fetched: int,
) -> None:
    recorder = ProvenanceRecorder(complete_error=RuntimeError("terminal persistence unavailable"))
    _install_recorder(monkeypatch, module, recorder)
    crawl = configure(monkeypatch)

    with pytest.raises(RuntimeError, match="terminal persistence unavailable"):
        crawl()

    assert recorder.completed[0]["source"] == source


def test_tce_failed_run_does_not_advance_watermark(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = ProvenanceRecorder()
    _install_recorder(monkeypatch, tce, recorder)
    monkeypatch.setattr(tce, "TCE_SC_ENABLED", True)
    monkeypatch.setattr(tce, "_fetch_licitacoes", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("phase failed")))
    monkeypatch.setattr(tce, "_fetch_contratos", lambda **_kwargs: [{"id": 2}])
    monkeypatch.setattr(tce.time, "sleep", lambda _seconds: None)
    committed: list[dict[str, Any]] = []
    monkeypatch.setattr(tce, "watermark_commit", lambda **kwargs: committed.append(kwargs))

    records = tce.crawl(mode="incremental", resume=True)

    assert records == [{"id": 2, "_tipo": "contrato"}]
    assert recorder.completed == []
    assert recorder.failed[0]["source"] == "tce_sc"
    assert recorder.failed[0]["records_failed"] == 1
    assert committed == []
