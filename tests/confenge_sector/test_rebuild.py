"""Adversarial invariants for the untruncated sector full-lake rebuild."""

from __future__ import annotations

import inspect

from scripts.confenge_sector.rebuild import (
    SectorRootBucket,
    _source_sql,
    _stream_bucket_batches,
    main,
)


def _contract(root: str, idx: int, objeto: str) -> dict:
    return {
        "fornecedor_cnpj": f"{root}000100",
        "fornecedor_nome": "CONSTRUTORA TESTE LTDA",
        "objeto_contrato": objeto,
        "contrato_id": str(idx),
        "orgao_nome": f"ORGAO {idx % 3}",
        "data_publicacao": f"202{idx % 5}-01-01",
    }


def test_streaming_history_denominator_is_not_classify_buffer() -> None:
    bucket = SectorRootBucket(cnpj_raiz="12345678")
    for idx in range(750):
        bucket.add(_contract("12345678", idx, "Execucao de obra de pavimentacao"))

    stats = bucket.history.as_stats()
    assert stats["total_contract_count_full_history"] == 750
    assert stats["relevant_contract_count"] == 750
    assert stats["denominator_invariant_ok"] is True
    assert bucket.branch_cnpjs == set()


def test_full_lake_source_query_has_no_population_limit() -> None:
    stream_sql, denominator_sql, _ = _source_sql(
        [
            "id",
            "fornecedor_cnpj",
            "fornecedor_cnpj_8",
            "fornecedor_nome",
            "objeto_contrato",
        ]
    )
    assert "LIMIT" not in stream_sql.upper()
    assert "ORDER BY" in stream_sql.upper()
    assert "FORNECEDOR_CNPJ_8::TEXT ASC" in stream_sql.upper()
    assert "COUNT(DISTINCT" in denominator_sql.upper()
    parser_source = inspect.getsource(main)
    assert "--limit" not in parser_source
    assert "--max-companies" not in parser_source
    assert "--top-n" not in parser_source


def test_root_ordered_stream_is_memory_bounded_without_splitting_roots() -> None:
    rows = [
        {
            "id": str(idx),
            "fornecedor_cnpj": f"{root}000100",
            "fornecedor_cnpj_8": root,
            "fornecedor_nome": "CONSTRUTORA TESTE LTDA",
            "objeto_contrato": "Execucao de obra",
            "__cnpj_root": root,
        }
        for idx, root in enumerate(
            ["11111111", "11111111", "22222222", "33333333", "33333333", "44444444"]
        )
    ]

    class Cursor:
        def __init__(self) -> None:
            self.offset = 0
            self.itersize = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _sql: str) -> None:
            return None

        def fetchmany(self, size: int):
            batch = rows[self.offset : self.offset + size]
            self.offset += len(batch)
            return batch

    class Connection:
        def cursor(self, *, name: str):
            assert name.startswith("confenge_sector_")
            return Cursor()

    batches = list(
        _stream_bucket_batches(
            Connection(),
            stream_sql="SELECT fixture",
            available=[
                "id",
                "fornecedor_cnpj",
                "fornecedor_cnpj_8",
                "fornecedor_nome",
                "objeto_contrato",
            ],
            row_batch_size=3,
            root_batch_size=2,
        )
    )
    flattened = [bucket for batch in batches for bucket in batch]
    assert [len(batch) for batch in batches] == [2, 2]
    assert [bucket.cnpj_raiz for bucket in flattened] == [
        "11111111",
        "22222222",
        "33333333",
        "44444444",
    ]
    assert [bucket.history.total for bucket in flattened] == [2, 1, 2, 1]
