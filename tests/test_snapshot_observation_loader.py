"""Integral, reconciled snapshot loading above the former 10k cap (#288)."""

from __future__ import annotations

import math
import os
import tracemalloc
from typing import Any

import pytest

from scripts.ops.multi_source_open_pack import db_loaders
from scripts.ops.multi_source_open_pack.db_loaders import (
    LineageSelectionError,
    OpportunityLineageSelection,
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
    assert snapshot["memory_accounting"] == "chunk_spool_physical_bound"
    assert snapshot["physical_memory_bounded"] is True
    assert snapshot["peak_retained_items"] <= page_size
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


def test_invalid_memory_budget_configuration_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXTRA_OBSERVATION_MEMORY_BUDGET_MB", "not-a-number")

    with pytest.raises(ValueError, match="must be an integer"):
        db_loaders._memory_budget_bytes()


def test_selected_collection_run_is_exact_and_auditable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [_row(index, 2) for index in range(2)]
    for index, row in enumerate(rows):
        row["_lineage_run_id"] = 42
        row["_lineage_external_run_id"] = "weekly-collection-a"
        row["_lineage_source_record_id"] = f"pncp-{index}"
        row["_lineage_key"] = f"key-{index}"
    connection = _Connection(rows)
    monkeypatch.setattr(db_loaders, "_table_exists", lambda *_args: True)

    observations, snapshot = load_opportunity_intel_snapshot(
        connection,
        lineage=OpportunityLineageSelection(
            collection_id="collection-a",
            source_run_id=42,
            external_run_id="weekly-collection-a",
            mode="reused",
            expected_records=2,
            freshness_hours=3.5,
            freshness_sla_hours=24,
        ),
    )

    assert len(observations) == 2
    assert "source_snapshot_membership" in connection.sql
    assert connection.params == (42, "weekly-collection-a", "open", "upcoming")
    assert snapshot["lineage"] == {
        "collection_id": "collection-a",
        "source_run_id": 42,
        "external_run_id": "weekly-collection-a",
        "mode": "reused",
        "expected_records": 2,
        "loaded_records": 2,
        "sha256": snapshot["lineage"]["sha256"],
        "freshness_hours": 3.5,
        "freshness_sla_hours": 24,
    }
    assert len(snapshot["lineage"]["sha256"]) == 64


def test_row_without_selected_run_lineage_fails_package_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _row(0, 1)
    row["_lineage_run_id"] = 99
    row["_lineage_external_run_id"] = "weekly-foreign"
    row["_lineage_source_record_id"] = "foreign"
    connection = _Connection([row])
    monkeypatch.setattr(db_loaders, "_table_exists", lambda *_args: True)

    with pytest.raises(LineageSelectionError, match="expected run 42"):
        load_opportunity_intel_snapshot(
            connection,
            lineage=OpportunityLineageSelection(
                collection_id="collection-a",
                source_run_id=42,
                external_run_id="weekly-collection-a",
                mode="persisted",
                expected_records=1,
            ),
        )


def test_selected_run_count_must_equal_persisted_plus_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _row(0, 1)
    row["_lineage_run_id"] = 42
    row["_lineage_external_run_id"] = "weekly-collection-a"
    row["_lineage_source_record_id"] = "pncp-0"
    connection = _Connection([row])
    monkeypatch.setattr(db_loaders, "_table_exists", lambda *_args: True)

    with pytest.raises(LineageSelectionError, match="loaded=1 expected=2"):
        load_opportunity_intel_snapshot(
            connection,
            lineage=OpportunityLineageSelection(
                collection_id="collection-a",
                source_run_id=42,
                external_run_id="weekly-collection-a",
                mode="persisted",
                expected_records=2,
            ),
        )


def test_idempotent_reload_keeps_same_rows_and_lineage_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [_row(index, 2) for index in range(2)]
    for index, row in enumerate(rows):
        row["_lineage_run_id"] = 42
        row["_lineage_external_run_id"] = "weekly-collection-a"
        row["_lineage_source_record_id"] = f"pncp-{index}"
        row["_lineage_key"] = f"key-{index}"
    monkeypatch.setattr(db_loaders, "_table_exists", lambda *_args: True)
    lineage = OpportunityLineageSelection(
        collection_id="collection-a",
        source_run_id=42,
        external_run_id="weekly-collection-a",
        mode="persisted",
        expected_records=2,
    )

    first, first_snapshot = load_opportunity_intel_snapshot(
        _Connection([dict(row) for row in rows]), lineage=lineage
    )
    second, second_snapshot = load_opportunity_intel_snapshot(
        _Connection([dict(row) for row in rows]), lineage=lineage
    )

    assert [row.observation_id for row in first] == [
        row.observation_id for row in second
    ]
    assert first_snapshot["lineage"]["sha256"] == second_snapshot["lineage"]["sha256"]


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("REQUIRE_TEST_DB") != "1",
    reason="Set REQUIRE_TEST_DB=1 to run real lineage snapshot test",
)
def test_real_postgres_lineage_query_loads_only_the_selected_run() -> None:
    import psycopg2
    import psycopg2.extras

    dsn = os.getenv(
        "TEST_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test"
    )
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cursor:
            run_ids = []
            for suffix in ("selected", "foreign"):
                cursor.execute(
                    """
                    INSERT INTO opportunity_runs (
                        source, scope_key, external_run_id, status, scope_complete,
                        records_fetched, started_at, finished_at, metadata
                    ) VALUES (
                        'pncp', 'test-pr325-lineage', %s, 'completed', TRUE,
                        1, NOW(), NOW(), '{"test_pr325_lineage": true}'::jsonb
                    ) RETURNING id
                    """,
                    (f"test-pr325-{suffix}",),
                )
                run_ids.append(int(cursor.fetchone()["id"]))

            opportunity_ids = []
            for suffix in ("selected", "foreign"):
                source_id = f"test-pr325-lineage-{suffix}"
                cursor.execute(
                    """
                    INSERT INTO opportunity_intel (
                        source, source_id, content_hash, numero_controle_pncp,
                        objeto, orgao_cnpj, orgao_nome, municipio, uf,
                        status_canonico, data_publicacao, data_encerramento,
                        is_active, source_active, crawl_batch_id
                    ) VALUES (
                        'pncp', %s, %s, %s,
                        %s, '82922233000100', 'Comprador lineage',
                        'FLORIANOPOLIS', 'SC', 'open', CURRENT_DATE,
                        CURRENT_DATE + 30, TRUE, TRUE, 'test-pr325-lineage'
                    ) RETURNING id
                    """,
                    (
                        source_id,
                        f"hash-{source_id}",
                        source_id,
                        f"Objeto {suffix}",
                    ),
                )
                opportunity_ids.append(int(cursor.fetchone()["id"]))

            for run_id, suffix in zip(run_ids, ("selected", "foreign"), strict=True):
                source_id = f"test-pr325-lineage-{suffix}"
                cursor.execute(
                    """
                    INSERT INTO source_snapshot_membership (
                        source_run_id, source, scope_key, source_record_id,
                        canonical_opportunity_key
                    ) VALUES (%s, 'pncp', 'test-pr325-lineage', %s, %s)
                    """,
                    (run_id, source_id, source_id),
                )

        observations, snapshot = load_opportunity_intel_snapshot(
            conn,
            lineage=OpportunityLineageSelection(
                collection_id="test-pr325-collection",
                source_run_id=run_ids[0],
                external_run_id="test-pr325-selected",
                mode="persisted",
                expected_records=1,
            ),
        )

        assert [observation.id_externo for observation in observations] == [
            "test-pr325-lineage-selected"
        ]
        assert snapshot["rows_read"] == 1
        assert snapshot["lineage"]["source_run_id"] == run_ids[0]
        assert opportunity_ids[1] != opportunity_ids[0]
        assert "foreign" not in observations[0].objeto.lower()
    finally:
        conn.rollback()
        conn.close()
