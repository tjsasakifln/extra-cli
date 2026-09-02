"""Official PNCP identity must win over a technical table surrogate."""

from __future__ import annotations

import pytest

from scripts.confenge_outreach_pipeline.party_role import project_contractor_role
from scripts.confenge_target_fit import loader as target_fit_loader
from scripts.confenge_universe.source import (
    SourceConfig,
    _select_list,
    build_keyset_query,
    iter_contracts_keyset,
    normalize_contract_row,
    resolve_physical_map,
)


def test_table_with_id_and_pncp_control_number_keeps_official_identity() -> None:
    columns = ["id", "numero_controle_pncp", "ni_fornecedor", "valor_global"]
    physical = resolve_physical_map(columns)
    assert physical["contrato_id"] == "numero_controle_pncp"
    sql, params = build_keyset_query(
        columns=_select_list(columns, cursor_column="id"),
        physical_map=physical,
        cursor_column="id",
        keyset_contrato_id="25394409",
    )
    assert "ORDER BY id ASC" in sql
    assert "id > %s" in sql
    assert 25394409 in params
    row = normalize_contract_row(
        {"id": 25394409, "numero_controle_pncp": "00028986000108-1-000123/2026"},
        physical_map=physical,
    )
    assert row["contrato_id"] == "00028986000108-1-000123/2026"


def test_downstream_evidence_prefers_official_identity_when_both_exist() -> None:
    official = "00028986000108-1-000123/2026"
    projected = project_contractor_role(
        "00028986000108",
        [{
            "id": "25394409",
            "contrato_id": official,
            "supplier_cnpj14": "00028986000108",
            "buyer_cnpj14": "11111111000191",
            "supplier_role": "CONTRATADA",
            "buyer_role": "CONTRATANTE",
        }],
    )
    assert projected["evidence_ids"] == [official]


def test_id_only_schema_fails_closed_without_explicit_legacy_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    columns = ["id", "ni_fornecedor", "valor_global"]
    assert "contrato_id" not in resolve_physical_map(columns)
    assert resolve_physical_map(columns, allow_legacy_surrogate_contract_id=True)["contrato_id"] == "id"
    monkeypatch.setattr("scripts.confenge_universe.source.discover_columns", lambda _cfg: columns)
    with pytest.raises(RuntimeError, match="no official contract identity"):
        next(iter_contracts_keyset(SourceConfig(mode="dsn", dsn="postgresql://example.invalid/db")))


def test_keyset_uses_surrogate_cursor_but_yields_pncp_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    columns = ["id", "numero_controle_pncp", "ni_fornecedor", "valor_global"]
    raw = {
        "id": 25394409,
        "numero_controle_pncp": "00028986000108-1-000123/2026",
        "ni_fornecedor": "00028986000108",
        "valor_global": 1000,
    }
    queries: list[tuple[str, tuple[object, ...]]] = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
            queries.append((sql, params))
            self.rows = (
                [{"column_name": column} for column in columns]
                if "information_schema.columns" in sql
                else ([] if 25394409 in params else [raw])
            )

        def fetchall(self):
            return self.rows

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

        def close(self) -> None:
            return None

    monkeypatch.setattr("scripts.confenge_universe.source._connect_dsn", lambda _dsn: Connection())
    batches = list(iter_contracts_keyset(SourceConfig(mode="dsn", dsn="postgresql://example.invalid/db")))
    assert batches == [[{"contrato_id": "00028986000108-1-000123/2026", "orgao_cnpj": None, "orgao_nome": None, "fornecedor_cnpj": "00028986000108", "fornecedor_nome": None, "objeto_contrato": None, "valor_total": 1000, "data_inicio": None, "data_fim": None, "data_publicacao": None, "data_assinatura": None, "uf": None, "municipio": None, "is_active": None, "source": None}]]
    selects = [sql for sql, _params in queries if "FROM public.pncp_supplier_contracts" in sql]
    assert all("ORDER BY id ASC" in sql for sql in selects)


def test_source_refuses_blank_official_id_even_when_surrogate_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    columns = ["id", "numero_controle_pncp", "ni_fornecedor", "valor_global"]

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, sql: str, _params: tuple[object, ...] = ()) -> None:
            self.rows = (
                [{"column_name": column} for column in columns]
                if "information_schema.columns" in sql
                else [{"id": 1, "numero_controle_pncp": "  ", "ni_fornecedor": "00028986000108", "valor_global": 1}]
            )

        def fetchall(self):
            return self.rows

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

        def close(self) -> None:
            return None

    monkeypatch.setattr("scripts.confenge_universe.source._connect_dsn", lambda _dsn: Connection())
    with pytest.raises(RuntimeError, match="row missing official contract identity"):
        next(iter_contracts_keyset(SourceConfig(mode="dsn", dsn="postgresql://example.invalid/db")))


def test_target_fit_loader_selects_and_uses_pncp_control_number(monkeypatch: pytest.MonkeyPatch) -> None:
    columns = {"id", "numero_controle_pncp", "ni_fornecedor", "valor_global"}
    queries: list[str] = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, sql: str, _params: tuple[object, ...]) -> None:
            queries.append(sql)
            self.rows = [{"id": 25394409, "numero_controle_pncp": "00028986000108-1-000123/2026", "ni_fornecedor": "00028986000108", "valor_global": 1000}]

        def fetchall(self):
            return self.rows

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

    monkeypatch.setattr(target_fit_loader, "_COLS_CACHE", columns)
    contracts, *_rest = target_fit_loader._load_contracts(Connection(), raiz="00028986", limit=None)
    assert "numero_controle_pncp" in queries[0]
    assert contracts[0]["contrato_id"] == "00028986000108-1-000123/2026"
