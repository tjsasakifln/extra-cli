"""#326 physically memory-bounded snapshot load above one chunk."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.ops.multi_source_open_pack import db_loaders
from scripts.ops.multi_source_open_pack.db_loaders import (
    JsonlSpool,
    load_opportunity_intel_snapshot,
)


def _row(index: int, total: int) -> dict[str, Any]:
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
        "_snapshot_id": "100:100:",
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
        batch = self.rows[self.position : self.position + size]
        self.position += len(batch)
        return batch

    def close(self) -> None:
        self.connection.closed = True


class _Connection:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.sql = ""
        self.params: tuple[Any, ...] = ()
        self.closed = False

    def cursor(self, name: str | None = None) -> _Cursor:
        return _Cursor(self.rows, self)


def test_snapshot_retains_only_chunk_not_full_population(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    total = 250
    page_size = 40
    connection = _Connection([_row(index, total) for index in range(total)])
    monkeypatch.setattr(db_loaders, "_table_exists", lambda *_args: True)

    observations, snapshot = load_opportunity_intel_snapshot(
        connection,
        page_size=page_size,
    )

    assert isinstance(observations, JsonlSpool)
    assert snapshot["physical_memory_bounded"] is True
    assert snapshot["eligible_count"] == total
    assert snapshot["rows_read"] == total
    assert snapshot["peak_retained_items"] <= page_size
    assert observations.peak_retained <= page_size or observations.peak_retained == 0
    assert len(observations) == total
    streamed = list(observations)
    assert len(streamed) == total
    assert observations.peak_retained <= page_size
    assert {item.id_externo for item in streamed} == {
        f"82922233000100-1-{index:06d}/2026" for index in range(total)
    }
