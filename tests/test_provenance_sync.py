"""Unit tests for the fail-closed synchronous provenance contract."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.crawl import provenance_sync


class RecordingTracker:
    def __init__(self) -> None:
        self.started: dict[str, Any] | None = None
        self.completed: dict[str, Any] | None = None
        self.failed: dict[str, Any] | None = None

    async def start_run(self, run_id: str, source: str, **kwargs: Any) -> None:
        self.started = {"run_id": run_id, "source": source, **kwargs}

    async def complete_run(self, run_id: str, **kwargs: Any) -> None:
        self.completed = {"run_id": run_id, **kwargs}

    async def fail_run(self, run_id: str, **kwargs: Any) -> None:
        self.failed = {"run_id": run_id, **kwargs}


@pytest.fixture
def tracker(monkeypatch: pytest.MonkeyPatch) -> RecordingTracker:
    recording = RecordingTracker()
    monkeypatch.setattr(provenance_sync, "_tracker", recording)
    return recording


def test_start_returns_the_persisted_run_id(tracker: RecordingTracker) -> None:
    run_id = provenance_sync.provenance_start(source="pcp", mode="incremental")

    assert run_id.startswith("pcp-")
    assert tracker.started == {
        "run_id": run_id,
        "source": "pcp",
        "mode": "incremental",
        "params": None,
    }


def test_complete_forwards_schema_counts_by_name(tracker: RecordingTracker) -> None:
    provenance_sync.provenance_complete(
        run_id="run-001",
        source="pcp",
        records_fetched=11,
        records_deduplicated=2,
        records_upserted=7,
        records_dlq=1,
        records_failed=1,
        pages_planned=4,
        pages_completed=3,
        watermarks_committed=2,
        duration_ms=987,
    )

    assert tracker.completed == {
        "run_id": "run-001",
        "source": "pcp",
        "records_fetched": 11,
        "records_deduplicated": 2,
        "records_upserted": 7,
        "records_dlq": 1,
        "records_failed": 1,
        "pages_planned": 4,
        "pages_completed": 3,
        "watermarks_committed": 2,
        "duration_ms": 987,
    }


def test_fail_forwards_error_and_counts_by_name(tracker: RecordingTracker) -> None:
    provenance_sync.provenance_fail(
        run_id="run-002",
        source="dom_sc",
        error_message="upstream timeout",
        records_fetched=5,
        records_failed=1,
        duration_ms=321,
    )

    assert tracker.failed is not None
    assert tracker.failed["run_id"] == "run-002"
    assert tracker.failed["source"] == "dom_sc"
    assert tracker.failed["error_message"] == "upstream timeout"
    assert tracker.failed["records_fetched"] == 5
    assert tracker.failed["records_failed"] == 1
    assert tracker.failed["duration_ms"] == 321


def test_terminal_persistence_error_is_propagated(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenTracker(RecordingTracker):
        async def complete_run(self, run_id: str, **kwargs: Any) -> None:
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(provenance_sync, "_tracker", BrokenTracker())

    with pytest.raises(RuntimeError, match="database unavailable"):
        provenance_sync.provenance_complete(run_id="run-003", source="pcp")


def test_positional_terminal_arguments_are_rejected() -> None:
    with pytest.raises(TypeError):
        provenance_sync.provenance_complete("run-004", "pcp", 10)  # type: ignore[misc]

    with pytest.raises(TypeError):
        provenance_sync.provenance_fail("run-004", "pcp", "error")  # type: ignore[misc]
