"""Integral, reconciled snapshot loading above the former 10k cap (#288)."""

from __future__ import annotations

import math
import tracemalloc
from typing import Any

import pytest

from scripts.ops.multi_source_open_pack import db_loaders
from scripts.ops.multi_source_open_pack.db_loaders import (
    SnapshotReconciliationError,
    load_opportunity_intel_snapshot,
)


def _row(index: int, total: int, snapshot_id: str = "100:100:") -> dict[str, Any]:
    return {
        "id": index + 1,
        "source": "pncp",
        "source_id": f"source-{index:05d}",
        "numero_controle_pncp": f"82922233000100-1-{index:06d}/2026",
        "orgao_cnpj": "82922233000100",
        "orgao_nome": "MUNICIPIO DE FLORIANOPOLIS",
        "municipio": "FLORIANOPOLIS",
        "uf": "SC",
        "objeto": f"Pavimentacao {index}",
        "modalidade": "Concorrencia",
        "valor_estimado": 1000 + index,
        "status_canonico": "open",
        "data_publicacao": "2026-08-01",
        "data_abertura": "2026-08-10",
        "data_encerramento": "2026-09-01",
        "link_edital": f"https://pncp.gov.br/{index}",
        "source_url": "",
        "run_id": "run-snapshot",
        "crawl_batch_id": "batch-snapshot",
        "proveniencia": {},
        "_snapshot_eligible_count": total,
        "_snapshot_id": snapshot_id,
        "_snapshot_row_present": True,
    }


class _Cursor:
    def __init__(self, rows: list[dict[str, Any]], connection: _Connection):
        self.rows = rows
        self.connection = connection
        self.position = 0
        self.itersize = 0

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.connection.sql = sql
        self.connection.params = params

    def fetchmany(self, size: int) -> list[dict[str, Any]]:
        self.connection.fetch_sizes.append(size)
        batch = self.rows[self.position : self.position + size]
        self.position += len(batch)
        return batch

    def close(self) -> None:
        self.connection.closed = True


class _Connection:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.cursor_name = ""
        self.sql = ""
        self.params: tuple[Any, ...] = ()
        self.fetch_sizes: list[int] = []
        self.closed = False

    def cursor(self, name: str | None = None) -> _Cursor:
        self.cursor_name = name or ""
        return _Cursor(self.rows, self)


def test_more_than_ten_thousand_rows_are_read_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    total = 10_037
    page_size = 777
    connection = _Connection([_row(index, total) for index in range(total)])
    monkeypatch.setattr(db_loaders, "_table_exists", lambda *_args: True)

    tracemalloc.start()
    try:
        observations, snapshot = load_opportunity_intel_snapshot(
            connection,
            page_size=page_size,
        )
        _current_memory, peak_memory = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert len(observations) == total
    assert len({observation.id_externo for observation in observations}) == total
    assert snapshot["eligible_count"] == total
    assert snapshot["rows_read"] == total
    assert snapshot["pages_fetched"] == math.ceil(total / page_size)
    assert snapshot["complete"] is True
    assert snapshot["presentation_truncated"] is False
    assert snapshot["estimated_memory_bytes"] < snapshot["memory_budget_bytes"]
    assert peak_memory < snapshot["memory_budget_bytes"]
    assert connection.cursor_name.startswith("extra_opportunity_intel_")
    assert "LIMIT" not in connection.sql.upper()
    assert "MATERIALIZED" in connection.sql
    assert "ORDER BY eligible.id ASC" in connection.sql
    assert set(connection.fetch_sizes) == {page_size}
    assert connection.closed is True


def test_snapshot_count_mismatch_fails_instead_of_returning_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection([_row(index, 4) for index in range(3)])
    monkeypatch.setattr(db_loaders, "_table_exists", lambda *_args: True)

    with pytest.raises(SnapshotReconciliationError, match="rows_read=3"):
        load_opportunity_intel_snapshot(connection, page_size=2)


def test_memory_budget_exhaustion_fails_without_successful_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection([_row(0, 1)])
    monkeypatch.setattr(db_loaders, "_table_exists", lambda *_args: True)

    with pytest.raises(SnapshotReconciliationError, match="exceeds budget"):
        load_opportunity_intel_snapshot(
            connection,
            page_size=1,
            memory_budget_bytes=1,
        )
