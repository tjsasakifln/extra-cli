"""#549 — engineering supplier_registry coverage and cadastral contact join."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.ops.refresh_engineering_supplier_registry import refresh
from scripts.testing.real_db_guard import canonical_dsn

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/109_engineering_supplier_registry.sql"


def test_universe_uses_official_categoria_not_objeto_regex() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "fn_is_official_engineering_categoria" in sql
    assert "v_engineering_supplier_universe" in sql
    assert "v_supplier_cadastral_contact" in sql
    assert "objeto_contrato" not in sql
    assert "ILIKE" not in sql
    assert "enriched_at" in sql
    assert "enriched_source" in sql
    assert "Not decision-maker discovery" in sql
    assert "categoria_processo_nome" in sql


def test_refresh_is_resumable_and_does_not_invent_rows() -> None:
    fetched: list[str] = []

    class _Cur:
        def __init__(self, conn: _Conn) -> None:
            self.conn = conn
            self._rows: list[tuple[str, ...]] = []

        def execute(self, sql: str, params=None) -> None:
            self.conn.statements.append(sql)
            if "v_engineering_supplier_universe" in sql and "LEFT JOIN" in sql:
                after, limit = params
                cnpjs = ["11111111000191", "22222222000100", "33333333000155"]
                chosen = [c for c in cnpjs if c > after][: int(limit)]
                self._rows = [(c,) for c in chosen]
            else:
                self._rows = []

        def fetchall(self):
            return list(self._rows)

    class _Conn:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def cursor(self):
            return _Cur(self)

        def commit(self) -> None:
            return None

    def _fetch(cnpj: str):
        fetched.append(cnpj)
        if cnpj.endswith("00"):
            return None
        return {
            "cnpj14": cnpj,
            "razao_social": "Empresa",
            "source": "brasilapi",
            "source_version": "cnpj/v1",
            "source_date": "2026-09-04",
        }

    upserts: list[list[dict]] = []

    import scripts.ops.refresh_engineering_supplier_registry as mod

    original = mod.upsert_registry_rows
    mod.upsert_registry_rows = lambda _conn, rows: upserts.append(rows) or len(rows)
    try:
        first = refresh(
            _Conn(),
            after="",
            limit=2,
            run_id="t",
            missing_only=True,
            dry_run=False,
            fetcher=_fetch,
        )
        assert first["planned"] == 2
        assert fetched == ["11111111000191", "22222222000100"]
        assert first["skipped"] == 1
        assert first["cursor"] == "22222222000100"
        resumed = refresh(
            _Conn(),
            after=first["cursor"],
            limit=10,
            run_id="t",
            missing_only=True,
            dry_run=False,
            fetcher=_fetch,
        )
        assert resumed["cursor"] == "33333333000155"
        assert resumed["planned"] == 1
    finally:
        mod.upsert_registry_rows = original


@pytest.mark.real_db
def test_cadastral_contact_join_carries_source_and_enriched_at() -> None:
    import psycopg2
    import psycopg2.extras

    dsn = os.getenv("LOCAL_DATALAKE_DSN") or canonical_dsn()
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.views "
                "WHERE table_name = 'v_supplier_cadastral_contact'"
            )
            if cur.fetchone() is None:
                pytest.fail("migration 109 not applied")
            cur.execute(
                """
                INSERT INTO supplier_registry (
                    cnpj14, razao_social, source, source_version, source_date
                ) VALUES ('99888777000166', 'Fornecedor Teste', 'brasilapi', 'cnpj/v1', CURRENT_DATE)
                ON CONFLICT (cnpj14) DO UPDATE SET razao_social = EXCLUDED.razao_social
                """
            )
            cur.execute(
                """
                INSERT INTO enriched_entities (
                    cnpj, email, telefone, enriched_at, enriched_source
                ) VALUES (
                    '99888777000166', 'contato@example.com', '4833330000',
                    '2026-09-01T12:00:00Z', 'brasilapi'
                )
                ON CONFLICT (cnpj) DO UPDATE SET
                    email = EXCLUDED.email,
                    telefone = EXCLUDED.telefone,
                    enriched_at = EXCLUDED.enriched_at,
                    enriched_source = EXCLUDED.enriched_source
                """
            )
            cur.execute(
                """
                SELECT cadastral_email, cadastral_telefone, enriched_at, enriched_source,
                       has_cadastral_contact, registry_source
                FROM v_supplier_cadastral_contact
                WHERE cnpj14 = '99888777000166'
                """
            )
            row = cur.fetchone()
            assert row["cadastral_email"] == "contato@example.com"
            assert row["cadastral_telefone"] == "4833330000"
            assert row["enriched_at"] is not None
            assert row["enriched_source"] == "brasilapi"
            assert row["has_cadastral_contact"] is True
            assert row["registry_source"] == "brasilapi"
            cur.execute(
                "SELECT public.fn_is_official_engineering_categoria('Obras', NULL) AS ok"
            )
            assert cur.fetchone()["ok"] is True
            cur.execute(
                "SELECT public.fn_is_official_engineering_categoria("
                "'registro de precos no objeto', NULL) AS ok"
            )
            assert cur.fetchone()["ok"] is False
        conn.commit()
    finally:
        conn.close()
