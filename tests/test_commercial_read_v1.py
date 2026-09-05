"""#550 — commercial_read_v1 column contract and independent clocks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads(
    (ROOT / "docs/contracts/commercial-read/v1/commercial_read_v1.json").read_text(encoding="utf-8")
)
SQL = (ROOT / "db/migrations/115_commercial_read_v1.sql").read_text(encoding="utf-8")


def test_column_contract_is_stable() -> None:
    for col in CONTRACT["columns"]:
        assert col in SQL
    assert "v_recent_engineering_wins" in SQL
    assert "confenge_commercial_read_v1" in SQL
    assert "contract_engineering_class" in SQL
    assert "ILIKE" not in SQL


def test_clocks_are_independent_in_sql() -> None:
    assert "DATA_FRESHNESS" in SQL
    assert "EVENT_RECENCY" in SQL
    assert "COMMERCIAL_ACTIONABILITY" in SQL
    assert "NOT_ACTIONABLE" in SQL
    assert "REVOGACAO" in SQL
    assert "c.first_seen_at::date - c.data_publicacao_fonte" in SQL
    assert "CURRENT_DATE - coalesce(c.data_assinatura" in SQL


def test_role_is_select_only_without_credentials() -> None:
    assert "NOLOGIN" in SQL
    assert "GRANT SELECT" in SQL
    assert "password" not in SQL.lower()
    assert "GRANT INSERT" not in SQL
    assert "GRANT UPDATE" not in SQL
