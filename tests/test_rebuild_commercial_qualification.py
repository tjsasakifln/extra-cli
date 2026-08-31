from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from scripts.confenge_activation.rebuild_commercial_qualification import (
    QUALIFICATION_SQL,
    iter_qualifications,
)

NOW = datetime(2026, 8, 31, tzinfo=UTC)


class _Cursor:
    def __init__(self, rows, error: Exception | None = None):
        self.rows = rows
        self.error = error
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        self.sql = sql
        if self.error:
            raise self.error

    def __iter__(self):
        return iter(self.rows)


class _Connection:
    def __init__(self, rows=(), error: Exception | None = None):
        self.cursor_value = _Cursor(rows, error)

    def cursor(self):
        return self.cursor_value


def _row(contract_id: str, objeto: str, *, root: str = "11222333", qdate: date = date(2025, 5, 10)):
    return {
        "root8": root,
        "supplier_cnpj14": root + "000144",
        "buyer_cnpj14": "99888777000166",
        "contrato_id": contract_id,
        "objeto": objeto,
        "qdate": qdate,
        "qfield": "data_assinatura",
    }


def test_pass_without_target_fit_shadow_and_irrelevant_object_is_excluded():
    conn = _Connection(
        [
            _row("engineering", "Execução de obras e serviços de engenharia para pavimentação"),
            _row("office", "Aquisição de material de escritório"),
        ]
    )
    roots = list(iter_qualifications(conn, now=NOW))
    assert [q.qualifying_contract_id for q in roots] == ["engineering"]
    assert roots[0].supplier_cnpj14 == "11222333000144"
    assert "confenge_target_fit" not in conn.cursor_value.sql.lower()


def test_query_is_canonical_supplier_not_buyer_and_revocation_safe():
    normalized = " ".join(QUALIFICATION_SQL.lower().split())
    assert "public.v_contracts_canonical_v2" in normalized
    assert "is distinct from" in normalized
    assert "coalesce(c.is_active, true)" in normalized
    assert "c.objeto" in normalized


def test_latest_relevant_contract_and_population_are_deterministic():
    rows = [
        _row("older", "serviços de engenharia", qdate=date(2024, 1, 2)),
        _row("latest", "pavimentação asfáltica", qdate=date(2026, 1, 2)),
    ]
    first = [q.as_dict() for q in iter_qualifications(_Connection(rows), now=NOW)]
    second = [q.as_dict() for q in iter_qualifications(_Connection(list(reversed(rows))), now=NOW)]
    assert first == second
    assert first[0]["qualifying_contract_id"] == "latest"
    assert first[0]["qualifying_contract_count"] == 2


def test_expired_contract_is_not_qualified_but_leap_normalization_survives():
    expired = list(
        iter_qualifications(
            _Connection([_row("expired", "obra de engenharia", qdate=date(2023, 8, 31))]),
            now=NOW,
        )
    )
    assert expired == []
    leap_now = datetime(2027, 2, 28, tzinfo=UTC)
    leap = list(
        iter_qualifications(
            _Connection([_row("leap", "obra de engenharia", qdate=date(2024, 2, 29))]),
            now=leap_now,
        )
    )
    assert leap[0].qualified_until == "2027-03-01"


def test_datalake_unavailable_fails_closed():
    with pytest.raises(RuntimeError, match="datalake down"):
        list(iter_qualifications(_Connection(error=RuntimeError("datalake down")), now=NOW))
